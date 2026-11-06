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


"""Workflow assistant references are ordered and checked."""

import pytest
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
)
from codemie_iac.envelope import DocumentKind
from codemie_iac.plan_apply.bulk_create import (
    BulkCreator,
    check_references,
)
from codemie_iac.plan_apply.errors import UnresolvedReferenceError
from codemie_iac.plan_apply.ordering import DependencyGraph
from .fakes import (
    FakeAssistants,
    FakeClient,
)

from .helpers import (
    ParsingAssistants,
    TARGET,
    _assistant,
    _ctx,
    _workflow,
)


def test_name_only_workflow_assistant_is_an_ordering_edge():
    wf = _workflow(WorkflowAssistant(id="a1", name="helper"))
    helper = _assistant("helper")
    graph = DependencyGraph([wf, helper])
    assert graph.edges(wf) == [(DocumentKind.ASSISTANT, "helper")]
    assert [d.meta.name for d in graph.order()] == ["helper", "wf"]


def test_inline_assistant_with_display_name_is_not_an_edge():
    wf = _workflow(WorkflowAssistant(id="a1", name="helper", system_prompt="inline"))
    graph = DependencyGraph([wf, _assistant("helper")])
    assert graph.edges(wf) == []


def test_missing_name_only_workflow_assistant_fails_preflight():
    wf = _workflow(WorkflowAssistant(id="a1", name="ghost"))
    ctx = _ctx([wf], client=FakeClient(assistants=ParsingAssistants([])))
    with pytest.raises(UnresolvedReferenceError):
        check_references([wf], ctx)


def test_bundle_with_workflow_before_name_only_assistant_creates_in_order():
    wf = _workflow(WorkflowAssistant(id="a1", name="helper"))
    client = FakeClient(assistants=FakeAssistants())
    report = BulkCreator(client).create_all([wf, _assistant("helper")], TARGET)
    assert report.failed is None
    assert [c.name for c in report.created] == ["helper", "wf"]
