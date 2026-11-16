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

import io

import requests

from codemie_iac.cli.commands.export import export_command
from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.cli.main import main
from codemie_iac.envelope import Bundle, Document
from codemie_iac.serializer import to_yaml
from tests.plan_apply.fakes import FakeClient, FakeExport

CATEGORY = {
    "version": "v1",
    "meta": {"kind": "category", "name": "cat1"},
    "spec": {"name": "cat1", "description": "A category"},
}
INTEGRATION = {
    "version": "v1",
    "meta": {"kind": "integration", "name": "jira"},
    "spec": {
        "alias": "jira",
        "credential_type": "Jira",
        "credential_values": [{"key": "token", "ref": "env:JIRA_TOKEN"}],
    },
}
EXPECTED = to_yaml(Bundle([Document.model_validate(CATEGORY)]))


def _client(**kw):
    return FakeClient(export=FakeExport({("category", "c1"): CATEGORY}, **kw))


def _run(client, out_path=None, kind="category", environ=None):
    out = io.StringIO()
    status = export_command(
        kind, "c1", out_path, project="p", client=client, out=out, environ=environ
    )
    return status, out.getvalue()


def test_prints_yaml_to_out():
    status, text = _run(_client())
    assert status == ExitStatus.SUCCESS
    assert text == EXPECTED


def test_out_path_writes_file_and_keeps_out_empty(tmp_path):
    target = tmp_path / "c.yaml"
    status, text = _run(_client(), str(target))
    assert status == ExitStatus.SUCCESS
    assert text == ""
    assert target.read_text() == EXPECTED


def test_http_error_writes_no_file(tmp_path):
    target = tmp_path / "c.yaml"
    error = requests.HTTPError("500 Server Error")
    status, text = _run(_client(error=error), str(target))
    assert status == ExitStatus.APPLY_FAILED
    assert "HTTPError" in text or "HTTP" in text
    assert not target.exists()


def test_existing_out_file_untouched_on_failure(tmp_path):
    target = tmp_path / "c.yaml"
    target.write_text("keep")
    status, _ = _run(_client(), str(target), kind="skill")
    assert status == ExitStatus.APPLY_FAILED
    assert target.read_text() == "keep"


def test_credential_is_a_reference_only():
    client = FakeClient(export=FakeExport({("integration", "c1"): INTEGRATION}))
    status, text = _run(
        client, kind="integration", environ={"JIRA_TOKEN": "s3cret-value"}
    )
    assert status == ExitStatus.SUCCESS
    assert "env:JIRA_TOKEN" in text
    assert "s3cret-value" not in text


def test_bogus_kind_is_a_usage_error():
    assert main(["export", "bogus", "x"]) == int(ExitStatus.CONFIG_ERROR)


def test_json_flag_is_rejected():
    assert main(["export", "category", "x", "--json"]) == int(ExitStatus.CONFIG_ERROR)
