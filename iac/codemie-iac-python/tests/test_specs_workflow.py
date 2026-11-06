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
from pydantic import ValidationError

from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.assistant import MCPServerConfig
from codemie_sdk.models.workflow import WorkflowMode
from codemie_iac.specs.workflow import WorkflowSpec


def test_workflow_spec_wraps_definition_directly():
    workflow = WorkflowDefinition(name="wf", mode=WorkflowMode.SEQUENTIAL)
    spec = WorkflowSpec(workflow=workflow)
    assert spec.workflow.name == "wf"


def test_workflow_spec_round_trips_including_icon_url():
    workflow = WorkflowDefinition(
        name="wf", mode=WorkflowMode.SEQUENTIAL, icon_url="https://example.com/icon.png"
    )
    spec = WorkflowSpec(workflow=workflow)
    assert WorkflowSpec.model_validate(spec.model_dump()) == spec


def test_workflow_spec_rejects_unknown_field():
    workflow = WorkflowDefinition(name="wf", mode=WorkflowMode.SEQUENTIAL)
    with pytest.raises(ValidationError, match="(?i)extra"):
        WorkflowSpec(workflow=workflow, bogus_field="x")


def test_workflow_spec_from_entity():
    workflow = WorkflowDefinition(name="wf", mode=WorkflowMode.SEQUENTIAL)
    spec = WorkflowSpec.from_entity(workflow)
    assert spec == WorkflowSpec(workflow=workflow)


def _workflow_with_mcp_auth_token(auth_token: str) -> WorkflowDefinition:
    from codemie_sdk.builders.workflow.definition import WorkflowMCPServer

    return WorkflowDefinition(
        name="wf",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={
            "a": WorkflowAssistant(
                id="a",
                system_prompt="p",
                mcp_servers=[
                    WorkflowMCPServer(
                        name="m",
                        config=MCPServerConfig(command="npx", auth_token=auth_token),
                    )
                ],
            )
        },
    )


def test_workflow_spec_rejects_literal_auth_token_built_directly():
    """Regression: `WorkflowSpec.workflow`'s field type is the unmodified
    SDK `WorkflowDefinition`, so a `WorkflowSpec` built directly from model
    instances (bypassing `from_entity`) had no guard at all against a real
    secret in an inline MCP server's `auth_token` -- unlike `AssistantSpec`,
    whose equivalent field is typed `CredentialRef | None` and can't accept
    one in the first place."""
    workflow = _workflow_with_mcp_auth_token("a-real-secret")
    with pytest.raises(ValidationError, match="auth_token"):
        WorkflowSpec(workflow=workflow)


def test_workflow_spec_accepts_reference_shaped_auth_token_built_directly():
    workflow = _workflow_with_mcp_auth_token("env:MY_REF")
    spec = WorkflowSpec(workflow=workflow)
    assert (
        spec.workflow.assistants["a"].mcp_servers[0].config.auth_token == "env:MY_REF"
    )


def test_workflow_spec_accepts_a_full_oauth2_auth_config():
    from codemie_sdk.builders.workflow.definition import WorkflowMCPServer

    auth_config = {
        "token_url": "https://idp.example/token",
        "client_id": "cid",
        "token_delivery": {"method": "header", "name": "Authorization"},
    }
    workflow = WorkflowDefinition(
        name="wf",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={
            "a": WorkflowAssistant(
                id="a",
                system_prompt="p",
                mcp_servers=[
                    WorkflowMCPServer(
                        name="m",
                        config=MCPServerConfig(
                            url="https://m", auth_config=auth_config
                        ),
                    )
                ],
            )
        },
    )
    assert WorkflowSpec(workflow=workflow).workflow == workflow
    literal = {**auth_config, "client_secret": "s3cret-value"}
    workflow.assistants["a"].mcp_servers[0].config.auth_config = literal
    with pytest.raises(ValidationError, match="client_secret"):
        WorkflowSpec(workflow=workflow)
