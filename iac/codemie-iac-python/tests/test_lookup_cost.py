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


"""Live lookups of skill values are narrowed server-side and made once per
distinct value, however many agents use it and however many phases read it."""

from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.workflow import WorkflowMode

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.specs.workflow import WorkflowSpec

from .plan_apply.fakes import FakeClient

TARGET = "proj"
UUID_A = "123e4567-e89b-12d3-a456-426614174000"
UUID_B = "123e4567-e89b-12d3-a456-426614174001"


def _workflow(agent_skills):
    assistants = {
        f"a{i}": WorkflowAssistant(
            id=f"a{i}",
            name=f"agent{i}",
            model="gpt",
            system_prompt="p",
            skill_ids=skills,
        )
        for i, skills in enumerate(agent_skills)
    }
    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants=assistants,
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.WORKFLOW, name="wf"),
        spec=WorkflowSpec(workflow=definition),
    )


def test_each_distinct_raw_value_is_listed_once_with_server_side_filters():
    client = FakeClient()
    workflow = _workflow([[UUID_A, UUID_B], [UUID_A], [UUID_A, UUID_B]])
    report = BulkCreator(client).create_all([workflow], TARGET)
    assert report.failed is None
    listings = client.skills.calls_to("list")
    assert sorted(c.kwargs["filters"]["search"] for c in listings) == [UUID_A, UUID_B]
    assert all(c.kwargs["filters"]["project"] == [TARGET] for c in listings)
