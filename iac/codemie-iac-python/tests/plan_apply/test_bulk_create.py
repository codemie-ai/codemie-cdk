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
from codemie_sdk.exceptions import ApiError
from codemie_sdk.models.integration import IntegrationType

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.plan_apply.credentials import (
    EnvCredentialResolver,
)
from codemie_iac.plan_apply.errors import (
    ApplyError,
    UnresolvableCredentialError,
    UnresolvedReferenceError,
)
from codemie_iac.specs.assistant import AssistantSpec
from codemie_iac.specs.category import CategorySpec
from codemie_iac.specs.integration import IntegrationSpec
from codemie_iac.specs.skill import SkillSpec

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


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant(name, **extra):
    spec = AssistantSpec(
        name=name,
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
        **extra,
    )
    return _doc(DocumentKind.ASSISTANT, name, spec)


def _category(name="cat"):
    return _doc(DocumentKind.CATEGORY, name, CategorySpec(name=name))


def _skill(name="sk", **extra):
    spec = SkillSpec(name=name, description="d", content="c", project=TARGET, **extra)
    return _doc(DocumentKind.SKILL, name, spec)


def _integration(alias="jira", values=()):
    spec = IntegrationSpec(
        project_name=TARGET,
        alias=alias,
        credential_type="Jira",
        credential_values=list(values),
        setting_type=IntegrationType.PROJECT,
    )
    return _doc(DocumentKind.INTEGRATION, alias, spec)


class IdAssistants(FakeAssistants):
    """Returns an id derived from the created name; optional live list."""

    def __init__(self, existing=(), fail_on=None, **kw):
        super().__init__(**kw)
        self.existing = list(existing)
        self.fail_on = fail_on

    def create(self, request):
        if request.name == self.fail_on:
            self.calls.append(Call("create", (request,), {}))
            raise ApiError("boom", 422)
        self._call("create", request)
        return SimpleNamespace(message="ok", assistant_id=f"id-{request.name}")

    def list(self, minimal_response=True, page=0, per_page=12, **kw):
        self.calls.append(Call("list", (), {"page": page}))
        items = self.existing[page * per_page : (page + 1) * per_page]
        return list(items)


def _live(name, project=TARGET, id_=None):
    return SimpleNamespace(id=id_ or f"live-{name}", name=name, project=project)


def _writes(client):
    return [
        (svc, c.method)
        for svc in (
            "assistants",
            "skills",
            "workflows",
            "datasources",
            "integrations",
            "categories",
        )
        for c in getattr(client, svc).calls
        if c.method.startswith("create")
    ]


class SeqClient(FakeClient):
    """Records global create order across services."""


def test_cross_referenced_bundle_created_in_dependency_order():
    assistants = IdAssistants()
    client = FakeClient(
        assistants=assistants,
        categories=FakeCategories(),
        integrations=FakeIntegrations(),
    )
    docs = [
        _assistant("main", assistant_ids=["sub"], categories=["cat"]),
        _assistant("sub"),
        _category("cat"),
    ]
    report = BulkCreator(client).create_all(docs, TARGET)

    assert report.failed is None
    names = [e.name for e in report.created]
    assert names[-1] == "main"
    assert sorted(names) == ["cat", "main", "sub"]
    main_req = assistants.calls_to("create")[-1].args[0]
    assert main_req.assistant_ids == ["id-sub"]
    assert main_req.categories == ["cat-1"]
    assert sorted(e.id for e in report.created) == ["cat-1", "id-main", "id-sub"]


def test_integration_reference_replaced_with_platform_id_and_secret_revealed():
    from codemie_iac.specs.integration import CredentialRefEntry

    integ = _integration(values=[CredentialRefEntry(key="token", ref="env:JIRA_TOKEN")])
    from codemie_iac.specs.assistant import ToolKitDetailsSpec

    asst = _assistant(
        "a", toolkits=[ToolKitDetailsSpec(toolkit="Jira", settings="jira")]
    )
    client = FakeClient()
    creds = EnvCredentialResolver({"JIRA_TOKEN": "s3cret"})
    report = BulkCreator(client, credentials=creds).create_all([asst, integ], TARGET)

    assert report.failed is None
    int_req = client.integrations.calls_to("create")[0].args[0]
    assert int_req.credential_values[0].value == "s3cret"
    a_req = client.assistants.calls_to("create")[0].args[0]
    assert a_req.toolkits[0].settings.id == "int-1"
    assert "s3cret" not in repr(report)


def test_reference_absent_everywhere_raises_with_zero_writes():
    client = FakeClient(assistants=IdAssistants())
    docs = [_category("cat"), _assistant("main", assistant_ids=["ghost"])]
    with pytest.raises(UnresolvedReferenceError) as exc:
        BulkCreator(client).create_all(docs, TARGET)
    assert "ghost" in str(exc.value)
    assert _writes(client) == []


