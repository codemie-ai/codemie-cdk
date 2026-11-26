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

"""Reuse of an already existing category on apply."""

from typing import TYPE_CHECKING

from ..envelope import Document, DocumentKind
from .errors import PLATFORM_ERRORS, PlatformRejectionError
from .field_policy import policy_for

if TYPE_CHECKING:
    from .bulk_create import ResolveContext

__all__ = ["existing_category"]


def existing_category(
    ctx: "ResolveContext", document: Document
) -> tuple[str, list[str]] | None:
    """``(live id, differing field names)`` of the category named like
    ``document``, or ``None`` when it is not a category, there is no client or
    no such category exists. Reads only; field names only, never values.

    The diff uses the listing item. Fetching the category by id would need
    admin rights on the platform, which a regular user applying a bundle lacks."""
    # Local import: single_apply imports bulk_create, which imports this module.
    from .single_apply import Difference, diff

    kind, name = document.meta.kind, document.meta.name
    if kind is not DocumentKind.CATEGORY or ctx.lookup.client is None:
        return None
    try:
        found = ctx.lookup.find_live(kind, name)
    except PLATFORM_ERRORS as exc:
        # Raised below, outside the handler: the SDK error may carry secrets.
        rejection = PlatformRejectionError(
            "platform_rejection",
            kind.value,
            name,
            exc,
            ctx.credentials.revealed_values(),
        )
    else:
        rejection = None
    if rejection is not None:
        raise rejection
    if found is None:
        return None
    findings = diff(document, found.source, policy_for(document), ctx.credentials, ctx)
    return found.id, [f.field for f in findings if isinstance(f, Difference)]
