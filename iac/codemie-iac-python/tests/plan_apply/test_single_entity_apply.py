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

import logging
from types import SimpleNamespace

import pytest
import requests
from codemie_sdk.exceptions import ApiError
from pydantic import TypeAdapter

from codemie_iac.credentials import CredentialRef
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.credentials import (
    EnvCredentialResolver,
)
from codemie_iac.plan_apply.errors import (
    ApplyError,
    PlatformRejectionError,
    UnresolvableCredentialError,
)
from codemie_iac.plan_apply.kinds import _FIND_MAX_PAGES
from codemie_iac.plan_apply.single_apply import ApplyResult, SingleEntityPlanner
from codemie_iac.specs.assistant import AssistantSpec
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.integration import CredentialRefEntry, IntegrationSpec

from .fakes import FakeAssistants, FakeClient, FakeDatasources, FakeIntegrations

TARGET = "proj"


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant():
    spec = AssistantSpec(
        name="asst",
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
        shared=True,
    )
    return _doc(DocumentKind.ASSISTANT, "asst", spec)


def _live(**over):
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


def _integration(ref):
    spec = IntegrationSpec(
        project_name=TARGET,
        alias="jira",
        credential_type="Jira",
        credential_values=[CredentialRefEntry(key="token", ref=CredentialRef(ref))],
    )
    return _doc(DocumentKind.INTEGRATION, "jira", spec)


def _planner(client):
    return SingleEntityPlanner(
        client, credentials=EnvCredentialResolver({"JIRA_TOKEN": "tok"})
    )


def test_apply_without_id_creates_and_returns_new_id():
    client = FakeClient()
    result = _planner(client).apply(_assistant(), None, TARGET)
    assert result == ApplyResult(id="asst-1", created=True)
    assert len(client.assistants.calls_to("create")) == 1
    assert client.assistants.calls_to("get") == []


def test_apply_with_empty_plan_sends_no_write():
    client = FakeClient(assistants=FakeAssistants(get=_live()))
    result = _planner(client).apply(_assistant(), "asst-1", TARGET)
    assert result == ApplyResult(id="asst-1", created=False)
    assert [c.method for c in client.assistants.calls] == ["get"]


def test_apply_with_difference_updates_with_complete_body():
    client = FakeClient(assistants=FakeAssistants(get=_live(system_prompt="old")))
    result = _planner(client).apply(_assistant(), "asst-1", TARGET)
    assert result == ApplyResult(id="asst-1", created=False)
    (call,) = client.assistants.calls_to("update")
    assert call.args[0] == "asst-1"
    assert call.args[1].system_prompt == "p"
    assert client.assistants.calls_to("create") == []


def test_unresolved_credential_fails_with_zero_writes_on_create():
    client = FakeClient()
    with pytest.raises(UnresolvableCredentialError):
        _planner(client).apply(_integration("env:MISSING_VAR"), None, TARGET)
    assert client.integrations.calls == []


def test_unresolved_credential_fails_with_zero_writes_on_update():
    client = FakeClient(
        integrations=FakeIntegrations(get={"credential_values": [], "alias": "x"})
    )
    with pytest.raises(UnresolvableCredentialError):
        _planner(client).apply(_integration("env:MISSING_VAR"), "int-1", TARGET)
    assert client.integrations.calls_to("update") == []


def test_api_error_on_create_becomes_platform_rejection():
    client = FakeClient(assistants=FakeAssistants(create=ApiError("bad", 422)))
    with pytest.raises(PlatformRejectionError) as info:
        _planner(client).apply(_assistant(), None, TARGET)
    assert info.value.entity_kind == "assistant"
    assert info.value.entity_name == "asst"


def test_api_error_on_update_becomes_platform_rejection():
    client = FakeClient(
        assistants=FakeAssistants(
            get=_live(system_prompt="old"), update=ApiError("bad", 422)
        )
    )
    with pytest.raises(PlatformRejectionError):
        _planner(client).apply(_assistant(), "asst-1", TARGET)


def test_datasource_create_returns_no_id():
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "knowledge_base_jira",
            "name": "ds",
            "project_name": TARGET,
            "description": "d",
            "jql": "project = A",
        }
    )
    client = FakeClient(datasources=FakeDatasources())
    doc = _doc(DocumentKind.DATASOURCE, "ds", spec)
    result = _planner(client).apply(doc, None, TARGET)
    assert result == ApplyResult(id=None, created=True)
    assert len(client.datasources.calls_to("create")) == 1


