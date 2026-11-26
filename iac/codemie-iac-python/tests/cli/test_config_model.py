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

import pytest

from codemie_iac.cli.config_model import (
    ENVIRONMENT_KEYS,
    ConfigError,
    load_config,
)

SECRET = "s3cr3t-value-xyz"


def test_unknown_keys_warn_once_by_path_without_values():
    doc = {
        "project": {"name": "demo"},
        "environment": {"codemie_api_url": "https://x", "jwt_token": SECRET},
        "api": {"url": SECRET},
    }
    model, warnings = load_config(doc)
    assert model.project.name == "demo"
    assert len(warnings) == 2
    assert any("environment.jwt_token" in text for text in warnings)
    assert any("key api " in text for text in warnings)
    assert all(SECRET not in text for text in warnings)


def test_node_keys_are_known_and_not_inspected():
    doc = {
        "version": "1",
        "project": {"name": "demo", "description": "d"},
        "imported": {"anything": [1]},
        "tool_definitions": {},
        "datasource_defaults": {"x": 1},
        "resources": {"assistants": []},
    }
    _, warnings = load_config(doc)
    assert warnings == []


def test_secret_in_wrongly_typed_field_not_in_error():
    with pytest.raises(ConfigError) as info:
        load_config({"project": SECRET})
    assert SECRET not in str(info.value)
    assert "project" in str(info.value)


def test_string_fields_are_coerced():
    model, _ = load_config({"environment": {"username": 42, "password": None}})
    assert model.environment.username == "42"
    assert model.environment.password == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", True),
        (None, True),
        (True, True),
        (False, False),
        ("TRUE", True),
        ("False", False),
        (" false ", False),
    ],
)
def test_verify_ssl_accepted(raw, expected):
    model, _ = load_config({"environment": {"verify_ssl": raw}})
    assert model.environment.verify_ssl is expected


@pytest.mark.parametrize("raw", ["0", "flase", "yes", 1])
def test_verify_ssl_rejected_names_key_not_value(raw):
    with pytest.raises(ConfigError) as info:
        load_config({"environment": {"verify_ssl": raw}})
    assert "environment.verify_ssl" in str(info.value)
    assert "flase" not in str(info.value)


def test_environment_keys_exposed_for_init_template():
    assert ENVIRONMENT_KEYS == (
        "codemie_api_url",
        "auth_server_url",
        "auth_realm_name",
        "client_id",
        "client_secret",
        "username",
        "password",
        "verify_ssl",
    )
