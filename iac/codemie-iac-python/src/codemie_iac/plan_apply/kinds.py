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
from collections.abc import Callable, Mapping
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
    ProviderDataSourceRequest,
    SharePointDataSourceRequest,
    SvnDataSourceRequest,
    UpdateAzureDevOpsWikiDataSourceRequest,
    UpdateAzureDevOpsWorkItemDataSourceRequest,
    UpdateCodeDataSourceRequest,
    UpdateConfluenceDataSourceRequest,
    UpdateGitFaqDataSourceRequest,
    UpdateGoogleDataSourceRequest,
    UpdateJiraDataSourceRequest,
    UpdateProviderDataSourceRequest,
    UpdateSharePointDataSourceRequest,
    UpdateSvnDataSourceRequest,
    UpdateXrayDataSourceRequest,
    UpdateXWikiDataSourceRequest,
    XrayDataSourceRequest,
    XWikiDataSourceRequest,
)
from codemie_sdk.models.integration import Integration
from codemie_sdk.models.skill import SkillCreateRequest, SkillUpdateRequest
from codemie_sdk.models.workflow import WorkflowCreateRequest, WorkflowUpdateRequest
from pydantic import BaseModel, ValidationError

from ..envelope import Document, DocumentKind
from .errors import ApplyError

logger = logging.getLogger(__name__)

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
    find_id(client, document) -> id of the created entity looked up by its
        identity, for kinds whose create response carries no id
    """

    create: Callable[[Any, Document, Resolved], Any]
    update: Callable[..., Any]
    get: Callable[[Any, Document, str], Any]
    extract_id: Callable[[Any], str | None]
    to_comparable: Callable[[Any], dict[str, Any]]
    find_id: Callable[[Any, Document], str | None] | None = None


def created_id(
    adapter: KindAdapter, client: Any, document: Document, response: Any
) -> str | None:
    """The id of a just-created entity: from the response, else by lookup.

    The entity already exists when the lookup runs, so a lookup failure is
    logged and answered with ``None`` rather than failing the create."""
    entity_id = adapter.extract_id(response)
    if entity_id is None and adapter.find_id is not None:
        try:
            entity_id = adapter.find_id(client, document)
        except Exception as exc:  # noqa: BLE001 - the entity exists; never fail the create
            logger.warning(
                "created %s %r in project %r but could not look its id up: %s",
                document.meta.kind.value,
                document.meta.name,
                getattr(document.spec, "project_name", None),
                type(exc).__name__,
            )
    return entity_id


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
        # Never ``str(exc)``: pydantic embeds the offending input, which here
        # may be a revealed credential.
        reason = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<body>'}: {e['msg']}"
            for e in exc.errors(
                include_input=False, include_url=False, include_context=False
            )
        )
        raise ApplyError(
            "invalid_body", document.meta.kind.value, document.meta.name, reason
        ) from None


def _spec_body(document: Document, resolved: Resolved, **exclude: Any) -> dict:
    body = document.spec.model_dump(mode="python", exclude=set(exclude) or None)
    body.update(resolved)
    return body


def _clear_omitted_icon(body: dict, live: Any) -> dict:
    """An omitted ``icon_url`` clears one that is set on the live entity.

    Neither the SDK (``exclude_none``) nor the backend (``if value is not None``)
    treats ``None`` as "clear", so an empty string is sent instead.
    """
    if body.get("icon_url") is None and getattr(live, "icon_url", None):
        body["icon_url"] = ""
    return body


def _assistant_update_body(document: Document, resolved: Resolved, live: Any) -> dict:
    return _clear_omitted_icon(_spec_body(document, resolved), live)


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
        "start_hint": document.spec.start_hint,
    }
    body.update(overrides)
    return body


def _workflow_update_body(document: Document, resolved: Resolved, live: Any) -> dict:
    return _clear_omitted_icon(_workflow_body(document, resolved), live)


def _integration_body(document: Document, resolved: Resolved) -> dict:
    # Credential values only ever come from ``resolved``; the spec holds refs.
    return _spec_body(document, resolved, credential_values=None)


def _datasource_body(document: Document, resolved: Resolved) -> dict:
    body = _spec_body(document, resolved)
    body.pop("type", None)  # the request classes fix their own type
    # The requests name the flag by its camelCase alias; the typed svn,
    # SharePoint and Xray requests refuse the field name beside it.
    visible = body.pop("shared_with_project", False)
    body.setdefault("project_space_visible", visible)
    # An omitted svn branch is the SDK's default on create and the stored value
    # on update; the request rejects an explicit None.
    if body.get("branch") is None:
        body.pop("branch", None)
    return body


#: Fields the backend PUT overwrites when omitted, per datasource type: an
#: update must always send them, from the document or else from live state.
_HAZARD_FIELDS: dict[str, tuple[str, ...]] = {
    "svn": ("prompt", "files_filter", "project_space_visible", "docs_generation"),
    "knowledge_base_sharepoint": ("files_filter",),
    "provider": ("description", "project_space_visible"),
}

#: Hazard fields the update request requires: a missing value cannot be sent.
_REQUIRED_HAZARD_FIELDS: dict[str, tuple[str, ...]] = {
    "provider": ("description", "project_space_visible"),
}

#: Document fields an update request cannot carry, per datasource type.
_CREATE_ONLY_FIELDS: dict[str, tuple[str, ...]] = {
    "svn": ("index_type",),
    # The Xray update route does not pass the embedding model to the index.
    "knowledge_base_xray": ("embedding_model",),
}

#: Request field -> the differently named field on the spec and on the live
#: ``DataSource`` top level. Other hazard fields live in the type's sub-object.
_TOP_LEVEL_FIELDS = {
    "project_space_visible": "shared_with_project",
    "description": "description",
}
_LIVE_SUBOBJECT = {"svn": "svn", "knowledge_base_sharepoint": "sharepoint"}


def _is_authored(document: Document, resolved: Resolved, field: str) -> bool:
    spec_field = _TOP_LEVEL_FIELDS.get(field, field)
    spec = document.spec
    return field in resolved or (
        spec_field in spec.model_fields_set and getattr(spec, spec_field) is not None
    )


def _live_value(live: Mapping[str, Any], ds_type: str, field: str) -> Any:
    top_field = _TOP_LEVEL_FIELDS.get(field)
    if top_field:
        return live.get(top_field)
    return (live.get(_LIVE_SUBOBJECT.get(ds_type, "")) or {}).get(field)


def _complete_body(document: Document, resolved: Resolved, live: Any) -> dict:
    """The datasource body with every hazard field filled: from the document
    when it authors the field, else from the live value."""
    body = _datasource_body(document, resolved)
    ds_type = document.spec.type
    live = _to_comparable(live) if not isinstance(live, Mapping) else live
    for field in _CREATE_ONLY_FIELDS.get(ds_type, ()):
        body.pop(field, None)
    for field in _HAZARD_FIELDS.get(ds_type, ()):
        if _is_authored(document, resolved, field):
            continue
        live_value = _live_value(live, ds_type, field)
        if live_value is not None:
            body[field] = live_value
        elif field in _REQUIRED_HAZARD_FIELDS.get(ds_type, ()):
            raise ApplyError(
                "missing_required_field",
                "datasource",
                document.meta.name,
                f"{field!r} is required on update but is neither set in the "
                "document nor present on the live datasource; set it in the document",
            )
    return body


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
    update_body: Callable[[Document, Resolved, Any], dict] | None = None,
    to_comparable: Callable[[Any], dict[str, Any]] = _to_comparable,
    find_id: Callable[[Any, Document], str | None] | None = None,
    adjust_update: Callable[[dict, frozenset[str] | None], dict] | None = None,
) -> KindAdapter:
    def create(client, document, resolved):
        request = _build(create_cls, body(document, resolved), document)
        return getattr(getattr(client, service), create_method)(request)

    def get(client, document, entity_id):
        return getattr(getattr(client, service), get_method)(entity_id)

    def update(client, document, entity_id, resolved, changed=None):
        if update_body is None:
            data = body(document, resolved)
        else:
            live = (get_fn or get)(client, document, entity_id)
            data = update_body(document, resolved, live)
        if adjust_update is not None:
            data = adjust_update(data, changed)
        request = _build(update_cls, data, document)
        return getattr(getattr(client, service), update_method)(entity_id, request)

    return KindAdapter(
        create=create,
        update=update,
        get=get_fn or get,
        extract_id=extract,
        to_comparable=to_comparable,
        find_id=find_id,
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
# by a later task, before an adapter is ever requested.
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
    "svn": (SvnDataSourceRequest, UpdateSvnDataSourceRequest),
    "knowledge_base_sharepoint": (
        SharePointDataSourceRequest,
        UpdateSharePointDataSourceRequest,
    ),
    "knowledge_base_xray": (XrayDataSourceRequest, UpdateXrayDataSourceRequest),
}

# --- datasource live view ------------------------------------------------------
#
# The live view is the SDK ``DataSource`` model as read, with two adjustments
# for how a document describes a datasource.

# A document's code datasource is always ``type: code``; the SDK reports the
# index type (``code``, ``summary`` or ``chunk-summary``) as the datasource
# type. The index type itself is compared through the code sub-object. An SVN
# datasource is reported under the same index types.
_CODE_FAMILY = frozenset({"code", "summary", "chunk-summary"})


def _datasource_view(live: Any) -> dict[str, Any]:
    view = _to_comparable(live)
    if view.get("type") in _CODE_FAMILY:
        # An SVN datasource is stored under a code index type; its settings
        # come from the ``svn`` sub-object, not the code one.
        if view.get("svn") is not None:
            view["type"] = "svn"
            view.pop("code", None)
        else:
            view["type"] = "code"
    # Without a schedule the backend reports its default timezone, which a
    # document does not author: only expose the timezone alongside a cron.
    if not view.get("cron_expression"):
        view.pop("timezone", None)
    return view


def _datasource_get(client: Any, document: Document, entity_id: str) -> Any:
    return _datasource_view(client.datasources.get(entity_id))


#: A datasource create answers a message only, so the new id is looked up by
#: project and name. Listing has no name filter: it pages through the project.
_FIND_PAGE_SIZE = 100
_FIND_MAX_PAGES = 20


def _find_datasource_id(client: Any, document: Document) -> str | None:
    spec = document.spec
    for page in range(_FIND_MAX_PAGES):
        found = client.datasources.list(
            page=page, per_page=_FIND_PAGE_SIZE, projects=[spec.project_name]
        )
        for item in found:
            # Name and project are unique across all datasource types; the list
            # item does not say whether it is an svn one, so the type is not
            # compared.
            if item.name == spec.name and item.project_name == spec.project_name:
                return item.id
        if len(found) < _FIND_PAGE_SIZE:
            return None
    logger.warning(
        "datasource %r in project %r not found within %d list pages",
        spec.name,
        spec.project_name,
        _FIND_MAX_PAGES,
    )
    return None


# --- reindex-aware updates -------------------------------------------------------
#
# The backend reindexes on a datasource update unless told otherwise, and
# rejects a Git FAQ update that carries a source field without a full reindex.
# ``changed`` (see ``KindAdapter``) lets an update say what it needs.

_GIT_FAQ_SOURCE_FIELDS = frozenset({"link", "branch", "files_filter", "setting_id"})
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


def _git_faq_update(data: dict, changed: frozenset[str] | None) -> dict:
    """A source change is sent whole with ``full_reindex``; otherwise the
    source fields are left out (the backend answers 422 to a source field
    without a full reindex)."""
    if changed is None or changed & _GIT_FAQ_SOURCE_FIELDS:
        return {**data, "full_reindex": True}
    return {k: v for k, v in data.items() if k not in _GIT_FAQ_SOURCE_FIELDS}


def _code_update(data: dict, changed: frozenset[str] | None) -> dict:
    """Metadata-only changes skip the incremental reindex the backend starts
    by default."""
    if changed is not None and changed <= _CODE_METADATA_FIELDS:
        return {**data, "skip_reindex": True}
    return data


def _svn_update(data: dict, changed: frozenset[str] | None) -> dict:
    """Like code: the backend reprocesses the repository on every update unless
    ``skip_reindex`` is set, so a metadata-only change skips it."""
    if changed is not None and changed <= _CODE_METADATA_FIELDS:
        return {**data, "skip_reindex": True}
    return data


#: Fields whose change alters what a knowledge-base index holds. The backend
#: stores them without reindexing unless ``full_reindex`` is set.
_SOURCE_FIELDS = {
    "knowledge_base_sharepoint": frozenset(
        {
            "site_url",
            "include_pages",
            "include_documents",
            "include_lists",
            "max_file_size_mb",
            "files_filter",
            "auth_type",
            "oauth_client_id",
            "oauth_tenant_id",
            "embedding_model",
            "setting_id",
        }
    ),
    "knowledge_base_xray": frozenset({"jql", "setting_id"}),
}


def _source_update(source_fields: frozenset[str]):
    def adjust(data: dict, changed: frozenset[str] | None) -> dict:
        if changed is None or changed & source_fields:
            return {**data, "full_reindex": True}
        return data

    return adjust


_UPDATE_ADJUSTERS = {
    "code": _code_update,
    "knowledge_base_git_faq": _git_faq_update,
    "svn": _svn_update,
    **{t: _source_update(f) for t, f in _SOURCE_FIELDS.items()},
}

DATASOURCE_ADAPTERS: dict[str, KindAdapter] = {
    ds_type: _make_adapter(
        service="datasources",
        body=_datasource_body,
        create_cls=create_cls,
        update_cls=update_cls,
        extract=_no_id,
        get_fn=_datasource_get,
        update_body=(
            _complete_body
            if ds_type in _HAZARD_FIELDS or ds_type in _CREATE_ONLY_FIELDS
            else None
        ),
        to_comparable=_datasource_view,
        find_id=_find_datasource_id,
        adjust_update=_UPDATE_ADJUSTERS.get(ds_type),
    )
    for ds_type, (create_cls, update_cls) in _DATASOURCE_CLASSES.items()
}


#: The provider update request has no ``name`` / ``project_name`` field, yet
#: the backend reads both from the PUT body and clears them when absent. Its
#: body merges ``settings``, so they travel there.
_PROVIDER_UPDATE_IDENTITY = ("name", "project_name")


def _live_provider_settings(live: Any) -> dict[str, Any]:
    """The provider settings stored on the live datasource (base and create
    params, which the platform splits server-side)."""
    provider = live.get("provider") if isinstance(live, Mapping) else live.provider
    if provider is None:
        return {}
    params = provider.get if isinstance(provider, Mapping) else None
    out: dict[str, Any] = {}
    for name in ("base_params", "create_params"):
        value = params(name) if params else getattr(provider, name, None)
        out.update(value or {})
    return out


def _provider_update_body(document: Document, resolved: Resolved, live: Any) -> dict:
    body = _complete_body(document, resolved, live)
    # The backend resets every schema parameter the PUT omits to its default, so
    # the live settings fill the keys the document leaves out. A secret comes
    # back masked, which the platform reads as "keep the stored value".
    body["settings"] = {**_live_provider_settings(live), **body.get("settings", {})}
    identity = {
        field: getattr(document.spec, field) for field in _PROVIDER_UPDATE_IDENTITY
    }
    body["settings"] = {**body.get("settings", {}), **identity}
    return body


def _provider_create(client: Any, document: Document, resolved: Resolved) -> Any:
    request = _build(
        ProviderDataSourceRequest, _datasource_body(document, resolved), document
    )
    return client.datasources.create_provider_datasource(
        request.toolkit_id, request.provider_name, request
    )


def _provider_update(
    client: Any,
    document: Document,
    entity_id: str,
    resolved: Resolved,
    changed: frozenset[str] | None = None,
) -> Any:
    live = client.datasources.get(entity_id)
    request = _build(
        UpdateProviderDataSourceRequest,
        _provider_update_body(document, resolved, live),
        document,
    )
    return client.datasources.update_provider_datasource(entity_id, request)


_PROVIDER_ADAPTER = KindAdapter(
    create=_provider_create,
    update=_provider_update,
    get=lambda client, _doc, entity_id: client.datasources.get(entity_id),
    extract_id=_no_id,  # the backend answers a message only; no index id
    to_comparable=_datasource_view,
    find_id=_find_datasource_id,
)
DATASOURCE_ADAPTERS["provider"] = _PROVIDER_ADAPTER


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
    to_comparable=_datasource_view,
    find_id=_find_datasource_id,
)

ADAPTERS: dict[DocumentKind, KindAdapter] = {
    DocumentKind.ASSISTANT: _make_adapter(
        service="assistants",
        body=_spec_body,
        create_cls=AssistantCreateRequest,
        update_cls=AssistantUpdateRequest,
        update_body=_assistant_update_body,
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
        update_body=_workflow_update_body,
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
