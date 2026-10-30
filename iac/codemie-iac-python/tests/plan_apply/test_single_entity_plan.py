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
from codemie_sdk.models.datasource import DataSource
from codemie_sdk.models.integration import IntegrationType
from pydantic import TypeAdapter

from codemie_iac.credentials import CredentialRef
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.field_policy import FIELD_POLICIES, policy_for
from codemie_iac.plan_apply.kinds import DATASOURCE_ADAPTERS
from codemie_iac.plan_apply.single_apply import (
    CannotCompare,
    Difference,
    Plan,
    SingleEntityPlanner,
    _flatten_live,
    diff,
)
from .fakes import FakeAssistants, FakeClient, FakeDatasources
from codemie_iac.specs.assistant import AssistantSpec, PromptVariableSpec
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.integration import CredentialRefEntry, IntegrationSpec

SECRET = "s3cr3t-token-value"


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant(**extra):
    spec = AssistantSpec(
        name="asst",
        description="d",
        system_prompt="p",
        project="proj",
        llm_model_type="gpt",
        shared=True,
        **extra,
    )
    return _doc(DocumentKind.ASSISTANT, "asst", spec)


def _live_assistant(**over):
    live = {
        "id": "asst-1",
        "created_by": {"id": "u"},
        "name": "asst",
        "description": "d",
        "icon_url": None,
        "system_prompt": "p",
        "project": "proj",
        "llm_model_type": "gpt",
        "shared": True,
        "is_react": False,
        "is_global": False,
        "updated_date": "2026-01-01T00:00:00",
        "version_count": 3,
        "toolkits": [],
        "context": [],
        "categories": [],
        "assistant_ids": [],
        "prompt_variables": None,
    }
    live.update(over)
    return live


def _resolver():
    return EnvCredentialResolver({"JIRA_TOKEN": SECRET, "PROV_KEY": SECRET})


def _run(doc, live):
    return diff(doc, live, policy_for(doc), _resolver())


def _plan(doc, live):
    result = _run(doc, live)
    return Plan(
        differences=[r for r in result if isinstance(r, Difference)],
        cannot_compare=[r for r in result if isinstance(r, CannotCompare)],
    )


def test_live_equal_to_document_gives_empty_plan():
    plan = _plan(_assistant(), _live_assistant())
    assert plan.is_empty
    assert plan.differences == [] and plan.cannot_compare == []


def test_externally_changed_field_is_reported():
    result = _run(_assistant(), _live_assistant(system_prompt="edited"))
    assert result == [
        Difference(field="system_prompt", document_value="p", live_value="edited")
    ]


def test_only_server_managed_fields_differing_gives_empty_plan():
    live = _live_assistant(
        updated_date="2030-05-05", version_count=99, id="other", created_by=None
    )
    assert _plan(_assistant(), live).is_empty


def test_reference_fields_without_context_are_cannot_compare_not_skipped():
    doc = _assistant(categories=["cat-name"], assistant_ids=["sub-name"])
    live = _live_assistant(categories=["cat-uuid"], assistant_ids=["asst-uuid"])
    fields = [c.field for c in _plan(doc, live).cannot_compare]
    assert fields == ["assistant_ids", "categories"]


def test_masked_prompt_variable_is_cannot_compare():
    doc = _assistant(
        prompt_variables=[PromptVariableSpec(key="k", default_value="real")]
    )
    live = _live_assistant(
        prompt_variables=[{"key": "k", "description": None, "default_value": "*" * 8}]
    )
    result = _run(doc, live)
    assert [type(r) for r in result] == [CannotCompare]
    assert result[0].field == "prompt_variables"


def test_masked_credentials_with_ref_are_cannot_compare_and_never_leak():
    spec = IntegrationSpec(
        project_name="proj",
        alias="jira",
        credential_type="Jira",
        credential_values=[
            CredentialRefEntry(key="token", ref=CredentialRef("env:JIRA_TOKEN"))
        ],
        setting_type=IntegrationType.PROJECT,
    )
    doc = _doc(DocumentKind.INTEGRATION, "jira", spec)
    live = {
        "id": "i-1",
        "project_name": "proj",
        "alias": "jira",
        "default": False,
        "is_global": False,
        "credential_type": "Jira",
        "setting_type": "project",
        "credential_values": [{"key": "token", "value": "*" * 10}],
    }
    plan = _plan(doc, live)
    assert plan.differences == []
    assert [c.field for c in plan.cannot_compare] == ["credential_values"]
    assert plan.is_empty  # unknowable is not a change: no needless write
    for text in (repr(plan), str(plan), plan.model_dump_json(), str(plan.model_dump())):
        assert SECRET not in text
        assert "**********" not in text


