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
    assert "environ" not in calls


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


def test_plan_without_id_is_accepted_by_parser(target, monkeypatch):
    monkeypatch.setattr(
        main_module, "plan_command", lambda f, i, **k: ExitStatus.SUCCESS
    )
    assert main(["plan", "f.yaml"]) == 0
