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

Every connection setting comes from ``codemie.yaml`` (``project.name`` and the
``environment:`` mapping), except ``--project``, which overrides the project.
String values in the file may reference ``${NAME}`` / ``${NAME:-default}``; the
real environment and a ``.env`` file only feed those references and the
``env:NAME`` credentials of the documents.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import yaml
from codemie_sdk import CodeMieClient

from .config_model import ConfigError, EnvironmentSection, load_config
from .env_file import read_env_file

__all__ = ["ConfigError", "TargetConfig", "DEFAULT_CONFIG_PATH", "is_local_url"]

DEFAULT_CONFIG_PATH = "./codemie.yaml"
DEFAULT_ENV_FILE = "./.env"

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_LOCAL_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0", "192.168")
_CLIENT_PAIR = (
    ("client_id", "auth_client_id"),
    ("client_secret", "auth_client_secret"),
)
_USER_PAIR = (("username", "username"), ("password", "password"))


def is_local_url(url: str) -> bool:
    """Same rule as the SDK: the lower-cased URL contains a local marker."""
    lowered = url.lower()
    return any(marker in lowered for marker in _LOCAL_MARKERS)


@dataclass(frozen=True)
class LoginPlan:
    """How to log in: ``local``, ``client_credentials`` or ``password``."""

    kind: str
    client_args: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class TargetConfig:
    """Resolved target project and client connection settings."""

    project: str
    _login: LoginPlan = field(repr=False)
    _verify_ssl: bool = True
    _environ: Mapping[str, str] = field(default_factory=dict, repr=False)
    warnings: tuple[str, ...] = ()

    @classmethod
    def resolve(
        cls,
        project_flag: Optional[str],
        config_path: Optional[str],
        environ: Optional[Mapping[str, str]] = None,
        env_file: Optional[str] = None,
    ) -> "TargetConfig":
        """Read ``codemie.yaml``; ``--project`` overrides ``project.name``."""
        real = os.environ if environ is None else environ
        env = {**_load_env_file(env_file), **real}
        path = config_path or DEFAULT_CONFIG_PATH
        warnings: list[str] = []
        try:
            return cls._build(project_flag, path, env, warnings)
        except ConfigError as exc:
            if not exc.warnings:
                exc.warnings = tuple(warnings)
            raise

    @classmethod
    def _build(
        cls,
        project_flag: Optional[str],
        path: str,
        env: Mapping[str, str],
        warnings: list[str],
    ) -> "TargetConfig":
        document = _expand(_load_document(path), env)
        config, found = load_config(document)
        warnings.extend(found)
        project = project_flag or config.project.name
        if not project:
            raise ConfigError(
                f"Missing project: use --project or set project.name in {path}"
            )
        settings = config.environment
        if not settings.codemie_api_url:
            raise ConfigError(f"Missing environment.codemie_api_url in {path}")
        if not settings.verify_ssl:
            warnings.append(
                "environment.verify_ssl is false: TLS certificates are not verified"
            )
        return cls(
            project=project,
            _login=_login_plan(settings),
            _verify_ssl=settings.verify_ssl,
            _environ=env,
            warnings=tuple(warnings),
        )

    @property
    def environment(self) -> Mapping[str, str]:
        """Real environment merged over ``.env``; what ``env:NAME`` credentials read."""
        return self._environ

    def build_client(self) -> CodeMieClient:
        """Construct the platform client from the stored login plan."""
        return CodeMieClient(**self._login.client_args, verify_ssl=self._verify_ssl)


def _pair_args(
    settings: EnvironmentSection, pair: tuple[tuple[str, str], ...]
) -> dict[str, str]:
    values = {arg: getattr(settings, key) for key, arg in pair}
    return values if all(values.values()) else {}


def _has_any(settings: EnvironmentSection, pair: tuple[tuple[str, str], ...]) -> bool:
    return any(getattr(settings, key) for key, _ in pair)


def _missing(settings: EnvironmentSection, keys: tuple[str, ...]) -> list[str]:
    return [f"environment.{key}" for key in keys if not getattr(settings, key)]


def _local_plan(settings: EnvironmentSection) -> LoginPlan:
    missing = _missing(settings, ("username", "password"))
    if missing:
        raise ConfigError(
            "A local codemie_api_url needs username and password; missing "
            + ", ".join(missing)
        )
    # The SDK constructor requires the two Keycloak arguments even for a local URL.
    args = {
        "codemie_api_domain": settings.codemie_api_url,
        "auth_server_url": "",
        "auth_realm_name": "",
    }
    return LoginPlan("local", {**args, **_pair_args(settings, _USER_PAIR)})


def _remote_plan(settings: EnvironmentSection) -> LoginPlan:
    """Keycloak login: client_id + client_secret, or client_id + username + password."""
    missing = _missing(settings, ("auth_server_url", "auth_realm_name", "client_id"))
    uses_secret = bool(settings.client_secret)
    if not uses_secret:
        if _has_any(settings, _USER_PAIR):
            missing += _missing(settings, ("username", "password"))
        else:
            missing.append(
                "environment.client_secret "
                "(or environment.username and environment.password)"
            )
    if missing:
        raise ConfigError("A remote login is incomplete; missing " + ", ".join(missing))
    if uses_secret and _has_any(settings, _USER_PAIR):
        raise ConfigError(
            "A remote login is ambiguous: set environment.client_secret or "
            "environment.username and environment.password, not both"
        )
    args = {
        "codemie_api_domain": settings.codemie_api_url,
        "auth_server_url": settings.auth_server_url,
        "auth_realm_name": settings.auth_realm_name,
        "auth_client_id": settings.client_id,
    }
    if uses_secret:
        return LoginPlan(
            "client_credentials", {**args, "auth_client_secret": settings.client_secret}
        )
    return LoginPlan("password", {**args, **_pair_args(settings, _USER_PAIR)})


def _login_plan(settings: EnvironmentSection) -> LoginPlan:
    if is_local_url(settings.codemie_api_url):
        return _local_plan(settings)
    return _remote_plan(settings)


def _load_document(path: str) -> dict[str, Any]:
    """Parse the config file; a missing file is a config error."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
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


def _substitute(match: "re.Match[str]", env: Mapping[str, str]) -> str:
    name, default = match.group(1), match.group(2)
    found = env.get(name)
    if found:
        return found
    if default is None:
        raise ConfigError(
            f"codemie.yaml references ${{{name}}}, which is not set "
            f"(use ${{{name}:-}} to allow an empty value)"
        )
    return default


def _expand(value: Any, env: Mapping[str, str]) -> Any:
    """Expand ``${NAME}`` / ``${NAME:-default}`` in every string, recursively.

    A ``${NAME}`` that is unset or empty is a config error; ``${NAME:-}`` is how
    a value is allowed to be empty.
    """
    if isinstance(value, str):
        return _VAR.sub(lambda m: _substitute(m, env), value)
    if isinstance(value, dict):
        return {key: _expand(item, env) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item, env) for item in value]
    return value
