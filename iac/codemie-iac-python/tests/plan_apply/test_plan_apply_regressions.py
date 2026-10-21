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

"""Regression tests for plan/apply behaviour, one section per behaviour."""

import copy
from types import SimpleNamespace

import pytest
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.assistant import Assistant, AssistantBase
from codemie_sdk.models.datasource import DataSource
from codemie_sdk.models.integration import IntegrationType
from codemie_sdk.models.workflow import WorkflowMode
from pydantic import TypeAdapter

from codemie_iac.credentials import CredentialRef
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import (
    BulkCreator,
    ResolveContext,
    build_resolved,
    check_references,
)
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import ApplyError, UnresolvedReferenceError
from codemie_iac.plan_apply.field_policy import policy_for
from codemie_iac.plan_apply.lookup import NameLookup
from codemie_iac.plan_apply.ordering import DependencyGraph
from codemie_iac.plan_apply.single_apply import (
    CannotCompare,
    Difference,
    SingleEntityPlanner,
    diff,
)
from codemie_iac.specs.assistant import (
    AssistantSpec,
    MCPServerConfigSpec,
    MCPServerDetailsSpec,
    PromptVariableSpec,
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
    FakeCategories,
    FakeClient,
    FakeDatasources,
    FakeIntegrations,
    FakeSkills,
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


# --- The target project is enforced for every kind ---
def _skill(project):
    spec = SkillSpec(name="s", description="d", content="c", project=project)
    return _doc(DocumentKind.SKILL, "s", spec)


_OTHER_PROJECT_DOCS = {
    "assistant": lambda: _assistant(project="A"),
    "skill": lambda: _skill("A"),
    "integration": lambda: _integration(project="A"),
    "datasource": lambda: _datasource(
        {"type": "knowledge_base_jira", "jql": "project = A"}, project="A"
    ),
}


@pytest.mark.parametrize("kind", list(_OTHER_PROJECT_DOCS))
def test_apply_rejects_document_whose_project_is_not_the_target(kind):
    client = FakeClient()
    with pytest.raises(ApplyError) as info:
        _planner(client).apply(_OTHER_PROJECT_DOCS[kind](), None, "B")
    assert info.value.error_type == "project_mismatch"
    for svc in ("assistants", "skills", "integrations", "datasources"):
        assert getattr(client, svc).calls == []


def test_update_rejects_document_project_differing_from_live_and_target():
    # Live assistant in B, document says A, target B: used to PUT project=A.
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(project="B")))
    with pytest.raises(ApplyError) as info:
        _planner(client).apply(_assistant(project="A"), "asst-1", "B")
    assert info.value.error_type == "project_mismatch"
    assert client.assistants.calls_to("update") == []


def test_plan_rejects_document_project_differing_from_target():
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(project="B")))
    with pytest.raises(ApplyError) as info:
        _planner(client).plan(_assistant(project="A"), "asst-1", "B")
    assert info.value.error_type == "project_mismatch"


def test_bulk_preflight_rejects_document_project_differing_from_target():
    client = FakeClient()
    with pytest.raises(ApplyError) as info:
        BulkCreator(client).create_all([_assistant(project="A")], "B")
    assert info.value.error_type == "project_mismatch"
    assert client.assistants.calls == []


# --- A masked value hides only what it masks ---
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
            "settings": settings,
            "tools": [{"name": n, "settings_config": False} for n in tools],
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


def test_masked_embedded_integration_secret_does_not_hide_toolkit_change():
    live = _live_toolkits(["t1"], _MASKED_SETTINGS)
    findings = _toolkit_findings(_toolkit_doc(["t1", "t2"]), live)
    assert [type(f) for f in findings] == [Difference]
    assert findings[0].field == "toolkits"


def test_masked_embedded_integration_secret_alone_is_no_finding():
    live = _live_toolkits(["t1"], _MASKED_SETTINGS)
    assert _toolkit_findings(_toolkit_doc(["t1"]), live) == []


