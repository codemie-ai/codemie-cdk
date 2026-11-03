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

"""Per-kind adapter tables binding IaC documents to ``codemie_sdk`` services.

Every operation of a ``KindAdapter`` takes the SDK client (anything exposing
the service attributes of ``CodeMieClient``: ``assistants``, ``skills``,
``workflows``, ``datasources``, ``integrations``, ``categories``) and the
``Document``, so callers never branch on the kind:

    adapter = adapter_for(document)
    response = adapter.create(client, document, resolved)
    entity_id = adapter.extract_id(response)

``resolved`` is a mapping of request-body field overrides produced by the
reference/credential resolution step (platform ids, credential values, a
workflow's ``project``...). It is merged over the body derived from the
document spec; two keys are special for workflows: ``yaml_config`` (a
pre-rendered config) and ``resolve_assistant_name`` (a callable passed to
``WorkflowDefinition.to_yaml_config``). Platform ids are only passed in and
returned, never stored.
"""

import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from codemie_sdk.exceptions import NotFoundError
from codemie_sdk.models.assistant import AssistantCreateRequest, AssistantUpdateRequest
from codemie_sdk.models.categories import CategoryCreateRequest, CategoryUpdateRequest
from codemie_sdk.models.datasource import (
    AzureDevOpsWikiDataSourceRequest,
    AzureDevOpsWorkItemDataSourceRequest,
    CodeDataSourceRequest,
    ConfluenceDataSourceRequest,
    GitFaqDataSourceRequest,
    GoogleDataSourceRequest,
    JiraDataSourceRequest,
    UpdateAzureDevOpsWikiDataSourceRequest,
    UpdateAzureDevOpsWorkItemDataSourceRequest,
    UpdateCodeDataSourceRequest,
    UpdateConfluenceDataSourceRequest,
    UpdateGitFaqDataSourceRequest,
    UpdateGoogleDataSourceRequest,
    UpdateJiraDataSourceRequest,
    UpdateXWikiDataSourceRequest,
    XWikiDataSourceRequest,
)
from codemie_sdk.models.integration import Integration
from codemie_sdk.models.skill import SkillCreateRequest, SkillUpdateRequest
from codemie_sdk.models.workflow import WorkflowCreateRequest, WorkflowUpdateRequest
from pydantic import BaseModel, ValidationError

from ..envelope import Document, DocumentKind
from .errors import ApplyError

__all__ = [
    "ADAPTERS",
    "DATASOURCE_ADAPTERS",
    "INTEGRATION_LIST_CAP",
    "KindAdapter",
    "adapter_for",
]

#: ``IntegrationService.get`` looks an integration up by listing, 100 items max.
INTEGRATION_LIST_CAP = 100

Resolved = Mapping[str, Any]
_ID_KEYS = ("assistant_id", "id", "workflow_id", "setting_id")


@dataclass(frozen=True)
class KindAdapter:
    """Operations for one kind (or one datasource type).

    create(client, document, resolved) -> raw SDK response
    update(client, document, entity_id, resolved, changed=None) -> raw SDK
        response; ``changed`` names the fields a plan found different (or
        could not compare), ``None`` meaning "unknown: write everything"
    get(client, document, entity_id) -> live SDK object
    extract_id(response) -> platform id, or None when the response has none
    to_comparable(live) -> plain dict of the live object's fields
    """

    create: Callable[[Any, Document, Resolved], Any]
    update: Callable[..., Any]
    get: Callable[[Any, Document, str], Any]
    extract_id: Callable[[Any], str | None]
    to_comparable: Callable[[Any], dict[str, Any]]


# --- shared helpers --------------------------------------------------------


def _extract_id(response: Any) -> str | None:
    for key in _ID_KEYS:
        value = (
            response.get(key)
            if isinstance(response, dict)
            else getattr(response, key, None)
        )
        if isinstance(value, str) and value:
            return value
    return None


def _no_id(_response: Any) -> None:
    return None


def _to_comparable(live: Any) -> dict[str, Any]:
    if isinstance(live, BaseModel):
        return live.model_dump(mode="json")
    if isinstance(live, dict):
        return dict(live)
    return dict(vars(live))


