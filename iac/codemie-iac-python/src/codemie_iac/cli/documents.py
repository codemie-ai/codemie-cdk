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

from pathlib import Path

from .. import serializer
from ..envelope import Bundle, Document

__all__ = [
    "InvalidDocumentError",
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
    try:
        return serializer.from_yaml(text)
    except serializer.DocumentParseError as exc:
        # The parser's own message quotes the source line, which may hold a secret.
        raise InvalidDocumentError(f"{path}: {_location(exc)}") from None


def _location(exc: serializer.DocumentParseError) -> str:
    mark = getattr(exc.__cause__, "problem_mark", None)
    if mark is None:
        return str(exc)  # structural error (empty document): no source quoted
    return f"invalid YAML at line {mark.line + 1}, column {mark.column + 1}"
