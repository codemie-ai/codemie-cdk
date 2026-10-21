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
from pydantic import TypeAdapter

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.single_apply import SingleEntityPlanner
from codemie_iac.specs.datasource import DatasourceSpec

from .fakes import FakeClient, FakeDatasources

TARGET = "proj"


def _ds(ds_type="knowledge_base_jira", name="ds", project=TARGET):
    data = {
        "type": ds_type,
        "name": name,
        "project_name": project,
        "description": "d",
    }
    if ds_type == "knowledge_base_jira":
        data["jql"] = "project = A"
    spec = TypeAdapter(DatasourceSpec).validate_python(data)
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name=name),
        spec=spec,
    )


def _live(**over):
    live = {"id": "ds-1", "name": "ds", "project_name": TARGET, "description": "d"}
    live.update(over)
    return SimpleNamespace(**live)


def _planner(client):
    return SingleEntityPlanner(client, credentials=EnvCredentialResolver({}))


def _writes(client):
    return client.datasources.calls_to("create") + client.datasources.calls_to("update")


@pytest.mark.parametrize(
    "live, expected",
    [
        (_live(name="other"), "other"),
        (_live(project_name="elsewhere"), "elsewhere"),
    ],
)
@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_identity_mismatch_fails_with_zero_writes(live, expected, operation):
    client = FakeClient(datasources=FakeDatasources(get=live))
    with pytest.raises(ApplyError) as info:
        getattr(_planner(client), operation)(_ds(), "ds-1", TARGET)
    reason = info.value.reason
    assert "renaming or moving a datasource is not supported" in reason
    assert expected in reason
    assert _writes(client) == []


def test_matching_identity_is_accepted():
    client = FakeClient(datasources=FakeDatasources(get=_live()))
    _planner(client).plan(_ds(), "ds-1", TARGET)


@pytest.mark.parametrize(
    "call",
    [
        lambda p, d: p.plan(d, "ds-1", TARGET),
        lambda p, d: p.apply(d, None, TARGET),
        lambda p, d: p.apply(d, "ds-1", TARGET),
    ],
    ids=["plan", "apply-create", "apply-update"],
)
def test_file_datasource_fails_single_entity_ops(call):
    client = FakeClient(datasources=FakeDatasources(get=_live()))
    with pytest.raises(ApplyError) as info:
        call(_planner(client), _ds("knowledge_base_file"))
    assert info.value.entity_kind == "datasource"
    assert "file datasources are not supported" in info.value.reason
    assert client.datasources.calls == []


def test_file_datasource_fails_bulk_preflight_with_nothing_created():
    client = FakeClient()
    creator = BulkCreator(client, credentials=EnvCredentialResolver({}))
    with pytest.raises(ApplyError) as info:
        creator.create_all([_ds(), _ds("knowledge_base_file", name="f")], TARGET)
    assert "file datasources are not supported" in info.value.reason
    assert client.datasources.calls == []


@pytest.mark.parametrize(
    "extra",
    [
        {"type": "svn", "link": "https://svn/x"},
        {"type": "knowledge_base_sharepoint", "site_url": "https://sp/x"},
        {"type": "knowledge_base_xray", "jql": "project = X"},
        {"type": "provider", "provider_name": "p", "toolkit_id": "t"},
    ],
    ids=["svn", "sharepoint", "xray", "provider"],
)
def test_new_kinds_are_not_rejected_by_the_support_guard(extra):
    from codemie_iac.plan_apply.guards import guard_supported

    data = {"name": "ds", "project_name": TARGET, "description": "d", **extra}
    spec = TypeAdapter(DatasourceSpec).validate_python(data)
    doc = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name="ds"),
        spec=spec,
    )
    guard_supported(doc)  # does not raise