def _build(request_cls: type[BaseModel], data: dict, document: Document) -> Any:
    try:
        return request_cls(**data)
    except ValidationError as exc:
        # Raised below, outside the handler, so that neither the cause nor the
        # context (the offending input) stays reachable from the error.
        # Never ``str(exc)``: pydantic embeds the offending input, which here
        # may be a revealed credential.
        reason = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<body>'}: {e['msg']}"
            for e in exc.errors(
                include_input=False, include_url=False, include_context=False
            )
        )
        error = ApplyError(
            "invalid_body", document.meta.kind.value, document.meta.name, reason
        )
    raise error


def _spec_body(document: Document, resolved: Resolved, **exclude: Any) -> dict:
    body = document.spec.model_dump(mode="python", exclude=set(exclude) or None)
    body.update(resolved)
    return body


def _workflow_body(document: Document, resolved: Resolved) -> dict:
    definition = document.spec.workflow
    overrides = dict(resolved)
    resolver = overrides.pop("resolve_assistant_name", None)
    yaml_config = overrides.pop("yaml_config", None)
    if yaml_config is None:
        yaml_config = definition.to_yaml_config(resolver)
    body = {
        "name": definition.name,
        "description": definition.description,
        "mode": definition.mode,
        "shared": definition.shared,
        "icon_url": definition.icon_url,
        "yaml_config": yaml_config,
    }
    body.update(overrides)
    return body


def _integration_body(document: Document, resolved: Resolved) -> dict:
    # Credential values only ever come from ``resolved``; the spec holds refs.
    return _spec_body(document, resolved, credential_values=None)


def _datasource_body(document: Document, resolved: Resolved) -> dict:
    body = _spec_body(document, resolved)
    body.pop("type", None)  # the request classes fix their own type
    # The code request carries a second, camelCase visibility key.
    body.setdefault("project_space_visible", body.get("shared_with_project", False))
    return body


@contextmanager
def _no_request_body_log() -> Iterator[None]:
    """Keep the SDK from logging request bodies while a write is sent.

    The SDK logs ``Request body: ...`` at DEBUG for every POST and PUT, and
    the bodies carry the resolved credentials, which no scrubbing can reach.
    """
    logger = logging.getLogger("codemie_sdk.utils.http")
    level = logger.level
    logger.setLevel(max(level, logging.INFO))
    try:
        yield
    finally:
        logger.setLevel(level)


def _reject_declined_assistant(response: Any, document: Document) -> None:
    """The platform answers HTTP 200 with the validation result and saves
    nothing when a tool has no usable integration."""
    validation = getattr(response, "validation", None)
    if validation is None or not getattr(validation, "has_missing_integrations", True):
        return
    types = sorted(
        {
            str(getattr(m, "credential_type", ""))
            for m in getattr(validation, "missing_by_credential_type", None) or []
        }
        - {""}
    )
    raise ApplyError(
        "integration_missing",
        document.meta.kind.value,
        document.meta.name,
        "the platform did not save the assistant: some tools have no "
        "integration it can use"
        + (f" (credential types: {', '.join(types)})" if types else "")
        + "; pin an integration on them or create it first",
    )


def _make_adapter(
    *,
    service: str,
    body: Callable[[Document, Resolved], dict],
    create_cls: type[BaseModel],
    update_cls: type[BaseModel],
    create_method: str = "create",
    update_method: str = "update",
    get_method: str = "get",
    extract: Callable[[Any], str | None] = _extract_id,
    get_fn: Callable[[Any, Document, str], Any] | None = None,
    adjust_update: Callable[[dict, frozenset[str] | None], dict] | None = None,
    check_response: Callable[[Any, Document], None] | None = None,
) -> KindAdapter:
    def send(method, document, *args):
        with _no_request_body_log():
            response = method(*args)
        if check_response is not None:
            check_response(response, document)
        return response

    def create(client, document, resolved):
        request = _build(create_cls, body(document, resolved), document)
        method = getattr(getattr(client, service), create_method)
        return send(method, document, request)

    def update(client, document, entity_id, resolved, changed=None):
        data = body(document, resolved)
        if adjust_update is not None:
            data = adjust_update(data, changed)
        request = _build(update_cls, data, document)
        method = getattr(getattr(client, service), update_method)
        return send(method, document, entity_id, request)

    def get(client, document, entity_id):
        return getattr(getattr(client, service), get_method)(entity_id)

    return KindAdapter(
        create=create,
        update=update,
        get=get_fn or get,
        extract_id=extract,
        to_comparable=_to_comparable,
    )


