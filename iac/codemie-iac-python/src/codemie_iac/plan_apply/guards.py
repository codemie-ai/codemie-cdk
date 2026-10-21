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

"""Guards for operations that are not supported on datasources.

``guard_supported`` rejects file datasources before any adapter lookup;
``guard_datasource_identity`` rejects a rename or a move to another project
by comparing the document with the live datasource, before any write.
"""

from collections.abc import Mapping
from typing import Any

from codemie_sdk.models.assistant import AssistantCreateRequest, AssistantUpdateRequest

from ..envelope import Document, DocumentKind
from .errors import ApplyError

__all__ = [
    "SPEC_PROJECT_FIELDS",
    "guard_datasource_identity",
    "guard_name",
    "guard_project",
    "guard_supported",
]

#: kind -> name of the spec field that carries the entity's project (``None``
#: when the document omits it). Workflows
#: take the target project when written and categories are global, so neither
#: has one.
SPEC_PROJECT_FIELDS = {
    DocumentKind.ASSISTANT: "project",
    DocumentKind.SKILL: "project",
    DocumentKind.INTEGRATION: "project_name",
    DocumentKind.DATASOURCE: "project_name",
}

#: kind -> the spec field the platform knows the entity by. References resolve
#: through ``meta.name``, so it has to be the same string.
_SPEC_NAME_FIELDS = {
    DocumentKind.ASSISTANT: lambda spec: spec.name,
    DocumentKind.SKILL: lambda spec: spec.name,
    DocumentKind.CATEGORY: lambda spec: spec.name,
    DocumentKind.DATASOURCE: lambda spec: spec.name,
    DocumentKind.WORKFLOW: lambda spec: spec.workflow.name,
    DocumentKind.INTEGRATION: lambda spec: spec.alias,
}

_FILE_TYPE = "knowledge_base_file"


def _is_datasource(document: Document) -> bool:
    return document.meta.kind is DocumentKind.DATASOURCE


def _error(document: Document, error_type: str, reason: str) -> ApplyError:
    return ApplyError(error_type, document.meta.kind.value, document.meta.name, reason)


def _sdk_carries_assistant_skills() -> bool:
    """Whether the installed SDK's assistant requests have a ``skill_ids``
    field. Older SDKs ignore unknown fields, so skills would be dropped."""
    return all(
        "skill_ids" in cls.model_fields
        for cls in (AssistantCreateRequest, AssistantUpdateRequest)
    )


def guard_supported(document: Document) -> None:
    """Raise ``ApplyError`` for a file datasource (no adapter is consulted), or
    for an assistant with ``skill_ids`` when the installed SDK cannot send them."""
    if _is_datasource(document) and document.spec.type == _FILE_TYPE:
        raise _error(
            document,
            "unsupported_datasource_type",
            f"datasource type {_FILE_TYPE!r}: file datasources are not supported",
        )
    if (
        document.meta.kind is DocumentKind.ASSISTANT
        and document.spec.skill_ids
        and not _sdk_carries_assistant_skills()
    ):
        raise _error(
            document,
            "unsupported_sdk",
            "skill_ids: the installed codemie-sdk assistant request has no "
            "skill_ids field, so the skills would be dropped silently; upgrade "
            "codemie-sdk-python or remove skill_ids from the document",
        )


def _live_value(live: Any, key: str) -> Any:
    if isinstance(live, Mapping):
        return live.get(key)
    return getattr(live, key, None)


def _live_toolkit_id(live: Any) -> Any:
    provider = _live_value(live, "provider")
    return _live_value(provider, "toolkit_id") if provider is not None else None


def guard_datasource_identity(document: Document, live: Any) -> None:
    """Raise ``ApplyError`` if the live datasource has another name, project
    or (provider) toolkit."""
    if not _is_datasource(document):
        return
    spec = document.spec
    live_toolkit = _live_toolkit_id(live)
    if (
        spec.type == "provider"
        and live_toolkit is not None
        and live_toolkit != spec.toolkit_id
    ):
        raise _error(
            document,
            "datasource_identity_mismatch",
            f"toolkit_id cannot change (document {spec.toolkit_id!r}, live "
            f"{live_toolkit!r}); recreate the datasource",
        )
    live_name = _live_value(live, "name")
    live_project = _live_value(live, "project_name")
    if live_name == spec.name and live_project == spec.project_name:
        return
    raise _error(
        document,
        "datasource_identity_mismatch",
        "renaming or moving a datasource is not supported: document is "
        f"{spec.name!r} in project {spec.project_name!r}, live is "
        f"{live_name!r} in project {live_project!r}",
    )


def guard_project(document: Document, target: str) -> None:
    """Raise ``ApplyError`` if the document names a project other than ``target``.

    The request body takes its project from the document, so an entity would
    otherwise be created in (or moved to) a project the run does not target.
    """
    field = SPEC_PROJECT_FIELDS.get(document.meta.kind)
    project = getattr(document.spec, field, None) if field else None
    if project is not None and project != target:
        raise _error(
            document,
            "project_mismatch",
            f"document is in project {project!r}, not target {target!r}",
        )


def guard_name(document: Document) -> None:
    """Raise ``ApplyError`` if ``meta.name`` differs from the entity's own name.

    Bundle matching and the live lookup use ``meta.name``, while the platform
    (and the names other entities reference) use the spec name, so the two
    must be equal or a reference by either would miss.
    """
    spec_name = _SPEC_NAME_FIELDS[document.meta.kind](document.spec)
    if spec_name != document.meta.name:
        raise _error(
            document,
            "name_mismatch",
            f"meta.name {document.meta.name!r} differs from the "
            f"{'alias' if document.meta.kind is DocumentKind.INTEGRATION else 'name'}"
            f" in the spec {spec_name!r}; they must be equal",
        )
