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

"""Regression tests for the code-review findings (CR-001 .. CR-014)."""

from types import SimpleNamespace

import json

import pytest
from codemie_sdk.exceptions import ApiError
from codemie_sdk.models.integration import IntegrationType
from pydantic import BaseModel, TypeAdapter

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply import bulk_create, lookup
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import ApplyError, PlatformRejectionError
from codemie_iac.plan_apply.kinds import _build
from codemie_iac.plan_apply.ordering import DependencyGraph
from codemie_iac.plan_apply.single_apply import SingleEntityPlanner
from codemie_iac.specs.assistant import (
    AssistantSpec,
    MCPServerConfigSpec,
    MCPServerDetailsSpec,
)
from codemie_iac.specs.category import CategorySpec
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.integration import IntegrationSpec

from .fakes import (
    FakeAssistants,
    FakeCategories,
    FakeClient,
    FakeDatasources,
    FakeIntegrations,
)

TARGET = "proj"
SECRET = "s3cr3t-token-value"


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant(name="a", **extra):
    spec = AssistantSpec(
        name=name,
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
        **extra,
    )
    return _doc(DocumentKind.ASSISTANT, name, spec)


def _integration(alias="jira"):
    spec = IntegrationSpec(
        project_name=TARGET,
        alias=alias,
        credential_type="Jira",
        credential_values=[],
        setting_type=IntegrationType.PROJECT,
    )
    return _doc(DocumentKind.INTEGRATION, alias, spec)


def _datasource(name="ds", setting_id="jira"):
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "knowledge_base_jira",
            "name": name,
            "project_name": TARGET,
            "description": "d",
            "jql": "project = A",
            "setting_id": setting_id,
        }
    )
    return _doc(DocumentKind.DATASOURCE, name, spec)


def _mcp_assistant(name="a"):
    server = MCPServerDetailsSpec(
        name="srv",
        enabled=True,
        config=MCPServerConfigSpec(command="npx", env={"TOKEN": "env:MCP_TOKEN"}),
    )
    return _assistant(name, mcp_servers=[server])


CREDS = {"MCP_TOKEN": SECRET}


# --- CR-006 / CR-005 -----------------------------------------------------------


def test_invalid_body_reason_never_contains_input_values():
    class Req(BaseModel):
        count: int

    with pytest.raises(ApplyError) as info:
        _build(Req, {"count": SECRET}, _assistant())
    text = f"{info.value} {info.value.reason} {info.value.__cause__!r}"
    assert SECRET not in text
    assert "count" in info.value.reason


def test_platform_rejection_scrubs_revealed_secrets():
    cause = ApiError(f"bad token {SECRET}", 422)
    cause.response = {"detail": [{"loc": ["body", "f"], "msg": f"x {SECRET}"}]}
    error = PlatformRejectionError(
        "platform_rejection", "assistant", "a", cause, [SECRET]
    )
    assert SECRET not in f"{error} {error.reason} {error.structured_errors}"


def test_bulk_failure_reason_does_not_leak_revealed_secret():
    client = FakeClient(
        assistants=FakeAssistants(create=ApiError(f"echo {SECRET}", 422))
    )
    creator = BulkCreator(client, credentials=EnvCredentialResolver(CREDS))
    report = creator.create_all([_mcp_assistant()], TARGET)
    assert report.failed.error_type == "platform_rejection"
    assert SECRET not in report.model_dump_json()


def _real_http_error(message):
    """What the SDK raises: ``raise_for_status()`` on a failed request."""
    import requests

    response = requests.Response()
    response.status_code = 422
    response._content = json.dumps(
        {"detail": [{"loc": ["body", "token"], "msg": f"bad {SECRET}"}]}
    ).encode()
    response.request = requests.Request(
        "POST", "https://x/v1/assistants", data=json.dumps({"token": SECRET})
    ).prepare()
    return requests.HTTPError(message, response=response, request=response.request)


def test_bulk_real_http_error_becomes_a_scrubbed_platform_rejection():
    client = FakeClient(
        assistants=FakeAssistants(create=_real_http_error(f"422 for {SECRET}"))
    )
    creator = BulkCreator(client, credentials=EnvCredentialResolver(CREDS))
    report = creator.create_all([_mcp_assistant()], TARGET)
    assert report.failed.error_type == "platform_rejection"
    assert report.failed.structured_errors[0].field == "token"
    assert SECRET not in report.model_dump_json()


def test_single_apply_real_http_error_is_scrubbed_and_not_chained():
    client = FakeClient(
        assistants=FakeAssistants(create=_real_http_error(f"422 for {SECRET}"))
    )
    planner = SingleEntityPlanner(client, EnvCredentialResolver(CREDS))
    with pytest.raises(PlatformRejectionError) as info:
        planner.apply(_mcp_assistant(), None, TARGET)
    error = info.value
    assert SECRET not in f"{error} {error.reason} {error.structured_errors}"
    assert error.__cause__ is None and error.__suppress_context__


# --- CR-001 -----------------------------------------------------------------------


def test_unexpected_error_keeps_created_list_and_reports_failure(monkeypatch):
    original = bulk_create.build_resolved

    def flaky(document, ctx):
        if document.meta.name == "second":
            raise RuntimeError("boom")
        return original(document, ctx)

    monkeypatch.setattr(bulk_create, "build_resolved", flaky)
    docs = [
        _doc(DocumentKind.CATEGORY, "cat", CategorySpec(name="cat")),
        _assistant("second"),
    ]
    report = BulkCreator(FakeClient()).create_all(docs, TARGET)
    assert [e.name for e in report.created] == ["cat"]
    assert report.failed.name == "second"
    assert report.failed.error_type == "apply_failed"