def test_apply_never_deletes():
    client = FakeClient(assistants=FakeAssistants(get=_live(system_prompt="old")))
    _planner(client).apply(_assistant(), "asst-1", TARGET)
    assert all(not c.method.startswith("delete") for c in client.assistants.calls)


# --- svn / sharepoint / xray / provider datasources ---------------------------

_NEW = {
    "svn": {"link": "https://svn/x"},
    "knowledge_base_sharepoint": {"site_url": "https://sp/x"},
    "knowledge_base_xray": {"jql": "project = X"},
    "provider": {"provider_name": "prov", "toolkit_id": "tk", "settings": {"r": "eu"}},
}
_LIVE_SUB = {
    "svn": {"link": "https://svn/x"},
    "knowledge_base_sharepoint": {"site_url": "https://sp/x"},
    "knowledge_base_xray": {"jql": "project = X"},
    "provider": {"provider_fields": {"toolkit_id": "tk", "base_params": {"r": "eu"}}},
}
_CREATE = {"provider": "create_provider_datasource"}
_UPDATE = {"provider": "update_provider_datasource"}


def _new_doc(ds_type, **over):
    data = {"type": ds_type, "name": "ds", "project_name": TARGET, "description": "d"}
    data.update(_NEW[ds_type])
    data.update(over)
    spec = TypeAdapter(DatasourceSpec).validate_python(data)
    return _doc(DocumentKind.DATASOURCE, "ds", spec)


def _new_live(ds_type, **over):
    from codemie_sdk.models.datasource import DataSource

    payload = {
        "id": "ds-7",
        "project_name": TARGET,
        "repo_name": "ds",
        "index_type": ds_type,
        "description": "d",
        "created_by": {"user_id": "u", "username": "x", "name": "n"},
        "update_date": "2026-01-01T00:00:00",
        "user_abilities": [],
        "completed": True,
        "project_space_visible": False,
    }
    payload.update(_LIVE_SUB[ds_type])
    payload.update(over)
    return DataSource.model_validate(payload)


def _writes_of(client, ds_type):
    ds = client.datasources
    return ds.calls_to(_CREATE.get(ds_type, "create")) + ds.calls_to(
        _UPDATE.get(ds_type, "update")
    )


@pytest.mark.parametrize("ds_type", sorted(_NEW))
def test_new_kind_without_id_creates_and_returns_the_identifier(ds_type):
    # Neither datasource create nor the provider POST answers with an id, so
    # the id is looked up by project and name once the datasource exists.
    client = FakeClient(datasources=FakeDatasources(list=[_new_live(ds_type)]))
    result = _planner(client).apply(_new_doc(ds_type), None, TARGET)
    assert result == ApplyResult(id="ds-7", created=True)
    assert len(client.datasources.calls_to(_CREATE.get(ds_type, "create"))) == 1
    assert client.datasources.calls_to("get") == []
    (lookup,) = client.datasources.calls_to("list")
    assert lookup.kwargs["projects"] == [TARGET]


@pytest.mark.parametrize("ds_type", sorted(_NEW))
def test_new_kind_not_yet_listed_is_created_without_an_identifier(ds_type):
    client = FakeClient()
    result = _planner(client).apply(_new_doc(ds_type), None, TARGET)
    assert result == ApplyResult(id=None, created=True)


def test_created_id_ignores_datasources_of_another_name_or_project():
    others = [
        _new_live("svn", repo_name="other"),
        _new_live("svn", project_name="elsewhere"),
    ]
    client = FakeClient(datasources=FakeDatasources(list=others))
    result = _planner(client).apply(_new_doc("svn"), None, TARGET)
    assert result == ApplyResult(id=None, created=True)


def test_created_id_is_found_on_a_later_page():
    class Paged(FakeDatasources):
        def list(self, **kwargs):
            super().list(**kwargs)
            if kwargs["page"] == 0:
                return [_new_live("svn", repo_name=f"f{i}") for i in range(100)]
            return [_new_live("svn")]

    client = FakeClient(datasources=Paged())
    result = _planner(client).apply(_new_doc("svn"), None, TARGET)
    assert result == ApplyResult(id="ds-7", created=True)
    assert [c.kwargs["page"] for c in client.datasources.calls_to("list")] == [0, 1]


_LOOKUP_FAILURES = [
    ApiError("boom", 503),
    requests.ConnectionError("down"),
    requests.Timeout("slow"),
    ValueError("unparseable page"),
]


@pytest.mark.parametrize("failure", _LOOKUP_FAILURES, ids=lambda f: type(f).__name__)
def test_id_lookup_failure_after_create_does_not_fail_the_apply(failure, caplog):
    caplog.set_level("WARNING")
    client = FakeClient(datasources=FakeDatasources(list=failure))
    result = _planner(client).apply(_new_doc("svn"), None, TARGET)
    assert result == ApplyResult(id=None, created=True)
    assert len(client.datasources.calls_to("create")) == 1
    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    text = record.getMessage()
    assert "ds" in text and TARGET in text and type(failure).__name__ in text


