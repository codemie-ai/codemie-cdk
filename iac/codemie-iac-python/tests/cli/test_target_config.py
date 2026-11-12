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

"""Tests for TargetConfig resolution (everything comes from codemie.yaml)."""

from unittest.mock import patch

import pytest

from codemie_iac.cli.exit_status import ExitStatus, exit_status_for
from codemie_iac.cli.target_config import (
    ConfigError,
    TargetConfig,
    _expand,
    is_local_url,
)

__all__: list[str] = []

SECRET = "s3cr3t-value-xyz"
REMOTE = "https://api.example.com"
KEYCLOAK = "  auth_server_url: https://kc.example.com/auth\n  auth_realm_name: realm\n"


def _write(tmp_path, text):
    path = tmp_path / "codemie.yaml"
    path.write_text(text)
    return str(path)


def _cfg(tmp_path, environment, project="demo"):
    return _write(tmp_path, f"project:\n  name: {project}\nenvironment:\n{environment}")


def _client_kwargs(target):
    with patch("codemie_iac.cli.target_config.CodeMieClient") as client:
        target.build_client()
    return client.call_args.kwargs


def test_local_url_with_username_and_password(tmp_path):
    cfg = _cfg(
        tmp_path,
        "  codemie_api_url: http://localhost:8080\n  username: u\n  password: p\n",
    )
    target = TargetConfig.resolve(None, cfg, {})
    assert target.project == "demo"
    assert target._login.kind == "local"
    assert _client_kwargs(target) == {
        "codemie_api_domain": "http://localhost:8080",
        "auth_server_url": "",
        "auth_realm_name": "",
        "username": "u",
        "password": "p",
        "verify_ssl": True,
    }


@pytest.mark.parametrize(
    ("creds", "missing"),
    [
        ("", "environment.username"),
        ("  username: u\n", "environment.password"),
        ("  password: p\n", "environment.username"),
    ],
)
def test_local_without_full_pair_is_rejected(tmp_path, creds, missing):
    cfg = _cfg(tmp_path, f"  codemie_api_url: http://127.0.0.1\n{creds}")
    with pytest.raises(ConfigError, match=missing):
        TargetConfig.resolve(None, cfg, {})


def test_remote_client_credentials(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n{KEYCLOAK}  client_id: cid\n"
        f"  client_secret: {SECRET}\n",
    )
    target = TargetConfig.resolve(None, cfg, {})
    assert target._login.kind == "client_credentials"
    kwargs = _client_kwargs(target)
    assert kwargs["auth_client_id"] == "cid"
    assert kwargs["auth_server_url"] == "https://kc.example.com/auth"
    assert "username" not in kwargs


def test_remote_client_id_username_password(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n{KEYCLOAK}  client_id: c\n"
        "  username: u\n  password: p\n",
    )
    target = TargetConfig.resolve(None, cfg, {})
    kwargs = _client_kwargs(target)
    assert target._login.kind == "password"
    assert kwargs["auth_client_id"] == "c" and kwargs["username"] == "u"
    assert "auth_client_secret" not in kwargs


def test_remote_username_password_without_client_id_is_rejected(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n{KEYCLOAK}  username: u\n  password: p\n",
    )
    with pytest.raises(ConfigError, match="environment.client_id"):
        TargetConfig.resolve(None, cfg, {})


def test_remote_both_pairs_prefers_client_credentials(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n{KEYCLOAK}  client_id: c\n  client_secret: s\n"
        "  username: u\n  password: p\n",
    )
    target = TargetConfig.resolve(None, cfg, {})
    assert target._login.kind == "client_credentials"
    kwargs = _client_kwargs(target)
    assert "username" not in kwargs and "password" not in kwargs


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        (
            "  auth_realm_name: r\n  client_id: c\n  username: u\n  password: p\n",
            "auth_server_url",
        ),
        (
            "  auth_server_url: a\n  client_id: c\n  username: u\n  password: p\n",
            "auth_realm_name",
        ),
        ("  auth_server_url: a\n  auth_realm_name: r\n", "client_id"),
        (
            "  auth_server_url: a\n  auth_realm_name: r\n  client_id: c\n",
            "client_secret",
        ),
        (
            "  auth_server_url: a\n  auth_realm_name: r\n  client_id: c\n"
            "  username: u\n",
            "environment.password",
        ),
    ],
)
def test_remote_incomplete_names_environment_keys(tmp_path, body, missing):
    cfg = _cfg(tmp_path, f"  codemie_api_url: {REMOTE}\n{body}")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, cfg, {})
    assert missing in str(info.value)
    assert "environment." in str(info.value)


