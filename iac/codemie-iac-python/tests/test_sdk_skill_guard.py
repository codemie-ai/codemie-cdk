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

"""An assistant with ``skill_ids`` is rejected when the installed SDK would
drop them, and applied normally once the SDK carries the field."""

import pytest
from codemie_sdk.models.assistant import AssistantCreateRequest, AssistantUpdateRequest

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply import guards, kinds
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.guards import guard_supported
from codemie_iac.specs.assistant import AssistantSpec
from codemie_iac.specs.skill import SkillSpec

from .plan_apply.fakes import FakeClient

TARGET = "proj"
UUID = "123e4567-e89b-12d3-a456-426614174000"


def _assistant(skills):
    spec = AssistantSpec(
        name="asst",
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
        skill_ids=skills,
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.ASSISTANT, name="asst"),
        spec=spec,
    )


def _sdk_supports(monkeypatch, supported):
    monkeypatch.setattr(guards, "_sdk_carries_assistant_skills", lambda: supported)


def test_skills_are_rejected_when_the_sdk_cannot_send_them(monkeypatch):
    _sdk_supports(monkeypatch, False)
    with pytest.raises(ApplyError) as exc:
        guard_supported(_assistant([UUID]))
    assert exc.value.error_type == "unsupported_sdk"
    assert "skill_ids" in exc.value.reason


def test_skills_are_accepted_when_the_sdk_can_send_them(monkeypatch):
    _sdk_supports(monkeypatch, True)
    guard_supported(_assistant([UUID]))


def test_assistant_without_skill_ids_is_unaffected(monkeypatch):
    _sdk_supports(monkeypatch, False)
    guard_supported(_assistant(None))


def test_empty_skill_ids_are_rejected_when_the_sdk_cannot_send_them(monkeypatch):
    _sdk_supports(monkeypatch, False)
    with pytest.raises(ApplyError) as exc:
        guard_supported(_assistant([]))
    assert exc.value.error_type == "unsupported_sdk"


def test_the_live_assistant_model_must_carry_skill_ids_too(monkeypatch):
    class _Request:
        model_fields = {"skill_ids": None}

    class _Live:
        model_fields: dict = {}

    monkeypatch.setattr(guards, "AssistantCreateRequest", _Request)
    monkeypatch.setattr(guards, "AssistantUpdateRequest", _Request)
    monkeypatch.setattr(guards, "Assistant", _Live)
    assert guards._sdk_carries_assistant_skills() is False
    monkeypatch.setattr(guards, "Assistant", _Request)
    assert guards._sdk_carries_assistant_skills() is True


def test_bulk_apply_fails_before_any_write(monkeypatch):
    _sdk_supports(monkeypatch, False)
    client = FakeClient()
    with pytest.raises(ApplyError):
        BulkCreator(client).create_all([_assistant([UUID])], TARGET)
    assert client.assistants.calls == []


@pytest.mark.skipif(
    not guards._sdk_carries_assistant_skills(),
    reason="installed codemie-sdk assistant request has no skill_ids field",
)
def test_skill_ids_reach_the_create_request():
    client = FakeClient()
    skill = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.SKILL, name="my-skill"),
        spec=SkillSpec(
            name="my-skill",
            description="A valid skill description",
            content="c" * 100,
            project=TARGET,
        ),
    )
    client = FakeClient()
    BulkCreator(client).create_all([_assistant(["my-skill"]), skill], TARGET)
    (call,) = [c for c in client.assistants.calls if c.method == "create"]
    # The name resolves to the id the created skill got, not the name itself.
    assert call.args[0].skill_ids == ["skill-1"]


def test_skill_ids_reach_the_request_on_an_sdk_that_carries_them(monkeypatch):
    # Stand-in request classes declare the field the pinned SDK may lack, so
    # this runs on every SDK, unlike the test above.
    class _Create(AssistantCreateRequest):
        skill_ids: list[str] = []

    class _Update(AssistantUpdateRequest):
        skill_ids: list[str] = []

    adapter = kinds._make_adapter(
        service="assistants",
        body=kinds._spec_body,
        create_cls=_Create,
        update_cls=_Update,
    )
    monkeypatch.setitem(kinds.ADAPTERS, DocumentKind.ASSISTANT, adapter)
    _sdk_supports(monkeypatch, True)
    client = FakeClient()
    skill = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.SKILL, name="my-skill"),
        spec=SkillSpec(
            name="my-skill",
            description="A valid skill description",
            content="c" * 100,
            project=TARGET,
        ),
    )
    client = FakeClient()
    BulkCreator(client).create_all([_assistant(["my-skill"]), skill], TARGET)
    (call,) = [c for c in client.assistants.calls if c.method == "create"]
    # The name resolves to the id the created skill got, not the name itself.
    assert call.args[0].skill_ids == ["skill-1"]
