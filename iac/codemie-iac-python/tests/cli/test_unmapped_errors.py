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

"""Unmapped errors never escape as a traceback or as exit status 1."""

import io
import json

import pytest

from codemie_iac import serializer
from codemie_iac.cli import main as main_module
from codemie_iac.cli.commands.apply import apply_command
from codemie_iac.cli.commands.plan import plan_command
from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.cli.main import main
from codemie_iac.cli.target_config import TargetConfig
from codemie_iac.envelope import Bundle
from tests.plan_apply.fakes import FakeAssistants, FakeClient
from tests.plan_apply.test_single_entity_apply import _assistant

SECRET = "s3cr3t-in-exception-text"


def _doc(tmp_path):
    path = tmp_path / "a.yaml"
    path.write_text(serializer.to_yaml(Bundle([_assistant()])))
    return path


def _check(status, text, json_output, expected):
    assert status == expected
    assert status != ExitStatus.CHANGES_PENDING
    assert SECRET not in text
    assert "Traceback" not in text
    if json_output:
        assert json.loads(text)["exit_code"] == int(expected)


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("command", [plan_command, apply_command])
def test_missing_file_gives_five(tmp_path, command, as_json):
    out = io.StringIO()
    status = command(
        tmp_path / f"{SECRET}.yaml",
        "x",
        json_output=as_json,
        project="proj",
        client=FakeClient(),
        out=out,
    )
    assert status == ExitStatus.INVALID_DOCUMENT
    assert status != ExitStatus.CHANGES_PENDING
    if as_json:
        json.loads(out.getvalue())


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("command", [plan_command, apply_command])
def test_non_utf8_file_gives_five(tmp_path, command, as_json):
    path = tmp_path / "a.yaml"
    path.write_bytes(b"name: \xff\xfe\x80\n")
    out = io.StringIO()
    status = command(
        path, "x", json_output=as_json, project="p", client=FakeClient(), out=out
    )
    _check(status, out.getvalue(), as_json, ExitStatus.INVALID_DOCUMENT)


@pytest.mark.parametrize("as_json", [False, True])
def test_non_utf8_file_in_directory_gives_five(tmp_path, as_json):
    (tmp_path / "a.yaml").write_bytes(b"name: \xff\xfe\x80\n")
    out = io.StringIO()
    status = apply_command(
        tmp_path, None, json_output=as_json, project="p", client=FakeClient(), out=out
    )
    _check(status, out.getvalue(), as_json, ExitStatus.INVALID_DOCUMENT)


@pytest.mark.parametrize("as_json", [False, True])
def test_plan_client_generic_error_is_defined_status(tmp_path, as_json):
    client = FakeClient(assistants=FakeAssistants(get=RuntimeError(f"boom {SECRET}")))
    out = io.StringIO()
    status = plan_command(
        _doc(tmp_path),
        "asst-1",
        json_output=as_json,
        project="proj",
        client=client,
        out=out,
    )
    _check(status, out.getvalue(), as_json, ExitStatus.APPLY_FAILED)
    assert "RuntimeError" in out.getvalue()


@pytest.mark.parametrize("as_json", [False, True])
def test_apply_client_generic_error_is_apply_failed(tmp_path, as_json):
    client = FakeClient(
        assistants=FakeAssistants(create=RuntimeError(f"boom {SECRET}"))
    )
    out = io.StringIO()
    status = apply_command(
        _doc(tmp_path),
        None,
        json_output=as_json,
        project="proj",
        client=client,
        out=out,
    )
    _check(status, out.getvalue(), as_json, ExitStatus.APPLY_FAILED)


class _BadTarget:
    project = "demo"

    def build_client(self):
        raise RuntimeError(f"sdk exploded {SECRET}")


@pytest.mark.parametrize("as_json", [False, True])
def test_build_client_failure_is_config_error(monkeypatch, capsys, as_json):
    monkeypatch.setattr(
        main_module.TargetConfig, "resolve", lambda *a, **k: _BadTarget()
    )
    argv = ["plan", "f.yaml", "--id", "x"] + (["--json"] if as_json else [])
    code = main(argv)
    _check(ExitStatus(code), capsys.readouterr().out, as_json, ExitStatus.CONFIG_ERROR)


@pytest.mark.parametrize("as_json", [False, True])
def test_runner_generic_failure_is_apply_failed(monkeypatch, capsys, as_json):
    class _Target:
        project = "demo"

        def build_client(self):
            return object()

    def boom(*args, **kwargs):
        raise RuntimeError(f"boom {SECRET}")

    monkeypatch.setattr(main_module.TargetConfig, "resolve", lambda *a, **k: _Target())
    monkeypatch.setattr(main_module, "plan_command", boom)
    argv = ["plan", "f.yaml"] + (["--json"] if as_json else [])
    code = main(argv)
    _check(ExitStatus(code), capsys.readouterr().out, as_json, ExitStatus.APPLY_FAILED)


def test_non_utf8_config_is_config_error(tmp_path):
    path = tmp_path / "codemie.yaml"
    path.write_bytes(b"project: \xff\xfe\x80\n")
    from codemie_iac.cli.target_config import ConfigError

    with pytest.raises(ConfigError):
        TargetConfig.resolve("p", str(path), environ={})
