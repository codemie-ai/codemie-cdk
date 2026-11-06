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


"""An assistant the platform declines is a failure."""

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
    _assistant,
    _declined,
    _live_assistant,
    _planner,
)


def test_bulk_create_reports_a_declined_assistant_as_failed():
    client = FakeClient(assistants=FakeAssistants(create=_declined()))
    report = BulkCreator(client).create_all([_assistant()], TARGET)
    assert report.created == []
    assert report.failed.error_type == "integration_missing"
    assert "Jira" in report.failed.reason


def test_single_create_and_update_raise_for_a_declined_assistant():
    client = FakeClient(
        assistants=FakeAssistants(
            create=_declined(),
            update=_declined(),
            get=_live_assistant(system_prompt="x"),
        )
    )
    with pytest.raises(ApplyError) as created:
        _planner(client).apply(_assistant(), None, TARGET)
    with pytest.raises(ApplyError) as updated:
        _planner(client).apply(_assistant(), "asst-1", TARGET)
    assert created.value.error_type == updated.value.error_type == "integration_missing"
