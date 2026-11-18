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

"""Export a platform entity as a document."""

from typing import Any

from .envelope import Document, DocumentKind
from .plan_apply.errors import UnresolvedReferenceError
from .plan_apply.guards import SPEC_PROJECT_FIELDS
from .plan_apply.lookup import LIVE_FINDERS

__all__ = ["NON_PORTABLE_FIELDS", "export_document", "find_entity_id"]

#: Spec fields an export leaves out, per kind, because they are not part of the
#: entity's definition:
#: - the project field (``SPEC_PROJECT_FIELDS``): ``apply`` takes it from the
#:   target project in ``codemie.yaml`` and refuses a different one;
#: - tied to one live entity: an assistant's ``slug`` is unique per project, so
#:   with it the file could not be applied as a *new* assistant (the platform
#:   derives one from the name and suffixes a clash).
#: Add a field here when it is one of these and the spec still carries it.
NON_PORTABLE_FIELDS: dict[DocumentKind, frozenset[str]] = {
    kind: frozenset({field}) for kind, field in SPEC_PROJECT_FIELDS.items()
}
NON_PORTABLE_FIELDS[DocumentKind.ASSISTANT] |= {"slug"}


def _without_non_portable_fields(
    kind: DocumentKind, raw: dict[str, Any]
) -> dict[str, Any]:
    dropped = NON_PORTABLE_FIELDS.get(kind, frozenset())
    spec = raw.get("spec")
    if not dropped or not isinstance(spec, dict):
        return raw
    return {**raw, "spec": {k: v for k, v in spec.items() if k not in dropped}}


def export_document(client: Any, kind: DocumentKind | str, entity_id: str) -> Document:
    """Fetch entity ``entity_id`` of ``kind`` and parse it into a ``Document``.

    Fields in ``NON_PORTABLE_FIELDS`` are dropped before parsing, so the
    document applies as a new entity without clashing with the original.
    """
    kind = DocumentKind(kind)
    raw = client.export.export(kind.value, entity_id)
    return Document.model_validate(_without_non_portable_fields(kind, raw))


def find_entity_id(
    client: Any, project: str, kind: DocumentKind | str, alias: str
) -> str:
    """The id of the one ``kind`` entity called ``alias`` in ``project``.

    Raises ``UnresolvedReferenceError`` when none or several match; the
    several case lists their ids so the caller can pick one with ``--id``.
    """
    kind = DocumentKind(kind)
    matches = LIVE_FINDERS[kind](client, project, alias)
    if len(matches) == 1:
        return str(matches[0].id)
    reason = f"no {kind.value} named {alias!r} in project {project!r}"
    if matches:
        ids = ", ".join(str(m.id) for m in matches)
        reason = (
            f"{len(matches)} {kind.value} entities named {alias!r} in project "
            f"{project!r}; use --id with one of: {ids}"
        )
    raise UnresolvedReferenceError("unresolved_reference", kind.value, alias, reason)