def test_unresolvable_ref_is_flagged_without_value():
    spec = IntegrationSpec(
        project_name="proj",
        credential_type="Jira",
        credential_values=[
            CredentialRefEntry(key="token", ref=CredentialRef("env:MISSING_VAR"))
        ],
    )
    doc = _doc(DocumentKind.INTEGRATION, "i", spec)
    result = _run(doc, {"credential_values": [{"key": "token", "value": "*" * 10}]})
    assert result[0].field == "credential_values"
    assert "unresolvable" in result[0].reason


def test_datasource_nested_live_fields_are_flattened():
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "knowledge_base_jira",
            "name": "ds",
            "project_name": "proj",
            "description": "d",
            "jql": "project = A",
        }
    )
    doc = _doc(DocumentKind.DATASOURCE, "ds", spec)
    live = {
        "name": "ds",
        "project_name": "proj",
        "description": "d",
        "type": "knowledge_base_jira",
        "status": "completed",
        "update_date": "x",
        "jira": {"jql": "project = B", "custom_fields": None},
    }
    assert _run(doc, live) == [
        Difference(field="jql", document_value="project = A", live_value="project = B")
    ]


def test_policy_table_covers_every_kind_and_datasource_type():
    expected = {k.value for k in DocumentKind if k is not DocumentKind.DATASOURCE}
    expected |= set(DATASOURCE_ADAPTERS) | {"knowledge_base_file"}
    assert set(FIELD_POLICIES) == expected
    for policy in FIELD_POLICIES.values():
        assert not policy.deny & policy.comparable


def test_models_forbid_extra():
    with pytest.raises(ValueError):
        Difference(field="f", document_value=1, live_value=2, extra=1)


# --- SingleEntityPlanner ---------------------------------------------------


def _planner(live):
    client = FakeClient(assistants=FakeAssistants(get=SimpleNamespace(**live)))
    return client, SingleEntityPlanner(client, credentials=_resolver())


def test_planner_reads_only_the_given_id():
    client, planner = _planner(_live_assistant(system_prompt="edited"))
    plan = planner.plan(_assistant(), "asst-1", "proj")
    assert [c.args for c in client.assistants.calls_to("get")] == [("asst-1",)]
    assert [c.method for c in client.assistants.calls] == ["get"]
    assert [d.field for d in plan.differences] == ["system_prompt"]


def test_planner_returns_empty_plan_when_live_matches():
    _, planner = _planner(_live_assistant())
    assert planner.plan(_assistant(), "asst-1", "proj").is_empty


# --- svn / sharepoint / xray / provider datasources ---------------------------

_NEW_DS = {
    # The platform stores an SVN datasource under a code index type.
    "svn": (
        {
            "index_type": "code",
            "vcs_type": "svn",
            "link": "https://svn/x",
            "branch": "trunk",
        },
        {"link": "https://svn/x"},
    ),
    "knowledge_base_sharepoint": (
        {"sharepoint": {"site_url": "https://sp/x", "files_filter": "*.docx"}},
        {"site_url": "https://sp/x", "files_filter": "*.docx"},
    ),
    "knowledge_base_xray": ({"xray": {"jql": "project = X"}}, {"jql": "project = X"}),
    "provider": (
        {
            "provider_fields": {
                "provider_id": "p-1",
                "toolkit_id": "tk",
                "base_params": {"region": "eu"},
                "create_params": {"api_key": "**********"},
            }
        },
        {
            "provider_name": "prov",
            "toolkit_id": "tk",
            "settings": {"region": "eu", "api_key": "env:PROV_KEY"},
        },
    ),
}
_CHANGED = {
    "svn": ("link", "https://svn/other"),
    "knowledge_base_sharepoint": ("files_filter", "*.pdf"),
    "knowledge_base_xray": ("jql", "project = Y"),
    "provider": ("settings", {"region": "us"}),
}


def _new_ds_doc(ds_type, **over):
    data = {"type": ds_type, "name": "ds", "project_name": "proj", "description": "d"}
    data.update(_NEW_DS[ds_type][1])
    data.update(over)
    spec = TypeAdapter(DatasourceSpec).validate_python(data)
    return _doc(DocumentKind.DATASOURCE, "ds", spec)


