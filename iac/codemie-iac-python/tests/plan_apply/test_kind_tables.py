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

"""Every per-kind table covers every ``DocumentKind``, except where it must not.

Adding a kind means touching all of these tables; this test fails when one is
forgotten, and pins the deliberate gaps with the reason for each.
"""

from codemie_iac import envelope
from codemie_iac.envelope import DocumentKind
from codemie_iac.plan_apply import bulk_create, field_policy, guards, kinds
from codemie_iac.plan_apply import lookup, ordering, single_apply

ALL_KINDS = set(DocumentKind)


def test_tables_keyed_by_every_kind():
    complete = {
        "envelope._SPEC_BY_KIND": envelope._SPEC_BY_KIND,
        "kinds.ADAPTERS": kinds.ADAPTERS,
        "lookup.LIVE_FINDERS": lookup.LIVE_FINDERS,
        "bulk_create._RESOLVED_BUILDERS": bulk_create._RESOLVED_BUILDERS,
        "guards._SPEC_NAME_FIELDS": guards._SPEC_NAME_FIELDS,
    }
    for name, table in complete.items():
        assert set(table) == ALL_KINDS, name


def test_field_policies_cover_every_kind_and_datasource_type():
    # Datasource policies are keyed by datasource ``type``, not by kind.
    keys = set(field_policy.FIELD_POLICIES)
    assert {k.value for k in ALL_KINDS - {DocumentKind.DATASOURCE}} <= keys
    assert set(kinds.DATASOURCE_ADAPTERS) <= keys


def test_deliberate_gaps_in_project_tables():
    # Workflows take the target project when written and categories are
    # global, so the document carries no project to compare.
    assert set(guards.SPEC_PROJECT_FIELDS) == ALL_KINDS - {
        DocumentKind.WORKFLOW,
        DocumentKind.CATEGORY,
    }
    # The live project of a datasource is checked together with its name by
    # ``guard_datasource_identity``; categories are global.
    assert set(single_apply._PROJECT_FIELDS) == ALL_KINDS - {
        DocumentKind.DATASOURCE,
        DocumentKind.CATEGORY,
    }


def test_edge_extractors_cover_every_kind_that_references_others():
    # Categories and integrations reference nothing.
    assert set(ordering.EDGE_EXTRACTORS) == ALL_KINDS - {
        DocumentKind.CATEGORY,
        DocumentKind.INTEGRATION,
    }