def test_client_id_without_secret_names_the_client_for_password_grant(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n{KEYCLOAK}  client_id: c\n"
        "  username: u\n  password: p\n",
    )
    target = TargetConfig.resolve(None, cfg, {})
    kwargs = _client_kwargs(target)
    assert target._login.kind == "password"
    assert kwargs["auth_client_id"] == "c" and "auth_client_secret" not in kwargs


def test_client_secret_without_id_is_not_replaced_by_password_grant(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n{KEYCLOAK}  client_secret: s\n"
        "  username: u\n  password: p\n",
    )
    with pytest.raises(ConfigError, match="environment.client_id"):
        TargetConfig.resolve(None, cfg, {})


def test_empty_value_counts_as_missing(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n{KEYCLOAK}  username: u\n  password: ''\n",
    )
    with pytest.raises(ConfigError, match="environment.password"):
        TargetConfig.resolve(None, cfg, {})


def test_missing_default_config_file_is_config_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match=r"codemie\.yaml"):
        TargetConfig.resolve("p", None, {})


def test_explicit_unreadable_path_raises(tmp_path):
    with pytest.raises(ConfigError, match="nope.yaml"):
        TargetConfig.resolve("p", str(tmp_path / "nope.yaml"), {})


def test_invalid_yaml_raises(tmp_path):
    with pytest.raises(ConfigError, match="not valid YAML"):
        TargetConfig.resolve("p", _write(tmp_path, "project: [unclosed\n"), {})


def test_empty_project_name_after_expansion_names_key_and_file(tmp_path):
    cfg = _write(
        tmp_path,
        "project:\n  name: ${PROJ:-}\nenvironment:\n  codemie_api_url: http://localhost\n",
    )
    with pytest.raises(ConfigError, match=r"project\.name.*codemie\.yaml"):
        TargetConfig.resolve(None, cfg, {})


def test_empty_api_url_after_expansion_names_key_and_file(tmp_path):
    cfg = _write(
        tmp_path, "project:\n  name: p\nenvironment:\n  codemie_api_url: ${U:-}\n"
    )
    with pytest.raises(ConfigError, match=r"environment\.codemie_api_url.*codemie"):
        TargetConfig.resolve(None, cfg, {})


def test_project_flag_overrides_file_and_allows_empty_name(tmp_path):
    cfg = _write(
        tmp_path,
        "project:\n  name: file\nenvironment:\n  codemie_api_url: http://localhost\n"
        "  username: u\n  password: p\n",
    )
    assert TargetConfig.resolve("flag", cfg, {}).project == "flag"


def test_fixed_name_variables_are_ignored(tmp_path):
    cfg = _cfg(
        tmp_path,
        "  codemie_api_url: http://localhost\n  username: u\n  password: p\n",
    )
    env = {
        "CODEMIE_PROJECT": "env",
        "CODEMIE_API_URL": "https://other.example.com",
        "CODEMIE_USERNAME": "x",
        "CODEMIE_VERIFY_SSL": "false",
    }
    target = TargetConfig.resolve(None, cfg, env)
    assert target.project == "demo"
    assert _client_kwargs(target)["username"] == "u"
    assert target.warnings == ()


def test_jwt_token_never_reaches_client_or_output(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: {REMOTE}\n  jwt_token: {SECRET}\n",
    )
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve(None, cfg, {})
    assert SECRET not in str(info.value)
    assert SECRET not in "".join(info.value.warnings)
    assert any("environment.jwt_token" in w for w in info.value.warnings)


def test_jwt_token_with_complete_login_is_only_a_warning(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: http://localhost\n  username: u\n  password: p\n"
        f"  jwt_token: {SECRET}\n",
    )
    target = TargetConfig.resolve(None, cfg, {})
    assert len(target.warnings) == 1
    assert SECRET not in target.warnings[0] + repr(target)
    assert SECRET not in str(_client_kwargs(target))


def test_api_section_is_unknown_and_not_a_fallback(tmp_path):
    cfg = _write(
        tmp_path,
        f"project:\n  name: p\napi:\n  url: {REMOTE}\n",
    )
    with pytest.raises(ConfigError, match="codemie_api_url") as info:
        TargetConfig.resolve(None, cfg, {})
    assert any("api" in w for w in info.value.warnings)


