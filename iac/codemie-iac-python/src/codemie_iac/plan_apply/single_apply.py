# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Single-entity plan: diff a document against the live entity.

``diff`` compares the document spec with the live SDK object, restricted by a
``FieldPolicy``, and returns ``Difference`` / ``CannotCompare`` findings.

Comparison rules:

- Only fields that are in ``policy.comparable`` (and not in ``policy.deny``)
  are compared; a field absent from the live view is not observable and is
  skipped.
- Reference-shaped spec fields (``REFERENCE_FIELDS``) hold names/aliases
  where the live entity holds platform ids, expanded integration objects or a
  rendered workflow config. With a ``ResolveContext`` they are resolved the
  way a write would resolve them and the resolved value is compared. Without
  one they are ``CannotCompare`` (never silently skipped). Fields that carry
  credential refs are compared with revealed values, but a ``Difference`` on
  them is redacted.
- ``None``, ``""`` and empty collections are all "unset" and compare equal.
  Live dicts are projected onto the document's keys, so server-added keys
  inside nested objects are not differences.
- Credential-ref fields and live values that are masked (8 asterisks for
  prompt variables, 10 for credentials) are ``CannotCompare``: never a
  difference, never a match, and no value is ever put in the finding.
  Credential refs are only checked for presence/resolvability.
- A masked value only makes a field uncomparable where the document looks at
  it: the mask check runs on the live value projected onto the document's
  keys, and per item for lists of equal length (one masked prompt variable
  does not hide an edit of another). Integrations embedded in toolkits / MCP
  servers are compared by id only.
- A comparable field the document authors but the live view cannot show (for
  example a ``timezone`` when the datasource has no schedule) is
  ``CannotCompare``, never skipped.
- ``Plan.is_empty`` depends on differences only: a ``CannotCompare`` field
  is unknowable, not a change, so it does not force a write. ``apply`` lists
  such fields in ``ApplyResult.uncomparable`` and ``force=True`` writes anyway.
