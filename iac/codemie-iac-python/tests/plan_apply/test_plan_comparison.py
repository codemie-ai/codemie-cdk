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


"""What a plan reports and what it leaves out."""

import pytest
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.single_apply import (
    CannotCompare,
    Difference,
)
from codemie_iac.specs.assistant import (
    MCPServerConfigSpec,
    PromptVariableSpec,
)
from .fakes import (
    FakeAssistants,
    FakeClient,
    FakeSkills,
    FakeWorkflows,
)

from .helpers import (
    SECRET,
    TARGET,
    _MASKED_SETTINGS,
    _assistant,
    _inline_workflow,
    _integration,
    _live_assistant,
    _live_toolkits,
    _live_workflow,
    _masked_integration_client,
    _mcp_assistant,
    _planner,
    _prompt_findings,
    _real_assistant,
    _skill,
    _toolkit_doc,
    _toolkit_findings,
)


def test_masked_embedded_integration_secret_does_not_hide_toolkit_change():
    live = _live_toolkits(["t1"], _MASKED_SETTINGS)
    findings = _toolkit_findings(_toolkit_doc(["t1", "t2"]), live)
    assert [type(f) for f in findings] == [Difference]
    assert findings[0].field == "toolkits"


def test_masked_embedded_integration_secret_alone_is_no_finding():
    live = _live_toolkits(["t1"], _MASKED_SETTINGS)
    assert _toolkit_findings(_toolkit_doc(["t1"]), live) == []


def test_unmasked_embedded_integration_values_are_not_a_difference():
    settings = {
        **_MASKED_SETTINGS,
        "credential_values": [{"key": "url", "value": "https://jira.example"}],
    }
    live = _live_toolkits(["t1"], settings)
    assert _toolkit_findings(_toolkit_doc(["t1"]), live) == []


def test_one_masked_prompt_variable_does_not_hide_edit_of_another():
    doc_vars = [
        PromptVariableSpec(key="secret", default_value="real"),
        PromptVariableSpec(key="plain", default_value="new"),
    ]
    live_vars = [
        {"key": "secret", "description": None, "default_value": "*" * 8},
        {"key": "plain", "description": None, "default_value": "old"},
    ]
    findings = _prompt_findings(doc_vars, live_vars)
    assert [type(f) for f in findings] == [Difference]
    assert findings[0].field == "prompt_variables"


def test_masked_prompt_variable_with_other_variables_equal_is_cannot_compare():
    doc_vars = [
        PromptVariableSpec(key="secret", default_value="real"),
        PromptVariableSpec(key="plain", default_value="same"),
    ]
    live_vars = [
        {"key": "secret", "description": None, "default_value": "*" * 8},
        {"key": "plain", "description": None, "default_value": "same"},
    ]
    findings = _prompt_findings(doc_vars, live_vars)
    assert [type(f) for f in findings] == [CannotCompare]


def test_plan_with_unset_integration_secret_reports_cannot_compare():
    client = _masked_integration_client()
    doc = _integration(ref="env:MISSING_VAR")
    plan = _planner(client, {}).plan(doc, "int-1", TARGET)
    assert [c.field for c in plan.cannot_compare] == ["credential_values"]
    assert "unresolvable" in plan.cannot_compare[0].reason


def test_plan_with_unset_mcp_secret_reports_cannot_compare():
    doc = _mcp_assistant(MCPServerConfigSpec(command="npx", env={"T": "env:NOPE"}))
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(mcp_servers=[])))
    plan = _planner(client, {}).plan(doc, "asst-1", TARGET)
    assert plan.differences == []
    assert [c.field for c in plan.cannot_compare] == ["mcp_servers"]
    assert "unresolvable" in plan.cannot_compare[0].reason


def test_apply_still_requires_every_secret():
    client = _masked_integration_client()
    with pytest.raises(ApplyError):
        _planner(client, {}).apply(_integration(ref="env:NOPE"), "int-1", TARGET)
    assert client.integrations.calls_to("update") == []


