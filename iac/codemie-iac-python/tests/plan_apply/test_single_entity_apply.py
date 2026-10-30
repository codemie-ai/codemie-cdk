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
from pydantic import TypeAdapter

from codemie_iac.credentials import CredentialRef
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import (
    PlatformRejectionError,
    UnresolvableCredentialError,
)
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
