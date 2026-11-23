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

"""Workflow engine settings: load, apply, plan and neutral when unset."""

import yaml
from codemie_sdk.builders.workflow.definition import (
    WorkflowEngineRetryPolicy,
    WorkflowNextState,
    WorkflowPoolConfig,
    WorkflowState,
)
from codemie_iac.envelope import Bundle
from codemie_iac.serializer import from_yaml, to_yaml
from .fakes import FakeClient, FakeWorkflows
from .helpers import TARGET, _inline_workflow, _live_workflow, _planner

SETTINGS = {
    "max_concurrency": 7,
    "recursion_limit": 33,
    "verbose": True,
    "type": "custom-type",
    "max_nesting_level": 4,
    "pool_config": WorkflowPoolConfig(
        enabled=True, min_size=2, max_size=9, refill_interval_seconds=15
    ),
    "retry_policy": WorkflowEngineRetryPolicy(
        initial_interval=1.5, backoff_factor=3.0, max_interval=40.0, max_attempts=6
    ),
}
ENGINE_KEYS = [*SETTINGS]


def _state():
    return WorkflowState(
        id="s1",
        assistant_id="a1",
        task="t",
        next=WorkflowNextState(override_task=True, include_in_llm_history=False),
    )


def _configured():
    return _inline_workflow(states=[_state()], **SETTINGS)


def _sent_config(doc) -> dict:
    client = FakeClient(workflows=FakeWorkflows())
    _planner(client).apply(doc, None, TARGET)
    sent = client.workflows.calls_to("create_workflow")[0].args[0]
    return yaml.safe_load(sent.yaml_config)


def _plan_fields(doc, live):
    client = FakeClient(workflows=FakeWorkflows(get=live))
    plan = _planner(client).plan(doc, "wf-1", TARGET)
    return [d.field for d in plan.differences]


def _assert_settings(definition):
    for key, value in SETTINGS.items():
        assert getattr(definition, key) == value
    nxt = definition.states[0].next
    assert nxt.override_task is True
    assert nxt.include_in_llm_history is False


def test_settings_survive_a_yaml_round_trip():
    doc = _configured()
    _assert_settings(doc.spec.workflow)
    reloaded = from_yaml(to_yaml(Bundle([doc])))
    assert reloaded == Bundle([doc])
    _assert_settings(list(reloaded)[0].spec.workflow)


def test_apply_sends_every_setting_in_the_yaml_config():
    config = _sent_config(_configured())
    assert config["max_concurrency"] == 7
    assert config["recursion_limit"] == 33
    assert config["verbose"] is True
    assert config["type"] == "custom-type"
    assert config["max_nesting_level"] == 4
    assert config["pool_config"] == {
        "enabled": True,
        "min_size": 2,
        "max_size": 9,
        "refill_interval_seconds": 15,
    }
    assert config["retry_policy"] == {
        "initial_interval": 1.5,
        "backoff_factor": 3.0,
        "max_interval": 40.0,
        "max_attempts": 6,
    }
    nxt = config["states"][0]["next"]
    assert nxt["override_task"] is True
    assert nxt["include_in_llm_history"] is False


def test_unchanged_live_state_plans_to_nothing():
    doc = _configured()
    assert _plan_fields(doc, _live_workflow(doc)) == []


def test_a_changed_stored_setting_is_one_yaml_config_difference():
    doc = _configured()
    live = _live_workflow(doc)
    stored = yaml.safe_load(live.yaml_config)
    stored["recursion_limit"] = 99
    live = live.model_copy(update={"yaml_config": yaml.safe_dump(stored)})
    assert _plan_fields(doc, live) == ["yaml_config"]


def test_unset_settings_are_neutral_in_the_plan():
    doc = _inline_workflow()
    live = _live_workflow(doc)
    stored = yaml.safe_load(live.yaml_config)
    stored.update(
        max_concurrency=10,
        recursion_limit=25,
        verbose=False,
        pool_config={"enabled": False},
        retry_policy={"max_attempts": 3},
    )
    live = live.model_copy(update={"yaml_config": yaml.safe_dump(stored)})
    assert _plan_fields(doc, live) == []


def test_unset_settings_are_not_sent():
    config = _sent_config(_inline_workflow())
    assert not [key for key in ENGINE_KEYS if config.get(key) is not None]
