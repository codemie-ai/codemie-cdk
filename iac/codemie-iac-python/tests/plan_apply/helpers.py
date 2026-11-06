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


"""Shared builders and fakes for the plan/apply behaviour tests."""

import copy
from types import SimpleNamespace
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
    WorkflowMCPServer,
    WorkflowTool,
)
from codemie_sdk.models.assistant import Assistant, AssistantBase
from codemie_sdk.models.datasource import DataSource
from codemie_sdk.models.integration import IntegrationType
from codemie_sdk.models.workflow import WorkflowMode
from pydantic import TypeAdapter
from codemie_iac.credentials import CredentialRef
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import (
    ResolveContext,
    build_resolved,
)
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.field_policy import policy_for
from codemie_iac.plan_apply.lookup import NameLookup
from codemie_iac.plan_apply.single_apply import (
    SingleEntityPlanner,
    diff,
)
from codemie_iac.specs.assistant import (
    AssistantSpec,
    MCPServerConfigSpec,
    MCPServerDetailsSpec,
    ToolDetailsSpec,
    ToolKitDetailsSpec,
)
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.integration import CredentialRefEntry, IntegrationSpec
from codemie_iac.specs.skill import SkillSpec
from codemie_iac.specs.workflow import WorkflowSpec
from .fakes import (
    Call,
    FakeAssistants,
    FakeClient,
    FakeDatasources,
    FakeIntegrations,
)

TARGET = "proj"


SECRET = "s3cr3t-token-value"


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant(name="asst", project=TARGET, **extra):
    spec = AssistantSpec(
        name=name,
        description="d",
        system_prompt="p",
        project=project,
        llm_model_type="gpt",
        shared=True,
        **extra,
    )
    return _doc(DocumentKind.ASSISTANT, name, spec)


def _integration(name="jira", alias="jira", ref=None, project=TARGET):
    values = [CredentialRefEntry(key="token", ref=CredentialRef(ref))] if ref else []
    spec = IntegrationSpec(
        project_name=project,
        alias=alias,
        credential_type="Jira",
        credential_values=values,
        setting_type=IntegrationType.PROJECT,
    )
    return _doc(DocumentKind.INTEGRATION, name, spec)


def _datasource(raw_spec, name="ds", project=TARGET):
    base = {"name": name, "project_name": project, "description": "d"}
    spec = TypeAdapter(DatasourceSpec).validate_python({**base, **raw_spec})
    return _doc(DocumentKind.DATASOURCE, name, spec)


def _live_assistant(**over):
    live = {
        "id": "asst-1",
        "name": "asst",
        "description": "d",
        "system_prompt": "p",
        "project": TARGET,
        "llm_model_type": "gpt",
        "shared": True,
    }
    live.update(over)
    return SimpleNamespace(**live)


def _planner(client, env=None):
    return SingleEntityPlanner(
        client, credentials=EnvCredentialResolver(env or {"JIRA_TOKEN": SECRET})
    )


def _ctx(bundle=(), created=None, env=None, client=None):
    resolver = EnvCredentialResolver(env or {})
    return ResolveContext(
        NameLookup(list(bundle), TARGET, client), resolver, dict(created or {})
    )


def _skill(project):
    spec = SkillSpec(
        name="skill-s",
        description="A valid skill description",
        content="c" * 100,
        project=project,
    )
    return _doc(DocumentKind.SKILL, "skill-s", spec)


_OTHER_PROJECT_DOCS = {
    "assistant": lambda: _assistant(project="A"),
    "skill": lambda: _skill("A"),
    "integration": lambda: _integration(project="A"),
    "datasource": lambda: _datasource(
        {"type": "knowledge_base_jira", "jql": "project = A"}, project="A"
    ),
}


_MASKED_SETTINGS = {
    "id": "int-1",
    "project_name": TARGET,
    "alias": "jira",
    "credential_type": "Jira",
    "credential_values": [{"key": "token", "value": "*" * 10}],
    "setting_type": "project",
}


