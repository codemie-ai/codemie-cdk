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

"""Recording fake codemie_sdk services for plan/apply tests.

Every fake records each call as a ``Call`` and returns a configurable
response (an ``Exception`` instance response is raised instead).
``FakeClient`` mirrors the service attributes of ``CodeMieClient``.
"""

from types import SimpleNamespace
from typing import Any, NamedTuple

__all__ = [
    "Call",
    "FakeAssistants",
    "FakeCategories",
    "FakeClient",
    "FakeDatasources",
    "FakeIntegrations",
    "FakeService",
    "FakeSkills",
    "FakeWorkflows",
]


class Call(NamedTuple):
    method: str
    args: tuple
    kwargs: dict


class FakeService:
    """Base fake: records calls; ``responses`` maps method name -> response."""

    DEFAULTS: dict[str, Any] = {}

    def __init__(self, **responses: Any):
        self.calls: list[Call] = []
        self.responses: dict[str, Any] = {**self.DEFAULTS, **responses}

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(Call(method, args, kwargs))
        response = self.responses.get(method)
        if isinstance(response, Exception):
            raise response
        return response

    def calls_to(self, method: str) -> list[Call]:
        return [c for c in self.calls if c.method == method]


class FakeAssistants(FakeService):
    DEFAULTS = {
        "create": SimpleNamespace(message="ok", assistant_id="asst-1"),
        "update": SimpleNamespace(message="ok", validation=None),
        "get": SimpleNamespace(id="asst-1", name="a"),
    }

    def create(self, request):
        return self._call("create", request)

    def update(self, assistant_id, request):
        return self._call("update", assistant_id, request)

    def get(self, assistant_id):
        return self._call("get", assistant_id)


class FakeSkills(FakeService):
    DEFAULTS = {
        "create": SimpleNamespace(id="skill-1"),
        "update": SimpleNamespace(id="skill-1"),
        "get": SimpleNamespace(id="skill-1"),
    }

    def create(self, request):
        return self._call("create", request)

    def update(self, skill_id, request):
        return self._call("update", skill_id, request)

    def get(self, skill_id):
        return self._call("get", skill_id)


class FakeWorkflows(FakeService):
    DEFAULTS = {
        "create_workflow": {"id": "wf-1"},
        "update": {"id": "wf-1"},
        "get": SimpleNamespace(id="wf-1"),
    }

    def create_workflow(self, request):
        return self._call("create_workflow", request)

    def update(self, workflow_id, request):
        return self._call("update", workflow_id, request)

    def get(self, workflow_id):
        return self._call("get", workflow_id)


class FakeDatasources(FakeService):
    # The real datasource create/update responses carry no entity id.
    DEFAULTS = {
        "create": {"message": "indexing started"},
        "update": {"message": "ok"},
        "get": SimpleNamespace(id="ds-1"),
    }

    def create(self, request):
        return self._call("create", request)

    def update(self, datasource_id, request, files=None):
        return self._call("update", datasource_id, request, files=files)

    def get(self, datasource_id):
        return self._call("get", datasource_id)


class FakeIntegrations(FakeService):
    DEFAULTS = {
        "create": {"id": "int-1"},
        "update": {"id": "int-1"},
        "get": SimpleNamespace(id="int-1"),
    }

    def create(self, settings):
        return self._call("create", settings)

    def update(self, setting_id, settings):
        return self._call("update", setting_id, settings)

    def get(self, integration_id, setting_type=None):
        return self._call("get", integration_id, setting_type=setting_type)


class FakeCategories(FakeService):
    DEFAULTS = {
        "create_category": SimpleNamespace(id="cat-1"),
        "update_category": SimpleNamespace(id="cat-1"),
        "get_category": SimpleNamespace(id="cat-1"),
    }

    def get_categories(self):
        return self._call("get_categories")

    def create_category(self, request):
        return self._call("create_category", request)

    def update_category(self, category_id, request):
        return self._call("update_category", category_id, request)

    def get_category(self, category_id):
        return self._call("get_category", category_id)


class FakeClient:
    """Stand-in for ``CodeMieClient``; pass a fake to override any service."""

    def __init__(self, **services: Any):
        self.assistants = services.get("assistants", FakeAssistants())
        self.skills = services.get("skills", FakeSkills())
        self.workflows = services.get("workflows", FakeWorkflows())
        self.datasources = services.get("datasources", FakeDatasources())
        self.integrations = services.get("integrations", FakeIntegrations())
        self.categories = services.get("categories", FakeCategories())
