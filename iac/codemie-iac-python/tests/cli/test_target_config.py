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

"""Tests for TargetConfig resolution (flags > env > codemie.yaml)."""

from unittest.mock import patch

import pytest

from codemie_iac.cli.exit_status import ExitStatus, exit_status_for
from codemie_iac.cli.target_config import ConfigError, TargetConfig, _expand

__all__: list[str] = []

SECRET = "s3cr3t-value-xyz"
FULL_ENV = {
    "CODEMIE_API_URL": "https://api.env",
    "CODEMIE_AUTH_URL": "https://auth.env",
    "CODEMIE_REALM": "realm-env",
    "CODEMIE_CLIENT_ID": "cid",
    "CODEMIE_CLIENT_SECRET": SECRET,
    "CODEMIE_PROJECT": "env-proj",
}


def _write(tmp_path, text):
    path = tmp_path / "codemie.yaml"
    path.write_text(text)
    return str(path)


def test_flag_beats_env_and_file(tmp_path):
    cfg = _write(tmp_path, "project:\n  name: file-proj\n")
    assert TargetConfig.resolve("flag-proj", cfg, FULL_ENV).project == "flag-proj"


def test_env_beats_file(tmp_path):
    cfg = _write(tmp_path, "project:\n  name: file-proj\n")
    assert TargetConfig.resolve(None, cfg, FULL_ENV).project == "env-proj"


def test_file_supplies_project_and_api(tmp_path):
    cfg = _write(
        tmp_path,
        "project:\n  name: file-proj\napi:\n  url: https://api.file\n"
        "  auth_url: https://auth.file\n  realm: realm-file\n",
    )
    env = {"CODEMIE_CLIENT_ID": "cid", "CODEMIE_CLIENT_SECRET": SECRET}
    target = TargetConfig.resolve(None, cfg, env)
    assert target.project == "file-proj"
    with patch("codemie_iac.cli.target_config.CodeMieClient") as client:
        target.build_client()
    kwargs = client.call_args.kwargs
    assert kwargs["codemie_api_domain"] == "https://api.file"
    assert kwargs["auth_server_url"] == "https://auth.file"
    assert kwargs["auth_realm_name"] == "realm-file"


def test_env_api_beats_file_api(tmp_path):
    cfg = _write(
        tmp_path,
        "project:\n  name: p\napi:\n  url: https://api.file\n"
        "  auth_url: a\n  realm: r\n",
    )
    target = TargetConfig.resolve(None, cfg, FULL_ENV)
    with patch("codemie_iac.cli.target_config.CodeMieClient") as client:
        target.build_client()
    kwargs = client.call_args.kwargs
    assert kwargs["codemie_api_domain"] == "https://api.env"
    assert kwargs["auth_client_id"] == "cid"
    assert kwargs["auth_client_secret"] == SECRET


def test_missing_project_raises(tmp_path):
    env = {k: v for k, v in FULL_ENV.items() if k != "CODEMIE_PROJECT"}
    with pytest.raises(ConfigError, match="project"):
        TargetConfig.resolve(None, str(tmp_path / "absent.yaml"), env)


def test_missing_api_field_raises_naming_key():
    env = {k: v for k, v in FULL_ENV.items() if k != "CODEMIE_REALM"}
    with pytest.raises(ConfigError, match="CODEMIE_REALM"):
        TargetConfig.resolve(None, None, env)


def test_invalid_yaml_raises(tmp_path):
    cfg = _write(tmp_path, "project: [unclosed\n")
    with pytest.raises(ConfigError, match="codemie.yaml|invalid"):
        TargetConfig.resolve(None, cfg, FULL_ENV)


def test_explicit_unreadable_path_raises(tmp_path):
    with pytest.raises(ConfigError):
        TargetConfig.resolve(None, str(tmp_path / "nope.yaml"), FULL_ENV)


def test_default_missing_file_ok_when_env_complete(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert TargetConfig.resolve(None, None, FULL_ENV).project == "env-proj"


def test_secrets_absent_from_error_text(tmp_path):
    env = {"CODEMIE_CLIENT_SECRET": SECRET, "CODEMIE_PASSWORD": SECRET}
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, str(tmp_path / "absent.yaml"), env)
    assert SECRET not in str(info.value)


def test_config_error_maps_to_config_error_status():
    assert exit_status_for(ConfigError("x")) is ExitStatus.CONFIG_ERROR


# --- env expansion, environment: block, JWT mode, verify_ssl -------------------

JWT = "jwt-secret-abc"


def _build(tmp_path, text, env, project="p"):
    cfg = _write(tmp_path, f"project:\n  name: {project}\n{text}")
    target = TargetConfig.resolve(None, cfg, env)
    with (
        patch("codemie_iac.cli.target_config.CodeMieClient") as client,
        patch("codemie_iac.cli.target_config.TokenClient") as token,
    ):
        built = target.build_client()
    return built, client, token


def test_expansion_default_and_env(tmp_path):
    text = (
        "environment:\n  codemie_api_url: ${CODEMIE_API_URL:-https://dflt}\n"
        "  auth_server_url: ${AUTH_HOST}/auth\n  auth_realm_name: r\n"
    )
    _, client, _ = _build(tmp_path, text, {"AUTH_HOST": "https://kc"})
    kwargs = client.call_args.kwargs
    assert kwargs["codemie_api_domain"] == "https://dflt"
    assert kwargs["auth_server_url"] == "https://kc/auth"


