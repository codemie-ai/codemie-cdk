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

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import ResolveContext
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import UnresolvedReferenceError
from codemie_iac.plan_apply.lookup import NameLookup
from codemie_iac.specs.skill import SkillSpec

TARGET = "proj"
UUID = "123e4567-e89b-12d3-a456-426614174000"


def _skill_doc(name):
    spec = SkillSpec(
        name=name,
        description="A valid skill description",
        content="c" * 100,
        project=TARGET,
    )
    return Document(
        version="v1", meta=DocumentMeta(kind=DocumentKind.SKILL, name=name), spec=spec
    )


class _Skills:
    def __init__(self, items):
        self.items = items

    def list(self, page=0, per_page=100):
        return SimpleNamespace(skills=self.items if page == 0 else [])


def _ctx(bundle=(), live=None, created=None):
    client = SimpleNamespace(skills=_Skills(live or []))
    return ResolveContext(
        NameLookup(list(bundle), TARGET, client),
        EnvCredentialResolver({}),
        dict(created or {}),
    )


def _live(name, id_=None):
    return SimpleNamespace(id=id_ or f"live-{name}", name=name, project=TARGET)


OWNER = _skill_doc("owner")


def test_bundle_name_resolves_to_created_id():
    ctx = _ctx(
        [_skill_doc("skill-one")],
        created={(DocumentKind.SKILL, "skill-one"): "id-skill-one"},
    )
    assert ctx.value_ids(DocumentKind.SKILL, ["skill-one"], OWNER) == ["id-skill-one"]


def test_live_name_resolves_and_order_is_preserved():
    ctx = _ctx(live=[_live("a"), _live("b")])
    assert ctx.value_ids(DocumentKind.SKILL, ["b", "a"], OWNER) == [
        "live-b",
        "live-a",
    ]


def test_uuid_without_match_passes_through():
    assert _ctx().value_ids(DocumentKind.SKILL, [UUID], OWNER) == [UUID]


def test_name_wins_over_uuid_shape():
    ctx = _ctx([_skill_doc(UUID)], created={(DocumentKind.SKILL, UUID): "id-by-name"})
    assert ctx.value_ids(DocumentKind.SKILL, [UUID], OWNER) == ["id-by-name"]


def test_unmatched_non_uuid_raises_naming_kind_name_and_owner():
    with pytest.raises(UnresolvedReferenceError) as err:
        _ctx().value_ids(DocumentKind.SKILL, ["ghost"], OWNER)
    text = str(err.value)
    assert "skill" in text and "ghost" in text and "skill/owner" in text


def test_ambiguous_live_name_raises_even_if_uuid_shaped():
    ctx = _ctx(live=[_live(UUID, "x1"), _live(UUID, "x2")])
    with pytest.raises(UnresolvedReferenceError, match="ambiguous"):
        ctx.value_ids(DocumentKind.SKILL, [UUID], OWNER)


def test_assistant_resolved_returns_skill_ids_for_names():
    from codemie_iac.plan_apply.bulk_create import build_resolved
    from codemie_iac.specs.assistant import AssistantSpec

    spec = AssistantSpec(
        name="a",
        description="d",
        system_prompt="p",
        llm_model_type="gpt",
        skill_ids=["b", UUID, "a"],
    )
    doc = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.ASSISTANT, name="a"),
        spec=spec,
    )
    ctx = _ctx(live=[_live("a"), _live("b")])
    assert build_resolved(doc, ctx)["skill_ids"] == ["live-b", UUID, "live-a"]
