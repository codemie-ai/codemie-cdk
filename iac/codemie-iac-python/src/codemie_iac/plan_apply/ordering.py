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

"""Dependency ordering of a bundle's documents (create-only apply).

Only references to entities present in the bundle are ordering edges;
references to entities outside it are resolved by a live lookup elsewhere.
"""

from collections.abc import Callable, Iterable, Iterator

from ..envelope import Document, DocumentKind
from .errors import ApplyError

__all__ = ["EDGE_EXTRACTORS", "DependencyGraph", "value_edges"]

Edge = tuple[DocumentKind, str]
_Key = tuple[DocumentKind, str]


def _assistant_integrations(spec) -> Iterator[str]:
    for toolkit in spec.toolkits:
        yield toolkit.settings
        for tool in toolkit.tools:
            yield tool.settings
    for server in spec.mcp_servers:
        yield server.settings
        yield server.mcp_connect_auth_token


def _assistant_value_edges(spec) -> Iterator[Edge]:
    for name in spec.skill_ids:
        yield DocumentKind.SKILL, name


def _assistant_edges(doc: Document) -> Iterator[Edge]:
    spec = doc.spec
    for name in spec.assistant_ids:
        yield DocumentKind.ASSISTANT, name
    for ctx in spec.context:
        yield DocumentKind.DATASOURCE, ctx.name
    yield from _assistant_value_edges(spec)
    for name in spec.categories:
        yield DocumentKind.CATEGORY, name
    for name in _assistant_integrations(spec):
        if name:
            yield DocumentKind.INTEGRATION, name


def _skill_edges(doc: Document) -> Iterator[Edge]:
    # Skill categories are values of a fixed platform list, not Category
    # entities, so a skill depends on nothing here.
    return iter(())


def _agent_value_edges(assistant) -> Iterator[Edge]:
    for name in assistant.skill_ids or ():
        yield DocumentKind.SKILL, name
    for name in assistant.datasource_ids or ():
        yield DocumentKind.DATASOURCE, name


def _workflow_edges(doc: Document) -> Iterator[Edge]:
    for assistant in doc.spec.workflow.assistants.values():
        yield from _agent_value_edges(assistant)
        if assistant.assistant_id:
            yield DocumentKind.ASSISTANT, assistant.assistant_id
        elif assistant.name and assistant.system_prompt is None:
            # A name-only reference: ``WorkflowDefinition.to_yaml_config``
            # resolves it to an assistant id when the workflow is rendered.
            yield DocumentKind.ASSISTANT, assistant.name
        aliases = [t.integration_alias for t in assistant.tools]
        aliases += [s.integration_alias for s in assistant.mcp_servers]
        for alias in aliases:
            if alias:
                yield DocumentKind.INTEGRATION, alias


def _datasource_edges(doc: Document) -> Iterator[Edge]:
    if doc.spec.setting_id:
        yield DocumentKind.INTEGRATION, doc.spec.setting_id


EDGE_EXTRACTORS: dict[DocumentKind, Callable[[Document], Iterable[Edge]]] = {
    DocumentKind.ASSISTANT: _assistant_edges,
    DocumentKind.SKILL: _skill_edges,
    DocumentKind.WORKFLOW: _workflow_edges,
    DocumentKind.DATASOURCE: _datasource_edges,
}


def value_edges(doc: Document) -> set[Edge]:
    """The edges of ``doc`` whose names may also be raw platform ids (skill and
    datasource values), as opposed to names that must resolve."""
    if doc.meta.kind is DocumentKind.ASSISTANT:
        return set(_assistant_value_edges(doc.spec))
    if doc.meta.kind is DocumentKind.WORKFLOW:
        agents = doc.spec.workflow.assistants.values()
        return {e for a in agents for e in _agent_value_edges(a)}
    return set()


def _key(doc: Document) -> _Key:
    return doc.meta.kind, doc.meta.name


class DependencyGraph:
    """Dependency graph over a list of documents; dependencies sort first."""

    def __init__(self, documents: Iterable[Document]):
        self._docs: dict[_Key, Document] = {}
        for doc in documents:
            key = _key(doc)
            if key in self._docs:
                raise ApplyError(
                    "duplicate_document",
                    key[0].value,
                    key[1],
                    f"more than one {key[0].value} document named {key[1]!r}",
                )
            self._docs[key] = doc

    def edges(self, doc: Document) -> list[Edge]:
        """In-bundle dependencies of ``doc`` (deduplicated, stable order)."""
        extractor = EDGE_EXTRACTORS.get(doc.meta.kind)
        found = extractor(doc) if extractor else ()
        unique = dict.fromkeys(e for e in found if e in self._docs)
        return list(unique)

    def order(self) -> list[Document]:
        """Documents in dependency-first order; raises on a cycle."""
        done: set[_Key] = set()
        result: list[Document] = []
        for key in self._docs:
            self._visit(key, [], done, result)
        return result

    def _visit(
        self, key: _Key, path: list[_Key], done: set[_Key], out: list[Document]
    ) -> None:
        if key in done:
            return
        if key in path:
            self._raise_cycle(path[path.index(key) :] + [key])
        doc = self._docs[key]
        path.append(key)
        for dep in self.edges(doc):
            self._visit(dep, path, done, out)
        path.pop()
        done.add(key)
        out.append(doc)

    @staticmethod
    def _raise_cycle(cycle: list[_Key]) -> None:
        text = " -> ".join(name for _, name in cycle)
        kind, name = cycle[0]
        raise ApplyError(
            "dependency_cycle", kind.value, name, f"dependency cycle: {text}"
        )
