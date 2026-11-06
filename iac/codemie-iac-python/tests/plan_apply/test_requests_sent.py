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