def _toolkit_doc(tools):
    toolkit = ToolKitDetailsSpec(
        toolkit="Jira",
        tools=[ToolDetailsSpec(name=n) for n in tools],
        settings="jira",
    )
    return _assistant(toolkits=[toolkit])


def _live_toolkits(tools, settings):
    return [
        {
            "toolkit": "Jira",
            "label": "",
            "settings_config": False,
            "is_external": False,
            "auto_credentials_lookup": True,
            "settings": settings,
            "tools": [
                {"name": n, "settings_config": False, "auto_credentials_lookup": True}
                for n in tools
            ],
        }
    ]


def _toolkit_findings(doc, live_toolkits):
    ctx = _ctx([_integration()], {(DocumentKind.INTEGRATION, "jira"): "int-1"})
    live = {
        "name": "asst",
        "description": "d",
        "system_prompt": "p",
        "project": TARGET,
        "llm_model_type": "gpt",
        "shared": True,
        "toolkits": live_toolkits,
    }
    return diff(doc, live, policy_for(doc), ctx.credentials, ctx)


def _prompt_findings(doc_vars, live_vars):
    doc = _assistant(prompt_variables=doc_vars)
    live = {
        "name": "asst",
        "description": "d",
        "system_prompt": "p",
        "project": TARGET,
        "llm_model_type": "gpt",
        "shared": True,
        "prompt_variables": live_vars,
    }
    return diff(doc, live, policy_for(doc), EnvCredentialResolver({}))


_JIRA_RAW = {
    "id": "ds-1",
    "project_name": TARGET,
    "repo_name": "ds",
    "description": "d",
    "index_type": "knowledge_base_jira",
    "date": "2026-01-01T00:00:00",
    "created_by": {"user_id": "u", "username": "u", "name": "u"},
    "update_date": "2026-01-01T00:00:00",
    "user_abilities": [],
    "completed": True,
    "project_space_visible": False,
    "jira": {"jql": "project = A"},
    "cron_expression": "0 1 * * *",
    "timezone": "UTC",
}


class RawDatasources(FakeDatasources):
    """Datasource service whose ``get`` parses a backend-shaped response with
    the real SDK ``DataSource`` model, as the live platform response would be."""

    def __init__(self, raw, **kw):
        super().__init__(**kw)
        self.raw = raw

    def get(self, datasource_id):
        self.calls.append(Call("get", (datasource_id,), {}))
        return DataSource.model_validate(copy.deepcopy(self.raw))


def _jira_doc(**extra):
    return _datasource({"type": "knowledge_base_jira", "jql": "project = A", **extra})


def _masked_integration_client():
    live = {
        "id": "int-1",
        "project_name": TARGET,
        "alias": "jira",
        "default": False,
        "is_global": False,
        "credential_type": "Jira",
        "setting_type": "project",
        "credential_values": [{"key": "token", "value": "*" * 10}],
    }
    return FakeClient(integrations=FakeIntegrations(get=live))


class ListedIntegrations(FakeIntegrations):
    def __init__(self, items, **kw):
        super().__init__(**kw)
        self.items = items

    def list_available(self, scope="visible_to_user"):
        self._call("list_available")
        return list(self.items)


def _live_integration(alias, project=TARGET, id_=None):
    return SimpleNamespace(
        id=id_ or f"id-{alias}-{project}", alias=alias, project_name=project
    )


class ParsingAssistants(FakeAssistants):
    """``list`` parses backend-shaped items with the real SDK models."""

    def __init__(self, raw_items, **kw):
        super().__init__(**kw)
        self.raw_items = raw_items

    def list(self, minimal_response=True, page=0, per_page=12, filters=None, **kw):
        self._call("list", minimal_response=minimal_response, page=page)
        model = AssistantBase if minimal_response else Assistant
        chunk = self.raw_items[page * per_page : (page + 1) * per_page]
        return [model.model_validate(i) for i in chunk]


