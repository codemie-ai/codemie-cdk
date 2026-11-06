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


"""Lookup edge cases: pagination, projects and duplicates."""

from types import SimpleNamespace
import pytest
from codemie_iac.plan_apply import lookup
from codemie_iac.plan_apply.errors import ApplyError
from codemie_iac.plan_apply.ordering import DependencyGraph

from .write_helpers import (
    TARGET,
    _assistant,
)


def test_live_item_without_project_is_not_a_match():
    assert not lookup._in_project(SimpleNamespace(name="x"), TARGET, "project")
    assert lookup._in_project(SimpleNamespace(project=TARGET), TARGET, "project")


def test_pagination_continues_past_short_pages_and_raises_on_truncation():
    pages = {0: ["a"] * 3, 1: ["b"] * 2}
    assert list(lookup._pages(lambda p: pages.get(p, []))) == ["a"] * 3 + ["b"] * 2
    with pytest.raises(ApplyError) as info:
        list(lookup._pages(lambda p: ["x"]))
    assert info.value.error_type == "lookup_truncated"


def test_duplicate_documents_are_rejected():
    with pytest.raises(ApplyError) as info:
        DependencyGraph([_assistant("dup"), _assistant("dup")])
    assert info.value.error_type == "duplicate_document"
