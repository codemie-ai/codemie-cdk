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

from types import SimpleNamespace

import pytest
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.workflow import WorkflowMode

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.plan_apply.errors import UnresolvedReferenceError
from codemie_iac.specs.skill import SkillSpec
from codemie_iac.specs.workflow import WorkflowSpec

from .plan_apply.fakes import FakeClient, FakeDatasources, FakeSkills

TARGET = "proj"
UUID = "123e4567-e89b-12d3-a456-426614174000"


class _ListedSkills(FakeSkills):
    def __init__(self, items=(), **kw):
        super().__init__(**kw)
        self.items = list(items)

    def list(self, page=0, per_page=100):
        return SimpleNamespace(skills=self.items if page == 0 else [])


class _ListedDatasources(FakeDatasources):
    def __init__(self, items=(), **kw):
        super().__init__(**kw)
        self.items = list(items)

    def list(self, page=0, per_page=100, projects=None):
        return self.items if page == 0 else []


def _workflow(skills=(), datasources=()):
    agent = WorkflowAssistant(
        id="a1",
        name="agent",
        model="gpt",
        system_prompt="p",
        skill_ids=list(skills),
        datasource_ids=list(datasources),
    )
    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={"a1": agent},
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.WORKFLOW, name="wf"),
        spec=WorkflowSpec(workflow=definition),
    )


def _skill(name):
    spec = SkillSpec(
        name=name,
        description="A valid skill description",
        content="c" * 100,
        project=TARGET,
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.SKILL, name=name),
        spec=spec,
    )


def _writes(client):
    return [
        c
        for svc in (client.skills, client.workflows, client.datasources)
        for c in svc.calls
        if c.method.startswith(("create", "update"))
    ]


def test_unmatched_skill_name_fails_before_any_write():
    client = FakeClient(skills=_ListedSkills(), datasources=_ListedDatasources())
    with pytest.raises(UnresolvedReferenceError, match="ghost"):
        BulkCreator(client).create_all([_workflow(skills=["ghost"])], TARGET)
    assert _writes(client) == []


def test_ambiguous_datasource_name_fails_before_any_write():
    dup = [
        SimpleNamespace(id="d1", name="ds", project_name=TARGET),
        SimpleNamespace(id="d2", name="ds", project_name=TARGET),
    ]
    client = FakeClient(skills=_ListedSkills(), datasources=_ListedDatasources(dup))
    with pytest.raises(UnresolvedReferenceError, match="ambiguous"):
        BulkCreator(client).create_all([_workflow(datasources=["ds"])], TARGET)
    assert _writes(client) == []


def test_uuid_values_pass_preflight_and_reach_the_workflow():
    client = FakeClient(skills=_ListedSkills(), datasources=_ListedDatasources())
    report = BulkCreator(client).create_all(
        [_workflow(skills=[UUID], datasources=[UUID])], TARGET
    )
    assert report.failed is None
    assert UUID in client.workflows.calls_to("create_workflow")[0].args[0].yaml_config


def test_in_bundle_skill_is_created_first_and_its_id_is_used():
    client = FakeClient(skills=_ListedSkills(), datasources=_ListedDatasources())
    report = BulkCreator(client).create_all(
        [_workflow(skills=["skill-a"]), _skill("skill-a")], TARGET
    )
    assert report.failed is None
    assert [e.name for e in report.created] == ["skill-a", "wf"]
    yaml_config = client.workflows.calls_to("create_workflow")[0].args[0].yaml_config
    assert "skill-1" in yaml_config
