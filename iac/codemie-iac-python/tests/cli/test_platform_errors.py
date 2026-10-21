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

"""The CLI shows the platform's reason and the rule an invalid document broke."""

import io
import json

import pytest
import requests

from codemie_iac import Bundle, Document, DocumentKind, DocumentMeta, to_yaml
from codemie_iac.cli.commands.apply import apply_command
from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.specs.skill import SkillSpec
from tests.plan_apply.fakes import FakeClient

__all__: list[str] = []

SKILL = dict(name="skill-x", description="A valid skill description", content="c" * 100)


class _Response:
    def __init__(self, status, body=None, text=""):
        self.status_code = status
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _http_error(response):
    exc = requests.HTTPError("422 Client Error: Unprocessable Entity")
    exc.response = response
    return exc


class _Failing:
    def __init__(self, exc):
        self.exc = exc

    def __getattr__(self, name):
        def call(*args, **kwargs):
            raise self.exc

        return call


def _skill_file(tmp_path):
    doc = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.SKILL, name="skill-x"),
        spec=SkillSpec(**SKILL, project="proj"),
    )
    path = tmp_path / "s.yaml"
    path.write_text(to_yaml(Bundle([doc])))
    return path


@pytest.mark.parametrize("as_dir", [False, True])
def test_apply_shows_platform_message_for_http_errors(tmp_path, as_dir):
    body = {"error": {"message": "content: String should have at least 100"}}
    client = FakeClient(skills=_Failing(_http_error(_Response(422, body))))
    out = io.StringIO()
    path = _skill_file(tmp_path)
    status = apply_command(
        tmp_path if as_dir else path,
        None,
        json_output=False,
        project="proj",
        client=client,
        out=out,
    )
    assert status == ExitStatus.APPLY_FAILED
    assert "content: String should have at least 100" in out.getvalue()


def test_apply_json_includes_platform_message(tmp_path):
    body = {"error": {"message": "indexType: Field required"}}
    client = FakeClient(skills=_Failing(_http_error(_Response(422, body))))
    out = io.StringIO()
    apply_command(
        _skill_file(tmp_path),
        None,
        json_output=True,
        project="proj",
        client=client,
        out=out,
    )
    data = json.loads(out.getvalue())
    assert any(
        "indexType: Field required" in e["message"] for e in data["structured_errors"]
    )


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("as_dir", [False, True])
def test_platform_message_never_leaks_resolved_credential(
    tmp_path, monkeypatch, as_json, as_dir
):
    from tests.cli.test_apply_command import _secret_integration, _write

    monkeypatch.setenv("LEAK_VAR", "s3cr3t-token-value")
    body = {"error": {"message": "bad token s3cr3t-token-value"}}
    client = FakeClient(integrations=_Failing(_http_error(_Response(422, body))))
    path = _write(tmp_path / "i.yaml", _secret_integration())
    out = io.StringIO()
    status = apply_command(
        tmp_path if as_dir else path,
        None,
        json_output=as_json,
        project="proj",
        client=client,
        out=out,
    )
    assert status == ExitStatus.APPLY_FAILED
    assert "s3cr3t-token-value" not in out.getvalue()
    assert "bad token" in out.getvalue()


def test_invalid_document_error_names_field_and_rule_not_input(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "version: v1\nmeta: {kind: skill, name: bad-skill}\n"
        "spec: {name: bad-skill, description: A long enough description,"
        " content: SECRET-INPUT-VALUE}\n"
    )
    out = io.StringIO()
    status = apply_command(
        path, None, json_output=False, project="proj", client=FakeClient(), out=out
    )
    assert status == ExitStatus.INVALID_DOCUMENT
    assert "content" in out.getvalue()
    assert "at least 100 characters" in out.getvalue()
    assert "SECRET-INPUT-VALUE" not in out.getvalue()


def test_render_error_shows_platform_message_of_an_unwrapped_http_error():
    """A failing read while planning is not wrapped in PlatformRejectionError."""
    from codemie_iac.cli.render import render_error

    exc = _http_error(_Response(404, {"error": {"message": "Assistant not found"}}))
    text = render_error(exc, json_output=False, status=ExitStatus.APPLY_FAILED)
    assert "404: Assistant not found" in text
