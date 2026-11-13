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

"""Tests for ``.env`` loading (feeds ``${NAME}`` and ``env:NAME`` only)."""

import json
import os
from unittest.mock import patch

import pytest

from codemie_iac.cli import main as main_module
from codemie_iac.cli.exit_status import ExitStatus, exit_status_for
from codemie_iac.cli.main import main
from codemie_iac.cli.target_config import ConfigError, TargetConfig

__all__: list[str] = []

SECRET = "s3cr3t-value-xyz"
YAML = (
    "project:\n  name: ${PROJ:-}\nenvironment:\n"
    "  codemie_api_url: ${API:-http://localhost:8080}\n"
    "  username: ${USER_NAME:-u}\n  password: ${PW:-p}\n"
)


def _dotenv(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def _yaml(tmp_path, monkeypatch, text=YAML):
    (tmp_path / "codemie.yaml").write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)


def _kwargs(target):
    with patch("codemie_iac.cli.target_config.CodeMieClient") as client:
        target.build_client()
    return client.call_args.kwargs


def test_default_dotenv_in_cwd_is_picked_up(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", "PROJ=from-dotenv\n")
    assert TargetConfig.resolve(None, None, {}).project == "from-dotenv"


def test_env_file_override_replaces_default(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", "PROJ=default-one\n")
    other = _dotenv(tmp_path / "other.env", "PROJ=other-one\n")
    target = TargetConfig.resolve(None, None, {}, env_file=other)
    assert target.project == "other-one"


def test_explicit_missing_file_is_config_error_naming_path(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    missing = str(tmp_path / "nope.env")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve("p", None, {}, env_file=missing)
    assert missing in str(info.value)
    assert exit_status_for(info.value) == ExitStatus.CONFIG_ERROR


def test_missing_default_dotenv_is_ignored(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    assert TargetConfig.resolve("p", None, {}).project == "p"


def test_real_env_beats_dotenv(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", "API=http://127.0.0.1:1\nPROJ=dotenv\n")
    env = {"API": "http://localhost:2", "PROJ": "real"}
    target = TargetConfig.resolve(None, None, env)
    assert target.project == "real"
    assert _kwargs(target)["codemie_api_domain"] == "http://localhost:2"


def test_dotenv_fills_unset_variables(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", "USER_NAME=from-dotenv\n")
    kwargs = _kwargs(TargetConfig.resolve("p", None, {"PW": "real-pw"}))
    assert kwargs["username"] == "from-dotenv"
    assert kwargs["password"] == "real-pw"


def test_resolve_does_not_mutate_given_mapping_or_os_environ(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", "PROJ=x\nCODEMIE_ZZZ_TEST=1\n")
    monkeypatch.delenv("CODEMIE_ZZZ_TEST", raising=False)
    env = {"OTHER": "1"}
    TargetConfig.resolve(None, None, env)
    assert env == {"OTHER": "1"}
    assert "CODEMIE_ZZZ_TEST" not in os.environ


def test_dotenv_fixed_names_do_not_configure_the_connection(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(
        tmp_path / ".env",
        "CODEMIE_API_URL=https://api.dotenv\nCODEMIE_PROJECT=ignored\n",
    )
    with pytest.raises(ConfigError, match="Missing project"):
        TargetConfig.resolve(None, None, {})
    kwargs = _kwargs(TargetConfig.resolve("p", None, {}))
    assert kwargs["codemie_api_domain"] == "http://localhost:8080"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("PROJ=plain", "plain"),
        ("export PROJ=exported", "exported"),
        ("export   PROJ = spaced ", "spaced"),
        ('PROJ="double quoted"', "double quoted"),
        ("PROJ='single quoted'", "single quoted"),
        ("PROJ=\"mismatch'", "\"mismatch'"),
        ("PROJ=a=b", "a=b"),
    ],
)
def test_parsing_values(tmp_path, monkeypatch, line, expected):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", f"# comment\n\n{line}\n")
    assert TargetConfig.resolve(None, None, {}).project == expected


def test_parsing_skips_comments_and_bad_keys(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(
        tmp_path / ".env",
        "# PROJ=commented\n1BAD=x\nBAD-KEY=x\nno equals sign\n=novalue\nPROJ=good\n",
    )
    assert TargetConfig.resolve(None, None, {}).project == "good"


def test_empty_value_counts_as_not_set(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", "PROJ=\n")
    with pytest.raises(ConfigError, match="Missing project"):
        TargetConfig.resolve(None, None, {})


def test_non_utf8_file_is_config_error_without_content(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    (tmp_path / ".env").write_bytes(b"PROJ=" + SECRET.encode() + b"\xff\xfe\n")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, None, {})
    assert "./.env" in str(info.value)
    assert SECRET not in str(info.value)


def test_unreadable_default_path_is_config_error(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    (tmp_path / ".env").mkdir()  # a directory, not a file
    with pytest.raises(ConfigError):
        TargetConfig.resolve("p", None, {})


def test_secrets_never_in_error_text(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", f"PW={SECRET}\n")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, None, {})
    assert SECRET not in str(info.value)


def test_cli_passes_env_file_to_resolve(monkeypatch):
    seen = {}

    class _T:
        project = "demo"
        environment: dict = {}
        warnings: tuple = ()

        def build_client(self):
            return "client"

    def fake(project, config, environ=None, env_file=None):
        seen["env_file"] = env_file
        return _T()

    monkeypatch.setattr(main_module.TargetConfig, "resolve", fake)
    monkeypatch.setitem(
        main_module._COMMANDS,
        "plan",
        ("h", main_module._add_plan, lambda a, **k: ExitStatus.SUCCESS, True),
    )
    main(["--env-file", "x.env", "plan", "f.yaml", "--id", "x"])
    assert seen["env_file"] == "x.env"
    main(["plan", "f.yaml", "--id", "x"])
    assert seen["env_file"] is None


def test_cli_missing_env_file_exits_4_without_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    missing = str(tmp_path / "gone.env")
    code = main(["--env-file", missing, "--project", "p", "plan", "f.yaml", "--json"])
    assert code == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 4


def test_dotenv_value_reaches_credential_resolution(tmp_path, monkeypatch):
    _yaml(tmp_path, monkeypatch)
    _dotenv(tmp_path / ".env", f"CRED_VAR={SECRET}\n")
    monkeypatch.delenv("CRED_VAR", raising=False)
    target = TargetConfig.resolve("p", None, {})
    assert target.environment["CRED_VAR"] == SECRET
    assert "CRED_VAR" not in os.environ
    assert SECRET not in repr(target)


def test_real_env_beats_dotenv_for_credentials(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CRED_VAR=from-dotenv\n")
    _yaml(tmp_path, monkeypatch)
    target = TargetConfig.resolve("p", None, {"CRED_VAR": "from-shell"})
    assert target.environment["CRED_VAR"] == "from-shell"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("CODEMIE_PASSWORD=abc # prod", "abc"),
        ('K="v" # c', "v"),
        ("K='v w' # c", "v w"),
        ('K="a # b"', "a # b"),
        ("K=a#b", "a#b"),
    ],
)
def test_inline_comments_and_quotes_are_stripped(line, expected):
    from codemie_iac.cli.env_file import parse_env_text

    assert parse_env_text(line) == {line.split("=")[0]: expected}
