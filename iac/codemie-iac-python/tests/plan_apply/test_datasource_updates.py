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


"""Datasource plan and update behaviour."""

import pytest
from codemie_iac.plan_apply.kinds import DATASOURCE_ADAPTERS
from .fakes import (
    FakeClient,
    FakeDatasources,
)

from .helpers import (
    RawDatasources,
    SECRET,
    TARGET,
    _CODE_RAW,
    _CODE_SPEC,
    _GIT_FAQ_RAW,
    _GIT_FAQ_SPEC,
    _JIRA_RAW,
    _datasource,
    _integration,
    _jira_doc,
    _masked_integration_client,
    _planner,
    _sent_update,
)


def test_datasource_schedule_change_is_a_difference_and_is_written():
    client = FakeClient(datasources=RawDatasources(_JIRA_RAW))
    doc = _jira_doc(cron_expression="0 5 * * *", timezone="UTC")
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert [d.field for d in plan.differences] == ["cron_expression"]
    _planner(client).apply(doc, "ds-1", TARGET)
    assert len(client.datasources.calls_to("update")) == 1


def test_datasource_matching_schedule_gives_empty_plan():
    client = FakeClient(datasources=RawDatasources(_JIRA_RAW))
    doc = _jira_doc(cron_expression="0 1 * * *", timezone="UTC")
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


