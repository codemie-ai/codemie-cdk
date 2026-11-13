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

"""The CLI's local/remote rule and login plan against the pinned SDK.

Rerun on every change of the ``codemie-sdk-python`` pin.
"""

from unittest.mock import patch

import pytest
from codemie_sdk import CodeMieClient

from codemie_iac.cli.config_model import ConfigError
from codemie_iac.cli.target_config import TargetConfig, is_local_url

__all__: list[str] = []

URLS = [
    "http://localhost:8080",
    "http://LOCALHOST",
    "http://127.0.0.1:8080",
    "http://0.0.0.0",
    "http://192.168.1.10",
    "https://api.example.com",
    "https://codemie.example.org/api",
    "https://localhost.example.com",
    "https://x/192.168",
]
_SDK = "codemie_sdk.client.client"


def _construct(**kwargs):
    with (
        patch(f"{_SDK}.LocalAuthCredentials") as local,
        patch(f"{_SDK}.KeycloakCredentials") as keycloak,
    ):
        CodeMieClient(**kwargs)
    return local, keycloak


def _sdk_is_local(url: str) -> bool:
    check = getattr(CodeMieClient, "_is_localhost_domain", None)
    if check is not None:
        return check(url)
    local, _ = _construct(
        auth_server_url="",
        auth_realm_name="",
        codemie_api_domain=url,
        username="u",
        password="p",
    )
    return local.called


@pytest.mark.parametrize("url", URLS)
def test_cli_rule_agrees_with_sdk(url):
    assert is_local_url(url) is _sdk_is_local(url)


def test_substring_behaviour_is_recorded():
    assert is_local_url("https://localhost.example.com")
    assert is_local_url("https://x/192.168")
    assert not is_local_url("https://api.example.com")


def _target(tmp_path, environment):
    path = tmp_path / "codemie.yaml"
    path.write_text(f"project:\n  name: p\nenvironment:\n{environment}")
    return TargetConfig.resolve(None, str(path), {})


def _build(tmp_path, environment):
    with (
        patch(f"{_SDK}.LocalAuthCredentials") as local,
        patch(f"{_SDK}.KeycloakCredentials") as keycloak,
    ):
        _target(tmp_path, environment).build_client()
    return local, keycloak


def test_local_with_credentials_builds_a_local_login(tmp_path):
    local, keycloak = _build(
        tmp_path,
        "  codemie_api_url: http://localhost:8080\n  username: u\n  password: p\n",
    )
    assert local.call_args.kwargs["email"] == "u"
    assert local.call_args.kwargs["password"] == "p"
    keycloak.assert_not_called()


def test_local_without_credentials_is_rejected_before_the_sdk(tmp_path):
    with pytest.raises(ConfigError, match="environment.username"):
        _target(tmp_path, "  codemie_api_url: http://localhost:8080\n")


KEYCLOAK = "  auth_server_url: https://kc.example.com\n  auth_realm_name: r\n"


def test_remote_client_credentials_reach_keycloak(tmp_path):
    local, keycloak = _build(
        tmp_path,
        f"  codemie_api_url: https://api.example.com\n{KEYCLOAK}"
        "  client_id: c\n  client_secret: s\n",
    )
    local.assert_not_called()
    kwargs = keycloak.call_args.kwargs
    assert (kwargs["client_id"], kwargs["client_secret"]) == ("c", "s")
    assert kwargs["username"] is None


def test_remote_username_password_reach_keycloak(tmp_path):
    _, keycloak = _build(
        tmp_path,
        f"  codemie_api_url: https://api.example.com\n{KEYCLOAK}"
        "  client_id: c\n  username: u\n  password: p\n",
    )
    kwargs = keycloak.call_args.kwargs
    assert (kwargs["username"], kwargs["password"]) == ("u", "p")
    assert kwargs["client_id"] == "c" and kwargs["client_secret"] is None


def test_sdk_prefers_username_password_when_given_both_pairs():
    """Why the CLI rejects both pairs: the SDK would pick the password grant."""
    from codemie_sdk.auth.credentials import KeycloakCredentials

    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "t"}

    with patch("codemie_sdk.auth.credentials.requests.post") as post:
        post.return_value = _Response()
        KeycloakCredentials(
            "https://kc.example.com", "r", "c", "s", "u", "p"
        ).get_token()
    assert post.call_args.kwargs["data"]["grant_type"] == "password"