def _new_ds_live(ds_type, **over):
    payload = {
        "id": "ds-7",
        "project_name": "proj",
        "repo_name": "ds",
        "index_type": ds_type,
        "description": "d",
        "created_by": {"user_id": "u", "username": "x", "name": "n"},
        "update_date": "2026-01-01T00:00:00",
        "user_abilities": [],
        "completed": True,
        "project_space_visible": False,
    }
    payload.update(_NEW_DS[ds_type][0])
    payload.update(over)
    return DataSource.model_validate(payload)


def _ds_planner(live):
    client = FakeClient(datasources=FakeDatasources(get=live))
    return client, SingleEntityPlanner(client, credentials=_resolver())


@pytest.mark.parametrize("ds_type", sorted(_NEW_DS))
def test_new_kind_equal_to_live_gives_empty_plan(ds_type):
    client, planner = _ds_planner(_new_ds_live(ds_type))
    plan = planner.plan(_new_ds_doc(ds_type), "ds-7", "proj")
    assert plan.differences == []
    assert plan.is_empty
    assert [c.method for c in client.datasources.calls] == ["get"]


@pytest.mark.parametrize("ds_type", sorted(_NEW_DS))
def test_new_kind_lists_the_differing_field(ds_type):
    field, value = _CHANGED[ds_type]
    live = _new_ds_live(ds_type)
    if ds_type == "provider":  # no masked secret, so settings are comparable
        live = _new_ds_live(
            ds_type,
            provider_fields={"toolkit_id": "tk", "base_params": {"region": "eu"}},
        )
    _, planner = _ds_planner(live)
    plan = planner.plan(_new_ds_doc(ds_type, **{field: value}), "ds-7", "proj")
    expected = "settings.region" if ds_type == "provider" else field
    assert [d.field for d in plan.differences] == [expected]


def test_provider_setting_change_is_planned_next_to_a_secret_reference():
    _, planner = _ds_planner(_new_ds_live("provider"))
    doc = _new_ds_doc("provider", settings={"region": "us", "api_key": "env:PROV_KEY"})
    plan = planner.plan(doc, "ds-7", "proj")
    assert [d.field for d in plan.differences] == ["settings.region"]
    assert [c.field for c in plan.cannot_compare] == ["settings.api_key"]
    assert not plan.is_empty


def test_embedding_model_is_compared_against_the_live_embeddings_model():
    ds_type = "knowledge_base_sharepoint"
    _, planner = _ds_planner(_new_ds_live(ds_type, embeddings_model="emb-a"))
    same = planner.plan(_new_ds_doc(ds_type, embedding_model="emb-a"), "ds-7", "proj")
    changed = planner.plan(
        _new_ds_doc(ds_type, embedding_model="emb-b"), "ds-7", "proj"
    )
    assert same.is_empty
    assert [d.field for d in changed.differences] == ["embedding_model"]


def test_xray_embedding_model_is_create_only_and_not_compared():
    # The Xray update route never stores the model, so a difference could not
    # be applied: it is not reported.
    ds_type = "knowledge_base_xray"
    _, planner = _ds_planner(_new_ds_live(ds_type, embeddings_model="emb-a"))
    plan = planner.plan(_new_ds_doc(ds_type, embedding_model="emb-b"), "ds-7", "proj")
    assert plan.is_empty


def test_provider_schedule_is_not_a_comparable_field():
    from codemie_iac.plan_apply.field_policy import FIELD_POLICIES

    policy = FIELD_POLICIES["provider"]
    assert not {"cron_expression", "timezone"} & set(policy.comparable)


def test_sharepoint_oauth_fields_are_compared_and_the_token_is_not():
    live = _new_ds_live(
        "knowledge_base_sharepoint",
        sharepoint={
            "site_url": "https://sp/x",
            "files_filter": "*.docx",
            "auth_type": "integration",
        },
    )
    _, planner = _ds_planner(live)
    doc = _new_ds_doc(
        "knowledge_base_sharepoint",
        auth_type="oauth_custom",
        access_token="env:SP_TOKEN",
    )
    plan = planner.plan(doc, "ds-7", "proj")
    assert [d.field for d in plan.differences] == ["auth_type"]
    assert [c.field for c in plan.cannot_compare] == ["access_token"]


