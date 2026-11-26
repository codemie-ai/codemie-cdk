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


"""What is actually sent to the platform."""

from types import SimpleNamespace
import pytest
from codemie_iac.envelope import DocumentKind
from codemie_iac.plan_apply import bulk_create
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.single_apply import SingleEntityPlanner
from .fakes import (
    FakeAssistants,
    FakeCategories,
    FakeClient,
    FakeDatasources,
    FakeIntegrations,
)

from .write_helpers import (
    CREDS,
    SECRET,
    TARGET,
    _assistant,
    _datasource,
    _integration,
    _mcp_assistant,
)


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


def test_workflow_yaml_non_mapping_raises_apply_error():
    with pytest.raises(ApplyError) as info:
        bulk_create._yaml_mapping(_assistant(), "- just\n- a list\n")
    assert info.value.error_type == "invalid_workflow_yaml"
    assert bulk_create._yaml_mapping(_assistant(), "") == {}
    with pytest.raises(ApplyError):
        bulk_create._dict_items(_assistant(), ["x"])


_SENSITIVE_ENV = {"BOT_PROMPT_API_KEY": SECRET}


def _sensitive_doc():
    return _assistant(
        name="bot",
        prompt_variables=[
            {
                "key": "api_key",
                "default_value": "env:BOT_PROMPT_API_KEY",
                "is_sensitive": True,
            },
            {"key": "plain", "default_value": "hello"},
        ],
    )


def _sent_variables(request):
    return {v.key: v.default_value for v in request.prompt_variables}


def test_bulk_create_sends_revealed_sensitive_prompt_variable():
    client = FakeClient()
    BulkCreator(client, credentials=EnvCredentialResolver(_SENSITIVE_ENV)).create_all(
        [_sensitive_doc()], TARGET
    )
    request = client.assistants.calls_to("create")[0].args[0]
    assert _sent_variables(request) == {"api_key": SECRET, "plain": "hello"}
    assert request.prompt_variables[0].is_sensitive is True


def _update_client():
    live = SimpleNamespace(
        id="asst-1", name="bot", description="old", project=TARGET, categories=[]
    )
    return FakeClient(assistants=FakeAssistants(get=live))


def test_update_sends_revealed_sensitive_prompt_variable_without_leaking():
    client = _update_client()
    planner = SingleEntityPlanner(
        client, credentials=EnvCredentialResolver(_SENSITIVE_ENV)
    )
    result = planner.apply(_sensitive_doc(), "asst-1", TARGET)
    request = client.assistants.calls_to("update")[0].args[1]
    assert _sent_variables(request)["api_key"] == SECRET
    assert SECRET not in repr(result)


def test_missing_env_for_sensitive_prompt_variable_is_unresolvable():
    client = _update_client()
    planner = SingleEntityPlanner(client, credentials=EnvCredentialResolver({}))
    with pytest.raises(ApplyError) as info:
        planner.apply(_sensitive_doc(), "asst-1", TARGET)
    assert info.value.error_type == "unresolvable_credential"
    assert client.assistants.calls_to("update") == []


def _live_bot(prompt_variables):
    return SimpleNamespace(
        id="asst-1",
        name="bot",
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
        categories=[],
        prompt_variables=prompt_variables,
    )


def _sensitive_only_doc():
    return _assistant(
        name="bot",
        prompt_variables=[
            {
                "key": "api_key",
                "default_value": "env:BOT_PROMPT_API_KEY",
                "is_sensitive": True,
            }
        ],
    )


def _apply_to(live, doc, **kwargs):
    client = FakeClient(assistants=FakeAssistants(get=live))
    planner = SingleEntityPlanner(
        client, credentials=EnvCredentialResolver(_SENSITIVE_ENV)
    )
    result = planner.apply(doc, "asst-1", TARGET, **kwargs)
    return client, result


def test_unchanged_sensitive_variable_writes_nothing_unless_forced():
    live = _live_bot(
        [{"key": "api_key", "default_value": "*" * 8, "is_sensitive": True}]
    )
    client, skipped = _apply_to(live, _sensitive_only_doc())
    assert client.assistants.calls_to("update") == []
    assert "prompt_variables" in skipped.uncomparable
    client, _ = _apply_to(live, _sensitive_only_doc(), force=True)
    request = client.assistants.calls_to("update")[0].args[1]
    assert _sent_variables(request) == {"api_key": SECRET}


def test_adding_a_sensitive_variable_is_written():
    client, _ = _apply_to(_live_bot([]), _sensitive_only_doc())
    request = client.assistants.calls_to("update")[0].args[1]
    assert _sent_variables(request) == {"api_key": SECRET}


def test_editing_a_plain_variable_next_to_a_sensitive_one_is_written():
    live = _live_bot(
        [
            {"key": "api_key", "default_value": "*" * 8, "is_sensitive": True},
            {"key": "plain", "default_value": "old"},
        ]
    )
    client, _ = _apply_to(live, _sensitive_doc())
    request = client.assistants.calls_to("update")[0].args[1]
    assert _sent_variables(request) == {"api_key": SECRET, "plain": "hello"}


def test_adding_a_plain_variable_next_to_a_sensitive_one_is_written():
    live = _live_bot(
        [{"key": "api_key", "default_value": "*" * 8, "is_sensitive": True}]
    )
    client, _ = _apply_to(live, _sensitive_doc())
    request = client.assistants.calls_to("update")[0].args[1]
    assert _sent_variables(request) == {"api_key": SECRET, "plain": "hello"}
