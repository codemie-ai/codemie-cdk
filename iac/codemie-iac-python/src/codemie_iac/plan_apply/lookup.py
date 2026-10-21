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

"""Name -> platform entity lookup for references between entities.

A reference is first resolved against the bundle (``ReferenceResolver``).
A name that is not in the bundle falls back to a read-only live lookup in the
target project. Anything that resolves nowhere (or ambiguously) is an
``UnresolvedReferenceError``. Platform ids are only returned, never stored.
"""

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from codemie_sdk.models.integration import IntegrationType

from ..envelope import Document, DocumentKind
from ..resolver import ReferenceResolutionError, ReferenceResolver
from .errors import ApplyError, UnresolvedReferenceError

__all__ = ["LIVE_FINDERS", "EntityKey", "NameLookup", "Reference"]

EntityKey = tuple[DocumentKind, str]

_PAGE_SIZE = 100
_MAX_PAGES = 50


@dataclass(frozen=True)
class Reference:
    """A resolved reference.

    ``id`` is the platform id; ``source`` is the bundle ``Document`` or the
    live SDK object it came from.
    """

    id: str
    source: Any


def _pages(fetch: Callable[[int], Any]) -> Iterator[Any]:
    """Every item, paging until an empty page (a short page may just mean the
    server caps ``per_page`` below ours). Raises rather than truncating."""
    for page in range(_MAX_PAGES):
        items = list(fetch(page))
        if not items:
            return
        yield from items
    raise ApplyError(
        "lookup_truncated",
        "lookup",
        "pagination",
        f"live lookup exceeded {_MAX_PAGES} pages; refusing to guess from a "
        "truncated listing",
    )


# The live assistant listing only returns assistants the calling user can see
# (shared in their projects, in projects they administer, or their own), so a
# missing assistant may exist but be invisible to the caller. Say so.
_VISIBILITY_NOTE: dict[DocumentKind, str] = {
    DocumentKind.ASSISTANT: " (or it exists but is not visible to the current user)",
}


def _in_project(item: Any, target: str, attr: str) -> bool:
    return getattr(item, attr, None) == target


def _named(items: Iterable[Any], name: str) -> list[Any]:
    return [i for i in items if getattr(i, "name", None) == name]


def _find_assistants(client: Any, target: str, name: str) -> list[Any]:
    # Not ``minimal_response``: its SDK model (``AssistantBase``) drops the
    # ``project`` the backend sends, so no assistant would match the target.
    items = _pages(
        lambda p: client.assistants.list(
            minimal_response=False,
            page=p,
            per_page=_PAGE_SIZE,
            filters={"project": [target]},
        )
    )
    return [i for i in _named(items, name) if _in_project(i, target, "project")]


def _find_skills(client: Any, target: str, name: str) -> list[Any]:
    items = _pages(lambda p: client.skills.list(page=p, per_page=_PAGE_SIZE).skills)
    return [i for i in _named(items, name) if _in_project(i, target, "project")]


def _find_workflows(client: Any, target: str, name: str) -> list[Any]:
    items = _pages(
        lambda p: client.workflows.list(page=p, per_page=_PAGE_SIZE, projects=[target])
    )
    return _named(items, name)


def _find_datasources(client: Any, target: str, name: str) -> list[Any]:
    items = _pages(
        lambda p: client.datasources.list(
            page=p, per_page=_PAGE_SIZE, projects=[target]
        )
    )
    return _named(items, name)


def _find_integrations(client: Any, target: str, name: str) -> list[Any]:
    """Integrations of the target project with alias ``name``, every page of
    both the project and the user listing (``get_by_alias`` reads one page and
    returns the first match whatever its project)."""
    found = []
    for setting_type in (IntegrationType.PROJECT, IntegrationType.USER):
        items = _pages(
            lambda p, st=setting_type: client.integrations.list(
                setting_type=st, page=p, per_page=_PAGE_SIZE
            )
        )
        found += [
            i
            for i in items
            if getattr(i, "alias", None) == name
            and _in_project(i, target, "project_name")
        ]
    return found