def test_unmasked_embedded_integration_values_are_not_a_difference():
    settings = {
        **_MASKED_SETTINGS,
        "credential_values": [{"key": "url", "value": "https://jira.example"}],
    }
    live = _live_toolkits(["t1"], settings)
    assert _toolkit_findings(_toolkit_doc(["t1"]), live) == []


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


def test_one_masked_prompt_variable_does_not_hide_edit_of_another():
    doc_vars = [
        PromptVariableSpec(key="secret", default_value="real"),
        PromptVariableSpec(key="plain", default_value="new"),
    ]
    live_vars = [
        {"key": "secret", "description": None, "default_value": "*" * 8},
        {"key": "plain", "description": None, "default_value": "old"},
    ]
    findings = _prompt_findings(doc_vars, live_vars)
    assert [type(f) for f in findings] == [Difference]
    assert findings[0].field == "prompt_variables"


def test_masked_prompt_variable_with_other_variables_equal_is_cannot_compare():
    doc_vars = [
        PromptVariableSpec(key="secret", default_value="real"),
        PromptVariableSpec(key="plain", default_value="same"),
    ]
    live_vars = [
        {"key": "secret", "description": None, "default_value": "*" * 8},
        {"key": "plain", "description": None, "default_value": "same"},
    ]
    findings = _prompt_findings(doc_vars, live_vars)
    assert [type(f) for f in findings] == [CannotCompare]


# --- Schedule fields and writes the diff cannot see ---
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


def test_datasource_schedule_change_is_a_difference_and_is_written():
    client = FakeClient(datasources=RawDatasources(_JIRA_RAW))
    doc = _jira_doc(cron_expression="0 5 * * *", timezone="UTC")
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert [d.field for d in plan.differences] == ["cron_expression"]
    _planner(client).apply(doc, "ds-1", TARGET)
    assert len(client.datasources.calls_to("update")) == 1


def test_datasource_matching_schedule_gives_empty_plan():
    client = FakeClient(datasources=RawDatasources(_JIRA_RAW))
    doc = _jira_doc(cron_expression="0 1 * * *", timezone="UTC")
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


