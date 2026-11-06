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


"""Builders for the write-path and error-reporting tests."""

from types import SimpleNamespace
import json
from codemie_sdk.models.integration import IntegrationType
from pydantic import TypeAdapter
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.single_apply import SingleEntityPlanner
from codemie_iac.specs.assistant import (
    AssistantSpec,
    MCPServerConfigSpec,
    MCPServerDetailsSpec,
)
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.integration import IntegrationSpec
from .fakes import (
    FakeAssistants,
    FakeCategories,
    FakeClient,
)

TARGET = "proj"


SECRET = "s3cr3t-token-value"


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant(name="a", **extra):
    spec = AssistantSpec(
        name=name,
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
        **extra,
    )
    return _doc(DocumentKind.ASSISTANT, name, spec)


def _integration(alias="jira"):
    spec = IntegrationSpec(
        project_name=TARGET,
        alias=alias,
        credential_type="Jira",
        credential_values=[],
        setting_type=IntegrationType.PROJECT,
    )
    return _doc(DocumentKind.INTEGRATION, alias, spec)


def _datasource(name="ds", setting_id="jira"):
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "knowledge_base_jira",
            "name": name,
            "project_name": TARGET,
            "description": "d",
            "jql": "project = A",
            "setting_id": setting_id,
        }
    )
    return _doc(DocumentKind.DATASOURCE, name, spec)


def _mcp_assistant(name="a"):
    server = MCPServerDetailsSpec(
        name="srv",
        enabled=True,
        config=MCPServerConfigSpec(command="npx", env={"TOKEN": "env:MCP_TOKEN"}),
    )
    return _assistant(name, mcp_servers=[server])


CREDS = {"MCP_TOKEN": SECRET}


def _real_http_error(message):
    """What the SDK raises: ``raise_for_status()`` on a failed request."""
    import requests

    response = requests.Response()
    response.status_code = 422
    response._content = json.dumps(
        {"detail": [{"loc": ["body", "token"], "msg": f"bad {SECRET}"}]}
    ).encode()
    response.request = requests.Request(
        "POST", "https://x/v1/assistants", data=json.dumps({"token": SECRET})
    ).prepare()
    return requests.HTTPError(message, response=response, request=response.request)


def _planner(client, creds=None):
    return SingleEntityPlanner(client, credentials=EnvCredentialResolver(creds or {}))


def _live_assistant(**over):
    live = {"id": "asst-1", "name": "a", "description": "d", "system_prompt": "p"}
    live.update(project=TARGET, llm_model_type="gpt", categories=[], assistant_ids=[])
    live.update(over)
    return SimpleNamespace(**live)


def _cat_client(live):
    return FakeClient(
        assistants=FakeAssistants(get=live),
        categories=FakeCategories(
            get_categories=[SimpleNamespace(id="cat-9", name="cat")]
        ),
    )