def test_id_lookup_failure_warning_never_echoes_the_error_text(caplog):
    caplog.set_level("WARNING")
    failure = ApiError(f"token={PROV_SECRET}", 500)
    client = FakeClient(datasources=FakeDatasources(list=failure))
    _planner(client).apply(_new_doc("svn"), None, TARGET)
    assert caplog.records and PROV_SECRET not in caplog.text


def test_id_lookup_page_cap_exhausted_returns_none_and_warns(caplog):
    caplog.set_level("WARNING")

    class Endless(FakeDatasources):
        def list(self, **kwargs):
            super().list(**kwargs)
            return [_new_live("svn", repo_name=f"f{i}") for i in range(100)]

    client = FakeClient(datasources=Endless())
    result = _planner(client).apply(_new_doc("svn"), None, TARGET)
    assert result == ApplyResult(id=None, created=True)
    assert len(client.datasources.calls_to("list")) == _FIND_MAX_PAGES
    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "ds" in record.getMessage() and TARGET in record.getMessage()


def test_update_does_not_look_the_id_up():
    client = FakeClient(datasources=FakeDatasources(get=_new_live("svn")))
    _planner(client).apply(_new_doc("svn"), "ds-7", TARGET)
    assert client.datasources.calls_to("list") == []


@pytest.mark.parametrize("ds_type", sorted(_NEW))
def test_new_kind_with_empty_plan_sends_no_write(ds_type):
    client = FakeClient(datasources=FakeDatasources(get=_new_live(ds_type)))
    result = _planner(client).apply(_new_doc(ds_type), "ds-7", TARGET)
    assert result == ApplyResult(id="ds-7", created=False)
    assert _writes_of(client, ds_type) == []


@pytest.mark.parametrize("ds_type", sorted(_NEW))
def test_new_kind_with_difference_updates_once(ds_type):
    over = {"provider": {"settings": {"r": "us"}}}.get(ds_type, {"description": "x"})
    client = FakeClient(datasources=FakeDatasources(get=_new_live(ds_type)))
    result = _planner(client).apply(_new_doc(ds_type, **over), "ds-7", TARGET)
    assert result == ApplyResult(id="ds-7", created=False)
    (call,) = _writes_of(client, ds_type)
    assert call.method == _UPDATE.get(ds_type, "update")
    assert call.args[0] == "ds-7"


@pytest.mark.parametrize(
    "ds_type", ["svn", "knowledge_base_sharepoint", "knowledge_base_xray"]
)
@pytest.mark.parametrize(
    "live_over, expected",
    [({"repo_name": "renamed"}, "renamed"), ({"project_name": "other"}, "other")],
    ids=["rename", "move"],
)
def test_new_kind_rename_or_move_is_rejected_naming_both_values(
    ds_type, live_over, expected
):
    client = FakeClient(
        datasources=FakeDatasources(get=_new_live(ds_type, **live_over))
    )
    with pytest.raises(ApplyError) as info:
        _planner(client).apply(_new_doc(ds_type), "ds-7", TARGET)
    reason = info.value.reason
    assert expected in reason
    assert "'ds'" in reason or repr(TARGET) in reason
    assert "renaming or moving a datasource is not supported" in reason
    assert _writes_of(client, ds_type) == []


PROV_SECRET = "pr0v-s3cret-value"


def _secret_provider_doc():
    return _new_doc(
        "provider", settings={"region": "eu", "api_key": "env:PROV_API_KEY"}
    )


def _all_text(*parts):
    return " ".join(str(p) + repr(p) for p in parts)


def test_provider_secret_setting_is_sent_but_never_surfaces_in_errors_or_logs(
    caplog,
):
    caplog.set_level("DEBUG")
    echo = ApiError(f"bad request: api_key={PROV_SECRET}", 422)
    client = FakeClient(
        datasources=FakeDatasources(create_provider_datasource=echo),
    )
    planner = SingleEntityPlanner(
        client, credentials=EnvCredentialResolver({"PROV_API_KEY": PROV_SECRET})
    )
    with pytest.raises(PlatformRejectionError) as info:
        planner.apply(_secret_provider_doc(), None, TARGET)

    sent = client.datasources.calls_to("create_provider_datasource")[0].args[2]
    assert sent.settings["api_key"] == PROV_SECRET  # revealed only in the body
    assert PROV_SECRET not in _all_text(info.value, info.value.reason)
    assert PROV_SECRET not in caplog.text