def test_reference_found_live_in_target_project_is_used():
    assistants = IdAssistants(existing=[_live("ext")])
    client = FakeClient(assistants=assistants)
    report = BulkCreator(client).create_all(
        [_assistant("main", assistant_ids=["ext"])], TARGET
    )
    assert report.failed is None
    assert assistants.calls_to("create")[0].args[0].assistant_ids == ["live-ext"]


def test_live_entity_in_other_project_is_not_a_match():
    assistants = IdAssistants(existing=[_live("ext", project="other")])
    client = FakeClient(assistants=assistants)
    with pytest.raises(UnresolvedReferenceError):
        BulkCreator(client).create_all(
            [_assistant("main", assistant_ids=["ext"])], TARGET
        )
    assert _writes(client) == []


def test_ambiguous_live_reference_is_unresolved():
    assistants = IdAssistants(existing=[_live("ext"), _live("ext", id_="x2")])
    client = FakeClient(assistants=assistants)
    with pytest.raises(UnresolvedReferenceError):
        BulkCreator(client).create_all(
            [_assistant("main", assistant_ids=["ext"])], TARGET
        )
    assert _writes(client) == []


def test_same_name_as_existing_entity_still_creates():
    assistants = IdAssistants(existing=[_live("dup")])
    client = FakeClient(assistants=assistants)
    report = BulkCreator(client).create_all([_assistant("dup")], TARGET)
    assert report.failed is None
    assert len(assistants.calls_to("create")) == 1
    assert [e.id for e in report.created] == ["id-dup"]


def test_failure_on_entity_n_reports_it_and_the_n_minus_1_created():
    assistants = IdAssistants(fail_on="b")
    client = FakeClient(assistants=assistants)
    docs = [_assistant("a"), _assistant("b"), _assistant("c")]
    report = BulkCreator(client).create_all(docs, TARGET)

    assert [e.name for e in report.created] == ["a"]
    assert report.failed.name == "b"
    assert report.failed.kind is DocumentKind.ASSISTANT
    assert report.failed.error_type == "platform_rejection"
    assert len(assistants.calls_to("create")) == 2  # c never attempted


def test_unset_credential_var_fails_before_any_write():
    from codemie_iac.specs.integration import CredentialRefEntry

    integ = _integration(values=[CredentialRefEntry(key="t", ref="env:MISSING_VAR")])
    client = FakeClient()
    with pytest.raises(UnresolvableCredentialError):
        BulkCreator(client, credentials=EnvCredentialResolver({})).create_all(
            [_category("cat"), integ], TARGET
        )
    assert _writes(client) == []


def test_dependency_cycle_fails_before_any_write():
    client = FakeClient()
    docs = [
        _assistant("a", assistant_ids=["b"]),
        _assistant("b", assistant_ids=["a"]),
    ]
    with pytest.raises(ApplyError) as exc:
        BulkCreator(client).create_all(docs, TARGET)
    assert exc.value.error_type == "dependency_cycle"
    assert _writes(client) == []


def test_unsupported_kind_variant_fails_preflight_via_adapter(monkeypatch):
    from codemie_iac.plan_apply import bulk_create

    def boom(_doc):
        raise ApplyError("unsupported_datasource_type", "datasource", "ds", "no")

    monkeypatch.setattr(bulk_create, "adapter_for", boom)
    client = FakeClient()
    with pytest.raises(ApplyError):
        BulkCreator(client).create_all([_category("cat")], TARGET)
    assert _writes(client) == []


def test_skill_categories_are_sent_as_values_without_a_category_entity():
    client = FakeClient(skills=FakeSkills(), categories=FakeCategories())
    report = BulkCreator(client).create_all(
        [_skill("sk", categories=["code_review"])], TARGET
    )
    assert report.failed is None
    assert client.skills.calls_to("create")[0].args[0].categories == ["code_review"]
    assert client.categories.calls == []


def test_skill_categories_ignore_a_category_entity_of_the_same_name():
    client = FakeClient(skills=FakeSkills(), categories=FakeCategories())
    BulkCreator(client).create_all(
        [_skill("sk", categories=["cat"]), _category("cat")], TARGET
    )
    assert client.skills.calls_to("create")[0].args[0].categories == ["cat"]