"""

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import yaml
from codemie_sdk.exceptions import ApiError
from pydantic import BaseModel, ConfigDict, computed_field

from ..credentials import CredentialRef
from ..envelope import Document, DocumentKind
from .credentials import EnvCredentialResolver, SecretValue
from .bulk_create import (
    ResolveContext,
    build_resolved,
    check_credentials,
    check_references,
)
from .errors import ApplyError, PlatformRejectionError
from .field_policy import FieldPolicy, policy_for
from .guards import guard_datasource_identity, guard_project, guard_supported
from .kinds import adapter_for
from .lookup import NameLookup

__all__ = [
    "REFERENCE_FIELDS",
    "ApplyResult",
    "CannotCompare",
    "Difference",
    "Plan",
    "SingleEntityPlanner",
    "diff",
]

REFERENCE_FIELDS = frozenset(
    {
        "categories",
        "assistant_ids",
        "toolkits",
        "mcp_servers",
        "yaml_config",
        "setting_id",
    }
)
_ID_LIST_FIELDS = frozenset({"categories", "assistant_ids"})
_INTEGRATION_FIELDS = frozenset({"toolkits", "mcp_servers"})
#: Comparable fields the live view may legitimately omit (the timezone is only
#: exposed alongside a schedule); authored but absent means ``CannotCompare``.
_OPTIONAL_LIVE_FIELDS = frozenset({"cron_expression", "timezone"})
_REDACTED = "[redacted]"
_UNRESOLVABLE = "unresolvable credential reference"
_PROJECT_FIELDS = {
    DocumentKind.ASSISTANT: "project",
    DocumentKind.SKILL: "project",
    DocumentKind.WORKFLOW: "project",
    DocumentKind.INTEGRATION: "project_name",
}

_MASK_LENGTHS = frozenset({8, 10})
_NESTED_DATASOURCE_KEYS = (
    "code",
    "git_faq",
    "jira",
    "confluence",
    "azure_devops_wiki",
    "azure_devops_work_item",
    "xwiki",
)
_WORKFLOW_FIELDS = {"name", "description", "mode", "shared", "icon_url"}


class Difference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    document_value: Any
    live_value: Any


class CannotCompare(BaseModel):
    """A field that could not be compared; ``reason`` never holds a value."""

    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    differences: list[Difference] = []
    cannot_compare: list[CannotCompare] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_empty(self) -> bool:
        return not self.differences


# --- normalisation ---------------------------------------------------------


def _is_mask(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) in _MASK_LENGTHS and set(value) == {"*"}
    )


def _has_mask(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_has_mask(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_mask(v) for v in value)
    return _is_mask(value)


def _canon(value: Any) -> Any:
    """Canonical form: every empty value becomes None and empties are dropped."""
    if isinstance(value, Mapping):
        items = {k: _canon(v) for k, v in value.items()}
        value = {k: v for k, v in items.items() if v is not None}
    elif isinstance(value, list):
        value = [_canon(v) for v in value]
    return value if value not in ("", [], {}) else None


def _project(document_value: Any, live_value: Any) -> Any:
    """Restrict ``live_value`` to the shape (keys) of ``document_value``."""
    if isinstance(document_value, dict) and isinstance(live_value, Mapping):
        return {k: _project(v, live_value.get(k)) for k, v in document_value.items()}
    if (
        isinstance(document_value, list)
        and isinstance(live_value, list)
        and len(document_value) == len(live_value)
    ):
        return [_project(d, v) for d, v in zip(document_value, live_value)]
    return live_value


def _flatten_live(live: Mapping[str, Any]) -> dict[str, Any]:
    """Merge datasource sub-objects into the top level (top level wins)."""
    flat = dict(live)
    for key in _NESTED_DATASOURCE_KEYS:
        sub = flat.get(key)
        if isinstance(sub, Mapping):
            for name, value in sub.items():
                if flat.get(name) is None:
                    flat[name] = value
    if "google_doc_link" in flat:
        flat.setdefault("google_doc", flat["google_doc_link"])
    return flat


def _document_values(document: Document, all_fields: bool = False) -> dict[str, Any]:
    spec = document.spec
    if document.meta.kind is DocumentKind.WORKFLOW:
        values = spec.workflow.model_dump(mode="json", include=_WORKFLOW_FIELDS)
        if all_fields:
            values["yaml_config"] = "workflow"  # always a reference field
        return values
    return spec.model_dump(mode="json")


# --- credentials -----------------------------------------------------------


def _credential_finding(
    field: str, refs: list[CredentialRef], resolver: EnvCredentialResolver
) -> CannotCompare:
    if all(resolver.is_resolvable(ref) for ref in refs):
        reason = "credential reference; live value is masked and cannot be compared"
    else:
        reason = f"{_UNRESOLVABLE}; live value is masked and cannot be compared"
    return CannotCompare(field=field, reason=reason)


def _credential_findings(
    document: Document, resolver: EnvCredentialResolver
) -> list[CannotCompare]:
    spec = document.spec
    findings: list[CannotCompare] = []
    entries = getattr(spec, "credential_values", None)
    if entries:
        findings.append(
            _credential_finding("credential_values", [e.ref for e in entries], resolver)
        )
    nested = SimpleNamespace(
        mcp_servers=getattr(spec, "mcp_servers", None),
        workflow=getattr(spec, "workflow", None),
    )
    refs = resolver.collect_refs(nested)
    if refs:
        field = "mcp_servers" if hasattr(spec, "mcp_servers") else "yaml_config"
        findings.append(_credential_finding(field, refs, resolver))
    return findings


# --- reference fields ----------------------------------------------------------


def _ids(value: Any) -> list[str]:
    ids = []
    for item in value or []:
        if isinstance(item, Mapping):
            item = item.get("id")
        elif not isinstance(item, str):
            item = getattr(item, "id", None)
        ids.append(str(item))
    return sorted(ids)


def _load_yaml(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError:
        return value


_INTEGRATION_KEYS = frozenset({"settings", "mcp_connect_auth_token"})


def _integrations_by_id(value: Any) -> Any:
    """Reduce every embedded integration to its id.

    The backend embeds the whole integration (with masked ``credential_values``
    and non-sensitive settings) in toolkits / MCP servers; the document only
    references one, so only its identity is comparable.
    """
    if isinstance(value, list):
        return [_integrations_by_id(v) for v in value]
    if not isinstance(value, Mapping):
        return value
    return {
        k: {"id": v.get("id")}
        if k in _INTEGRATION_KEYS and isinstance(v, Mapping)
        else _integrations_by_id(v)
        for k, v in value.items()
    }


def _normalise_reference(field: str, resolved: Any, live: Any) -> tuple[Any, Any]:
    if field in _ID_LIST_FIELDS:
        return _ids(resolved), _ids(live)
    if field in _INTEGRATION_FIELDS:
        return _integrations_by_id(resolved), _integrations_by_id(live)
    if field == "yaml_config":
        return _load_yaml(resolved), _load_yaml(live)
    return resolved, live


def _redact(finding: Difference | CannotCompare | None, redact: bool):
    if redact and isinstance(finding, Difference):
        return Difference(
            field=finding.field, document_value=_REDACTED, live_value=_REDACTED
        )
    return finding


def _reference_findings(
    document: Document,
    live_view: Mapping[str, Any],
    policy: FieldPolicy,
    ctx: ResolveContext | None,
    credential_fields: set[str],
    unresolvable_fields: set[str],
) -> list[Difference | CannotCompare]:
    present = {
        f
        for f, v in _document_values(document, all_fields=True).items()
        if f in REFERENCE_FIELDS and _canon(v) is not None
    }
    if ctx is None:
        return [
            CannotCompare(field=f, reason="references not resolved; cannot compare")
            for f in sorted(present - credential_fields)
        ]
    resolved = build_resolved(document, ctx)
    findings: list[Difference | CannotCompare] = []
    for field in sorted(REFERENCE_FIELDS & resolved.keys()):
        if field not in policy.comparable or field not in live_view:
            continue
        if field in unresolvable_fields:  # already reported as CannotCompare
            continue
        redact = field in credential_fields
        pair = _normalise_reference(field, resolved[field], live_view[field])
        finding = _redact(_compare_field(field, *pair), redact)
        if finding is not None and not (redact and isinstance(finding, CannotCompare)):
            findings.append(finding)
    return findings


# --- diff ------------------------------------------------------------------


def _comparable_part(document_value: Any, live_value: Any) -> tuple[Any, Any, bool]:
    """``(document, live, hidden)`` with the masked parts left out.

    Lists of equal length are cut per item; anything else is all or nothing.
    ``hidden`` says that something the document authors could not be seen.
    """
    if (
        isinstance(document_value, list)
        and isinstance(live_value, list)
        and len(document_value) == len(live_value)
    ):
        pairs = [
            (d, v)
            for d, v in zip(document_value, live_value)
            if not _has_mask(_project(d, v))
        ]
        hidden = len(pairs) < len(document_value)
        return [d for d, _ in pairs], [v for _, v in pairs], hidden
    if _has_mask(_project(document_value, live_value)):
        return None, None, True
    return document_value, live_value, False


def _compare_field(
    field: str, document_value: Any, live_value: Any
) -> Difference | CannotCompare | None:
    document, live, hidden = _comparable_part(document_value, live_value)
    if _canon(document) != _canon(_project(document, live)):
        return Difference(
            field=field, document_value=document_value, live_value=live_value
        )
    if hidden:
        return CannotCompare(field=field, reason="live value is masked")
    return None


def _unobservable_findings(
    document: Document, live_view: Mapping[str, Any], policy: FieldPolicy
) -> list[CannotCompare]:
    """Authored raw-only fields the live view did not carry (never skipped)."""
    values = _document_values(document)
    return [
        CannotCompare(
            field=field, reason="not returned by the live view; cannot compare"
        )
        for field in sorted(_OPTIONAL_LIVE_FIELDS & policy.comparable)
        if field not in live_view and _canon(values.get(field)) is not None
    ]


def diff(
    document: Document,
    live: Any,
    policy: FieldPolicy,
    resolver: EnvCredentialResolver,
    ctx: ResolveContext | None = None,
) -> list[Difference | CannotCompare]:
    """Findings between a document and its live entity.

    ``live`` is the live SDK object, or an already-comparable dict. ``ctx``
    resolves reference fields for comparison; without it they are reported as
    ``CannotCompare``.
    """
    comparable = (
        live if isinstance(live, Mapping) else adapter_for(document).to_comparable(live)
    )
    live_view = _flatten_live(comparable)
    findings: list[Difference | CannotCompare] = _credential_findings(
        document, resolver
    )
    credential_fields = {f.field for f in findings}
    unresolvable = {f.field for f in findings if _UNRESOLVABLE in f.reason}
    handled = {f.field for f in findings} | REFERENCE_FIELDS | policy.deny
    for field, document_value in _document_values(document).items():
        if field in handled or field not in policy.comparable or field not in live_view:
            continue
        finding = _compare_field(field, document_value, live_view[field])
        if finding is not None:
            findings.append(finding)
    findings.extend(_unobservable_findings(document, live_view, policy))
    findings.extend(
        _reference_findings(
            document, live_view, policy, ctx, credential_fields, unresolvable
        )
    )
    return findings


def _guard_project(document: Document, live: Mapping[str, Any], target: str) -> None:
    """Refuse to overwrite an entity that lives in another project."""
    field = _PROJECT_FIELDS.get(document.meta.kind)
    live_project = live.get(field) if field else None
    if live_project is not None and live_project != target:
        raise ApplyError(
            "project_mismatch",
            document.meta.kind.value,
            document.meta.name,
            f"live entity is in project {live_project!r}, not target {target!r}",
        )


# --- planner / apply ---------------------------------------------------------


class _PlanCredentials:
    """Credentials for a read-only plan: an unset variable is not an error.

    ``credential_values`` are never compared, so a ref that cannot be resolved
    only needs a placeholder to build the (compared) request body; the field
    is reported as an "unresolvable credential reference" ``CannotCompare``.
    """

    def __init__(self, inner: EnvCredentialResolver):
        self._inner = inner

    def is_resolvable(self, ref: CredentialRef) -> bool:
        return self._inner.is_resolvable(ref)

    def resolve(self, ref: CredentialRef) -> SecretValue:
        if self._inner.is_resolvable(ref):
            return self._inner.resolve(ref)
        return SecretValue("")

    def revealed_values(self) -> frozenset[str]:
        return self._inner.revealed_values()

    collect_refs = staticmethod(EnvCredentialResolver.collect_refs)


class ApplyResult(BaseModel):
    """Outcome of a single-entity apply; ``id`` is returned, never stored."""

    model_config = ConfigDict(extra="forbid")

    id: str | None
    created: bool
    #: Fields the document authors that could not be compared; with an empty
    #: plan nothing was written for them (see ``force``). Field names only.
    uncomparable: list[str] = []


class SingleEntityPlanner:
    """Plans (and applies) one document against one live entity."""

    def __init__(self, client: Any, credentials: EnvCredentialResolver | None = None):
        self._client = client
        self._credentials = credentials or EnvCredentialResolver()

    def _plan_credentials(self) -> "_PlanCredentials":
        return _PlanCredentials(self._credentials)

    def plan(self, document: Document, entity_id: str, target: str) -> Plan:
        """Diff ``document`` against the entity ``entity_id`` (one read, no writes)."""
        guard_project(document, target)
        ctx = self._context(target, self._plan_credentials())
        return self._plan(document, entity_id, target, ctx)

    def _context(self, target: str, credentials: Any = None) -> ResolveContext:
        lookup = NameLookup([], target, self._client)
        return ResolveContext(lookup, credentials or self._credentials)

    def _plan(
        self, document: Document, entity_id: str, target: str, ctx: ResolveContext
    ) -> Plan:
        guard_supported(document)
        adapter = adapter_for(document)
        live = adapter.get(self._client, document, entity_id)
        guard_datasource_identity(document, live)
        _guard_project(document, adapter.to_comparable(live), target)
        policy = policy_for(document)
        findings = diff(document, live, policy, self._credentials, ctx)
        return Plan(
            differences=[f for f in findings if isinstance(f, Difference)],
            cannot_compare=[f for f in findings if isinstance(f, CannotCompare)],
        )

    def apply(
        self,
        document: Document,
        entity_id: str | None,
        target: str,
        force: bool = False,
    ) -> ApplyResult:
        """Create (no ``entity_id``) or update the entity; never deletes.

        References and credential refs are checked before anything is read or
        written. An update with an empty plan sends no write, unless ``force``
        is set; fields the plan could not compare (a rotated secret, a masked
        value) are then not known to be unchanged, so they are listed in
        ``ApplyResult.uncomparable``. ``force`` writes the full document.
        """
        guard_supported(document)
        guard_project(document, target)
        ctx = self._context(target)
        check_references([document], ctx)
        check_credentials([document], ctx)
        if entity_id is not None:
            plan = self._plan(document, entity_id, target, ctx)
            if plan.is_empty and not force:
                return ApplyResult(
                    id=entity_id,
                    created=False,
                    uncomparable=[c.field for c in plan.cannot_compare],
                )
        resolved = build_resolved(document, ctx)
        adapter = adapter_for(document)
        try:
            if entity_id is None:
                response = adapter.create(self._client, document, resolved)
            else:
                adapter.update(self._client, document, entity_id, resolved)
        except ApiError as exc:
            raise PlatformRejectionError(
                "platform_rejection",
                document.meta.kind.value,
                document.meta.name,
                exc,
                self._credentials.revealed_values(),
            ) from exc
        if entity_id is not None:
            return ApplyResult(id=entity_id, created=False)
        return ApplyResult(id=adapter.extract_id(response), created=True)
