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


"""A workflow that names a datasource created in the same run waits for the
platform to list it, and fails clearly if it never does."""

from types import SimpleNamespace

from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.workflow import WorkflowMode
from pydantic import TypeAdapter

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply import lookup
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.workflow import WorkflowSpec

from .plan_apply.fakes import Call, FakeClient, FakeDatasources

TARGET = "proj"


class _SlowListing(FakeDatasources):
    """Lists the datasource only after ``misses`` empty answers, like a code
    datasource whose index row is written by a background task."""

    def __init__(self, misses, **kw):
        super().__init__(**kw)
        self.misses = misses

    def list(self, page=0, per_page=12, **kwargs):
        self.calls.append(Call("list", (), {"page": page, **kwargs}))
        if page > 0 or self.misses > 0:
            self.misses -= 1 if page == 0 else 0
            return []
        return [SimpleNamespace(id="ds-id", name="ds", project_name=TARGET)]


def _documents():
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "svn",
            "name": "ds",
            "project_name": TARGET,
            "description": "d",
            "link": "https://svn.example.com/repo",
        }
    )
    datasource = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name="ds"),
        spec=spec,
    )
    agent = WorkflowAssistant(
        id="a1",
        name="agent",
        model="gpt",
        system_prompt="p",
        datasource_ids=["ds"],
    )
    definition = WorkflowDefinition(
        name="wf",
        description="d",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={"a1": agent},
    )
    workflow = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.WORKFLOW, name="wf"),
        spec=WorkflowSpec(workflow=definition),
    )
    return [workflow, datasource]


def _apply(monkeypatch, misses):
    waits = []
    monkeypatch.setattr(lookup, "_wait", waits.append)
    client = FakeClient(datasources=_SlowListing(misses))
    return BulkCreator(client).create_all(_documents(), TARGET), client, waits


def test_workflow_is_created_once_the_datasource_is_listed(monkeypatch):
    report, client, waits = _apply(monkeypatch, misses=3)
    assert report.failed is None
    assert (
        "ds-id" in client.workflows.calls_to("create_workflow")[0].args[0].yaml_config
    )
    assert 0 < len(waits) <= lookup._ID_WAIT_ATTEMPTS


def test_a_datasource_that_never_shows_up_fails_with_a_bounded_wait(monkeypatch):
    report, client, waits = _apply(monkeypatch, misses=10_000)
    assert report.failed is not None
    assert report.failed.error_type == "unresolved_reference"
    assert "created but is still not listed" in report.failed.reason
    assert len(waits) == lookup._ID_WAIT_ATTEMPTS
    assert client.workflows.calls_to("create_workflow") == []