def _raw_assistant(name, project=TARGET):
    return {
        "id": f"id-{name}",
        "name": name,
        "description": "d",
        "system_prompt": "p",
        "project": project,
    }


_CODE_RAW = {
    **_JIRA_RAW,
    "index_type": "code",
    "link": "https://git/x.git",
    "branch": "main",
    "files_filter": "src/**",
    "embeddings_model": "emb",
    "summarization_model": "sm",
    "prompt": "summarise",
    "docs_generation": True,
}


_CODE_RAW.pop("jira")


_CODE_RAW.pop("cron_expression")


_CODE_RAW.pop("timezone")


_CODE_SPEC = {
    "type": "code",
    "link": "https://git/x.git",
    "branch": "main",
    "index_type": "code",
    "files_filter": "src/**",
    "embeddings_model": "emb",
    "summarization_model": "sm",
    "prompt": "summarise",
    "docs_generation": True,
}


_GIT_FAQ_RAW = {
    **_CODE_RAW,
    "index_type": "knowledge_base_git_faq",
    "files_filter": "docs/**",
}


_GIT_FAQ_SPEC = {
    "type": "knowledge_base_git_faq",
    "link": "https://git/x.git",
    "branch": "main",
    "files_filter": "docs/**",
    "embedding_model": "emb",
}


def _sent_update(client):
    return client.datasources.calls_to("update")[0].args[1]


def _mcp_assistant(config=None, **server):
    config = config or MCPServerConfigSpec(command="npx")
    return _assistant(
        mcp_servers=[
            MCPServerDetailsSpec(name="srv", enabled=True, config=config, **server)
        ]
    )


def _workflow(assistant):
    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={"a1": assistant},
    )
    return _doc(DocumentKind.WORKFLOW, "wf", WorkflowSpec(workflow=definition))


def _real_assistant(**over):
    from codemie_sdk.models.assistant import Assistant

    raw = {
        "id": "asst-1",
        "name": "asst",
        "description": "d",
        "system_prompt": "p",
        "project": TARGET,
        "llm_model_type": "gpt",
        "shared": True,
        "created_by": {"user_id": "u", "username": "u", "name": "u"},
        "toolkits": [],
        "context": [],
    }
    return Assistant.model_validate({**raw, **over})


def _declined():
    missing = SimpleNamespace(credential_type="Jira")
    return SimpleNamespace(
        message="not saved",
        assistant_id=None,
        validation=SimpleNamespace(
            has_missing_integrations=True, missing_by_credential_type=[missing]
        ),
    )


def _workflow_with_tool(tool_alias="jira", **server):
    from codemie_sdk.models.assistant import MCPServerConfig

    tool = WorkflowTool(
        id="t1",
        tool="x",
        integration_alias=tool_alias,
        mcp_server=WorkflowMCPServer(
            name="srv",
            enabled=True,
            config=MCPServerConfig(command="npx", env={"TOKEN": "env:API_TOKEN"}),
            **server,
        ),
    )
    definition = WorkflowDefinition(
        name="wf", description="d", mode=WorkflowMode.SEQUENTIAL, tools=[tool]
    )
    return _doc(DocumentKind.WORKFLOW, "wf", WorkflowSpec(workflow=definition))


def _inline_workflow(**definition):
    helper = WorkflowAssistant(
        id="a1", name="helper", system_prompt="p", model="gpt-4o"
    )
    base = {"name": "wf", "description": "d", "mode": WorkflowMode.SEQUENTIAL}
    wf = WorkflowDefinition(**{**base, "assistants": {"a1": helper}, **definition})
    return _doc(DocumentKind.WORKFLOW, "wf", WorkflowSpec(workflow=wf))


def _live_workflow(doc, **over):
    from codemie_sdk.models.workflow import Workflow

    resolved = build_resolved(doc, _ctx())
    raw = {
        "id": "wf-1",
        "project": TARGET,
        "name": "wf",
        "description": "d",
        "mode": "Sequential",
        "yaml_config": resolved["yaml_config"],
    }
    return Workflow.model_validate({**raw, **over})