@pytest.mark.parametrize("value", ["false", "${NAME:-}"])
def test_verify_ssl_off_warns_once_and_is_passed(tmp_path, value):
    cfg = _cfg(
        tmp_path,
        "  codemie_api_url: http://localhost\n  username: u\n  password: p\n"
        f"  verify_ssl: {value}\n",
    )
    env = {"NAME": "FALSE"} if value.startswith("$") else {}
    target = TargetConfig.resolve(None, cfg, env)
    assert len([w for w in target.warnings if "verify_ssl" in w]) == 1
    assert _client_kwargs(target)["verify_ssl"] is False


def test_verify_ssl_empty_expansion_means_true(tmp_path):
    cfg = _cfg(
        tmp_path,
        "  codemie_api_url: http://localhost\n  username: u\n  password: p\n"
        "  verify_ssl: ${NAME:-}\n",
    )
    target = TargetConfig.resolve(None, cfg, {})
    assert target.warnings == ()
    assert _client_kwargs(target)["verify_ssl"] is True


@pytest.mark.parametrize("value", ["'0'", "flase"])
def test_verify_ssl_garbage_is_config_error(tmp_path, value):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: http://localhost\n  verify_ssl: {value}\n",
    )
    with pytest.raises(ConfigError, match=r"environment\.verify_ssl"):
        TargetConfig.resolve(None, cfg, {})


def test_wrongly_typed_section_does_not_leak_value(tmp_path):
    cfg = _write(tmp_path, f"project: {SECRET}\n")
    with pytest.raises(ConfigError) as info:
        TargetConfig.resolve("p", cfg, {})
    assert SECRET not in str(info.value)


def test_expansion_from_environment_mapping(tmp_path):
    cfg = _cfg(
        tmp_path,
        "  codemie_api_url: ${API:-http://localhost}\n  username: ${U}\n"
        "  password: ${P}\n",
    )
    kwargs = _client_kwargs(TargetConfig.resolve(None, cfg, {"U": "me", "P": "pw"}))
    assert (kwargs["codemie_api_domain"], kwargs["username"]) == (
        "http://localhost",
        "me",
    )


@pytest.mark.parametrize("environ", [{}, {"PW": ""}])
def test_unset_or_empty_variable_without_default_is_a_config_error(tmp_path, environ):
    cfg = _cfg(
        tmp_path,
        "  codemie_api_url: http://localhost\n  username: u\n  password: ${PW}\n",
    )
    with pytest.raises(ConfigError, match=r"\$\{PW\}.*not set"):
        TargetConfig.resolve(None, cfg, environ)


def test_expansion_nested_and_literal_dollar():
    assert _expand({"o": ["${V}", {"k": "${V:-z}"}, 3]}, {"V": "vv"}) == {
        "o": ["vv", {"k": "vv"}, 3]
    }
    assert _expand("pa$$word$x", {}) == "pa$$word$x"


def test_node_style_file_with_unset_bare_variable_is_a_config_error(tmp_path):
    """Observed: an unset bare ${X} in an uninspected section fails expansion."""
    cfg = _write(
        tmp_path,
        "version: '1'\nproject:\n  name: p\n  description: d\n"
        "environment:\n  codemie_api_url: http://localhost\n  username: u\n"
        "  password: p\nimported:\n  assistants: []\n"
        "resources:\n  assistants:\n    - name: a\n      token: ${NODE_ONLY_VAR}\n",
    )
    with pytest.raises(ConfigError, match=r"\$\{NODE_ONLY_VAR\}"):
        TargetConfig.resolve(None, cfg, {})
    ok = TargetConfig.resolve(None, cfg, {"NODE_ONLY_VAR": "x"})
    assert ok.warnings == ()


@pytest.mark.parametrize(
    ("url", "local"),
    [
        ("http://localhost:8080", True),
        ("http://LOCALHOST", True),
        ("http://127.0.0.1", True),
        ("http://0.0.0.0:1", True),
        ("http://192.168.1.5", True),
        ("https://api.example.com", False),
        ("https://localhost.example.com", True),
        ("https://x/192.168", True),
    ],
)
def test_is_local_url(url, local):
    assert is_local_url(url) is local


def test_secrets_not_in_repr(tmp_path):
    cfg = _cfg(
        tmp_path,
        f"  codemie_api_url: http://localhost\n  username: u\n  password: {SECRET}\n",
    )
    assert SECRET not in repr(TargetConfig.resolve(None, cfg, {}))


def test_config_error_maps_to_config_error_status():
    assert exit_status_for(ConfigError("x")) is ExitStatus.CONFIG_ERROR
