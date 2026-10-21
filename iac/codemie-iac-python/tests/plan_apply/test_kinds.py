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
from codemie_sdk.exceptions import NotFoundError
from codemie_sdk.models.assistant import AssistantCreateRequest, AssistantUpdateRequest
from codemie_sdk.models.categories import CategoryCreateRequest
from codemie_sdk.models.datasource import (
    BaseDataSourceRequest,
    CodeDataSourceRequest,
)
from codemie_sdk.models.integration import Integration, IntegrationType
from codemie_sdk.models.skill import SkillCreateRequest
from codemie_sdk.models.workflow import WorkflowCreateRequest
from codemie_sdk.builders.workflow.definition import WorkflowDefinition
from codemie_sdk.models.workflow import WorkflowMode as SdkWorkflowMode
from pydantic import TypeAdapter

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.kinds import (
    ADAPTERS,
    DATASOURCE_ADAPTERS,
    INTEGRATION_LIST_CAP,
    KindAdapter,
    adapter_for,
)
from codemie_iac.specs.assistant import AssistantSpec
from codemie_iac.specs.category import CategorySpec
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.integration import IntegrationSpec
from codemie_iac.specs.skill import SkillSpec
from codemie_iac.specs.workflow import WorkflowSpec

from .fakes import FakeClient, FakeIntegrations, FakeSkills


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant():
    spec = AssistantSpec(
        name="asst",
        description="d",
        system_prompt="p",
        project="proj",
        llm_model_type="gpt",
        shared=True,
    )
    return _doc(DocumentKind.ASSISTANT, "asst", spec)


def _skill():
    spec = SkillSpec(name="sk", description="d", content="c", project="proj")
    return _doc(DocumentKind.SKILL, "sk", spec)


def _workflow():
    definition = WorkflowDefinition(
        name="wf", description="wd", mode=SdkWorkflowMode.SEQUENTIAL, shared=True
    )
    return _doc(DocumentKind.WORKFLOW, "wf", WorkflowSpec(workflow=definition))


def _category():
    return _doc(DocumentKind.CATEGORY, "cat", CategorySpec(name="cat", description="x"))


def _integration():
    spec = IntegrationSpec(
        project_name="proj",
        alias="jira",
        credential_type="Jira",
        credential_values=[],
        setting_type=IntegrationType.PROJECT,
    )
    return _doc(DocumentKind.INTEGRATION, "jira", spec)


def _datasource(**spec):
    spec.setdefault("name", "ds")
    spec.setdefault("project_name", "proj")
    spec.setdefault("description", "d")
    parsed = TypeAdapter(DatasourceSpec).validate_python(spec)
    return _doc(DocumentKind.DATASOURCE, spec["name"], parsed)


# kind, document factory, resolved overrides, service attr, create method, update method,
# get method, request type, expected id from default fake responses
KIND_CASES = [
    pytest.param(
        DocumentKind.ASSISTANT,
        _assistant,
        {},
        "assistants",
        "create",
        "update",
        "get",
        AssistantCreateRequest,
        "asst-1",
        id="assistant",
    ),
    pytest.param(
        DocumentKind.SKILL,
        _skill,
        {},
        "skills",
        "create",
        "update",
        "get",
        SkillCreateRequest,
        "skill-1",
        id="skill",
    ),
    pytest.param(
        DocumentKind.WORKFLOW,
        _workflow,
        {"project": "proj"},
        "workflows",
        "create_workflow",
        "update",
        "get",
        WorkflowCreateRequest,
        "wf-1",
        id="workflow",
    ),
    pytest.param(
        DocumentKind.CATEGORY,
        _category,
        {},
        "categories",
        "create_category",
        "update_category",
        "get_category",
        CategoryCreateRequest,
        "cat-1",
        id="category",
    ),
    pytest.param(
        DocumentKind.INTEGRATION,
        _integration,
        {"credential_values": [{"key": "url", "value": "https://x"}]},
        "integrations",
        "create",
        "update",
        "get",
        Integration,
        "int-1",
        id="integration",
    ),
    pytest.param(
        DocumentKind.DATASOURCE,
        lambda: _datasource(type="knowledge_base_jira", jql="a=b"),
        {},
        "datasources",
        "create",
        "update",
        "get",
        BaseDataSourceRequest,
        None,
        id="datasource",
    ),
]


