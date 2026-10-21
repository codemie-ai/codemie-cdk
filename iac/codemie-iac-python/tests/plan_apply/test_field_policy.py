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

"""Contract: every read-only SDK response field is classified in field_policy.

A field on the live SDK response that no write (create/update) request model
accepts must be either ``deny`` or ``comparable``; a new, unclassified field
fails here instead of silently becoming a perpetual diff (or being ignored).
"""

import pytest
from codemie_sdk.models.assistant import Assistant
from codemie_sdk.models.categories import CategoryResponse
from codemie_sdk.models.datasource import DataSource
from codemie_sdk.models.integration import Integration
from codemie_sdk.models.skill import SkillDetailResponse
from codemie_sdk.models.workflow import Workflow
from pydantic import BaseModel

from codemie_iac.envelope import DocumentKind
from codemie_iac.plan_apply.field_policy import FIELD_POLICIES
from codemie_iac.plan_apply.kinds import DATASOURCE_ADAPTERS, _DATASOURCE_CLASSES

_RESPONSES: dict[DocumentKind, type[BaseModel]] = {
    DocumentKind.ASSISTANT: Assistant,
    DocumentKind.SKILL: SkillDetailResponse,
    DocumentKind.WORKFLOW: Workflow,
    DocumentKind.CATEGORY: CategoryResponse,
    DocumentKind.INTEGRATION: Integration,
}
# Datasource type -> the response sub-object flattened into the live view.
_SUBOBJECT = {
    "code": "code",
    "knowledge_base_git_faq": "git_faq",
    "knowledge_base_jira": "jira",
    "knowledge_base_confluence": "confluence",
    "llm_routing_google": None,
    "knowledge_base_azure_devops_wiki": "azure_devops_wiki",
    "knowledge_base_azure_devops_work_item": "azure_devops_work_item",
    "knowledge_base_xwiki": "xwiki",
    "knowledge_base_file": None,
}


def _names(model: type[BaseModel]) -> set[str]:
    """Field names plus aliases of a model."""
    names: set[str] = set()
    for name, info in model.model_fields.items():
        names.add(name)
        if info.alias:
            names.add(info.alias)
    return names


def _live_fields(response: type[BaseModel], nested: str | None = None) -> set[str]:
    """Top-level response fields plus the flattened datasource sub-object."""
    fields = set(response.model_fields)
    sub = response.model_fields[nested].annotation if nested else None
    for arg in getattr(sub, "__args__", ()):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            fields |= set(arg.model_fields)
    if "google_doc_link" in fields:
        fields.add("google_doc")
    return fields


def _unclassified(policy_key: str, live: set[str], write: set[str]) -> set[str]:
    policy = FIELD_POLICIES[policy_key]
    return {f for f in live - write if f not in policy.deny | policy.comparable}


def _write_models(kind: DocumentKind) -> set[str]:
    from codemie_sdk.models.assistant import (
        AssistantCreateRequest,
        AssistantUpdateRequest,
    )
    from codemie_sdk.models.categories import (
        CategoryCreateRequest,
        CategoryUpdateRequest,
    )
    from codemie_sdk.models.skill import SkillCreateRequest, SkillUpdateRequest
    from codemie_sdk.models.workflow import (
        WorkflowCreateRequest,
        WorkflowUpdateRequest,
    )

    pairs = {
        DocumentKind.ASSISTANT: (AssistantCreateRequest, AssistantUpdateRequest),
        DocumentKind.SKILL: (SkillCreateRequest, SkillUpdateRequest),
        DocumentKind.WORKFLOW: (WorkflowCreateRequest, WorkflowUpdateRequest),
        DocumentKind.CATEGORY: (CategoryCreateRequest, CategoryUpdateRequest),
        DocumentKind.INTEGRATION: (Integration, Integration),
    }
    return set().union(*(_names(cls) for cls in pairs[kind]))


@pytest.mark.parametrize("kind", list(_RESPONSES), ids=lambda k: k.value)
def test_every_readonly_response_field_is_classified(kind):
    missing = _unclassified(
        kind.value, _live_fields(_RESPONSES[kind]), _write_models(kind)
    )
    assert not missing, f"unclassified {kind.value} response fields: {sorted(missing)}"


@pytest.mark.parametrize("ds_type", list(DATASOURCE_ADAPTERS))
def test_every_readonly_datasource_field_is_classified(ds_type):
    write = set().union(*(_names(cls) for cls in _DATASOURCE_CLASSES[ds_type]))
    missing = _unclassified(
        ds_type, _live_fields(DataSource, _SUBOBJECT[ds_type]), write
    )
    assert not missing, f"unclassified {ds_type} response fields: {sorted(missing)}"


def test_file_datasource_policy_classifies_every_response_field():
    # File datasources have no write model: the whole response is classified.
    missing = _unclassified(
        "knowledge_base_file",
        _live_fields(DataSource, _SUBOBJECT["knowledge_base_file"]),
        set(),
    )
    assert not missing, f"unclassified file datasource fields: {sorted(missing)}"