def test_backend_computed_settings_config_is_not_a_difference():
    live = _live_toolkits(["t1"], {"id": "int-1"})
    live[0]["settings_config"] = True
    live[0]["tools"][0]["settings_config"] = True
    assert _toolkit_findings(_toolkit_doc(["t1"]), live) == []


def test_auto_credentials_lookup_off_is_compared_and_kept():
    live = _live_toolkits(["t1"], {"id": "int-1"})
    live[0]["tools"][0]["auto_credentials_lookup"] = False
    findings = _toolkit_findings(_toolkit_doc(["t1"]), live)
    assert [f.field for f in findings] == ["toolkits"]


def test_unset_document_fields_are_not_compared():
    client = FakeClient(
        assistants=FakeAssistants(get=_live_assistant(slug="derived-slug"))
    )
    assert _planner(client).plan(_assistant(), "asst-1", TARGET).differences == []


def test_real_assistant_model_matching_the_document_gives_an_empty_plan():
    client = FakeClient(assistants=FakeAssistants(get=_real_assistant()))
    plan = _planner(client).plan(_assistant(), "asst-1", TARGET)
    assert plan.differences == []


def test_real_assistant_model_reports_exactly_the_edited_field():
    client = FakeClient(
        assistants=FakeAssistants(get=_real_assistant(system_prompt="old"))
    )
    plan = _planner(client).plan(_assistant(), "asst-1", TARGET)
    assert [d.field for d in plan.differences] == ["system_prompt"]


def test_real_skill_model_matching_the_document_gives_an_empty_plan():
    from codemie_sdk.models.skill import SkillDetailResponse

    live = SkillDetailResponse.model_validate(
        {
            "id": "sk-1",
            "name": "skill-s",
            "description": "A valid skill description",
            "content": "c" * 100,
            "project": TARGET,
            "visibility": "project",
            "createdDate": "2026-01-01T00:00:00",
            "created_by": {"user_id": "u", "username": "u", "name": "u"},
        }
    )
    client = FakeClient(skills=FakeSkills(get=live))
    plan = _planner(client).plan(_skill(TARGET), "sk-1", TARGET)
    assert plan.differences == []


def test_workflow_equal_to_its_live_state_gives_an_empty_plan():
    doc = _inline_workflow()
    client = FakeClient(workflows=FakeWorkflows(get=_live_workflow(doc)))
    assert _planner(client).plan(doc, "wf-1", TARGET).differences == []


def test_workflow_changed_description_is_exactly_one_difference():
    doc = _inline_workflow()
    client = FakeClient(
        workflows=FakeWorkflows(get=_live_workflow(doc, description="x"))
    )
    plan = _planner(client).plan(doc, "wf-1", TARGET)
    assert [d.field for d in plan.differences] == ["description"]


def test_workflow_changed_configuration_is_a_yaml_config_difference():
    doc = _inline_workflow()
    live = _live_workflow(doc)
    live = live.model_copy(
        update={"yaml_config": live.yaml_config.replace("helper", "other")}
    )
    client = FakeClient(workflows=FakeWorkflows(get=live))
    plan = _planner(client).plan(doc, "wf-1", TARGET)
    assert [d.field for d in plan.differences] == ["yaml_config"]


def test_live_workflow_mcp_token_never_appears_in_a_plan():
    doc = _inline_workflow()
    live = _live_workflow(doc)
    leaked = live.yaml_config.replace(
        "assistants:",
        "assistants:\n- id: x\n  mcp_servers:\n  - name: s\n    config:\n"
        f"      env:\n        TOKEN: {SECRET}",
        1,
    )
    client = FakeClient(
        workflows=FakeWorkflows(get=live.model_copy(update={"yaml_config": leaked}))
    )
    plan = _planner(client).plan(doc, "wf-1", TARGET)
    assert plan.differences and SECRET not in plan.model_dump_json()