def test_timezone_alone_without_a_schedule_is_not_a_difference():
    """Without a cron the backend reports its default timezone; a document that
    does not author a schedule must not see that default as a difference."""
    raw = {k: v for k, v in _JIRA_RAW.items() if k != "cron_expression"}
    client = FakeClient(datasources=RawDatasources({**raw, "timezone": "Europe/Kyiv"}))
    plan = _planner(client).plan(_jira_doc(), "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


def test_authored_timezone_without_a_live_schedule_is_cannot_compare():
    raw = {k: v for k, v in _JIRA_RAW.items() if k != "cron_expression"}
    client = FakeClient(datasources=RawDatasources(raw))
    plan = _planner(client).plan(_jira_doc(timezone="UTC"), "ds-1", TARGET)
    assert [c.field for c in plan.cannot_compare] == ["timezone"]


def test_authored_schedule_not_observable_is_cannot_compare_not_skipped():
    live = FakeDatasources(
        get={
            "name": "ds",
            "project_name": TARGET,
            "description": "d",
            "type": "knowledge_base_jira",
            "jira": {"jql": "project = A"},
        }
    )
    client = FakeClient(datasources=live)
    doc = _jira_doc(cron_expression="0 5 * * *")
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert [c.field for c in plan.cannot_compare] == ["cron_expression"]


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


def test_apply_reports_uncomparable_fields_it_did_not_write():
    client = _masked_integration_client()
    doc = _integration(ref="env:JIRA_TOKEN")
    result = _planner(client).apply(doc, "int-1", TARGET)
    assert result.created is False
    assert result.uncomparable == ["credential_values"]
    assert client.integrations.calls_to("update") == []


def test_apply_force_writes_even_when_the_plan_is_empty():
    client = _masked_integration_client()
    doc = _integration(ref="env:JIRA_TOKEN")
    result = _planner(client).apply(doc, "int-1", TARGET, force=True)
    assert result.created is False
    (call,) = client.integrations.calls_to("update")
    assert call.args[1].credential_values[0].value == SECRET


# --- A bundle integration is resolved by alias, not label ---
class ListedIntegrations(FakeIntegrations):
    def __init__(self, items, **kw):
        super().__init__(**kw)
        self.items = items

    def list(self, setting_type=IntegrationType.USER, page=0, per_page=10, **kw):
        self._call("list", setting_type=setting_type, page=page)
        if setting_type != IntegrationType.PROJECT:
            return []
        return self.items[page * per_page : (page + 1) * per_page]


def _live_integration(alias, project=TARGET, id_=None):
    return SimpleNamespace(
        id=id_ or f"id-{alias}-{project}", alias=alias, project_name=project
    )


def test_bundle_integration_without_id_is_resolved_by_alias_not_label():
    bundle = [_integration(name="jira-prod", alias="jira")]
    items = [
        _live_integration("jira-prod", id_="decoy"),
        _live_integration("jira", id_="real"),
    ]
    client = FakeClient(integrations=ListedIntegrations(items))
    ref = NameLookup(bundle, TARGET, client).resolve(
        DocumentKind.INTEGRATION, "jira-prod"
    )
    assert ref.id == "real"


def test_live_integration_lookup_pages_and_filters_by_project():
    other = [
        _live_integration("jira", project="other", id_=f"o{i}") for i in range(100)
    ]
    items = other + [_live_integration("jira", id_="mine")]
    client = FakeClient(integrations=ListedIntegrations(items))
    ref = NameLookup([], TARGET, client).resolve(DocumentKind.INTEGRATION, "jira")
    assert ref.id == "mine"


# --- Existing assistants are found; invisible ones are reported as such ---
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


def test_existing_assistant_is_found_through_real_sdk_parsing():
    assistants = ParsingAssistants([_raw_assistant("existing-helper")])
    ctx = _ctx(client=FakeClient(assistants=assistants))
    ctx.lookup.require(DocumentKind.ASSISTANT, "existing-helper")
    assert ctx.ref(DocumentKind.ASSISTANT, "existing-helper").id == "id-existing-helper"


def test_assistant_in_another_project_is_still_not_found():
    assistants = ParsingAssistants([_raw_assistant("helper", project="other")])
    ctx = _ctx(client=FakeClient(assistants=assistants))
    with pytest.raises(UnresolvedReferenceError):
        ctx.lookup.require(DocumentKind.ASSISTANT, "helper")


def test_unresolved_assistant_message_mentions_visibility():
    """The live scan only sees assistants the calling user can see, so an
    unresolved assistant reference must say it may be invisible, not only absent."""
    ctx = _ctx(client=FakeClient(assistants=ParsingAssistants([])))
    with pytest.raises(UnresolvedReferenceError) as exc:
        ctx.lookup.require(DocumentKind.ASSISTANT, "helper")
    message = str(exc.value)
    assert "not visible to the current user" in message
    assert "'helper'" in message


def test_unresolved_category_message_is_unchanged():
    categories = FakeCategories()
    categories.responses["get_categories"] = []
    ctx = _ctx(client=FakeClient(categories=categories))
    with pytest.raises(UnresolvedReferenceError) as exc:
        ctx.lookup.require(DocumentKind.CATEGORY, "nope")
    assert "not visible" not in str(exc.value)


# --- Code and Git FAQ datasources compare cleanly ---
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


@pytest.mark.parametrize("index_type", ["code", "summary", "chunk-summary"])
def test_code_datasource_identical_to_document_gives_empty_plan(index_type):
    raw = {**_CODE_RAW, "index_type": index_type}
    client = FakeClient(datasources=RawDatasources(raw))
    doc = _datasource({**_CODE_SPEC, "index_type": index_type})
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


def test_code_datasource_real_change_is_still_reported():
    client = FakeClient(datasources=RawDatasources(_CODE_RAW))
    doc = _datasource({**_CODE_SPEC, "branch": "develop"})
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert [d.field for d in plan.differences] == ["branch"]


def test_git_faq_datasource_identical_to_document_gives_empty_plan():
    raw = {
        **_CODE_RAW,
        "index_type": "knowledge_base_git_faq",
        "files_filter": "docs/**",
    }
    client = FakeClient(datasources=RawDatasources(raw))
    doc = _datasource(
        {
            "type": "knowledge_base_git_faq",
            "link": "https://git/x.git",
            "branch": "main",
            "files_filter": "docs/**",
            "embedding_model": "emb",
        }
    )
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


# --- Reindex-aware datasource updates ---
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


def test_git_faq_metadata_only_update_omits_source_fields_and_full_reindex():
    client = FakeClient(
        datasources=RawDatasources({**_GIT_FAQ_RAW, "description": "old"})
    )
    _planner(client).apply(_datasource(_GIT_FAQ_SPEC), "ds-1", TARGET)
    sent = _sent_update(client)
    assert sent.description == "d"
    assert sent.link is None and sent.branch is None and sent.files_filter is None
    assert not sent.full_reindex


def test_git_faq_source_change_is_sent_whole_with_full_reindex():
    client = FakeClient(datasources=RawDatasources(_GIT_FAQ_RAW))
    doc = _datasource({**_GIT_FAQ_SPEC, "branch": "develop"})
    _planner(client).apply(doc, "ds-1", TARGET)
    sent = _sent_update(client)
    assert sent.full_reindex is True
    assert (sent.link, sent.branch) == ("https://git/x.git", "develop")


def test_code_metadata_only_update_skips_the_reindex():
    client = FakeClient(datasources=RawDatasources({**_CODE_RAW, "description": "old"}))
    _planner(client).apply(_datasource(_CODE_SPEC), "ds-1", TARGET)
    assert _sent_update(client).skip_reindex is True


def test_code_source_change_keeps_the_default_reindex():
    client = FakeClient(datasources=RawDatasources(_CODE_RAW))
    doc = _datasource({**_CODE_SPEC, "branch": "develop"})
    _planner(client).apply(doc, "ds-1", TARGET)
    assert not _sent_update(client).skip_reindex


def test_forced_update_writes_everything_and_reindexes():
    client = FakeClient(datasources=RawDatasources(_CODE_RAW))
    _planner(client).apply(_datasource(_CODE_SPEC), "ds-1", TARGET, force=True)
    assert not _sent_update(client).skip_reindex


# --- MCP credential refs are collected wherever they are revealed ---
def _mcp_assistant(config=None, **server):
    config = config or MCPServerConfigSpec(command="npx")
    return _assistant(
        mcp_servers=[
            MCPServerDetailsSpec(name="srv", enabled=True, config=config, **server)
        ]
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
    assert [r.root for r in EnvCredentialResolver.collect_refs(doc.spec)] == [name]


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


# --- plan() works without every secret set ---
def test_plan_with_unset_integration_secret_reports_cannot_compare():
    client = _masked_integration_client()
    doc = _integration(ref="env:MISSING_VAR")
    plan = _planner(client, {}).plan(doc, "int-1", TARGET)
    assert [c.field for c in plan.cannot_compare] == ["credential_values"]
    assert "unresolvable" in plan.cannot_compare[0].reason


def test_plan_with_unset_mcp_secret_reports_cannot_compare():
    doc = _mcp_assistant(MCPServerConfigSpec(command="npx", env={"T": "env:NOPE"}))
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(mcp_servers=[])))
    plan = _planner(client, {}).plan(doc, "asst-1", TARGET)
    assert plan.differences == []
    assert [c.field for c in plan.cannot_compare] == ["mcp_servers"]
    assert "unresolvable" in plan.cannot_compare[0].reason


