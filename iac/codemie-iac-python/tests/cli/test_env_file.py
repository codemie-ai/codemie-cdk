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

"""Tests for ``.env`` loading (merged into the resolve environment)."""

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
BASE = {
    "CODEMIE_API_URL": "https://api.real",
    "CODEMIE_AUTH_URL": "https://auth.real",
    "CODEMIE_REALM": "realm-real",
}


def _dotenv(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def _kwargs(target):
    with patch("codemie_iac.cli.target_config.CodeMieClient") as client:
        target.build_client()
    return client.call_args.kwargs


def test_default_dotenv_in_cwd_is_picked_up(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CODEMIE_PROJECT=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    target = TargetConfig.resolve(None, None, BASE)
    assert target.project == "from-dotenv"


def test_env_file_override_replaces_default(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CODEMIE_PROJECT=default-one\n")
    other = _dotenv(tmp_path / "other.env", "CODEMIE_PROJECT=other-one\n")
    monkeypatch.chdir(tmp_path)
    target = TargetConfig.resolve(None, None, BASE, env_file=other)
    assert target.project == "other-one"


def test_explicit_missing_file_is_config_error_naming_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    missing = str(tmp_path / "nope.env")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve("p", None, BASE, env_file=missing)
    assert missing in str(info.value)
    assert exit_status_for(info.value) == ExitStatus.CONFIG_ERROR


def test_missing_default_dotenv_is_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert TargetConfig.resolve("p", None, BASE).project == "p"


def test_real_env_beats_dotenv(tmp_path, monkeypatch):
    _dotenv(
        tmp_path / ".env",
        "CODEMIE_API_URL=https://api.dotenv\nCODEMIE_REALM=realm-dotenv\n",
    )
    monkeypatch.chdir(tmp_path)
    kwargs = _kwargs(TargetConfig.resolve("p", None, BASE))
    assert kwargs["codemie_api_domain"] == "https://api.real"
    assert kwargs["auth_realm_name"] == "realm-real"


def test_dotenv_fills_unset_variables(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CODEMIE_REALM=realm-dotenv\n")
    monkeypatch.chdir(tmp_path)
    env = {k: v for k, v in BASE.items() if k != "CODEMIE_REALM"}
    kwargs = _kwargs(TargetConfig.resolve("p", None, env))
    assert kwargs["auth_realm_name"] == "realm-dotenv"
    assert kwargs["codemie_api_domain"] == "https://api.real"


def test_resolve_does_not_mutate_given_mapping_or_os_environ(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CODEMIE_PROJECT=x\nCODEMIE_ZZZ_TEST=1\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CODEMIE_ZZZ_TEST", raising=False)
    env = dict(BASE)
    TargetConfig.resolve(None, None, env)
    assert env == BASE
    assert "CODEMIE_ZZZ_TEST" not in os.environ


def test_dotenv_value_feeds_yaml_reference(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CODEMIE_API_URL=https://api.dotenv\n")
    (tmp_path / "codemie.yaml").write_text(
        "project:\n  name: p\nenvironment:\n"
        "  codemie_api_url: ${CODEMIE_API_URL:-}\n"
        "  auth_server_url: https://auth.file\n  auth_realm_name: r\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    kwargs = _kwargs(TargetConfig.resolve(None, None, {}))
    assert kwargs["codemie_api_domain"] == "https://api.dotenv"


def test_dotenv_beats_codemie_yaml_environment(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CODEMIE_API_URL=https://api.dotenv\n")
    (tmp_path / "codemie.yaml").write_text(
        "project:\n  name: p\nenvironment:\n  codemie_api_url: https://api.file\n"
        "  auth_server_url: a\n  auth_realm_name: r\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    kwargs = _kwargs(TargetConfig.resolve(None, None, {}))
    assert kwargs["codemie_api_domain"] == "https://api.dotenv"


def test_jwt_mode_with_token_only_from_dotenv(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", f"CODEMIE_JWT_TOKEN={SECRET}\n")
    monkeypatch.chdir(tmp_path)
    target = TargetConfig.resolve("p", None, {"CODEMIE_API_URL": "https://api.real"})
    with patch("codemie_iac.cli.target_config.TokenClient") as token:
        target.build_client()
    assert token.call_args.args[:2] == ("https://api.real", SECRET)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("CODEMIE_PROJECT=plain", "plain"),
        ("export CODEMIE_PROJECT=exported", "exported"),
        ("export   CODEMIE_PROJECT = spaced ", "spaced"),
        ('CODEMIE_PROJECT="double quoted"', "double quoted"),
        ("CODEMIE_PROJECT='single quoted'", "single quoted"),
        ("CODEMIE_PROJECT=\"mismatch'", "\"mismatch'"),
        ("CODEMIE_PROJECT=a=b", "a=b"),
        ("CODEMIE_PROJECT=${OTHER}", "${OTHER}"),
    ],
)
def test_parsing_values(tmp_path, monkeypatch, line, expected):
    _dotenv(tmp_path / ".env", f"# comment\n\n{line}\n")
    monkeypatch.chdir(tmp_path)
    assert TargetConfig.resolve(None, None, BASE).project == expected


def test_parsing_skips_comments_and_bad_keys(tmp_path, monkeypatch):
    _dotenv(
        tmp_path / ".env",
        "# CODEMIE_PROJECT=commented\n"
        "1BAD=x\nBAD-KEY=x\nno equals sign\n=novalue\n"
        "CODEMIE_PROJECT=good\n",
    )
    monkeypatch.chdir(tmp_path)
    assert TargetConfig.resolve(None, None, BASE).project == "good"


def test_empty_value_counts_as_not_set(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CODEMIE_PROJECT=\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="Missing project"):
        TargetConfig.resolve(None, None, BASE)


def test_non_utf8_file_is_config_error_without_content(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_bytes(b"CODEMIE_PROJECT=" + SECRET.encode() + b"\xff\xfe\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, None, BASE)
    assert "./.env" in str(info.value)
    assert SECRET not in str(info.value)


def test_unreadable_default_path_is_config_error(tmp_path, monkeypatch):
    (tmp_path / ".env").mkdir()  # a directory, not a file
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        TargetConfig.resolve("p", None, BASE)


def test_secrets_never_in_error_text(tmp_path, monkeypatch):
    _dotenv(
        tmp_path / ".env",
        f"CODEMIE_CLIENT_SECRET={SECRET}\nCODEMIE_PASSWORD={SECRET}\n",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, None, {})
    assert SECRET not in str(info.value)
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve("p", None, {})
    assert SECRET not in str(info.value)


def test_cli_passes_env_file_to_resolve(monkeypatch):
    seen = {}

    class _T:
        project = "demo"

        def build_client(self):
            return "client"

    def fake(project, config, environ=None, env_file=None):
        seen["env_file"] = env_file
        return _T()

    monkeypatch.setattr(main_module.TargetConfig, "resolve", fake)
    monkeypatch.setitem(
        main_module._COMMANDS,
        "plan",
        ("h", main_module._add_plan, lambda a, **k: ExitStatus.SUCCESS),
    )
    main(["--env-file", "x.env", "plan", "f.yaml"])
    assert seen["env_file"] == "x.env"
    main(["plan", "f.yaml"])
    assert seen["env_file"] is None


def test_cli_missing_env_file_exits_4_without_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    missing = str(tmp_path / "gone.env")
    code = main(["--env-file", missing, "--project", "p", "plan", "f.yaml", "--json"])
    assert code == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 4


def test_dotenv_value_reaches_credential_resolution(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", f"CRED_VAR={SECRET}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CRED_VAR", raising=False)
    target = TargetConfig.resolve("p", None, BASE)
    assert target.environment["CRED_VAR"] == SECRET
    assert "CRED_VAR" not in os.environ
    assert SECRET not in repr(target)


def test_real_env_beats_dotenv_for_credentials(tmp_path, monkeypatch):
    _dotenv(tmp_path / ".env", "CRED_VAR=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    target = TargetConfig.resolve("p", None, {**BASE, "CRED_VAR": "from-shell"})
    assert target.environment["CRED_VAR"] == "from-shell"
