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
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
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


def test_skill_categories_resolve_to_ids():
    client = FakeClient(skills=FakeSkills(), categories=FakeCategories())
    report = BulkCreator(client).create_all(
        [_skill("sk", categories=["cat"]), _category("cat")], TARGET
    )
    assert report.failed is None
    assert client.skills.calls_to("create")[0].args[0].categories == ["cat-1"]


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
