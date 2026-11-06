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


"""Credential references are collected wherever they are revealed."""

import pytest
from codemie_iac.envelope import DocumentKind
from codemie_iac.plan_apply.bulk_create import (
    BulkCreator,
    build_resolved,
)
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.ordering import DependencyGraph
from codemie_iac.specs.assistant import (
    MCPServerConfigSpec,
)
from .fakes import (
    FakeAssistants,
    FakeClient,
    FakeWorkflows,
)

from .helpers import (
    SECRET,
    TARGET,
    _ctx,
    _integration,
    _live_assistant,
    _mcp_assistant,
    _planner,
    _workflow_with_tool,
)


@pytest.mark.parametrize(
    "doc, name",
    [
        (
            _mcp_assistant(MCPServerConfigSpec(command="env:CMD_SECRET")),
            "env:CMD_SECRET",
        ),
        (
            _mcp_assistant(MCPServerConfigSpec(type="env:TYPE_SECRET")),
            "env:TYPE_SECRET",
        ),
        (_mcp_assistant(MCPServerConfigSpec(tools=["env:T_SECRET"])), "env:T_SECRET"),
        (_mcp_assistant(mcp_connect_url="env:URL_SECRET"), "env:URL_SECRET"),
        (_mcp_assistant(arguments="env:ARGS_SECRET"), "env:ARGS_SECRET"),
    ],
)
def test_every_revealed_mcp_ref_is_collected(doc, name):
    assert [r.root for r in EnvCredentialResolver().collect_refs(doc.spec)] == [name]


def test_unset_mcp_command_ref_fails_preflight_before_any_write():
    doc = _mcp_assistant(MCPServerConfigSpec(command="env:CMD_SECRET"))
    client = FakeClient()
    with pytest.raises(ApplyError) as info:
        BulkCreator(client, EnvCredentialResolver({})).create_all([doc], TARGET)
    assert info.value.error_type == "unresolvable_credential"
    assert client.assistants.calls == []


def test_mcp_connect_url_and_arguments_refs_are_revealed_in_body():
    doc = _mcp_assistant(mcp_connect_url="env:URL_SECRET", arguments="env:ARGS_SECRET")
    ctx = _ctx(env={"URL_SECRET": "https://u", "ARGS_SECRET": "a1"})
    (server,) = build_resolved(doc, ctx)["mcp_servers"]
    assert server["mcp_connect_url"] == "https://u"
    assert server["arguments"] == "a1"


def test_command_only_ref_difference_is_redacted():
    doc = _mcp_assistant(MCPServerConfigSpec(command="env:CMD_SECRET"))
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(mcp_servers=[])))
    plan = _planner(client, {"CMD_SECRET": SECRET}).plan(doc, "asst-1", TARGET)
    assert [d.field for d in plan.differences] == ["mcp_servers"]
    assert SECRET not in repr(plan) and SECRET not in plan.model_dump_json()


def test_workflow_tool_mcp_server_refs_are_collected():
    refs = EnvCredentialResolver().collect_refs(_workflow_with_tool().spec)
    assert [r.root for r in refs] == ["env:API_TOKEN"]


def test_workflow_tool_mcp_server_ref_is_revealed_in_the_yaml_config():
    client = FakeClient(workflows=FakeWorkflows())
    planner = _planner(client, env={"API_TOKEN": SECRET})
    planner.apply(_workflow_with_tool(tool_alias=None), None, TARGET)
    sent = client.workflows.calls_to("create_workflow")[0].args[0].yaml_config
    assert SECRET in sent and "env:API_TOKEN" not in sent


def test_unset_workflow_tool_credential_fails_before_any_write():
    client = FakeClient(workflows=FakeWorkflows())
    with pytest.raises(ApplyError):
        _planner(client, env={}).apply(
            _workflow_with_tool(tool_alias=None), None, TARGET
        )
    assert client.workflows.calls == []


def test_workflow_tool_integration_aliases_are_ordering_edges():
    wf = _workflow_with_tool(integration_alias="mcp-int")
    bundle = [wf, _integration("jira"), _integration("mcp-int", alias="mcp-int")]
    edges = DependencyGraph(bundle).edges(wf)
    assert (DocumentKind.INTEGRATION, "jira") in edges
    assert (DocumentKind.INTEGRATION, "mcp-int") in edges


def test_assistant_mcp_integration_alias_is_an_ordering_edge():
    doc = _mcp_assistant(integration_alias="mcp-int")
    bundle = [doc, _integration("mcp-int", alias="mcp-int")]
    assert (DocumentKind.INTEGRATION, "mcp-int") in DependencyGraph(bundle).edges(doc)