def test_adapters_cover_every_document_kind():
    assert set(ADAPTERS) == set(DocumentKind)
    assert all(isinstance(a, KindAdapter) for a in ADAPTERS.values())


@pytest.mark.parametrize(
    "kind,make,resolved,attr,create_m,update_m,get_m,req_type,expected_id", KIND_CASES
)
def test_create_routes_to_service_with_complete_body(
    kind, make, resolved, attr, create_m, update_m, get_m, req_type, expected_id
):
    client = FakeClient()
    doc = make()
    adapter = adapter_for(doc)

    response = adapter.create(client, doc, resolved)

    service = getattr(client, attr)
    (call,) = service.calls
    assert call.method == create_m
    assert isinstance(call.args[0], req_type)
    assert adapter.extract_id(response) == expected_id


@pytest.mark.parametrize(
    "kind,make,resolved,attr,create_m,update_m,get_m,req_type,expected_id", KIND_CASES
)
def test_update_and_get_route_with_entity_id(
    kind, make, resolved, attr, create_m, update_m, get_m, req_type, expected_id
):
    client = FakeClient()
    doc = make()
    adapter = adapter_for(doc)

    adapter.update(client, doc, "the-id", resolved)
    adapter.get(client, doc, "the-id")

    service = getattr(client, attr)
    update_call, get_call = service.calls
    assert update_call.method == update_m
    assert update_call.args[0] == "the-id"
    assert get_call.method == get_m
    assert get_call.args[0] == "the-id"


def test_assistant_body_is_complete_and_resolved_overrides_apply():
    client = FakeClient()
    doc = _assistant()
    adapter_for(doc).create(client, doc, {"categories": ["cat_1"]})
    (call,) = client.assistants.calls
    request = call.args[0]
    assert request.name == "asst"
    assert request.shared is True
    assert request.llm_model_type == "gpt"
    assert request.categories == ["cat_1"]
    adapter_for(doc).update(client, doc, "id-9", {})
    assert isinstance(client.assistants.calls[1].args[1], AssistantUpdateRequest)


def test_workflow_body_renders_yaml_config_and_uses_resolver():
    client = FakeClient()
    doc = _workflow()
    adapter_for(doc).create(client, doc, {"project": "proj"})
    request = client.workflows.calls[0].args[0]
    assert request.name == "wf"
    assert request.description == "wd"
    assert request.shared is True
    assert request.project == "proj"
    assert "states" in request.yaml_config


def test_workflow_without_project_is_an_apply_error():
    doc = _workflow()
    with pytest.raises(ApplyError) as err:
        adapter_for(doc).create(FakeClient(), doc, {})
    assert err.value.entity_kind == "workflow"
    assert err.value.entity_name == "wf"


def test_integration_without_resolved_credentials_is_an_apply_error():
    doc = _integration()
    with pytest.raises(ApplyError):
        adapter_for(doc).create(FakeClient(), doc, {})


def test_integration_get_uses_setting_type_and_names_the_cap_on_not_found():
    integrations = FakeIntegrations(get=NotFoundError("Integration", "int-9"))
    client = FakeClient(integrations=integrations)
    doc = _integration()
    with pytest.raises(ApplyError) as err:
        adapter_for(doc).get(client, doc, "int-9")
    assert str(INTEGRATION_LIST_CAP) in err.value.reason
    assert INTEGRATION_LIST_CAP == 100
    assert integrations.calls[0].kwargs["setting_type"] == IntegrationType.PROJECT