def _find_categories(client: Any, target: str, name: str) -> list[Any]:
    return _named(client.categories.get_categories(), name)


#: kind -> finder(client, target, name) -> matching live objects.
LIVE_FINDERS: dict[DocumentKind, Callable[[Any, str, str], list[Any]]] = {
    DocumentKind.ASSISTANT: _find_assistants,
    DocumentKind.SKILL: _find_skills,
    DocumentKind.WORKFLOW: _find_workflows,
    DocumentKind.DATASOURCE: _find_datasources,
    DocumentKind.INTEGRATION: _find_integrations,
    DocumentKind.CATEGORY: _find_categories,
}


def _integration_alias(document: Document) -> str | None:
    return document.spec.alias


#: kind -> the name a *bundle* entity is known by on the platform, when that is
#: not its ``meta.name`` (an integration is found by its alias; the create
#: response carries no id, so it is looked up after it was created).
_LIVE_NAMES: dict[DocumentKind, Callable[[Document], str | None]] = {
    DocumentKind.INTEGRATION: _integration_alias,
}


def _live_name(kind: DocumentKind, document: Document | None, name: str) -> str:
    if document is None or kind not in _LIVE_NAMES:
        return name
    return _LIVE_NAMES[kind](document) or name


class NameLookup:
    """Resolves ``(kind, name)`` references to platform ids.

    ``bundle`` is the documents being applied; ``client`` (optional) enables
    the live fallback in the ``target`` project. Without a client only the
    bundle is consulted.
    """

    def __init__(self, bundle: Iterable[Document], target: str, client: Any = None):
        self._resolver = ReferenceResolver(list(bundle))
        self._target = target
        self._client = client

    @property
    def target(self) -> str:
        return self._target

    def in_bundle(self, kind: DocumentKind, name: str) -> Document | None:
        """The bundle document for the reference; None if absent. Raises
        ``UnresolvedReferenceError`` if ambiguous within the bundle."""
        try:
            return self._resolver.resolve(kind.value, name)
        except ReferenceResolutionError as exc:
            if "ambiguous" in str(exc):
                raise self._error(kind, name, str(exc)) from exc
            return None

    def _live(self, kind: DocumentKind, name: str) -> Any | None:
        if self._client is None:
            return None
        matches = LIVE_FINDERS[kind](self._client, self._target, name)
        if len(matches) > 1:
            raise self._error(
                kind,
                name,
                f"ambiguous reference: {len(matches)} {kind.value} entities "
                f"named {name!r} in project {self._target!r}",
            )
        return matches[0] if matches else None

    @staticmethod
    def _error(kind: DocumentKind, name: str, reason: str, referrer: str | None = None):
        suffix = f" (referenced by {referrer})" if referrer else ""
        return UnresolvedReferenceError(
            "unresolved_reference", kind.value, name, reason + suffix
        )

    def require(
        self, kind: DocumentKind, name: str, referrer: str | None = None
    ) -> None:
        """Preflight check: the reference exists in the bundle or live."""
        if self.in_bundle(kind, name) is not None:
            return
        if self._live(kind, name) is None:
            raise self._error(
                kind,
                name,
                f"no {kind.value} named {name!r} in the bundle or in "
                f"project {self._target!r}" + _VISIBILITY_NOTE.get(kind, ""),
                referrer,
            )

    def resolve(
        self,
        kind: DocumentKind,
        name: str,
        created: Mapping[EntityKey, str] | None = None,
    ) -> Reference:
        """Platform id of the reference.

        ``created`` maps bundle entities already created in this run to their
        ids. A bundle entity without a recorded id (e.g. a datasource, whose
        create response carries none) is looked up live by name after create.
        """
        document = self.in_bundle(kind, name)
        known = (created or {}).get((kind, name))
        if known is not None and document is not None:
            return Reference(known, document)
        live = self._live(kind, _live_name(kind, document, name))
        entity_id = getattr(live, "id", None)
        if not entity_id:
            raise self._error(kind, name, f"no platform id for {kind.value} {name!r}")
        return Reference(entity_id, live)
