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


"""The target project and the entity name are enforced."""

import pytest
from codemie_iac.plan_apply.bulk_create import (
    BulkCreator,
)
from codemie_iac.plan_apply.errors import ApplyError
from .fakes import (
    FakeAssistants,
    FakeClient,
)

from .helpers import (
    TARGET,
    _OTHER_PROJECT_DOCS,
    _assistant,
    _datasource,
    _live_assistant,
    _planner,
    _skill,
)


@pytest.mark.parametrize("kind", list(_OTHER_PROJECT_DOCS))
def test_apply_rejects_document_whose_project_is_not_the_target(kind):
    client = FakeClient()
    with pytest.raises(ApplyError) as info:
        _planner(client).apply(_OTHER_PROJECT_DOCS[kind](), None, "B")
    assert info.value.error_type == "project_mismatch"
    for svc in ("assistants", "skills", "integrations", "datasources"):
        assert getattr(client, svc).calls == []


def test_update_rejects_document_project_differing_from_live_and_target():
    # Live assistant in B, document says A, target B: used to PUT project=A.
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(project="B")))
    with pytest.raises(ApplyError) as info:
        _planner(client).apply(_assistant(project="A"), "asst-1", "B")
    assert info.value.error_type == "project_mismatch"
    assert client.assistants.calls_to("update") == []


def test_plan_rejects_document_project_differing_from_target():
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(project="B")))
    with pytest.raises(ApplyError) as info:
        _planner(client).plan(_assistant(project="A"), "asst-1", "B")
    assert info.value.error_type == "project_mismatch"


def test_bulk_preflight_rejects_document_project_differing_from_target():
    client = FakeClient()
    with pytest.raises(ApplyError) as info:
        BulkCreator(client).create_all([_assistant(project="A")], "B")
    assert info.value.error_type == "project_mismatch"
    assert client.assistants.calls == []


@pytest.mark.parametrize(
    "build",
    [
        lambda: _skill(TARGET),
        lambda: _datasource({"type": "knowledge_base_jira", "jql": "project = A"}),
    ],
)
def test_meta_name_differing_from_spec_name_is_rejected(build):
    doc = build()
    doc.meta.name = "other-name"
    with pytest.raises(ApplyError) as info:
        _planner(FakeClient()).apply(doc, None, TARGET)
    assert info.value.error_type == "name_mismatch"


def test_bulk_create_rejects_a_name_mismatch_before_any_write():
    doc = _skill(TARGET)
    doc.meta.name = "other-name"
    client = FakeClient()
    with pytest.raises(ApplyError) as info:
        BulkCreator(client).create_all([doc], TARGET)
    assert info.value.error_type == "name_mismatch"
    assert client.skills.calls == []
