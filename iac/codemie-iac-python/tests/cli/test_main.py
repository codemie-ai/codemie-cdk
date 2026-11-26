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

import json
from pathlib import Path

import pytest

from codemie_iac.cli import main as main_module
from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.cli.main import main
from codemie_iac.cli.target_config import ConfigError


class _Target:
    project = "demo"
    environment = {"X": "1"}
    warnings = ("codemie.yaml: unknown key api is ignored",)

    def build_client(self):
        return "client"


@pytest.fixture
def target(monkeypatch):
    monkeypatch.setattr(main_module.TargetConfig, "resolve", lambda *a, **k: _Target())


@pytest.fixture
def no_config(monkeypatch):
    def fail(*args, **kwargs):
        raise ConfigError("Missing project")

    monkeypatch.setattr(main_module.TargetConfig, "resolve", fail)


def test_config_failure_returns_4(no_config):
    assert main(["plan", "f.yaml"]) == 4


def test_config_failure_json_is_parseable(no_config, capsys):
    assert main(["plan", "f.yaml", "--json"]) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 4


def test_usage_error_returns_4(capsys):
    assert main(["bogus"]) == 4


def test_help_returns_0(capsys):
    assert main(["--help"]) == 0


def test_plan_dispatch(target, monkeypatch):
    calls = {}

    def fake(file, entity_id, **kwargs):
        calls.update(file=file, entity_id=entity_id, **kwargs)
        return ExitStatus.CHANGES_PENDING

    monkeypatch.setattr(main_module, "plan_command", fake)
    code = main(["--project", "p", "plan", "f.yaml", "--id", "x", "--json"])
    assert code == 1
    assert calls["file"] == Path("f.yaml")
    assert calls["entity_id"] == "x"
    assert calls["json_output"] is True
    assert calls["project"] == "demo"
    assert calls["client"] == "client"
    assert calls["environ"] == {"X": "1"}


def test_apply_dispatch_without_id(target, monkeypatch):
    calls = {}

    def fake(path, entity_id, **kwargs):
        calls.update(path=path, entity_id=entity_id, **kwargs)
        return ExitStatus.SUCCESS

    monkeypatch.setattr(main_module, "apply_command", fake)
    assert main(["-c", "c.yaml", "apply", "dir"]) == 0
    assert calls["path"] == Path("dir")
    assert calls["entity_id"] is None
    assert calls["json_output"] is False
    assert calls["environ"] == {"X": "1"}


@pytest.mark.parametrize(
    "argv",
    [["plan", "f.yaml"], ["apply", "--id", "x", "."]],
    ids=["plan-without-id", "directory-with-id"],
)
def test_usage_errors_exit_4_before_the_client_is_built(monkeypatch, argv, capsys):
    def _resolve(*args, **kwargs):
        raise AssertionError("usage checks must run before any target is resolved")

    monkeypatch.setattr(main_module.TargetConfig, "resolve", _resolve)
    assert main(argv) == ExitStatus.CONFIG_ERROR
    assert "ConfigError" in capsys.readouterr().out


def test_warnings_go_to_stderr_once_and_json_stdout_parses(target, monkeypatch, capsys):
    def fake(file, entity_id, out, **kwargs):
        out.write('{"ok": true}\n')
        return ExitStatus.SUCCESS

    monkeypatch.setattr(main_module, "plan_command", fake)
    assert main(["plan", "f.yaml", "--id", "x", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": True}
    assert captured.err.count("unknown key api") == 1


def test_warnings_are_printed_when_resolve_fails(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise ConfigError("Missing environment.codemie_api_url", ("warn-one",))

    monkeypatch.setattr(main_module.TargetConfig, "resolve", fail)
    assert main(["plan", "f.yaml", "--id", "x", "--json"]) == 4
    captured = capsys.readouterr()
    assert captured.err == "warning: warn-one\n"
    assert json.loads(captured.out)["exit_code"] == 4


def test_command_without_target_skips_resolve(monkeypatch):
    def resolve(*args, **kwargs):
        raise AssertionError("resolve must not run")

    seen = {}

    def run(args, **context):
        seen.update(context)
        return ExitStatus.SUCCESS

    monkeypatch.setattr(main_module.TargetConfig, "resolve", resolve)
    monkeypatch.setitem(
        main_module._COMMANDS, "plan", ("h", main_module._add_plan, run, False)
    )
    assert main(["plan", "f.yaml", "--id", "x"]) == 0
    assert "client" not in seen
