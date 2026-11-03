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
from pydantic import TypeAdapter
from codemie_sdk.models.assistant import Assistant
from codemie_sdk.models.categories import CategoryResponse
from codemie_sdk.models.datasource import (
    DataSource,
    ProviderDataSourceRequest,
    UpdateProviderDataSourceRequest,
)
from codemie_sdk.models.integration import Integration
from codemie_sdk.models.skill import SkillDetailResponse
from codemie_sdk.models.workflow import Workflow
from pydantic import BaseModel

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.field_policy import FIELD_POLICIES
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.kinds import DATASOURCE_ADAPTERS, _DATASOURCE_CLASSES
from codemie_iac.plan_apply.single_apply import Difference, diff
from codemie_iac.specs.datasource import DatasourceSpec

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
    "svn": "svn",
    "knowledge_base_sharepoint": "sharepoint",
    "knowledge_base_xray": "xray",
    "provider": "provider",
}
# Provider requests are not in the generic adapter table (separate adapter).
_WRITE_MODELS = {
    **_DATASOURCE_CLASSES,
    "provider": (ProviderDataSourceRequest, UpdateProviderDataSourceRequest),
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
    write = set().union(*(_names(cls) for cls in _WRITE_MODELS[ds_type]))
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


# --- nested sub-objects flatten into the live view ---------------------------

_LIVE_BASE = {
    "id": "ds-7",
    "project_name": "proj",
    "repo_name": "ds",
    "created_by": {"user_id": "u", "username": "x", "name": "n"},
    "update_date": "2026-01-01T00:00:00",
    "user_abilities": [],
    "description": "d",
    "project_space_visible": False,
}


def _document(**spec):
    spec.setdefault("name", "ds")
    spec.setdefault("project_name", "proj")
    spec.setdefault("description", "d")
    parsed = TypeAdapter(DatasourceSpec).validate_python(spec)
    meta = DocumentMeta(kind=DocumentKind.DATASOURCE, name="ds")
    return Document(version="v1", meta=meta, spec=parsed)


def _findings(document, **live_fields):
    live = DataSource.model_validate({**_LIVE_BASE, **live_fields})
    return diff(
        document,
        live,
        FIELD_POLICIES[document.spec.type],
        EnvCredentialResolver({}),
    )


UNCHANGED_CASES = {
    "svn": (
        {
            "type": "svn",
            "link": "https://svn/x",
            "branch": "trunk",
            "files_filter": "*.c",
            "prompt": "p",
            "docs_generation": True,
        },
        {
            "index_type": "code",
            "vcs_type": "svn",
            "link": "https://svn/x",
            "branch": "trunk",
            "files_filter": "*.c",
            "prompt": "p",
            "docs_generation": True,
        },
    ),
    "knowledge_base_sharepoint": (
        {
            "type": "knowledge_base_sharepoint",
            "site_url": "https://sp/x",
            "include_pages": True,
            "max_file_size_mb": 10,
            "files_filter": "*.docx",
        },
        {
            "index_type": "knowledge_base_sharepoint",
            "sharepoint": {
                "site_url": "https://sp/x",
                "include_pages": True,
                "max_file_size_mb": 10,
                "files_filter": "*.docx",
            },
        },
    ),
    "knowledge_base_xray": (
        {"type": "knowledge_base_xray", "jql": "project = X"},
        {"index_type": "knowledge_base_xray", "xray": {"jql": "project = X"}},
    ),
}


@pytest.mark.parametrize("ds_type", sorted(UNCHANGED_CASES))
def test_unchanged_nested_subobject_compares_equal(ds_type):
    spec, live = UNCHANGED_CASES[ds_type]
    assert _findings(_document(**spec), **live) == []


def test_changed_nested_subobject_field_is_a_difference():
    spec, live = UNCHANGED_CASES["knowledge_base_xray"]
    findings = _findings(_document(**spec), **{**live, "xray": {"jql": "project = Y"}})
    assert [f.field for f in findings] == ["jql"]
    assert isinstance(findings[0], Difference)


_PROVIDER_SPEC = {
    "type": "provider",
    "provider_name": "prov",
    "toolkit_id": "tk",
    "settings": {"region": "eu"},
}


def _provider_live(base_params):
    return {
        "index_type": "provider",
        "provider_fields": {
            "provider_id": "p1",
            "toolkit_id": "tk",
            "base_params": base_params,
            "create_params": {},
        },
    }


def test_unchanged_provider_settings_compare_equal():
    findings = _findings(
        _document(**_PROVIDER_SPEC), **_provider_live({"region": "eu"})
    )
    assert findings == []


def test_masked_provider_secret_is_non_comparable_not_a_difference():
    spec = {
        **_PROVIDER_SPEC,
        "settings": {"region": "eu", "api_key": "env:PROV_KEY"},
    }
    findings = _findings(
        _document(**spec),
        **_provider_live({"region": "eu", "api_key": "********"}),
    )
    assert [type(f).__name__ for f in findings] == ["CannotCompare"]
    assert findings[0].field == "settings.api_key"
    assert "********" not in findings[0].reason


# --- every spec field is classified, and comparable ones can be read live --------


def _spec_classes():
    import typing

    from codemie_iac.specs.datasource import DatasourceSpec

    return typing.get_args(typing.get_args(DatasourceSpec)[0])


@pytest.mark.parametrize(
    "spec_cls", _spec_classes(), ids=lambda c: c.model_fields["type"].default
)
def test_every_datasource_spec_field_is_classified_exactly_once(spec_cls):
    policy = FIELD_POLICIES[spec_cls.model_fields["type"].default]
    fields = set(spec_cls.model_fields)
    assert fields - policy.comparable - policy.deny == set()
    assert policy.comparable & policy.deny == set()


_OPTIONAL_LIVE = {"cron_expression", "timezone"}  # exposed only with a schedule


def _live_view_keys(live_payload):
    from codemie_iac.plan_apply.single_apply import _flatten_live

    live = DataSource.model_validate({**_LIVE_BASE, **live_payload})
    adapter = DATASOURCE_ADAPTERS[_type_of(live_payload)]
    return set(_flatten_live(adapter.to_comparable(live)))


def _type_of(live_payload):
    sub = {
        "sharepoint": "knowledge_base_sharepoint",
        "xray": "knowledge_base_xray",
        "provider_fields": "provider",
    }
    for key, ds_type in sub.items():
        if key in live_payload:
            return ds_type
    return "svn"


@pytest.mark.parametrize(
    "ds_type, live_payload",
    [
        ("svn", UNCHANGED_CASES["svn"][1]),
        ("knowledge_base_sharepoint", UNCHANGED_CASES["knowledge_base_sharepoint"][1]),
        ("knowledge_base_xray", UNCHANGED_CASES["knowledge_base_xray"][1]),
        ("provider", _provider_live({"region": "eu"})),
    ],
)
def test_every_comparable_spec_field_is_present_in_the_live_view(ds_type, live_payload):
    spec_cls = next(
        c for c in _spec_classes() if c.model_fields["type"].default == ds_type
    )
    comparable = FIELD_POLICIES[ds_type].comparable & set(spec_cls.model_fields)
    missing = comparable - _live_view_keys(live_payload) - _OPTIONAL_LIVE
    assert missing == set()