def test_provider_secret_setting_never_surfaces_in_plan_output(caplog):
    caplog.set_level("DEBUG")
    live = _new_live(
        "provider",
        provider_fields={
            "toolkit_id": "tk",
            "base_params": {"region": "eu"},
            "create_params": {"api_key": "*" * 10},
        },
    )
    client = FakeClient(datasources=FakeDatasources(get=live))
    planner = SingleEntityPlanner(
        client, credentials=EnvCredentialResolver({"PROV_API_KEY": PROV_SECRET})
    )
    plan = planner.plan(_secret_provider_doc(), "ds-7", TARGET)
    text = _all_text(plan, plan.model_dump_json(), plan.model_dump())
    assert PROV_SECRET not in text and "*" * 10 not in text
    assert PROV_SECRET not in caplog.text
    assert plan.is_empty  # a masked secret is unknowable, not a change


def test_provider_secret_unset_in_env_fails_before_any_write():
    client = FakeClient()
    with pytest.raises(UnresolvableCredentialError):
        _planner(client).apply(_secret_provider_doc(), None, TARGET)
    assert client.datasources.calls == []


# --- provider_secret_lookup= wiring -------------------------------------------

LITERAL = "lit-s3cret-value"


def _prov_settings(**settings):
    return _new_doc("provider", settings=settings)


def _build_subject(client, **kw):
    return SingleEntityPlanner(client, **kw)


def _run(subject, doc):
    return subject.apply(doc, None, TARGET)


def _failing_lookup(provider_name, toolkit_id):
    raise RuntimeError(f"offline {LITERAL}")


def test_lookup_param_rejects_a_schema_secret_literal_before_any_write(no_lookup):
    client = FakeClient()
    subject = _build_subject(client, provider_secret_lookup=lambda p, t: ["pat"])
    with pytest.raises(UnresolvableCredentialError) as info:
        _run(subject, _prov_settings(region="eu", pat=LITERAL))
    assert "pat" in info.value.reason
    assert "unavailable" not in info.value.reason
    assert LITERAL not in str(info.value) and LITERAL not in info.value.reason
    assert client.datasources.calls == []


def test_lookup_param_accepts_a_non_secret_literal(no_lookup):
    client = FakeClient()
    subject = _build_subject(client, provider_secret_lookup=lambda p, t: ["api_key"])
    _run(subject, _prov_settings(region="eu"))
    assert len(client.datasources.calls_to("create_provider_datasource")) == 1


def test_without_a_lookup_every_string_literal_is_rejected(no_lookup):
    client = FakeClient()
    with pytest.raises(UnresolvableCredentialError) as info:
        _run(_build_subject(client), _prov_settings(region="eu"))
    assert "region" in info.value.reason
    assert "no lookup configured" in info.value.reason
    assert client.datasources.calls == []


def test_failing_lookup_param_reports_why_the_schema_was_unavailable(no_lookup):
    client = FakeClient()
    subject = _build_subject(client, provider_secret_lookup=_failing_lookup)
    with pytest.raises(UnresolvableCredentialError) as info:
        _run(subject, _prov_settings(region="eu"))
    assert "schema lookup was unavailable" in info.value.reason
    assert "RuntimeError" in info.value.reason
    assert LITERAL not in str(info.value) and LITERAL not in info.value.reason
    assert client.datasources.calls == []


def test_svn_created_id_is_found_from_a_list_item_without_svn_details():
    # The list endpoint does not say whether an item is svn: it reads as code.
    listed = _new_live("svn", index_type="code")
    assert listed.svn is None
    client = FakeClient(datasources=FakeDatasources(list=[listed]))
    result = _planner(client).apply(_new_doc("svn"), None, TARGET)
    assert result == ApplyResult(id="ds-7", created=True)


# --- review follow-ups ---------------------------------------------------------


def _sent_body(client, method):
    (call,) = client.datasources.calls_to(method)
    return call.args[-1].to_body()


def test_provider_update_keeps_live_settings_the_document_omits():
    # The backend resets every omitted schema parameter to its default.
    live = _new_live(
        "provider",
        provider_fields={
            "toolkit_id": "tk",
            "base_params": {"region": "us", "api_key": "**********"},
            "create_params": {"mode": "fast"},
        },
    )
    client = FakeClient(datasources=FakeDatasources(get=live))
    doc = _new_doc("provider", settings={"mode": "slow"}, description="changed")
    _planner(client).apply(doc, "ds-7", TARGET)
    sent = _sent_body(client, "update_provider_datasource")
    assert (sent["name"], sent["project_name"]) == ("ds", TARGET)
    assert sent["region"] == "us" and sent["api_key"] == "**********"
    assert sent["mode"] == "slow"