def test_apply_still_requires_every_secret():
    client = _masked_integration_client()
    with pytest.raises(ApplyError):
        _planner(client, {}).apply(_integration(ref="env:NOPE"), "int-1", TARGET)
    assert client.integrations.calls_to("update") == []


# --- Name-only workflow assistant references are ordered and checked ---
def _workflow(assistant):
    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={"a1": assistant},
    )
    return _doc(DocumentKind.WORKFLOW, "wf", WorkflowSpec(workflow=definition))


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


# --- meta.name must equal the entity's own name ---
@pytest.mark.parametrize(
    "build",
    [
        lambda: _skill(TARGET),
        lambda: _datasource({"type": "knowledge_base_jira", "jql": "project = A"}),
    ],
)
def test_meta_name_differing_from_spec_name_is_rejected(build):
    doc = build()
    doc.meta.name = "other-name"
    with pytest.raises(ApplyError) as info:
        _planner(FakeClient()).apply(doc, None, TARGET)
    assert info.value.error_type == "name_mismatch"


def test_bulk_create_rejects_a_name_mismatch_before_any_write():
    doc = _skill(TARGET)
    doc.meta.name = "other-name"
    client = FakeClient()
    with pytest.raises(ApplyError) as info:
        BulkCreator(client).create_all([doc], TARGET)
    assert info.value.error_type == "name_mismatch"
    assert client.skills.calls == []


