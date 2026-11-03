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


"""Plans over reference fields and other projects."""

import pytest
from codemie_iac.plan_apply.errors import ApplyError
from .fakes import (
    FakeAssistants,
    FakeClient,
)

from .write_helpers import (
    CREDS,
    SECRET,
    TARGET,
    _assistant,
    _cat_client,
    _live_assistant,
    _mcp_assistant,
    _planner,
)


def test_externally_changed_reference_field_is_reported():
    client = _cat_client(_live_assistant(categories=["other-id"]))
    plan = _planner(client).plan(_assistant(categories=["cat"]), "asst-1", TARGET)
    assert [d.field for d in plan.differences] == ["categories"]
    assert not plan.is_empty


def test_matching_reference_field_gives_empty_plan():
    client = _cat_client(_live_assistant(categories=[{"id": "cat-9"}]))
    plan = _planner(client).plan(_assistant(categories=["cat"]), "asst-1", TARGET)
    assert plan.is_empty


def test_credential_ref_document_with_matching_state_sends_no_write():
    live = _live_assistant(
        mcp_servers=[
            {"name": "srv", "enabled": True, "config": {"env": {"TOKEN": "*" * 8}}}
        ]
    )
    client = FakeClient(assistants=FakeAssistants(get=live))
    result = _planner(client, CREDS).apply(_mcp_assistant(), "asst-1", TARGET)
    assert result.created is False
    assert client.assistants.calls_to("update") == []


def test_reference_difference_with_credentials_is_redacted():
    live = _live_assistant(
        mcp_servers=[
            {"name": "srv", "enabled": False, "config": {"env": {"TOKEN": SECRET}}}
        ]
    )
    client = FakeClient(assistants=FakeAssistants(get=live))
    plan = _planner(client, CREDS).plan(_mcp_assistant(), "asst-1", TARGET)
    assert [d.field for d in plan.differences] == ["mcp_servers"]
    assert SECRET not in plan.model_dump_json()


def test_update_of_entity_in_other_project_is_refused():
    client = FakeClient(assistants=FakeAssistants(get=_live_assistant(project="other")))
    with pytest.raises(ApplyError) as info:
        _planner(client).apply(_assistant(), "asst-1", TARGET)
    assert info.value.error_type == "project_mismatch"
    assert client.assistants.calls_to("update") == []
