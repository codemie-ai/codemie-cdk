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

"""Create-only, dependency-ordered bulk apply.

``BulkCreator.create_all`` first runs every preflight check (cycles, adapter
support, reference resolution, credential resolution) and only then performs
writes, in dependency order. There is no dedupe, update, delete or scoped
apply: an entity whose name or content equals an existing one is still
created. Platform ids are held in memory for the duration of one run only,
and only substituted into request bodies; they are never written anywhere.

Datasource ``create`` returns no id. Assistants reference datasources by
``context`` name (the SDK ``Context`` has no id), so nothing needs the id;
if a caller does ask for it, ``NameLookup.resolve`` finds the datasource
live by name in the target project after it was created.

``build_resolved`` (and ``ResolveContext``) are reusable by single-entity
apply: they turn a document's name references and credential refs into the
``resolved`` request-body overrides that ``KindAdapter`` expects.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import yaml
from codemie_sdk.exceptions import ApiError
from pydantic import BaseModel, ConfigDict

from ..credentials import CredentialRef
from ..envelope import Document, DocumentKind
from .credentials import MCP_REF_FIELDS, EnvCredentialResolver
from .errors import ApplyError, FieldError, PlatformRejectionError, scrub
from .guards import guard_project, guard_supported
from .kinds import adapter_for
from .lookup import EntityKey, NameLookup, Reference
from .ordering import EDGE_EXTRACTORS, DependencyGraph

__all__ = [
    "PREFLIGHT_CHECKS",
    "BulkCreateReport",
    "BulkCreator",
    "CreatedEntity",
    "FailedEntity",
    "ResolveContext",
    "build_resolved",
    "check_adapters",
    "check_credentials",
    "check_cycles",
    "check_projects",
    "check_references",
    "check_supported",
]


class CreatedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DocumentKind
    name: str
    id: str | None = None


class FailedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DocumentKind
    name: str
    error_type: str
    reason: str
    structured_errors: list[FieldError] | None = None


class BulkCreateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: list[CreatedEntity]
    failed: FailedEntity | None = None


@dataclass
class ResolveContext:
    """Everything needed to substitute references and credentials in memory."""

    lookup: NameLookup
    credentials: EnvCredentialResolver
    created: dict[EntityKey, str] = field(default_factory=dict)

    def ref(self, kind: DocumentKind, name: str) -> Reference:
        return self.lookup.resolve(kind, name, self.created)

    def ids(self, kind: DocumentKind, names: Iterable[str]) -> list[str]:
        return [self.ref(kind, n).id for n in names]

    def integration(self, name: str | None) -> dict | None:
        """An ``Integration`` payload (no secrets) carrying the platform id."""
        if not name:
            return None
        ref = self.ref(DocumentKind.INTEGRATION, name)
        return _integration_payload(ref)

    def reveal(self, value: Any) -> Any:
        """Replace credential-ref strings (recursively) with secret values."""
        if isinstance(value, str):
            return self._reveal_str(value)
        if isinstance(value, list):
            return [self.reveal(v) for v in value]
        if isinstance(value, dict):
            return {k: self.reveal(v) for k, v in value.items()}
        return value

    def _reveal_str(self, value: str) -> str:
        try:
            ref = CredentialRef(value)
        except ValueError:
            return value
        return self.credentials.resolve(ref).reveal()


def _integration_payload(ref: Reference) -> dict:
    source = ref.source
    spec = source.spec if isinstance(source, Document) else source
    setting_type = getattr(spec, "setting_type", None)
    return {
        "id": ref.id,
        "project_name": getattr(spec, "project_name", None),
        "alias": getattr(spec, "alias", None),
        "credential_type": getattr(spec, "credential_type", None),
        "credential_values": [],
        "setting_type": setting_type,
    }


# --- resolved-body builders (one per kind) ----------------------------------


def _toolkit_body(toolkit: dict, ctx: ResolveContext) -> dict:
    out = dict(toolkit)
    out["settings"] = ctx.integration(toolkit.get("settings"))
    out["tools"] = [
        {**t, "settings": ctx.integration(t.get("settings"))}
        for t in toolkit.get("tools", [])
    ]
    return out


def _mcp_body(server: dict, ctx: ResolveContext) -> dict:
    out = dict(server)
    out["settings"] = ctx.integration(server.get("settings"))
    out["mcp_connect_auth_token"] = ctx.integration(
        server.get("mcp_connect_auth_token")
    )
    for key in MCP_REF_FIELDS:
        if out.get(key) is not None:
            out[key] = ctx.reveal(out[key])
    return out


def _assistant_resolved(document: Document, ctx: ResolveContext) -> dict:
    spec = document.spec
    dumped = spec.model_dump(mode="python")
    return {
        "assistant_ids": ctx.ids(DocumentKind.ASSISTANT, spec.assistant_ids),
        "categories": ctx.ids(DocumentKind.CATEGORY, spec.categories),
        "toolkits": [_toolkit_body(t, ctx) for t in dumped["toolkits"]],
        "mcp_servers": [_mcp_body(s, ctx) for s in dumped["mcp_servers"]],
    }


def _skill_resolved(document: Document, ctx: ResolveContext) -> dict:
    return {
        "categories": ctx.ids(DocumentKind.CATEGORY, document.spec.categories or [])
    }


def _integration_resolved(document: Document, ctx: ResolveContext) -> dict:
    return {
        "credential_values": [
            {"key": e.key, "value": ctx.credentials.resolve(e.ref).reveal()}
            for e in document.spec.credential_values
        ]
    }


def _workflow_assistants(document: Document, ctx: ResolveContext) -> dict:
    assistants = document.spec.workflow.assistants
    resolved = {}
    for key, assistant in assistants.items():
        if assistant.assistant_id:
            ref = ctx.ref(DocumentKind.ASSISTANT, assistant.assistant_id)
            assistant = assistant.model_copy(update={"assistant_id": ref.id})
        resolved[key] = assistant
    return resolved


def _yaml_error(document: Document) -> ApplyError:
    return ApplyError(
        "invalid_workflow_yaml",
        document.meta.kind.value,
        document.meta.name,
        "rendered workflow config is not a mapping of assistants",
    )


def _yaml_mapping(document: Document, rendered: str) -> dict:
    try:
        payload = yaml.safe_load(rendered)
    except yaml.YAMLError:
        raise _yaml_error(document) from None
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise _yaml_error(document)
    return payload


def _dict_items(document: Document, value: Any) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise _yaml_error(document)
    return value


def _workflow_yaml(document: Document, ctx: ResolveContext) -> str:
    definition = document.spec.workflow.model_copy(
        update={"assistants": _workflow_assistants(document, ctx)}
    )
    rendered = definition.to_yaml_config(
        lambda name: ctx.ref(DocumentKind.ASSISTANT, name).id
    )
    payload = _yaml_mapping(document, rendered)
    for assistant in _dict_items(document, payload.get("assistants")):
        for server in _dict_items(document, assistant.get("mcp_servers")):
            for key in MCP_REF_FIELDS:
                if server.get(key) is not None:
                    server[key] = ctx.reveal(server[key])
    return yaml.safe_dump(
        payload, sort_keys=False, default_flow_style=False, allow_unicode=True
    )


def _workflow_resolved(document: Document, ctx: ResolveContext) -> dict:
    return {
        "project": ctx.lookup.target,
        "yaml_config": _workflow_yaml(document, ctx),
    }


def _datasource_resolved(document: Document, ctx: ResolveContext) -> dict:
    alias = document.spec.setting_id
    if not alias:
        return {}
    return {"setting_id": ctx.ref(DocumentKind.INTEGRATION, alias).id}


def _nothing(_document: Document, _ctx: ResolveContext) -> dict:
    return {}


_RESOLVED_BUILDERS: dict[DocumentKind, Callable[[Document, ResolveContext], dict]] = {
    DocumentKind.ASSISTANT: _assistant_resolved,
    DocumentKind.SKILL: _skill_resolved,
    DocumentKind.INTEGRATION: _integration_resolved,
    DocumentKind.WORKFLOW: _workflow_resolved,
    DocumentKind.CATEGORY: _nothing,
    DocumentKind.DATASOURCE: _datasource_resolved,
}


def build_resolved(document: Document, ctx: ResolveContext) -> dict:
    """Request-body overrides for ``KindAdapter.create/update``: references
    replaced by platform ids, credential refs replaced by secret values."""
    return _RESOLVED_BUILDERS[document.meta.kind](document, ctx)


# --- preflight ----------------------------------------------------------------


def _label(document: Document) -> str:
    return f"{document.meta.kind.value}/{document.meta.name}"


def check_cycles(documents: list[Document], _ctx: ResolveContext) -> None:
    DependencyGraph(documents).order()


def check_supported(documents: list[Document], _ctx: ResolveContext) -> None:
    for document in documents:
        guard_supported(document)


def check_projects(documents: list[Document], ctx: ResolveContext) -> None:
    for document in documents:
        guard_project(document, ctx.lookup.target)


def check_adapters(documents: list[Document], _ctx: ResolveContext) -> None:
    for document in documents:
        adapter_for(document)


def check_references(documents: list[Document], ctx: ResolveContext) -> None:
    for document in documents:
        extractor = EDGE_EXTRACTORS.get(document.meta.kind)
        for kind, name in extractor(document) if extractor else ():
            ctx.lookup.require(kind, name, _label(document))


def check_credentials(documents: list[Document], ctx: ResolveContext) -> None:
    for document in documents:
        for ref in ctx.credentials.collect_refs(document.spec):
            ctx.credentials.resolve(ref)


#: Checks run in order before the first write; add new checks here.
PREFLIGHT_CHECKS: list[Callable[[list[Document], ResolveContext], None]] = [
    check_cycles,
    check_supported,
    check_projects,
    check_adapters,
    check_references,
    check_credentials,
]


# --- creator --------------------------------------------------------------------


class BulkCreator:
    """Creates every document of a bundle in dependency order."""

    def __init__(self, client: Any, credentials: EnvCredentialResolver | None = None):
        self._client = client
        self._credentials = credentials or EnvCredentialResolver()

    def create_all(
        self, documents: Iterable[Document], target: str
    ) -> BulkCreateReport:
        docs = list(documents)
        ctx = ResolveContext(NameLookup(docs, target, self._client), self._credentials)
        for check in PREFLIGHT_CHECKS:
            check(docs, ctx)
        created: list[CreatedEntity] = []
        for document in DependencyGraph(docs).order():
            try:
                created.append(self._create_one(document, ctx))
            except Exception as exc:  # noqa: BLE001 - keep the created list
                error = self._as_apply_error(document, exc)
                return BulkCreateReport(
                    created=created, failed=_failed(document, error)
                )
        return BulkCreateReport(created=created)

    def _as_apply_error(self, document: Document, exc: Exception) -> ApplyError:
        if isinstance(exc, ApplyError):
            return exc
        secrets = self._credentials.revealed_values()
        return ApplyError(
            "apply_failed",
            document.meta.kind.value,
            document.meta.name,
            scrub(f"{type(exc).__name__}: {exc}", secrets),
        )

    def _create_one(self, document: Document, ctx: ResolveContext) -> CreatedEntity:
        kind, name = document.meta.kind, document.meta.name
        adapter = adapter_for(document)
        resolved = build_resolved(document, ctx)
        try:
            response = adapter.create(self._client, document, resolved)
        except ApiError as exc:
            raise PlatformRejectionError(
                "platform_rejection",
                kind.value,
                name,
                exc,
                self._credentials.revealed_values(),
            ) from exc
        entity_id = adapter.extract_id(response)
        if entity_id is not None:
            ctx.created[(kind, name)] = entity_id
        return CreatedEntity(kind=kind, name=name, id=entity_id)


def _failed(document: Document, error: ApplyError) -> FailedEntity:
    return FailedEntity(
        kind=document.meta.kind,
        name=document.meta.name,
        error_type=error.error_type,
        reason=error.reason,
        structured_errors=getattr(error, "structured_errors", None),
    )
