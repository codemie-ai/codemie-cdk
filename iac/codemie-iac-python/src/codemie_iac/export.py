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

__all__ = ["export_document"]


def export_document(client: Any, kind: DocumentKind | str, entity_id: str) -> Document:
    """Fetch entity ``entity_id`` of ``kind`` and parse it into a ``Document``."""
    kind_value = kind.value if isinstance(kind, DocumentKind) else str(kind)
    return Document.model_validate(client.export.export(kind_value, entity_id))