def test_workflow_assistant_reference_becomes_id_and_project_is_target():
    from codemie_sdk.builders.workflow.definition import (
        WorkflowAssistant,
        WorkflowDefinition,
    )
    from codemie_sdk.models.workflow import WorkflowMode

    from codemie_iac.specs.workflow import WorkflowSpec

    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={"a1": WorkflowAssistant(id="a1", assistant_id="sub")},
    )
    wf = _doc(DocumentKind.WORKFLOW, "wf", WorkflowSpec(workflow=definition))
    client = FakeClient(assistants=IdAssistants())
    report = BulkCreator(client).create_all([wf, _assistant("sub")], TARGET)

    assert report.failed is None
    req = client.workflows.calls_to("create_workflow")[0].args[0]
    assert req.project == TARGET
    assert "assistant_id: id-sub" in req.yaml_config


def test_provider_datasource_settings_secret_refs_are_resolved():
    from pydantic import TypeAdapter

    from codemie_iac.plan_apply.bulk_create import ResolveContext, build_resolved
    from codemie_iac.plan_apply.lookup import NameLookup
    from codemie_iac.specs.datasource import DatasourceSpec

    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "provider",
            "name": "ds",
            "project_name": "proj",
            "description": "d",
            "provider_name": "prov",
            "toolkit_id": "tk",
            "settings": {"region": "eu", "api_key": "env:PROV_KEY"},
        }
    )
    ctx = ResolveContext(
        lookup=NameLookup([], "proj"),
        credentials=EnvCredentialResolver({"PROV_KEY": "s3cret"}),
    )

    resolved = build_resolved(_doc(DocumentKind.DATASOURCE, "ds", spec), ctx)

    assert resolved["settings"] == {"region": "eu", "api_key": "s3cret"}


# --- svn / sharepoint / xray / provider datasources ---------------------------

NEW_KIND_SPECS = {
    "svn": {"type": "svn", "link": "https://svn/x"},
    "knowledge_base_sharepoint": {
        "type": "knowledge_base_sharepoint",
        "site_url": "https://sp/x",
    },
    "knowledge_base_xray": {"type": "knowledge_base_xray", "jql": "project = X"},
    "provider": {
        "type": "provider",
        "provider_name": "prov",
        "toolkit_id": "tk",
        "settings": {"region": "eu"},
    },
}


def _new_ds(ds_type, **extra):
    from pydantic import TypeAdapter

    from codemie_iac.specs.datasource import DatasourceSpec

    data = {"name": "ds", "project_name": TARGET, "description": "d"}
    data.update(NEW_KIND_SPECS[ds_type])
    data.update(extra)
    spec = TypeAdapter(DatasourceSpec).validate_python(data)
    return _doc(DocumentKind.DATASOURCE, "ds", spec)


def _create_method(ds_type):
    return "create_provider_datasource" if ds_type == "provider" else "create"


def _sent(call, ds_type):
    """The identity fields the request carries: top-level, or (provider only)
    in the body merged with the provider settings."""
    if ds_type == "provider":
        return call.args[2].to_body() | call.args[2].settings
    return call.args[0].model_dump()


# A provider datasource has no integration: the platform never stores one.
INTEGRATION_KINDS = [k for k in sorted(NEW_KIND_SPECS) if k != "provider"]


@pytest.mark.parametrize("ds_type", INTEGRATION_KINDS)
def test_new_kind_created_after_its_integration_with_resolved_setting_id(ds_type):
    client = FakeClient()
    docs = [_new_ds(ds_type, setting_id="jira"), _integration("jira")]
    report = BulkCreator(client).create_all(docs, TARGET)

    assert report.failed is None
    assert [e.name for e in report.created] == ["jira", "ds"]
    (call,) = client.datasources.calls_to(_create_method(ds_type))
    sent = _sent(call, ds_type)
    assert sent["setting_id"] == "int-1"
    assert sent["name"] == "ds" and sent["project_name"] == TARGET


def _listed(ds_type):
    from codemie_sdk.models.datasource import DataSource

    payload = {
        "id": "ds-9",
        "project_name": TARGET,
        "repo_name": "ds",
        "index_type": "code" if ds_type == "svn" else ds_type,
        "description": "d",
        "created_by": {"user_id": "u", "username": "x", "name": "n"},
        "update_date": "2026-01-01T00:00:00",
        "user_abilities": [],
        "completed": True,
        "project_space_visible": False,
    }
    if ds_type == "svn":
        payload["svn"] = {"link": "https://svn/x"}
    return DataSource.model_validate(payload)


@pytest.mark.parametrize("ds_type", sorted(NEW_KIND_SPECS))
def test_new_kind_created_entity_carries_the_looked_up_id(ds_type):
    client = FakeClient(datasources=FakeDatasources(list=[_listed(ds_type)]))
    report = BulkCreator(client).create_all([_new_ds(ds_type)], TARGET)

    assert report.failed is None
    assert {e.name: e.id for e in report.created} == {"ds": "ds-9"}


