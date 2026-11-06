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

"""Regression tests for the 2026-10-05 standalone branch review findings
(CR-001..CR-007).

These IDs are scoped to that review run and are unrelated to the
differently-numbered findings of an earlier review round.
CR-006 (alias-less Integration credential collision) is covered in
test_specs_simple.py alongside the rest of IntegrationSpec.from_entity's
tests. CR-007's resolution -- retyping WorkflowMCPServer.config from a bare
dict to MCPServerConfig upstream (in codemie_sdk), then reusing
MCPServerConfigSpec.from_entity wholesale in WorkflowSpec.from_entity -- is
covered here.
"""

import pytest

from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
    WorkflowMCPServer,
)
from codemie_sdk.models.assistant import (
    AssistantCreateRequest,
    Integration,
    MCPServerConfig,
    MCPServerDetails,
    ToolDetails,
    ToolKitDetails,
)
from codemie_sdk.models.integration import CredentialTypes
from codemie_sdk.models.workflow import WorkflowMode

from codemie_iac.credentials import CredentialRef, reset_registry
from codemie_iac.envelope import Bundle, Document, DocumentKind, DocumentMeta
from codemie_iac.serializer import DocumentParseError, from_yaml, to_yaml
from codemie_iac.specs.assistant import AssistantSpec
from codemie_iac.specs.category import CategorySpec
from codemie_iac.specs.integration import CredentialRefEntry
from codemie_iac.specs.workflow import WorkflowSpec


# CR-001: the process-lifetime collision registry can be reset between
# logically unrelated batches.
def test_cr001_reset_registry_clears_prior_collisions():
    CredentialRef.from_entity("branch_review_a", "api_token")
    reset_registry()
    # Without the reset, a different identifier/key pair that happens to
    # sanitize to the same ref string would raise here.
    ref = CredentialRef.from_entity("branch-review-a", "api_token")
    assert ref.root == "env:BRANCH_REVIEW_A_API_TOKEN"


def test_cr001_reset_registry_does_not_affect_unrelated_refs():
    reset_registry()
    a = CredentialRef.from_entity("branch_review_b", "api_token")
    reset_registry()
    b = CredentialRef.from_entity("branch_review_b", "api_token")
    assert a == b


# CR-002: from_yaml must drop only a trailing empty sub-document, not an
# internal one.
def test_cr002_from_yaml_drops_trailing_empty_document():
    doc = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.CATEGORY, name="cat"),
        spec=CategorySpec(name="cat"),
    )
    text = to_yaml(Bundle([doc])) + "---\n"
    bundle = from_yaml(text)
    assert len(bundle.root) == 1


def test_cr002_from_yaml_raises_on_internal_empty_document():
    text = "---\nversion: v1\nmeta:\n  kind: category\n  name: cat\nspec:\n  name: cat\n---\n---\nversion: v1\nmeta:\n  kind: category\n  name: cat2\nspec:\n  name: cat2\n"
    with pytest.raises(DocumentParseError, match="empty document"):
        from_yaml(text)


# CR-003: an alias-less Integration reference raises instead of silently
# narrowing to None, at all four narrowing sites.
def _alias_less_integration() -> Integration:
    return Integration(
        project_name="my-project",
        alias=None,
        credential_type=CredentialTypes.JIRA,
        credential_values=[],
    )


def test_cr003_tool_details_raises_on_alias_less_settings():
    request = AssistantCreateRequest(
        name="a",
        description="d",
        system_prompt="s",
        project="p",
        llm_model_type="gpt",
        toolkits=[
            ToolKitDetails(
                toolkit="tk",
                tools=[ToolDetails(name="t", settings=_alias_less_integration())],
            )
        ],
    )
    with pytest.raises(ValueError, match="no alias"):
        AssistantSpec.from_entity(request)


def test_cr003_toolkit_details_raises_on_alias_less_settings():
    request = AssistantCreateRequest(
        name="a",
        description="d",
        system_prompt="s",
        project="p",
        llm_model_type="gpt",
        toolkits=[
            ToolKitDetails(toolkit="tk", tools=[], settings=_alias_less_integration())
        ],
    )
    with pytest.raises(ValueError, match="no alias"):
        AssistantSpec.from_entity(request)


def test_cr003_mcp_server_details_raises_on_alias_less_settings():
    request = AssistantCreateRequest(
        name="a",
        description="d",
        system_prompt="s",
        project="p",
        llm_model_type="gpt",
        mcp_servers=[
            MCPServerDetails(
                name="m",
                description=None,
                enabled=True,
                settings=_alias_less_integration(),
            )
        ],
    )
    with pytest.raises(ValueError, match="no alias"):
        AssistantSpec.from_entity(request)


def test_cr003_mcp_server_details_raises_on_alias_less_mcp_connect_auth_token():
    request = AssistantCreateRequest(
        name="a",
        description="d",
        system_prompt="s",
        project="p",
        llm_model_type="gpt",
        mcp_servers=[
            MCPServerDetails(
                name="m",
                description=None,
                enabled=True,
                mcp_connect_auth_token=_alias_less_integration(),
            )
        ],
    )
    with pytest.raises(ValueError, match="no alias"):
        AssistantSpec.from_entity(request)


