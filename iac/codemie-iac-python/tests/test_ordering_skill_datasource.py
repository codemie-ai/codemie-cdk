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

from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.workflow import WorkflowMode
from pydantic import TypeAdapter

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.ordering import DependencyGraph
from codemie_iac.specs.assistant import AssistantSpec
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.skill import SkillSpec
from codemie_iac.specs.workflow import WorkflowSpec


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _skill(name):
    spec = SkillSpec(
        name=name,
        description="A valid skill description",
        content="c" * 100,
        project="proj",
    )
    return _doc(DocumentKind.SKILL, name, spec)


def _datasource(name):
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "knowledge_base_file",
            "name": name,
            "project_name": "proj",
            "description": "d",
        }
    )
    return _doc(DocumentKind.DATASOURCE, name, spec)


def _workflow(skills, datasources):
    agent = WorkflowAssistant(
        id="a1",
        name="agent",
        model="gpt",
        system_prompt="p",
        skill_ids=skills,
        datasource_ids=datasources,
    )
    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={"a1": agent},
    )
    return _doc(DocumentKind.WORKFLOW, "wf", WorkflowSpec(workflow=definition))


def _assistant(skills):
    spec = AssistantSpec(
        name="asst",
        description="d",
        system_prompt="p",
        project="proj",
        llm_model_type="gpt",
        skill_ids=skills,
    )
    return _doc(DocumentKind.ASSISTANT, "asst", spec)


def _names(docs):
    return [d.meta.name for d in docs]


def test_workflow_comes_after_its_skills_and_datasources():
    docs = [_workflow(["skill-a"], ["ds"]), _datasource("ds"), _skill("skill-a")]
    assert _names(DependencyGraph(docs).order()) == ["skill-a", "ds", "wf"]


def test_assistant_comes_after_its_skills():
    docs = [_assistant(["skill-a"]), _skill("skill-a")]
    assert _names(DependencyGraph(docs).order()) == ["skill-a", "asst"]


def test_names_outside_the_bundle_add_no_edge():
    graph = DependencyGraph([_workflow(["gone"], ["gone-ds"])])
    assert graph.edges(graph.order()[0]) == []