# --- every live finder checks the project client-side ---
def _stub_client(workflows=(), datasources=()):
    return SimpleNamespace(
        workflows=SimpleNamespace(
            list=lambda page=0, **kw: list(workflows) if page == 0 else []
        ),
        datasources=SimpleNamespace(
            list=lambda page=0, **kw: list(datasources) if page == 0 else []
        ),
    )


def test_live_workflow_and_datasource_lookups_ignore_other_projects():
    from codemie_iac.plan_apply.lookup import LIVE_FINDERS

    client = _stub_client(
        workflows=[
            SimpleNamespace(name="w", project="other"),
            SimpleNamespace(name="w", project=TARGET),
        ],
        datasources=[
            SimpleNamespace(name="d", project_name="other"),
            SimpleNamespace(name="d", project_name=TARGET),
        ],
    )
    assert len(LIVE_FINDERS[DocumentKind.WORKFLOW](client, TARGET, "w")) == 1
    assert len(LIVE_FINDERS[DocumentKind.DATASOURCE](client, TARGET, "d")) == 1


# --- Plans over real SDK response models (not namespaces or dicts) ---
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


def test_real_assistant_model_matching_the_document_gives_an_empty_plan():
    client = FakeClient(assistants=FakeAssistants(get=_real_assistant()))
    plan = _planner(client).plan(_assistant(), "asst-1", TARGET)
    assert plan.differences == []


def test_real_assistant_model_reports_exactly_the_edited_field():
    client = FakeClient(
        assistants=FakeAssistants(get=_real_assistant(system_prompt="old"))
    )
    plan = _planner(client).plan(_assistant(), "asst-1", TARGET)
    assert [d.field for d in plan.differences] == ["system_prompt"]


def test_real_skill_model_matching_the_document_gives_an_empty_plan():
    from codemie_sdk.models.skill import SkillDetailResponse

    live = SkillDetailResponse.model_validate(
        {
            "id": "sk-1",
            "name": "s",
            "description": "d",
            "content": "c",
            "project": TARGET,
            "visibility": "project",
            "createdDate": "2026-01-01T00:00:00",
            "created_by": {"user_id": "u", "username": "u", "name": "u"},
        }
    )
    client = FakeClient(skills=FakeSkills(get=live))
    plan = _planner(client).plan(_skill(TARGET), "sk-1", TARGET)
    assert plan.differences == []