def _get_integration(client: Any, document: Document, entity_id: str) -> Any:
    try:
        return client.integrations.get(
            entity_id, setting_type=document.spec.setting_type
        )
    except NotFoundError as exc:
        raise ApplyError(
            "integration_not_found",
            document.meta.kind.value,
            document.meta.name,
            f"integration {entity_id!r} not found; lookup lists at most "
            f"{INTEGRATION_LIST_CAP} integrations, so it may exist beyond the "
            f"{INTEGRATION_LIST_CAP}-item cap",
        ) from exc


# --- datasource sub-table, keyed by spec ``type`` ----------------------------

# ``knowledge_base_file`` is deliberately absent: file datasources are rejected
# by ``guards.guard_supported``, before an adapter is ever requested.
_DATASOURCE_CLASSES: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "code": (CodeDataSourceRequest, UpdateCodeDataSourceRequest),
    "knowledge_base_git_faq": (GitFaqDataSourceRequest, UpdateGitFaqDataSourceRequest),
    "knowledge_base_jira": (JiraDataSourceRequest, UpdateJiraDataSourceRequest),
    "knowledge_base_confluence": (
        ConfluenceDataSourceRequest,
        UpdateConfluenceDataSourceRequest,
    ),
    "llm_routing_google": (GoogleDataSourceRequest, UpdateGoogleDataSourceRequest),
    "knowledge_base_azure_devops_wiki": (
        AzureDevOpsWikiDataSourceRequest,
        UpdateAzureDevOpsWikiDataSourceRequest,
    ),
    "knowledge_base_azure_devops_work_item": (
        AzureDevOpsWorkItemDataSourceRequest,
        UpdateAzureDevOpsWorkItemDataSourceRequest,
    ),
    "knowledge_base_xwiki": (XWikiDataSourceRequest, UpdateXWikiDataSourceRequest),
}

# --- datasource live view ------------------------------------------------------
#
# The live view is the SDK ``DataSource`` model as read, with two adjustments
# for how a document describes a datasource.

# A document's code datasource is always ``type: code``; the SDK reports the
# index type (``code``, ``summary`` or ``chunk-summary``) as the datasource
# type. The index type itself is compared through the code sub-object.
_CODE_FAMILY = frozenset({"code", "summary", "chunk-summary"})


def _datasource_view(live: Any) -> dict[str, Any]:
    view = _to_comparable(live)
    if view.get("type") in _CODE_FAMILY:
        view["type"] = "code"
    # Without a schedule the backend reports its default timezone, which a
    # document does not author: only expose the timezone alongside a cron.
    if not view.get("cron_expression"):
        view.pop("timezone", None)
    return view


def _datasource_get(client: Any, document: Document, entity_id: str) -> Any:
    return _datasource_view(client.datasources.get(entity_id))


# --- reindex-aware updates -------------------------------------------------------
#
# What a datasource update reindexes depends on the route. Code routes start an
# incremental reindex unless ``skip_reindex`` is set. The knowledge-base routes
# store a changed source and reindex only when ``full_reindex`` is set, so a
# source change without it leaves the index on the old source. ``changed``
# (see ``KindAdapter``) names the fields the plan found different (or could
# not compare); it never grows a reindex out of an unrelated write, such as a
# forced one that only pushes a rotated secret.

#: Per datasource type, the fields whose change needs a full reindex.
_REINDEX_SOURCE_FIELDS = {
    "knowledge_base_git_faq": frozenset(
        {"link", "branch", "files_filter", "setting_id"}
    ),
    "knowledge_base_jira": frozenset({"jql", "custom_fields", "setting_id"}),
    "knowledge_base_confluence": frozenset({"cql", "setting_id"}),
    "knowledge_base_azure_devops_wiki": frozenset({"wiki_query", "setting_id"}),
    "knowledge_base_azure_devops_work_item": frozenset({"wiql_query", "setting_id"}),
    "knowledge_base_xwiki": frozenset({"space", "wiki", "setting_id"}),
}
#: Types whose route answers 422 to a source field sent without a full reindex.
_OMIT_UNCHANGED_SOURCE = frozenset({"knowledge_base_git_faq"})
#: Code datasource fields whose change needs no reindex.
_CODE_METADATA_FIELDS = frozenset(
    {
        "description",
        "shared_with_project",
        "project_space_visible",
        "cron_expression",
        "timezone",
    }
)


