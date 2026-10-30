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

import copy
from types import SimpleNamespace

import codemie_iac.plan_apply as plan_apply
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply import BulkCreator, SingleEntityPlanner
from codemie_iac.specs.assistant import AssistantSpec

from .fakes import FakeAssistants, FakeClient

TARGET = "proj"

EXPECTED = {
    "ApplyError", "UnresolvedReferenceError", "UnresolvableCredentialError",
    "PlatformRejectionError", "FieldError", "SecretValue", "EnvCredentialResolver",
    "DependencyGraph", "KindAdapter", "ADAPTERS", "adapter_for", "NameLookup",
    "FieldPolicy", "FIELD_POLICIES", "BulkCreator", "BulkCreateReport",
    "CreatedEntity", "FailedEntity", "SingleEntityPlanner", "ApplyResult", "Plan",
    "Difference", "CannotCompare", "diff", "guard_supported",
    "guard_datasource_identity",
}  # fmt: skip


def _assistant(name):
    spec = AssistantSpec(
        name=name,
        description="d",
        system_prompt="p",
        project=TARGET,
        llm_model_type="gpt",
    )
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.ASSISTANT, name=name),
        spec=spec,
    )


def _snapshot(docs):
    return [d.model_dump() for d in docs]


def test_all_names_importable_and_public_names_exported():
    assert EXPECTED <= set(plan_apply.__all__)
    for name in plan_apply.__all__:
        assert hasattr(plan_apply, name), name


def test_single_create_persists_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    doc = _assistant("one")
    before = copy.deepcopy(doc)
    result = SingleEntityPlanner(FakeClient()).apply(doc, None, TARGET)
    assert result.id == "asst-1"
    assert doc.model_dump() == before.model_dump()
    assert list(tmp_path.iterdir()) == []


def test_bulk_create_persists_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class Ids(FakeAssistants):
        def create(self, request):
            self._call("create", request)
            return SimpleNamespace(message="ok", assistant_id=f"id-{request.name}")

    docs = [_assistant("a"), _assistant("b")]
    before = _snapshot(docs)
    report = BulkCreator(FakeClient(assistants=Ids())).create_all(docs, TARGET)
    assert sorted(e.id for e in report.created) == ["id-a", "id-b"]
    assert _snapshot(docs) == before
    assert list(tmp_path.rglob("*")) == []
