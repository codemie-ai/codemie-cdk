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

"""Tests for the static bearer-token client used in JWT mode."""

import re
from pathlib import Path
from unittest.mock import patch

import codemie_iac.plan_apply as plan_apply_pkg
from codemie_iac.cli.token_client import TokenClient

__all__: list[str] = []


def _engine_services() -> set[str]:
    """Every ``client.<service>`` attribute and ``service="<name>"`` the engine uses."""
    found: set[str] = set()
    for path in Path(plan_apply_pkg.__file__).parent.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r"\bclient\.([a-z_]+)\b", text))
        found.update(re.findall(r"service=\"([a-z_]+)\"", text))
    return found


def test_engine_service_set_is_not_empty():
    assert {"assistants", "datasources", "workflows"} <= _engine_services()


def test_token_client_exposes_every_engine_service():
    client = TokenClient("https://api.example/", "jwt-value", verify_ssl=True)
    missing = [name for name in _engine_services() if not hasattr(client, name)]
    assert missing == []


def test_services_get_static_token_and_flags():
    with patch("codemie_iac.cli.token_client.AssistantService") as service:
        client = TokenClient("https://api.example/", "jwt-value", verify_ssl=False)
    service.assert_called_once_with(
        "https://api.example", "jwt-value", verify_ssl=False
    )
    assert client.assistants is service.return_value
