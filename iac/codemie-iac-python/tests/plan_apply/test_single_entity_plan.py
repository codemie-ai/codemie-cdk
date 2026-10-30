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

from types import SimpleNamespace

import pytest
from codemie_sdk.models.integration import IntegrationType
from pydantic import TypeAdapter

from codemie_iac.credentials import CredentialRef
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.field_policy import FIELD_POLICIES, policy_for
from codemie_iac.plan_apply.kinds import DATASOURCE_ADAPTERS
from codemie_iac.plan_apply.single_apply import (
    CannotCompare,
    Difference,
    Plan,
    SingleEntityPlanner,
    diff,
)
from .fakes import FakeAssistants, FakeClient
from codemie_iac.specs.assistant import AssistantSpec, PromptVariableSpec
from codemie_iac.specs.datasource import DatasourceSpec
from codemie_iac.specs.integration import CredentialRefEntry, IntegrationSpec

SECRET = "s3cr3t-token-value"


def _doc(kind, name, spec):
    return Document(version="v1", meta=DocumentMeta(kind=kind, name=name), spec=spec)


def _assistant(**extra):
    spec = AssistantSpec(
        name="asst",
        description="d",
        system_prompt="p",
        project="proj",
        llm_model_type="gpt",
        shared=True,
        **extra,
    )
    return _doc(DocumentKind.ASSISTANT, "asst", spec)


def _live_assistant(**over):
    live = {
        "id": "asst-1",
        "created_by": {"id": "u"},
        "name": "asst",
        "description": "d",
        "icon_url": None,
        "system_prompt": "p",
        "project": "proj",
        "llm_model_type": "gpt",
        "shared": True,
        "is_react": False,
        "is_global": False,
        "updated_date": "2026-01-01T00:00:00",
        "version_count": 3,
        "toolkits": [],
        "context": [],
        "categories": [],
        "assistant_ids": [],
        "prompt_variables": None,
    }
    live.update(over)
    return live


def _resolver():
    return EnvCredentialResolver({"JIRA_TOKEN": SECRET})


def _run(doc, live):
    return diff(doc, live, policy_for(doc), _resolver())


def _plan(doc, live):
    result = _run(doc, live)
    return Plan(
        differences=[r for r in result if isinstance(r, Difference)],
        cannot_compare=[r for r in result if isinstance(r, CannotCompare)],
    )


def test_live_equal_to_document_gives_empty_plan():
    plan = _plan(_assistant(), _live_assistant())
    assert plan.is_empty
    assert plan.differences == [] and plan.cannot_compare == []


def test_externally_changed_field_is_reported():
    result = _run(_assistant(), _live_assistant(system_prompt="edited"))
    assert result == [
        Difference(field="system_prompt", document_value="p", live_value="edited")
    ]


def test_only_server_managed_fields_differing_gives_empty_plan():
    live = _live_assistant(
        updated_date="2030-05-05", version_count=99, id="other", created_by=None
    )
    assert _plan(_assistant(), live).is_empty


def test_reference_fields_without_context_are_cannot_compare_not_skipped():
    doc = _assistant(categories=["cat-name"], assistant_ids=["sub-name"])
    live = _live_assistant(categories=["cat-uuid"], assistant_ids=["asst-uuid"])
    fields = [c.field for c in _plan(doc, live).cannot_compare]
    assert fields == ["assistant_ids", "categories"]


def test_masked_prompt_variable_is_cannot_compare():
    doc = _assistant(
        prompt_variables=[PromptVariableSpec(key="k", default_value="real")]
    )
    live = _live_assistant(
        prompt_variables=[{"key": "k", "description": None, "default_value": "*" * 8}]
    )
    result = _run(doc, live)
    assert [type(r) for r in result] == [CannotCompare]
    assert result[0].field == "prompt_variables"


def test_masked_credentials_with_ref_are_cannot_compare_and_never_leak():
    spec = IntegrationSpec(
        project_name="proj",
        alias="jira",
        credential_type="Jira",
        credential_values=[
            CredentialRefEntry(key="token", ref=CredentialRef("env:JIRA_TOKEN"))
        ],
        setting_type=IntegrationType.PROJECT,
    )
    doc = _doc(DocumentKind.INTEGRATION, "jira", spec)
    live = {
        "id": "i-1",
        "project_name": "proj",
        "alias": "jira",
        "default": False,
        "is_global": False,
        "credential_type": "Jira",
        "setting_type": "project",
        "credential_values": [{"key": "token", "value": "*" * 10}],
    }
    plan = _plan(doc, live)
    assert plan.differences == []
    assert [c.field for c in plan.cannot_compare] == ["credential_values"]
    assert plan.is_empty  # unknowable is not a change: no needless write
    for text in (repr(plan), str(plan), plan.model_dump_json(), str(plan.model_dump())):
        assert SECRET not in text
        assert "**********" not in text


def test_unresolvable_ref_is_flagged_without_value():
    spec = IntegrationSpec(
        project_name="proj",
        credential_type="Jira",
        credential_values=[
            CredentialRefEntry(key="token", ref=CredentialRef("env:MISSING_VAR"))
        ],
    )
    doc = _doc(DocumentKind.INTEGRATION, "i", spec)
    result = _run(doc, {"credential_values": [{"key": "token", "value": "*" * 10}]})
    assert result[0].field == "credential_values"
    assert "unresolvable" in result[0].reason


def test_datasource_nested_live_fields_are_flattened():
    spec = TypeAdapter(DatasourceSpec).validate_python(
        {
            "type": "knowledge_base_jira",
            "name": "ds",
            "project_name": "proj",
            "description": "d",
            "jql": "project = A",
        }
    )
    doc = _doc(DocumentKind.DATASOURCE, "ds", spec)
    live = {
        "name": "ds",
        "project_name": "proj",
        "description": "d",
        "type": "knowledge_base_jira",
        "status": "completed",
        "update_date": "x",
        "jira": {"jql": "project = B", "custom_fields": None},
    }
    assert _run(doc, live) == [
        Difference(field="jql", document_value="project = A", live_value="project = B")
    ]


def test_policy_table_covers_every_kind_and_datasource_type():
    expected = {k.value for k in DocumentKind if k is not DocumentKind.DATASOURCE}
    expected |= set(DATASOURCE_ADAPTERS) | {"knowledge_base_file"}
    assert set(FIELD_POLICIES) == expected
    for policy in FIELD_POLICIES.values():
        assert not policy.deny & policy.comparable


def test_models_forbid_extra():
    with pytest.raises(ValueError):
        Difference(field="f", document_value=1, live_value=2, extra=1)


# --- SingleEntityPlanner ---------------------------------------------------


def _planner(live):
    client = FakeClient(assistants=FakeAssistants(get=SimpleNamespace(**live)))
    return client, SingleEntityPlanner(client, credentials=_resolver())


def test_planner_reads_only_the_given_id():
    client, planner = _planner(_live_assistant(system_prompt="edited"))
    plan = planner.plan(_assistant(), "asst-1", "proj")
    assert [c.args for c in client.assistants.calls_to("get")] == [("asst-1",)]
    assert [c.method for c in client.assistants.calls] == ["get"]
    assert [d.field for d in plan.differences] == ["system_prompt"]


def test_planner_returns_empty_plan_when_live_matches():
    _, planner = _planner(_live_assistant())
    assert planner.plan(_assistant(), "asst-1", "proj").is_empty
