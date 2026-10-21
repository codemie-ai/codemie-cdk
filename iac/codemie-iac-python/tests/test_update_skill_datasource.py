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

import yaml
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.workflow import WorkflowMode

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import ResolveContext, build_resolved
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.field_policy import policy_for
from codemie_iac.plan_apply.kinds import adapter_for
from codemie_iac.plan_apply.lookup import NameLookup
from codemie_iac.plan_apply.single_apply import Difference, diff
from codemie_iac.specs.assistant import AssistantSpec
from codemie_iac.specs.workflow import WorkflowSpec

from .plan_apply.fakes import FakeClient, FakeWorkflows

TARGET = "proj"


class _Skills:
    def list(self, page=0, per_page=100):
        items = [
            SimpleNamespace(id=f"id-{n}", name=n, project=TARGET) for n in ("sa", "sb")
        ]
        return SimpleNamespace(skills=items if page == 0 else [])


class _Datasources:
    def list(self, page=0, per_page=100, projects=None):
        return (
            [SimpleNamespace(id="id-ds", name="ds", project_name=TARGET)]
            if page == 0
            else []
        )


def _ctx():
    client = SimpleNamespace(skills=_Skills(), datasources=_Datasources())
    return ResolveContext(NameLookup([], TARGET, client), EnvCredentialResolver({}), {})


def _workflow_doc():
    agent = WorkflowAssistant(
        id="a1",
        name="agent",
        model="gpt",
        system_prompt="p",
        skill_ids=["sa", "sb"],
        datasource_ids=["ds"],
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


def _assistant_doc(skills):
    spec = AssistantSpec(
        name="asst",
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
        skill_ids=skills,
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.ASSISTANT, name="asst"),
        spec=spec,
    )


def _live_assistant(skill_ids):
    return {
        "name": "asst",
        "description": "d",
        "system_prompt": "p",
        "project": TARGET,
        "llm_model_type": "gpt",
        "skill_ids": skill_ids,
    }


def _findings(doc, live):
    return diff(doc, live, policy_for(doc), EnvCredentialResolver({}), _ctx())


def test_workflow_with_names_has_no_diff_against_live_ids():
    doc = _workflow_doc()
    live_yaml = build_resolved(doc, _ctx())["yaml_config"]
    assert yaml.safe_load(live_yaml)["assistants"][0]["skill_ids"] == [
        "id-sa",
        "id-sb",
    ]
    live = {"name": "wf", "description": "d", "yaml_config": live_yaml}
    assert not [f for f in _findings(doc, live) if f.field == "yaml_config"]


def test_workflow_update_payload_keeps_agent_skills_and_datasources():
    doc = _workflow_doc()
    client = FakeClient(workflows=FakeWorkflows())
    adapter_for(doc).update(client, doc, "wf-1", build_resolved(doc, _ctx()))
    request = client.workflows.calls_to("update")[0].args[1]
    agent = yaml.safe_load(request.yaml_config)["assistants"][0]
    assert agent["skill_ids"] == ["id-sa", "id-sb"]
    assert agent["datasource_ids"] == ["id-ds"]


def test_assistant_skills_in_a_different_order_are_not_a_difference():
    findings = _findings(
        _assistant_doc(["sb", "sa"]), _live_assistant(["id-sa", "id-sb"])
    )
    assert findings == []


def test_assistant_with_a_changed_skill_is_a_difference():
    findings = _findings(_assistant_doc(["sa"]), _live_assistant(["id-sb"]))
    assert [f.field for f in findings if isinstance(f, Difference)] == ["skill_ids"]