def test_other_kinds_do_not_translate_not_found():
    client = FakeClient(skills=FakeSkills(get=NotFoundError("Skill", "x")))
    doc = _skill()
    with pytest.raises(NotFoundError):
        adapter_for(doc).get(client, doc, "x")


def test_extract_id_is_none_without_id():
    adapter = ADAPTERS[DocumentKind.INTEGRATION]
    assert adapter.extract_id({"message": "ok"}) is None


def test_to_comparable_dumps_models_and_dicts():
    adapter = ADAPTERS[DocumentKind.CATEGORY]
    live = CategoryCreateRequest(name="n", description="d")
    assert adapter.to_comparable(live) == {"name": "n", "description": "d"}
    assert adapter.to_comparable({"a": 1}) == {"a": 1}


DS_CASES = {
    "code": dict(
        type="code",
        link="https://g/x",
        branch="main",
        index_type="code",
        embeddings_model="emb",
        prompt="pr",
        files_filter="*.py",
        docs_generation=True,
        shared_with_project=True,
    ),
    "knowledge_base_git_faq": dict(
        type="knowledge_base_git_faq",
        link="l",
        branch="b",
        files_filter="f",
        embedding_model="e",
    ),
    "knowledge_base_jira": dict(type="knowledge_base_jira", jql="a=b"),
    "knowledge_base_confluence": dict(
        type="knowledge_base_confluence", cql="c", max_pages=3
    ),
    "llm_routing_google": dict(type="llm_routing_google", google_doc="https://d"),
    "knowledge_base_azure_devops_wiki": dict(
        type="knowledge_base_azure_devops_wiki",
        wiki_query="q",
        organization="o",
        project="p",
        wiki_name="w",
    ),
    "knowledge_base_azure_devops_work_item": dict(
        type="knowledge_base_azure_devops_work_item",
        wiql_query="q",
        organization="o",
        project="p",
    ),
    "knowledge_base_xwiki": dict(type="knowledge_base_xwiki", space="s", wiki="w"),
}


def test_datasource_table_covers_every_spec_type_except_file():
    assert set(DATASOURCE_ADAPTERS) == set(DS_CASES)
    assert "knowledge_base_file" not in DATASOURCE_ADAPTERS


@pytest.mark.parametrize("ds_type", sorted(DS_CASES))
def test_datasource_create_and_update_send_complete_bodies(ds_type):
    client = FakeClient()
    doc = _datasource(**DS_CASES[ds_type])
    adapter = adapter_for(doc)

    response = adapter.create(client, doc, {})
    adapter.update(client, doc, "ds-7", {})

    create_call, update_call = client.datasources.calls
    request = create_call.args[0]
    assert request.type.value == ds_type
    body = request.model_dump(by_alias=True, exclude_none=True)
    assert body["name"] == "ds" and body["project_name"] == "proj"
    assert "project_space_visible" in body
    for field, value in DS_CASES[ds_type].items():
        if field not in ("type", "shared_with_project", "index_type"):
            assert getattr(request, field) == value
    assert update_call.args[0] == "ds-7"
    assert update_call.args[1].type.value == ds_type
    assert adapter.extract_id(response) is None


def test_code_datasource_project_space_visible_is_set_on_both_keys():
    client = FakeClient()
    doc = _datasource(**DS_CASES["code"])
    adapter_for(doc).create(client, doc, {})
    body = (
        client.datasources.calls[0].args[0].model_dump(by_alias=True, exclude_none=True)
    )
    assert body["project_space_visible"] is True
    assert body["projectSpaceVisible"] is True
    assert isinstance(client.datasources.calls[0].args[0], CodeDataSourceRequest)
    assert body["docsGeneration"] is True


def test_file_datasource_is_not_adaptable():
    doc = _datasource(type="knowledge_base_file")
    with pytest.raises(ApplyError):
        adapter_for(doc)
