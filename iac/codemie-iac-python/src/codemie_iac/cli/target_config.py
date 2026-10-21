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

"""Target project and platform connection settings for the plan/apply CLI.

Precedence per key: command-line flag > environment variable (the real
environment, then a ``.env`` file that only fills in unset names) > the
``environment:`` mapping of ``codemie.yaml`` > the legacy ``api:`` mapping.
String values in the file may reference ``${NAME}`` / ``${NAME:-default}``.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Union

import yaml
from codemie_sdk import CodeMieClient

from .env_file import read_env_file
from .token_client import TokenClient

__all__ = ["ConfigError", "TargetConfig", "DEFAULT_CONFIG_PATH"]

DEFAULT_CONFIG_PATH = "./codemie.yaml"
DEFAULT_ENV_FILE = "./.env"

#: client argument -> (env var, ``environment:`` key, legacy ``api:`` key)
_API_URL = ("codemie_api_domain", "CODEMIE_API_URL", "codemie_api_url", "url")
_KEYCLOAK = {
    "auth_server_url": ("CODEMIE_AUTH_URL", "auth_server_url", "auth_url"),
    "auth_realm_name": ("CODEMIE_REALM", "auth_realm_name", "realm"),
}
_OPTIONAL = {
    "auth_client_id": ("CODEMIE_CLIENT_ID", "client_id", None),
    "auth_client_secret": ("CODEMIE_CLIENT_SECRET", "client_secret", None),
    "username": ("CODEMIE_USERNAME", "username", None),
    "password": ("CODEMIE_PASSWORD", "password", None),
}
_JWT = ("CODEMIE_JWT_TOKEN", "jwt_token", None)
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(Exception):
    """Missing or invalid target configuration; the message never holds secrets."""


@dataclass(frozen=True)
class TargetConfig:
    """Resolved target project and client connection settings."""

    project: str
    _client_args: Mapping[str, Optional[str]] = field(repr=False)
    _jwt_token: Optional[str] = field(default=None, repr=False)
    _verify_ssl: bool = True
    _environ: Mapping[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def resolve(
        cls,
        project_flag: Optional[str],
        config_path: Optional[str],
        environ: Optional[Mapping[str, str]] = None,
        env_file: Optional[str] = None,
    ) -> "TargetConfig":
        """Merge flag, environment, ``.env`` and ``codemie.yaml`` values."""
        real = os.environ if environ is None else environ
        env = {**_load_env_file(env_file), **real}
        document = _expand(_load_document(config_path), env)
        project = project_flag or env.get("CODEMIE_PROJECT") or _file_project(document)
        if not project:
            raise ConfigError(
                "Missing project: use --project, CODEMIE_PROJECT or project.name "
                "in codemie.yaml"
            )
        jwt = _lookup(env, document, _JWT)
        return cls(
            project=project,
            _client_args=_client_args(env, document, bool(jwt)),
            _jwt_token=jwt,
            _verify_ssl=_verify_ssl(env),
            _environ=env,
        )

    @property
    def environment(self) -> Mapping[str, str]:
        """Real environment merged over ``.env``; what ``env:NAME`` credentials read."""
        return self._environ

    def build_client(self) -> Union[CodeMieClient, TokenClient]:
        """Construct the platform client (token client when a JWT is set)."""
        if self._jwt_token:
            return TokenClient(
                str(self._client_args["codemie_api_domain"]),
                self._jwt_token,
                verify_ssl=self._verify_ssl,
            )
        return CodeMieClient(**self._client_args, verify_ssl=self._verify_ssl)


def _load_document(config_path: Optional[str]) -> dict[str, Any]:
    """Parse the config file; only a missing *default* file is tolerated."""
    explicit = config_path is not None
    path = config_path if explicit else DEFAULT_CONFIG_PATH
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError:
        if explicit:
            raise ConfigError(f"Config file {path} cannot be read") from None
        return {}
    except (OSError, UnicodeDecodeError):
        raise ConfigError(f"Config file {path} cannot be read") from None
    except yaml.YAMLError:
        raise ConfigError(f"Config file {path} is not valid YAML") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must contain a YAML mapping")
    return data


def _load_env_file(env_file: Optional[str]) -> dict[str, str]:
    """Read ``.env``; only a missing *default* file is tolerated."""
    explicit = env_file is not None
    path = env_file if explicit else DEFAULT_ENV_FILE
    try:
        return read_env_file(path)
    except FileNotFoundError:
        if explicit:
            raise ConfigError(f"Env file {path} cannot be read") from None
        return {}
    except (OSError, UnicodeDecodeError):
        raise ConfigError(f"Env file {path} cannot be read") from None


def _mapping(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = document.get(key)
    return value if isinstance(value, dict) else {}


def _file_project(document: Mapping[str, Any]) -> Optional[str]:
    name = _mapping(document, "project").get("name")
    return str(name) if name else None


def _expand(value: Any, env: Mapping[str, str]) -> Any:
    """Expand ``${NAME}`` / ``${NAME:-default}`` in every string, recursively."""
    if isinstance(value, str):
        return _VAR.sub(lambda m: env.get(m.group(1)) or m.group(2) or "", value)
    if isinstance(value, dict):
        return {key: _expand(item, env) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item, env) for item in value]
    return value


def _verify_ssl(env: Mapping[str, str]) -> bool:
    return (env.get("CODEMIE_VERIFY_SSL") or "true").strip().lower() != "false"


def _lookup(
    env: Mapping[str, str],
    document: Mapping[str, Any],
    spec: tuple[str, str, Optional[str]],
) -> Optional[str]:
    """Environment variable > ``environment:`` value > legacy ``api:`` value."""
    env_name, env_key, api_key = spec
    value = env.get(env_name) or _mapping(document, "environment").get(env_key)
    if not value and api_key:
        value = _mapping(document, "api").get(api_key)
    return str(value) if value else None


def _require(
    env: Mapping[str, str],
    document: Mapping[str, Any],
    spec: tuple[str, str, Optional[str]],
) -> str:
    value = _lookup(env, document, spec)
    if not value:
        env_name, env_key, _ = spec
        raise ConfigError(
            f"Missing {env_name} (or environment.{env_key} in codemie.yaml)"
        )
    return value


def _client_args(
    env: Mapping[str, str], document: Mapping[str, Any], jwt_mode: bool
) -> dict[str, Optional[str]]:
    arg, env_name, env_key, api_key = _API_URL
    args: dict[str, Optional[str]] = {
        arg: _require(env, document, (env_name, env_key, api_key))
    }
    if jwt_mode:
        return args
    for arg, spec in _KEYCLOAK.items():
        args[arg] = _require(env, document, spec)
    for arg, spec in _OPTIONAL.items():
        args[arg] = _lookup(env, document, spec)
    return args
