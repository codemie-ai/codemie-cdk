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

"""Tests for ``codemie-iac init``."""

import json

import yaml

from codemie_iac.cli.config_model import ENVIRONMENT_KEYS, load_config
from codemie_iac.cli.main import main
from codemie_iac.cli.target_config import TargetConfig

__all__: list[str] = []


def test_init_writes_template_without_login(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def no_resolve(*args, **kwargs):
        raise AssertionError("init must not resolve a target")

    monkeypatch.setattr("codemie_iac.cli.main.TargetConfig.resolve", no_resolve)
    assert main(["init"]) == 0
    assert (tmp_path / "codemie.yaml").is_file()
    assert "codemie.yaml" in capsys.readouterr().out


def test_init_json_output_parses(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["path"].endswith("codemie.yaml")


def test_init_uses_global_config_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["-c", str(tmp_path / "other.yaml"), "init"]) == 0
    assert (tmp_path / "other.yaml").is_file()
    assert not (tmp_path / "codemie.yaml").exists()


def test_second_run_exits_4_and_keeps_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "codemie.yaml"
    target.write_bytes(b"project:\n  name: mine\n")
    before = target.read_bytes()
    assert main(["init"]) == 4
    assert target.read_bytes() == before
    assert "--force" in capsys.readouterr().out


def test_write_failure_exits_4(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    missing_dir = str(tmp_path / "nope" / "codemie.yaml")
    assert main(["-c", missing_dir, "init"]) == 4
    assert main(["-c", missing_dir, "init", "--force"]) == 4


def test_force_replaces_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "codemie.yaml"
    target.write_text("project:\n  name: mine\n")
    assert main(["init", "--force"]) == 0
    assert "mine" not in target.read_text()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["codemie.yaml"]


def test_template_parses_with_zero_warnings_and_covers_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    text = (tmp_path / "codemie.yaml").read_text()
    doc = yaml.safe_load(text.replace("${", "").replace(":-}", ""))
    assert set(doc["environment"]) == set(ENVIRONMENT_KEYS)
    assert "name" in doc["project"]
    assert text.count(":-}") == len(ENVIRONMENT_KEYS) + 1


def test_local_setup_through_template_variables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    env = {
        "CODEMIE_PROJECT": "demo",
        "CODEMIE_API_URL": "http://localhost:8080",
        "CODEMIE_USERNAME": "u",
        "CODEMIE_PASSWORD": "p",
    }
    target = TargetConfig.resolve(None, None, env)
    assert target.project == "demo"
    assert target.warnings == ()


def test_unset_template_has_no_model_warnings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    doc = yaml.safe_load((tmp_path / "codemie.yaml").read_text())
    expanded = {
        "project": {"name": ""},
        "environment": {key: "" for key in doc["environment"]},
    }
    assert load_config(expanded)[1] == []
