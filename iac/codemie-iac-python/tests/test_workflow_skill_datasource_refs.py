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
import yaml
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.workflow import WorkflowMode

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import ResolveContext, build_resolved
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import UnresolvedReferenceError
from codemie_iac.plan_apply.lookup import NameLookup
from codemie_iac.specs.workflow import WorkflowSpec

TARGET = "proj"
UUID_A = "123e4567-e89b-12d3-a456-426614174000"
UUID_B = "223e4567-e89b-12d3-a456-426614174001"


class _Skills:
    def list(self, page=0, per_page=100):
        items = [SimpleNamespace(id="sk-id", name="my-skill", project=TARGET)]
        return SimpleNamespace(skills=items if page == 0 else [])


class _Datasources:
    def list(self, page=0, per_page=100, projects=None):
        return (
            [SimpleNamespace(id="ds-id", name="my-ds", project_name=TARGET)]
            if page == 0
            else []
        )


def _workflow(skill_ids, datasource_ids):
    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={
            "a1": WorkflowAssistant(
                id="a1",
                name="agent",
                model="gpt",
                system_prompt="p",
                skill_ids=skill_ids,
                datasource_ids=datasource_ids,
            )
        },
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.WORKFLOW, name="wf"),
        spec=WorkflowSpec(workflow=definition),
    )


def _agent(document):
    client = SimpleNamespace(skills=_Skills(), datasources=_Datasources())
    ctx = ResolveContext(NameLookup([], TARGET, client), EnvCredentialResolver({}), {})
    rendered = build_resolved(document, ctx)["yaml_config"]
    return yaml.safe_load(rendered)["assistants"][0]


def test_agent_skill_and_datasource_names_become_ids():
    agent = _agent(_workflow(["my-skill"], ["my-ds"]))
    assert agent["skill_ids"] == ["sk-id"]
    assert agent["datasource_ids"] == ["ds-id"]


def test_raw_uuids_render_unchanged():
    agent = _agent(_workflow([UUID_A], [UUID_B]))
    assert agent["skill_ids"] == [UUID_A]
    assert agent["datasource_ids"] == [UUID_B]


def test_unknown_name_fails_naming_reference_and_workflow():
    with pytest.raises(UnresolvedReferenceError, match="ghost.*workflow/wf"):
        _agent(_workflow(["ghost"], []))