# CR-004: a non-string MCP env value coerces to str instead of crashing with
# a raw ValidationError. (`headers` is strictly dict[str, str] in the SDK
# itself, so only `env` -- typed dict[str, Any] -- can carry one.)
def test_cr004_non_string_env_values_coerce_to_str():
    request = AssistantCreateRequest(
        name="a",
        description="d",
        system_prompt="s",
        project="p",
        llm_model_type="gpt",
        mcp_servers=[
            MCPServerDetails(
                name="m",
                description=None,
                enabled=True,
                config=MCPServerConfig(
                    env={"DEBUG": True, "RETRIES": 3, "UNSET": None}
                ),
            )
        ],
    )
    spec = AssistantSpec.from_entity(request)
    config = spec.mcp_servers[0].config
    assert config.env == {"DEBUG": "True", "RETRIES": "3", "UNSET": ""}


# CR-005: the MCP auth_token CredentialRef is scoped by both assistant name
# and server name, so same-named servers in different assistants no longer
# collide.
def test_cr005_same_server_name_in_different_assistants_does_not_collide():
    def build(assistant_name: str) -> AssistantCreateRequest:
        return AssistantCreateRequest(
            name=assistant_name,
            description="d",
            system_prompt="s",
            project="p",
            llm_model_type="gpt",
            mcp_servers=[
                MCPServerDetails(
                    name="shared-mcp-name",
                    description=None,
                    enabled=True,
                    config=MCPServerConfig(auth_token="a-real-secret"),
                )
            ],
        )

    spec_one = AssistantSpec.from_entity(build("assistant-one"))
    spec_two = AssistantSpec.from_entity(build("assistant-two"))

    ref_one = spec_one.mcp_servers[0].config.auth_token
    ref_two = spec_two.mcp_servers[0].config.auth_token
    assert ref_one != ref_two
    assert ref_one == CredentialRef.from_entity(
        "assistant-one_shared-mcp-name", "auth_token"
    )
    assert ref_two == CredentialRef.from_entity(
        "assistant-two_shared-mcp-name", "auth_token"
    )


# CR-007: an inline MCP server's auth_token (and, since WorkflowMCPServer.config
# is now typed MCPServerConfig rather than a bare dict, env/headers too) is
# narrowed to a CredentialRef (via a CredentialRefEntry, mirroring
# IntegrationSpec.credential_values) instead of serializing the real secret
# in plaintext.
def _workflow_with_mcp_auth_token(secret: str = "a-real-secret") -> WorkflowDefinition:
    return WorkflowDefinition(
        name="wf",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={
            "a1": WorkflowAssistant(
                name="inline-assistant",
                mcp_servers=[
                    WorkflowMCPServer(
                        name="jira-mcp",
                        config={"command": "npx", "auth_token": secret},
                    )
                ],
            )
        },
    )


def test_cr007_from_entity_narrows_mcp_auth_token_in_config():
    spec = WorkflowSpec.from_entity(_workflow_with_mcp_auth_token())

    server = spec.workflow.assistants["a1"].mcp_servers[0]
    assert server.config.command == "npx"
    assert server.config.auth_token == "env:WF_A1_JIRA_MCP_AUTH_TOKEN"
    assert spec.credential_values == [
        CredentialRefEntry(
            key="wf_a1_jira-mcp",
            ref=CredentialRef.from_entity("wf_a1_jira-mcp", "auth_token"),
        )
    ]


def test_cr007_from_entity_never_embeds_the_real_secret():
    spec = WorkflowSpec.from_entity(_workflow_with_mcp_auth_token("super-secret-value"))

    dumped = spec.model_dump_json()
    assert "super-secret-value" not in dumped


def test_cr007_from_entity_does_not_mutate_the_input_definition():
    workflow = _workflow_with_mcp_auth_token()
    WorkflowSpec.from_entity(workflow)
    assert workflow.assistants["a1"].mcp_servers[0].config.auth_token == "a-real-secret"


def test_cr007_from_entity_leaves_configs_without_auth_token_untouched():
    workflow = WorkflowDefinition(
        name="wf2",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={
            "a1": WorkflowAssistant(
                name="inline-assistant",
                mcp_servers=[
                    WorkflowMCPServer(name="no-secret-mcp", config={"command": "npx"})
                ],
            )
        },
    )
    spec = WorkflowSpec.from_entity(workflow)
    assert spec.credential_values == []
    assert spec.workflow.assistants["a1"].mcp_servers[0].config == MCPServerConfig(
        command="npx"
    )


def test_cr007_from_entity_narrows_env_and_headers_too():
    """Closing the residual gap the dict-scanning version of this fix left
    open: now that config has a real schema, env/headers already shaped
    like a reference narrow the same way MCPServerConfigSpec does for
    AssistantSpec, and a non-string env value coerces instead of crashing.
    """
    workflow = WorkflowDefinition(
        name="wf3",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={
            "a1": WorkflowAssistant(
                name="inline-assistant",
                mcp_servers=[
                    WorkflowMCPServer(
                        name="svc",
                        config={
                            "command": "npx",
                            "headers": {"Authorization": "env:PRESET_REF"},
                            "env": {"RETRIES": 3},
                        },
                    )
                ],
            )
        },
    )
    spec = WorkflowSpec.from_entity(workflow)
    config = spec.workflow.assistants["a1"].mcp_servers[0].config
    assert config.headers == {"Authorization": "env:PRESET_REF"}
    assert config.env == {"RETRIES": "3"}
