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

"""Selecting the single document of a file for the single-entity commands."""

from collections.abc import Iterable
from pathlib import Path

from .. import serializer
from ..envelope import Bundle, Document
from ..plan_apply.guards import SPEC_PROJECT_FIELDS

__all__ = [
    "InvalidDocumentError",
    "apply_default_project",
    "read_bundle",
    "single_document",
]


class InvalidDocumentError(Exception):
    """The file does not hold exactly one document (exit status 5)."""


def single_document(bundle: Bundle) -> Document:
    """Return the only document of ``bundle``; raise if there are 0 or >1."""
    if len(bundle) != 1:
        raise InvalidDocumentError(
            f"expected exactly one document, found {len(bundle)}"
        )
    return bundle.root[0]


def read_bundle(path: Path) -> Bundle:
    """Parse the YAML file at ``path``; unreadable or non-UTF-8 files are invalid."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise InvalidDocumentError(f"cannot read document file {path}") from None
    return serializer.from_yaml(text)


def _with_project(document: Document, target: str) -> Document:
    field = SPEC_PROJECT_FIELDS.get(document.meta.kind)
    if field is None or getattr(document.spec, field, None) is not None:
        return document
    spec = document.spec.model_copy(update={field: target})
    return document.model_copy(update={"spec": spec})


def apply_default_project(documents: Iterable[Document], target: str) -> list[Document]:
    """Return ``documents`` with every omitted project set to ``target``.

    A document that names a project is returned as is, so the engine's
    project guard still refuses one that differs from the target.
    """
    return [_with_project(document, target) for document in documents]
