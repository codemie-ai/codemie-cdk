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

from ..envelope import Document, DocumentKind
from .errors import ApplyError

__all__ = ["guard_datasource_identity", "guard_project", "guard_supported"]

#: kind -> name of the spec field that carries the entity's project. Workflows
#: take the target project when written and categories are global, so neither
#: has one.
_SPEC_PROJECT_FIELDS = {
    DocumentKind.ASSISTANT: "project",
    DocumentKind.SKILL: "project",
    DocumentKind.INTEGRATION: "project_name",
    DocumentKind.DATASOURCE: "project_name",
}

_FILE_TYPE = "knowledge_base_file"


def _is_datasource(document: Document) -> bool:
    return document.meta.kind is DocumentKind.DATASOURCE


def _error(document: Document, error_type: str, reason: str) -> ApplyError:
    return ApplyError(error_type, document.meta.kind.value, document.meta.name, reason)


def guard_supported(document: Document) -> None:
    """Raise ``ApplyError`` for a file datasource (no adapter is consulted)."""
    if _is_datasource(document) and document.spec.type == _FILE_TYPE:
        raise _error(
            document,
            "unsupported_datasource_type",
            f"datasource type {_FILE_TYPE!r}: file datasources are not supported",
        )


def _live_value(live: Any, key: str) -> Any:
    if isinstance(live, Mapping):
        return live.get(key)
    return getattr(live, key, None)


def guard_datasource_identity(document: Document, live: Any) -> None:
    """Raise ``ApplyError`` if the live datasource has another name or project."""
    if not _is_datasource(document):
        return
    spec = document.spec
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
    field = _SPEC_PROJECT_FIELDS.get(document.meta.kind)
    project = getattr(document.spec, field, None) if field else None
    if project is not None and project != target:
        raise _error(
            document,
            "project_mismatch",
            f"document is in project {project!r}, not target {target!r}",
        )