def test_expansion_unset_and_empty_mean_not_set(tmp_path):
    text = "environment:\n  codemie_api_url: ${NOPE}\n  auth_server_url: ${EMPTY:-}\n"
    cfg = _write(tmp_path, f"project:\n  name: p\n{text}")
    with pytest.raises(ConfigError, match="CODEMIE_API_URL"):
        TargetConfig.resolve(None, cfg, {"EMPTY": ""})


def test_expansion_empty_var_uses_default(tmp_path):
    text = (
        "environment:\n  codemie_api_url: ${U:-https://d}\n"
        "  auth_server_url: a\n  auth_realm_name: r\n"
    )
    _, client, _ = _build(tmp_path, text, {"U": ""})
    assert client.call_args.kwargs["codemie_api_domain"] == "https://d"


def test_expansion_nested_and_literal_dollar(tmp_path):
    text = (
        "environment:\n  codemie_api_url: https://a\n  auth_server_url: a\n"
        "  auth_realm_name: r\n  password: pa$$word$x\n"
    )
    _, client, _ = _build(tmp_path, text, {})
    assert client.call_args.kwargs["password"] == "pa$$word$x"
    assert _expand({"o": ["${V}", {"k": "${V:-z}"}, 3]}, {"V": "vv"}) == {
        "o": ["vv", {"k": "vv"}, 3]
    }


def test_precedence_env_beats_environment_beats_api(tmp_path):
    text = (
        "environment:\n  codemie_api_url: https://envblock\n"
        "  auth_server_url: https://envblock-auth\n"
        "api:\n  url: https://api\n  auth_url: https://api-auth\n  realm: api-realm\n"
    )
    _, client, _ = _build(tmp_path, text, {"CODEMIE_API_URL": "https://procenv"})
    kwargs = client.call_args.kwargs
    assert kwargs["codemie_api_domain"] == "https://procenv"
    assert kwargs["auth_server_url"] == "https://envblock-auth"
    assert kwargs["auth_realm_name"] == "api-realm"


def test_environment_block_supplies_credentials(tmp_path):
    text = (
        "environment:\n  codemie_api_url: u\n  auth_server_url: a\n"
        "  auth_realm_name: r\n  client_id: cid\n  client_secret: sec\n"
        "  username: me\n  password: pw\n"
    )
    _, client, _ = _build(tmp_path, text, {})
    kwargs = client.call_args.kwargs
    assert (kwargs["auth_client_id"], kwargs["auth_client_secret"]) == ("cid", "sec")
    assert (kwargs["username"], kwargs["password"]) == ("me", "pw")


def test_jwt_from_env_uses_token_client_without_auth_url_realm(tmp_path):
    env = {"CODEMIE_API_URL": "https://api", "CODEMIE_JWT_TOKEN": JWT}
    built, client, token = _build(tmp_path, "", env)
    client.assert_not_called()
    token.assert_called_once_with("https://api", JWT, verify_ssl=True)
    assert built is token.return_value


def test_jwt_from_environment_block(tmp_path):
    text = "environment:\n  codemie_api_url: https://api\n  jwt_token: ${T}\n"
    _, client, token = _build(tmp_path, text, {"T": JWT})
    client.assert_not_called()
    assert token.call_args.args == ("https://api", JWT)


def test_jwt_still_requires_api_url_without_leaking(tmp_path):
    cfg = _write(tmp_path, "project:\n  name: p\n")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, cfg, {"CODEMIE_JWT_TOKEN": JWT})
    assert "CODEMIE_API_URL" in str(info.value)
    assert JWT not in str(info.value)


def test_no_jwt_still_requires_auth_url_and_realm(tmp_path):
    cfg = _write(tmp_path, "project:\n  name: p\n")
    with pytest.raises(ConfigError, match="CODEMIE_AUTH_URL"):
        TargetConfig.resolve(None, cfg, {"CODEMIE_API_URL": "u"})


def test_secrets_not_in_error_or_repr(tmp_path):
    env = {
        "CODEMIE_JWT_TOKEN": JWT,
        "CODEMIE_CLIENT_SECRET": SECRET,
        "CODEMIE_PASSWORD": SECRET,
    }
    cfg = _write(tmp_path, "project:\n  name: p\n")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(
            None, cfg, {k: v for k, v in env.items() if k != "CODEMIE_JWT_TOKEN"}
        )
    assert SECRET not in str(info.value)
    ok = TargetConfig.resolve(None, cfg, {**env, "CODEMIE_API_URL": "u"})
    assert JWT not in repr(ok) and SECRET not in repr(ok)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), ("true", True), ("", True), ("false", False), ("FALSE", False)],
)
def test_verify_ssl_parsing(tmp_path, value, expected):
    env = dict(FULL_ENV)
    if value is not None:
        env["CODEMIE_VERIFY_SSL"] = value
    _, client, _ = _build(tmp_path, "", env)
    assert client.call_args.kwargs["verify_ssl"] is expected


def test_verify_ssl_passed_to_token_client(tmp_path):
    env = {
        "CODEMIE_API_URL": "u",
        "CODEMIE_JWT_TOKEN": JWT,
        "CODEMIE_VERIFY_SSL": "False",
    }
    _, _, token = _build(tmp_path, "", env)
    assert token.call_args.kwargs["verify_ssl"] is False
