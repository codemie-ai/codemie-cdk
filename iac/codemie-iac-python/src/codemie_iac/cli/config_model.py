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

"""Model of ``codemie.yaml``: known keys, unknown-key warnings, safe errors."""

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

__all__ = [
    "ConfigError",
    "CodemieConfig",
    "EnvironmentSection",
    "ENVIRONMENT_KEYS",
    "load_config",
]


class ConfigError(Exception):
    """Missing or invalid target configuration; the message never holds secrets."""

    def __init__(self, message: str, warnings: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.warnings = warnings


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ProjectSection(_Section):
    name: str = ""
    description: Any = None

    @field_validator("name", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return "" if value is None else str(value)


class EnvironmentSection(_Section):
    codemie_api_url: str = ""
    auth_server_url: str = ""
    auth_realm_name: str = ""
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""
    verify_ssl: bool = True

    @field_validator(
        "codemie_api_url",
        "auth_server_url",
        "auth_realm_name",
        "client_id",
        "client_secret",
        "username",
        "password",
        mode="before",
    )
    @classmethod
    def _text(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @field_validator("verify_ssl", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        if value is None or isinstance(value, bool):
            return True if value is None else value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("", "true"):
                return True
            if text == "false":
                return False
        raise ValueError("expected true or false")


class CodemieConfig(_Section):
    project: ProjectSection = ProjectSection()
    environment: EnvironmentSection = EnvironmentSection()
    # Node.js package keys: known, never inspected by the Python CLI.
    version: Any = None
    imported: Any = None
    tool_definitions: Any = None
    datasource_defaults: Any = None
    resources: Any = None


ENVIRONMENT_KEYS: tuple[str, ...] = tuple(EnvironmentSection.model_fields)


def _unknown_paths(doc: Mapping[str, Any]) -> list[str]:
    paths = [key for key in doc if key not in CodemieConfig.model_fields]
    for section, model in (
        ("project", ProjectSection),
        ("environment", EnvironmentSection),
    ):
        value = doc.get(section)
        if isinstance(value, dict):
            paths += [
                f"{section}.{key}" for key in value if key not in model.model_fields
            ]
    return [str(path) for path in paths]


def _error_text(exc: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(p) for p in err['loc'])} ({err['type']})"
        for err in exc.errors(
            include_input=False, include_context=False, include_url=False
        )
    ]
    return "codemie.yaml has invalid settings: " + ", ".join(parts)


def load_config(doc: Mapping[str, Any]) -> tuple[CodemieConfig, list[str]]:
    """Validate ``doc``; return the model and one warning per unknown key path."""
    warnings = [
        f"codemie.yaml: unknown key {path} is ignored" for path in _unknown_paths(doc)
    ]
    try:
        return CodemieConfig.model_validate(doc), warnings
    except ValidationError as exc:
        raise ConfigError(_error_text(exc), tuple(warnings)) from None