# --- CR-002 / CR-014: revealed credentials reach the request -------------------


def test_bulk_create_sends_revealed_mcp_secret():
    client = FakeClient()
    BulkCreator(client, credentials=EnvCredentialResolver(CREDS)).create_all(
        [_mcp_assistant()], TARGET
    )
    request = client.assistants.calls_to("create")[0].args[0]
    assert request.mcp_servers[0].config.env["TOKEN"] == SECRET


def test_update_sends_revealed_secret_and_resolved_ids():
    live = SimpleNamespace(
        id="asst-1", name="a", description="old", project=TARGET, categories=[]
    )
    client = FakeClient(
        assistants=FakeAssistants(get=live),
        categories=FakeCategories(
            get_categories=[SimpleNamespace(id="cat-9", name="cat")]
        ),
    )
    doc = _mcp_assistant()
    doc.spec.categories = ["cat"]
    planner = SingleEntityPlanner(client, credentials=EnvCredentialResolver(CREDS))
    planner.apply(doc, "asst-1", TARGET)
    request = client.assistants.calls_to("update")[0].args[1]
    assert request.categories == ["cat-9"]
    assert request.mcp_servers[0].config.env["TOKEN"] == SECRET


# --- CR-003 -------------------------------------------------------------------------


def test_datasource_created_after_its_integration_with_resolved_setting_id():
    datasources = FakeDatasources()
    client = FakeClient(datasources=datasources, integrations=FakeIntegrations())
    report = BulkCreator(client).create_all([_datasource(), _integration()], TARGET)
    assert report.failed is None
    assert [e.kind for e in report.created] == [
        DocumentKind.INTEGRATION,
        DocumentKind.DATASOURCE,
    ]
    assert datasources.calls_to("create")[0].args[0].setting_id == "int-1"


# --- CR-004 -------------------------------------------------------------------------


def test_workflow_yaml_non_mapping_raises_apply_error():
    with pytest.raises(ApplyError) as info:
        bulk_create._yaml_mapping(_assistant(), "- just\n- a list\n")
    assert info.value.error_type == "invalid_workflow_yaml"
    assert bulk_create._yaml_mapping(_assistant(), "") == {}
    with pytest.raises(ApplyError):
        bulk_create._dict_items(_assistant(), ["x"])


# --- CR-008 / CR-009 / CR-010 -------------------------------------------------------


def test_live_item_without_project_is_not_a_match():
    assert not lookup._in_project(SimpleNamespace(name="x"), TARGET, "project")
    assert lookup._in_project(SimpleNamespace(project=TARGET), TARGET, "project")


def test_pagination_continues_past_short_pages_and_raises_on_truncation():
    pages = {0: ["a"] * 3, 1: ["b"] * 2}
    assert list(lookup._pages(lambda p: pages.get(p, []))) == ["a"] * 3 + ["b"] * 2
    with pytest.raises(ApplyError) as info:
        list(lookup._pages(lambda p: ["x"]))
    assert info.value.error_type == "lookup_truncated"


def test_duplicate_documents_are_rejected():
    with pytest.raises(ApplyError) as info:
        DependencyGraph([_assistant("dup"), _assistant("dup")])
    assert info.value.error_type == "duplicate_document"


# --- CR-011 / CR-012 / CR-013 ---------------------------------------------------------


def _planner(client, creds=None):
    return SingleEntityPlanner(client, credentials=EnvCredentialResolver(creds or {}))


def _live_assistant(**over):
    live = {"id": "asst-1", "name": "a", "description": "d", "system_prompt": "p"}
    live.update(project=TARGET, llm_model_type="gpt", categories=[], assistant_ids=[])
    live.update(over)
    return SimpleNamespace(**live)


def _cat_client(live):
    return FakeClient(
        assistants=FakeAssistants(get=live),
        categories=FakeCategories(
            get_categories=[SimpleNamespace(id="cat-9", name="cat")]
        ),
    )


def test_externally_changed_reference_field_is_reported():
    client = _cat_client(_live_assistant(categories=["other-id"]))
    plan = _planner(client).plan(_assistant(categories=["cat"]), "asst-1", TARGET)
    assert [d.field for d in plan.differences] == ["categories"]
    assert not plan.is_empty


def test_matching_reference_field_gives_empty_plan():
    client = _cat_client(_live_assistant(categories=[{"id": "cat-9"}]))
    plan = _planner(client).plan(_assistant(categories=["cat"]), "asst-1", TARGET)
    assert plan.is_empty


def test_credential_ref_document_with_matching_state_sends_no_write():
    live = _live_assistant(
        mcp_servers=[
            {"name": "srv", "enabled": True, "config": {"env": {"TOKEN": "*" * 8}}}
        ]
    )
    client = FakeClient(assistants=FakeAssistants(get=live))
    result = _planner(client, CREDS).apply(_mcp_assistant(), "asst-1", TARGET)
    assert result.created is False
    assert client.assistants.calls_to("update") == []


def test_reference_difference_with_credentials_is_redacted():
    live = _live_assistant(
        mcp_servers=[
            {"name": "srv", "enabled": False, "config": {"env": {"TOKEN": SECRET}}}
        ]
    )
    client = FakeClient(assistants=FakeAssistants(get=live))
    plan = _planner(client, CREDS).plan(_mcp_assistant(), "asst-1", TARGET)
    assert [d.field for d in plan.differences] == ["mcp_servers"]
    assert SECRET not in plan.model_dump_json()


def test_update_of_entity_in_other_project_is_refused():
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(project="other")))
    with pytest.raises(ApplyError) as info:
        _planner(client).apply(_assistant(), "asst-1", TARGET)
    assert info.value.error_type == "project_mismatch"
    assert client.assistants.calls_to("update") == []