def test_provider_toolkit_change_is_refused_as_create_only():
    _, planner = _ds_planner(_new_ds_live("provider"))
    with pytest.raises(ApplyError) as err:
        planner.plan(_new_ds_doc("provider", toolkit_id="other"), "ds-7", "proj")
    assert err.value.error_type == "datasource_identity_mismatch"
    assert "toolkit_id" in err.value.reason


def test_provider_live_state_follows_the_real_datasource_shape():
    # GET /v1/index/{id} answers ``provider_fields``; the SDK ``DataSource``
    # exposes it as ``provider`` (provider_id, toolkit_id, base_params,
    # create_params), which is what the comparable view and ``settings`` use.
    live = _new_ds_live("provider")
    assert live.provider.base_params == {"region": "eu"}
    view = DATASOURCE_ADAPTERS["provider"].to_comparable(live)
    assert "provider_fields" not in view
    assert view["provider"]["toolkit_id"] == "tk"
    assert _flatten_live(view)["settings"] == {
        "region": "eu",
        "api_key": "**********",
    }
    assert _flatten_live(view)["toolkit_id"] == "tk"


def test_provider_secret_setting_is_not_comparable_and_never_leaks():
    _, planner = _ds_planner(_new_ds_live("provider"))
    plan = planner.plan(_new_ds_doc("provider"), "ds-7", "proj")
    for text in (repr(plan), str(plan), plan.model_dump_json(), str(plan.model_dump())):
        assert SECRET not in text
        assert "**********" not in text


def test_skill_categories_are_compared_as_plain_values():
    from codemie_iac.specs.skill import SkillSpec

    spec = SkillSpec(
        name="skill-sk",
        description="A valid skill description",
        content="c" * 100,
        project="proj",
        categories=["code_review"],
    )
    doc = _doc(DocumentKind.SKILL, "skill-sk", spec)
    live = {
        "name": "skill-sk",
        "description": "A valid skill description",
        "content": "c" * 100,
        "project": "proj",
        "visibility": "project",
        "categories": ["code_review"],
    }
    policy = FIELD_POLICIES["skill"]
    assert diff(doc, live, policy, _resolver()) == []
    live["categories"] = ["testing"]
    (finding,) = diff(doc, live, policy, _resolver())
    assert (finding.field, finding.document_value) == ("categories", ["code_review"])


@pytest.mark.parametrize(
    "ds_type", ["knowledge_base_sharepoint", "knowledge_base_xray"]
)
def test_omitted_embedding_model_is_not_compared_to_the_platform_default(ds_type):
    _, planner = _ds_planner(_new_ds_live(ds_type, embeddings_model="platform-default"))
    plan = planner.plan(_new_ds_doc(ds_type), "ds-7", "proj")
    assert plan.is_empty


@pytest.mark.parametrize("field", ["oauth_client_id", "oauth_tenant_id"])
def test_sharepoint_oauth_ids_are_compared(field):
    live = _new_ds_live(
        "knowledge_base_sharepoint",
        sharepoint={
            "site_url": "https://sp/x",
            "files_filter": "*.docx",
            "auth_type": "oauth_custom",
            "oauth_client_id": "client-a",
            "oauth_tenant_id": "tenant-a",
        },
    )
    _, planner = _ds_planner(live)
    base = {
        "auth_type": "oauth_custom",
        "access_token": "env:SP_TOKEN",
        "oauth_client_id": "client-a",
        "oauth_tenant_id": "tenant-a",
    }
    same = planner.plan(
        _new_ds_doc("knowledge_base_sharepoint", **base), "ds-7", "proj"
    )
    changed = planner.plan(
        _new_ds_doc("knowledge_base_sharepoint", **{**base, field: "other"}),
        "ds-7",
        "proj",
    )
    assert same.is_empty
    assert [d.field for d in changed.differences] == [field]


def test_omitted_assistant_slug_is_not_a_difference():
    """The platform generates a slug from the name when the document omits it."""
    doc = _doc(
        DocumentKind.ASSISTANT,
        "asst",
        AssistantSpec(
            name="asst",
            description="d",
            system_prompt="p",
            project="proj",
            llm_model_type="gpt",
        ),
    )
    live = {
        "name": "asst",
        "description": "d",
        "system_prompt": "p",
        "project": "proj",
        "llm_model_type": "gpt",
        "slug": "asst",
    }
    assert diff(doc, live, FIELD_POLICIES["assistant"], _resolver()) == []