def test_timezone_alone_without_a_schedule_is_not_a_difference():
    """Without a cron the backend reports its default timezone; a document that
    does not author a schedule must not see that default as a difference."""
    raw = {k: v for k, v in _JIRA_RAW.items() if k != "cron_expression"}
    client = FakeClient(datasources=RawDatasources({**raw, "timezone": "Europe/Kyiv"}))
    plan = _planner(client).plan(_jira_doc(), "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


def test_authored_timezone_without_a_live_schedule_is_cannot_compare():
    raw = {k: v for k, v in _JIRA_RAW.items() if k != "cron_expression"}
    client = FakeClient(datasources=RawDatasources(raw))
    plan = _planner(client).plan(_jira_doc(timezone="UTC"), "ds-1", TARGET)
    assert [c.field for c in plan.cannot_compare] == ["timezone"]


def test_authored_schedule_not_observable_is_cannot_compare_not_skipped():
    live = FakeDatasources(
        get={
            "name": "ds",
            "project_name": TARGET,
            "description": "d",
            "type": "knowledge_base_jira",
            "jira": {"jql": "project = A"},
        }
    )
    client = FakeClient(datasources=live)
    doc = _jira_doc(cron_expression="0 5 * * *")
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert [c.field for c in plan.cannot_compare] == ["cron_expression"]


def test_apply_reports_uncomparable_fields_it_did_not_write():
    client = _masked_integration_client()
    doc = _integration(ref="env:JIRA_TOKEN")
    result = _planner(client).apply(doc, "int-1", TARGET)
    assert result.created is False
    assert result.uncomparable == ["credential_values"]
    assert client.integrations.calls_to("update") == []


def test_apply_force_writes_even_when_the_plan_is_empty():
    client = _masked_integration_client()
    doc = _integration(ref="env:JIRA_TOKEN")
    result = _planner(client).apply(doc, "int-1", TARGET, force=True)
    assert result.created is False
    (call,) = client.integrations.calls_to("update")
    assert call.args[1].credential_values[0].value == SECRET


@pytest.mark.parametrize("index_type", ["code", "summary", "chunk-summary"])
def test_code_datasource_identical_to_document_gives_empty_plan(index_type):
    raw = {**_CODE_RAW, "index_type": index_type}
    client = FakeClient(datasources=RawDatasources(raw))
    doc = _datasource({**_CODE_SPEC, "index_type": index_type})
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


def test_code_datasource_real_change_is_still_reported():
    client = FakeClient(datasources=RawDatasources(_CODE_RAW))
    doc = _datasource({**_CODE_SPEC, "branch": "develop"})
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert [d.field for d in plan.differences] == ["branch"]


def test_git_faq_datasource_identical_to_document_gives_empty_plan():
    raw = {
        **_CODE_RAW,
        "index_type": "knowledge_base_git_faq",
        "files_filter": "docs/**",
    }
    client = FakeClient(datasources=RawDatasources(raw))
    doc = _datasource(
        {
            "type": "knowledge_base_git_faq",
            "link": "https://git/x.git",
            "branch": "main",
            "files_filter": "docs/**",
            "embedding_model": "emb",
        }
    )
    plan = _planner(client).plan(doc, "ds-1", TARGET)
    assert plan.differences == [] and plan.cannot_compare == []


def test_git_faq_metadata_only_update_omits_source_fields_and_full_reindex():
    client = FakeClient(
        datasources=RawDatasources({**_GIT_FAQ_RAW, "description": "old"})
    )
    _planner(client).apply(_datasource(_GIT_FAQ_SPEC), "ds-1", TARGET)
    sent = _sent_update(client)
    assert sent.description == "d"
    assert sent.link is None and sent.branch is None and sent.files_filter is None
    assert not sent.full_reindex


def test_git_faq_source_change_is_sent_whole_with_full_reindex():
    client = FakeClient(datasources=RawDatasources(_GIT_FAQ_RAW))
    doc = _datasource({**_GIT_FAQ_SPEC, "branch": "develop"})
    _planner(client).apply(doc, "ds-1", TARGET)
    sent = _sent_update(client)
    assert sent.full_reindex is True
    assert (sent.link, sent.branch) == ("https://git/x.git", "develop")


def test_code_metadata_only_update_skips_the_reindex():
    client = FakeClient(datasources=RawDatasources({**_CODE_RAW, "description": "old"}))
    _planner(client).apply(_datasource(_CODE_SPEC), "ds-1", TARGET)
    assert _sent_update(client).skip_reindex is True


def test_code_source_change_keeps_the_default_reindex():
    client = FakeClient(datasources=RawDatasources(_CODE_RAW))
    doc = _datasource({**_CODE_SPEC, "branch": "develop"})
    _planner(client).apply(doc, "ds-1", TARGET)
    assert not _sent_update(client).skip_reindex


def test_forced_update_with_nothing_changed_does_not_reindex():
    """``force`` re-sends the document (e.g. a rotated secret); it does not
    make an unchanged source reindex."""
    client = FakeClient(datasources=RawDatasources(_CODE_RAW))
    _planner(client).apply(_datasource(_CODE_SPEC), "ds-1", TARGET, force=True)
    assert _sent_update(client).skip_reindex is True


def test_code_visibility_change_is_sent_under_the_key_the_backend_reads():
    client = FakeClient(datasources=RawDatasources(_CODE_RAW))
    doc = _datasource({**_CODE_SPEC, "shared_with_project": True})
    _planner(client).apply(doc, "ds-1", TARGET)
    sent = _sent_update(client)
    assert sent.model_dump(by_alias=True)["projectSpaceVisible"] is True
    assert sent.skip_reindex is True


@pytest.mark.parametrize(
    "ds_type, source, changed_source",
    [
        ("knowledge_base_jira", {"jql": "project = A"}, {"jql": "project = B"}),
        ("knowledge_base_confluence", {"cql": "space = A"}, {"cql": "space = B"}),
        (
            "knowledge_base_azure_devops_wiki",
            {"wiki_query": "a", "wiki_name": "w"},
            {"wiki_query": "b", "wiki_name": "w"},
        ),
        (
            "knowledge_base_azure_devops_work_item",
            {"wiql_query": "a"},
            {"wiql_query": "b"},
        ),
        (
            "knowledge_base_xwiki",
            {"space": "a", "wiki": "w"},
            {"space": "b", "wiki": "w"},
        ),
    ],
)
def test_knowledge_base_source_change_requests_a_full_reindex(
    ds_type, source, changed_source
):
    adapter = DATASOURCE_ADAPTERS[ds_type]
    doc = _datasource({"type": ds_type, **changed_source})
    client = FakeClient()
    adapter.update(client, doc, "ds-1", {}, frozenset(changed_source))
    assert client.datasources.calls_to("update")[0].args[1].full_reindex is True
    adapter.update(client, doc, "ds-1", {}, frozenset({"description"}))
    assert not client.datasources.calls_to("update")[1].args[1].full_reindex