def test_id_lookup_failure_after_create_still_records_the_entity(caplog):
    caplog.set_level("WARNING")
    client = FakeClient(datasources=FakeDatasources(list=ApiError("boom", 503)))
    report = BulkCreator(client).create_all([_new_ds("svn")], TARGET)

    assert report.failed is None
    assert [(e.name, e.id) for e in report.created] == [("ds", None)]
    assert len(client.datasources.calls_to("create")) == 1
    assert any("ApiError" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("ds_type", INTEGRATION_KINDS)
def test_new_kind_with_unresolved_integration_names_it_and_creates_nothing(ds_type):
    client = FakeClient()
    docs = [_category("cat"), _new_ds(ds_type, setting_id="ghost-int")]
    with pytest.raises(UnresolvedReferenceError) as exc:
        BulkCreator(client).create_all(docs, TARGET)
    assert "ghost-int" in str(exc.value)
    assert _writes(client) == []
    assert client.datasources.calls == []


def test_new_kind_integration_found_live_is_used_when_not_in_bundle():
    class ProjectScopeOnly(FakeIntegrations):
        def list(self, setting_type=None, page=0, per_page=10, filters=None):
            self._call("list", setting_type=setting_type, page=page)
            if setting_type is not IntegrationType.PROJECT or page:
                return []
            return [SimpleNamespace(id="live-int", alias="jira", project_name=TARGET)]

    client = FakeClient(integrations=ProjectScopeOnly())
    BulkCreator(client).create_all([_new_ds("svn", setting_id="jira")], TARGET)
    (call,) = client.datasources.calls_to("create")
    assert call.args[0].setting_id == "live-int"


# --- provider_secret_lookup= wiring -------------------------------------------

LITERAL = "lit-s3cret-value"


def _prov_settings(**settings):
    return _new_ds("provider", settings=settings)


def _build_subject(client, **kw):
    return BulkCreator(client, **kw)


def _run(subject, doc):
    return subject.create_all([doc], TARGET)


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


def test_unset_env_ref_in_a_non_secret_provider_setting_fails_before_any_write(
    no_lookup,
):
    client = FakeClient()
    subject = _build_subject(
        client,
        credentials=EnvCredentialResolver({"K": "s3cret"}),
        provider_secret_lookup=lambda p, t: ["api_key"],
    )
    docs = [
        _category("c1"),
        _new_ds(
            "provider",
            settings={"region": "env:REGION_UNSET", "api_key": "env:K"},
        ),
    ]
    with pytest.raises(UnresolvableCredentialError) as info:
        subject.create_all(docs, TARGET)
    assert "REGION_UNSET" in str(info.value)
    assert _writes(client) == []


def test_sharepoint_oauth_access_token_is_resolved_for_the_request():
    client = FakeClient()
    doc = _new_ds(
        "knowledge_base_sharepoint",
        auth_type="oauth_custom",
        access_token="env:SP_TOKEN",
    )
    creds = EnvCredentialResolver({"SP_TOKEN": "t0k"})
    report = BulkCreator(client, credentials=creds).create_all([doc], TARGET)
    assert report.failed is None
    (call,) = client.datasources.calls_to("create")
    assert call.args[0].access_token == "t0k"
    assert "t0k" not in repr(report)


def test_sharepoint_oauth_unset_access_token_fails_before_any_write():
    client = FakeClient()
    doc = _new_ds(
        "knowledge_base_sharepoint",
        auth_type="oauth_custom",
        access_token="env:SP_MISSING",
    )
    with pytest.raises(UnresolvableCredentialError):
        BulkCreator(client, credentials=EnvCredentialResolver({})).create_all(
            [_category("cat"), doc], TARGET
        )
    assert _writes(client) == []


def test_create_all_rejects_a_literal_provider_secret_before_any_call(no_lookup):
    client = FakeClient()
    subject = _build_subject(client, provider_secret_lookup=lambda p, t: ["pat"])
    with pytest.raises(UnresolvableCredentialError) as info:
        subject.create_all([_prov_settings(pat=LITERAL)], TARGET)
    assert "pat" in info.value.reason and LITERAL not in str(info.value)
    assert client.datasources.calls == []


def test_sharepoint_oauth_without_a_token_fails_the_create_naming_the_field():
    client = FakeClient()
    doc = _new_ds("knowledge_base_sharepoint", auth_type="oauth_custom")
    report = BulkCreator(client).create_all([doc], TARGET)
    assert report.failed is not None
    assert report.failed.error_type == "invalid_body"
    assert "access_token" in report.failed.reason
    assert client.datasources.calls_to("create") == []
