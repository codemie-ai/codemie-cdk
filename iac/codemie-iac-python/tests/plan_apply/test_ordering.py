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

import pytest
from pydantic import TypeAdapter

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.ordering import DependencyGraph


def _doc(kind, name, spec):
    return Document.model_validate(
        {"version": "v1", "meta": {"kind": kind, "name": name}, "spec": spec}
    )


def _assistant(name, **extra):
    spec = {
        "name": name,
        "description": "d",
        "system_prompt": "p",
        "project": "proj",
        "llm_model_type": "gpt",
    }
    spec.update(extra)
    return _doc("assistant", name, spec)


def _datasource(name):
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "knowledge_base_file",
            "name": name,
            "project_name": "proj",
            "description": "d",
        }
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name=name),
        spec=spec,
    )


def _names(docs):
    return [d.meta.name for d in docs]


def test_assistant_dependencies_come_first():
    parent = _assistant(
        "parent",
        assistant_ids=["child"],
        context=[{"context_type": "knowledge_base", "name": "kb"}],
    )
    child = _assistant("child")
    kb = _datasource("kb")

    order = _names(DependencyGraph([parent, child, kb]).order())

    assert order.index("child") < order.index("parent")
    assert order.index("kb") < order.index("parent")


def test_edges_ignore_entities_absent_from_bundle():
    parent = _assistant("parent", assistant_ids=["ghost"])

    graph = DependencyGraph([parent])

    assert graph.edges(parent) == []
    assert _names(graph.order()) == ["parent"]


def test_edges_list_kind_and_name():
    parent = _assistant("parent", assistant_ids=["child"])
    child = _assistant("child")

    assert DependencyGraph([parent, child]).edges(parent) == [
        (DocumentKind.ASSISTANT, "child")
    ]


def test_two_cycle_raises_with_path():
    a = _assistant("a", assistant_ids=["b"])
    b = _assistant("b", assistant_ids=["a"])

    with pytest.raises(ApplyError) as exc:
        DependencyGraph([a, b]).order()

    assert "a -> b -> a" in exc.value.reason
    assert exc.value.error_type == "dependency_cycle"
