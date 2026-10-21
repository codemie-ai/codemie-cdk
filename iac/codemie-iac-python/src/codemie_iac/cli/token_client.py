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

"""Bearer-token client for JWT mode.

``CodeMieClient`` cannot take a plain JWT (its ``external_token`` goes through a
Keycloak exchange), but the SDK services accept a static token. This client
exposes every service the plan/apply engine uses, built as ``CodeMieClient`` does.
"""

from codemie_sdk.services.assistant import AssistantService
from codemie_sdk.services.categories import CategoryService
from codemie_sdk.services.datasource import DatasourceService
from codemie_sdk.services.integration import IntegrationService
from codemie_sdk.services.skill import SkillService
from codemie_sdk.services.workflow import WorkflowService

__all__ = ["TokenClient"]


class TokenClient:
    """Minimal ``CodeMieClient`` stand-in authenticated with a static bearer token."""

    def __init__(self, api_domain: str, token: str, verify_ssl: bool = True):
        domain = api_domain.rstrip("/")
        self.assistants = AssistantService(domain, token, verify_ssl=verify_ssl)
        self.categories = CategoryService(domain, token, verify_ssl=verify_ssl)
        self.datasources = DatasourceService(domain, token, verify_ssl=verify_ssl)
        self.integrations = IntegrationService(domain, token, verify_ssl=verify_ssl)
        self.skills = SkillService(domain, token, verify_ssl=verify_ssl)
        self.workflows = WorkflowService(domain, token, verify_ssl=verify_ssl)