def _source_update(ds_type: str) -> Callable[[dict, frozenset[str] | None], dict]:
    source = _REINDEX_SOURCE_FIELDS[ds_type]

    def adjust(data: dict, changed: frozenset[str] | None) -> dict:
        if changed is None or changed & source:
            return {**data, "full_reindex": True}
        if ds_type in _OMIT_UNCHANGED_SOURCE:
            return {k: v for k, v in data.items() if k not in source}
        return data

    return adjust


def _code_update(data: dict, changed: frozenset[str] | None) -> dict:
    """Metadata-only changes skip the reindex. The update route reads the
    visibility only from the camelCase key, which the SDK's update request does
    not model, so it is added as an extra field."""
    data = {**data, "projectSpaceVisible": data.get("project_space_visible")}
    if changed is not None and changed <= _CODE_METADATA_FIELDS:
        data["skip_reindex"] = True
    return data


_UPDATE_ADJUSTERS = {
    "code": _code_update,
    **{ds_type: _source_update(ds_type) for ds_type in _REINDEX_SOURCE_FIELDS},
}

DATASOURCE_ADAPTERS: dict[str, KindAdapter] = {
    ds_type: _make_adapter(
        service="datasources",
        body=_datasource_body,
        create_cls=create_cls,
        update_cls=update_cls,
        extract=_no_id,
        get_fn=_datasource_get,
        adjust_update=_UPDATE_ADJUSTERS.get(ds_type),
    )
    for ds_type, (create_cls, update_cls) in _DATASOURCE_CLASSES.items()
}


def _datasource_adapter(document: Document) -> KindAdapter:
    ds_type = document.spec.type
    adapter = DATASOURCE_ADAPTERS.get(ds_type)
    if adapter is None:
        raise ApplyError(
            "unsupported_datasource_type",
            document.meta.kind.value,
            document.meta.name,
            f"datasource type {ds_type!r} cannot be applied",
        )
    return adapter


_DATASOURCE_DISPATCH = KindAdapter(
    create=lambda client, doc, resolved: _datasource_adapter(doc).create(
        client, doc, resolved
    ),
    update=lambda client, doc, entity_id, resolved, changed=None: _datasource_adapter(
        doc
    ).update(client, doc, entity_id, resolved, changed),
    get=lambda client, doc, entity_id: _datasource_adapter(doc).get(
        client, doc, entity_id
    ),
    extract_id=_no_id,
    to_comparable=_to_comparable,
)

ADAPTERS: dict[DocumentKind, KindAdapter] = {
    DocumentKind.ASSISTANT: _make_adapter(
        service="assistants",
        body=_spec_body,
        create_cls=AssistantCreateRequest,
        update_cls=AssistantUpdateRequest,
        check_response=_reject_declined_assistant,
    ),
    DocumentKind.SKILL: _make_adapter(
        service="skills",
        body=_spec_body,
        create_cls=SkillCreateRequest,
        update_cls=SkillUpdateRequest,
    ),
    DocumentKind.WORKFLOW: _make_adapter(
        service="workflows",
        body=_workflow_body,
        create_cls=WorkflowCreateRequest,
        update_cls=WorkflowUpdateRequest,
        create_method="create_workflow",
    ),
    DocumentKind.CATEGORY: _make_adapter(
        service="categories",
        body=_spec_body,
        create_cls=CategoryCreateRequest,
        update_cls=CategoryUpdateRequest,
        create_method="create_category",
        update_method="update_category",
        get_method="get_category",
    ),
    DocumentKind.INTEGRATION: _make_adapter(
        service="integrations",
        body=_integration_body,
        create_cls=Integration,
        update_cls=Integration,
        get_fn=_get_integration,
    ),
    DocumentKind.DATASOURCE: _DATASOURCE_DISPATCH,
}


def adapter_for(document: Document) -> KindAdapter:
    """The adapter for a document; datasources resolve by spec ``type``."""
    if document.meta.kind is DocumentKind.DATASOURCE:
        return _datasource_adapter(document)
    return ADAPTERS[document.meta.kind]