def test_xray_update_does_not_send_an_embedding_model():
    live = _new_live(
        "knowledge_base_xray",
        embeddings_model="emb-a",
        xray={"jql": "project = X"},
    )
    client = FakeClient(datasources=FakeDatasources(get=live))
    doc = _new_doc("knowledge_base_xray", embedding_model="emb-b", jql="project = Y")
    _planner(client).apply(doc, "ds-7", TARGET)
    (call,) = client.datasources.calls_to("update")
    assert "embedding" not in str(call.args[1].model_dump(by_alias=True)).lower()


def test_sharepoint_oauth_custom_update_with_env_token_sends_it_resolved():
    live = _new_live(
        "knowledge_base_sharepoint",
        sharepoint={"site_url": "https://sp/x", "auth_type": "oauth_custom"},
    )
    client = FakeClient(datasources=FakeDatasources(get=live))
    doc = _new_doc(
        "knowledge_base_sharepoint",
        auth_type="oauth_custom",
        access_token="env:SP_TOKEN",
        description="changed",
    )
    planner = SingleEntityPlanner(
        client, credentials=EnvCredentialResolver({"SP_TOKEN": "t0k"})
    )
    result = planner.apply(doc, "ds-7", TARGET)
    assert result.created is False
    (call,) = client.datasources.calls_to("update")
    assert call.args[1].access_token == "t0k"


def test_a_lookup_failure_of_any_kind_after_create_does_not_fail_the_apply():
    class Broken(FakeDatasources):
        def list(self, **kwargs):
            raise AttributeError("unexpected shape")

    client = FakeClient(datasources=Broken())
    result = _planner(client).apply(_new_doc("svn"), None, TARGET)
    assert result == ApplyResult(id=None, created=True)


def test_planners_do_not_share_a_provider_secret_lookup(no_lookup):
    first = _build_subject(FakeClient(), provider_secret_lookup=lambda p, t: [])
    second = _build_subject(FakeClient())  # no lookup: must still fail closed
    first_client, second_client = FakeClient(), FakeClient()
    first = _build_subject(first_client, provider_secret_lookup=lambda p, t: [])
    second = _build_subject(second_client)
    _run(first, _prov_settings(region="eu"))
    assert len(first_client.datasources.calls_to("create_provider_datasource")) == 1
    with pytest.raises(UnresolvableCredentialError) as info:
        _run(second, _prov_settings(region="eu"))
    assert "no lookup configured" in info.value.reason
    assert second_client.datasources.calls == []


# --- reindex flags (as for code and Git FAQ) ---------------------------------


def _update_request(client):
    (call,) = client.datasources.calls_to("update")
    return call.args[1]


def _apply_update(ds_type, live_over, force=False, **doc_over):
    client = FakeClient(
        datasources=FakeDatasources(get=_new_live(ds_type, **live_over))
    )
    _planner(client).apply(_new_doc(ds_type, **doc_over), "ds-7", TARGET, force=force)
    return _update_request(client)


def test_svn_metadata_only_update_skips_the_reindex():
    assert _apply_update("svn", {}, description="x").skip_reindex is True


def test_svn_source_change_keeps_the_default_reindex():
    request = _apply_update(
        "svn", {"svn": {"link": "https://svn/x"}}, link="https://svn/other"
    )
    assert not request.skip_reindex


def test_svn_forced_update_reindexes():
    assert not _apply_update("svn", {}, force=True).skip_reindex


def test_xray_metadata_only_update_is_not_a_full_reindex():
    request = _apply_update("knowledge_base_xray", {}, description="x")
    assert not request.full_reindex


def test_xray_jql_change_is_a_full_reindex():
    live = {"xray": {"jql": "project = X"}}
    request = _apply_update("knowledge_base_xray", live, jql="project = Y")
    assert request.full_reindex is True


def test_sharepoint_metadata_only_update_is_not_a_full_reindex():
    request = _apply_update("knowledge_base_sharepoint", {}, description="x")
    assert not request.full_reindex


def test_sharepoint_site_change_is_a_full_reindex():
    live = {"sharepoint": {"site_url": "https://sp/x"}}
    request = _apply_update(
        "knowledge_base_sharepoint", live, site_url="https://sp/other"
    )
    assert request.full_reindex is True


def test_forced_sharepoint_update_is_a_full_reindex():
    request = _apply_update("knowledge_base_sharepoint", {}, force=True)
    assert request.full_reindex is True
