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


"""Finding existing entities by name."""

from types import SimpleNamespace
import pytest
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
)
from codemie_sdk.models.integration import IntegrationType
from codemie_iac.envelope import DocumentKind
from codemie_iac.plan_apply.errors import ApplyError, UnresolvedReferenceError
from codemie_iac.plan_apply.lookup import NameLookup
from .fakes import (
    FakeCategories,
    FakeClient,
    FakeDatasources,
    FakeWorkflows,
)

from .helpers import (
    ListedIntegrations,
    ParsingAssistants,
    RawDatasources,
    TARGET,
    _JIRA_RAW,
    _ctx,
    _datasource,
    _integration,
    _live_integration,
    _planner,
    _raw_assistant,
    _workflow,
)


def test_bundle_integration_without_id_is_resolved_by_alias_not_label():
    bundle = [_integration(name="jira-prod", alias="jira")]
    items = [
        _live_integration("jira-prod", id_="decoy"),
        _live_integration("jira", id_="real"),
    ]
    client = FakeClient(integrations=ListedIntegrations(items))
    ref = NameLookup(bundle, TARGET, client).resolve(
        DocumentKind.INTEGRATION, "jira-prod"
    )
    assert ref.id == "real"


def test_live_integration_lookup_filters_by_project():
    other = [
        _live_integration("jira", project="other", id_=f"o{i}") for i in range(100)
    ]
    items = other + [_live_integration("jira", id_="mine")]
    client = FakeClient(integrations=ListedIntegrations(items))
    ref = NameLookup([], TARGET, client).resolve(DocumentKind.INTEGRATION, "jira")
    assert ref.id == "mine"


def test_same_alias_of_another_setting_type_does_not_make_a_bundle_reference_ambiguous():
    bundle = [_integration(name="jira", alias="jira")]  # a PROJECT integration
    user_one = _live_integration("jira", id_="mine")
    user_one.setting_type = IntegrationType.USER
    project_one = _live_integration("jira", id_="shared")
    project_one.setting_type = IntegrationType.PROJECT
    client = FakeClient(integrations=ListedIntegrations([user_one, project_one]))
    ref = NameLookup(bundle, TARGET, client).resolve(DocumentKind.INTEGRATION, "jira")
    assert ref.id == "shared"


def test_workflow_without_a_description_is_refused_before_any_write():
    from codemie_iac.plan_apply.guards import guard_supported

    wf = _workflow(WorkflowAssistant(id="a1", name="helper"))
    wf.spec.workflow = wf.spec.workflow.model_copy(update={"description": ""})
    with pytest.raises(ApplyError) as info:
        guard_supported(wf)
    assert info.value.error_type == "invalid_workflow"


def test_changed_google_document_is_refused():
    raw = {
        **_JIRA_RAW,
        "index_type": "llm_routing_google",
        "google_doc_link": "https://d/1",
    }
    raw.pop("jira")
    client = FakeClient(datasources=RawDatasources(raw))
    doc = _datasource({"type": "llm_routing_google", "google_doc": "https://d/2"})
    with pytest.raises(ApplyError) as info:
        _planner(client).plan(doc, "ds-1", TARGET)
    assert info.value.error_type == "unsupported_datasource_change"


def test_existing_assistant_is_found_through_real_sdk_parsing():
    assistants = ParsingAssistants([_raw_assistant("existing-helper")])
    ctx = _ctx(client=FakeClient(assistants=assistants))
    ctx.lookup.require(DocumentKind.ASSISTANT, "existing-helper")
    assert ctx.ref(DocumentKind.ASSISTANT, "existing-helper").id == "id-existing-helper"


def test_assistant_in_another_project_is_still_not_found():
    assistants = ParsingAssistants([_raw_assistant("helper", project="other")])
    ctx = _ctx(client=FakeClient(assistants=assistants))
    with pytest.raises(UnresolvedReferenceError):
        ctx.lookup.require(DocumentKind.ASSISTANT, "helper")


def test_unresolved_assistant_message_mentions_visibility():
    """The live scan only sees assistants the calling user can see, so an
    unresolved assistant reference must say it may be invisible, not only absent."""
    ctx = _ctx(client=FakeClient(assistants=ParsingAssistants([])))
    with pytest.raises(UnresolvedReferenceError) as exc:
        ctx.lookup.require(DocumentKind.ASSISTANT, "helper")
    message = str(exc.value)
    assert "not visible to the current user" in message
    assert "'helper'" in message


def test_unresolved_category_message_is_unchanged():
    categories = FakeCategories()
    categories.responses["get_categories"] = []
    ctx = _ctx(client=FakeClient(categories=categories))
    with pytest.raises(UnresolvedReferenceError) as exc:
        ctx.lookup.require(DocumentKind.CATEGORY, "nope")
    assert "not visible" not in str(exc.value)


def test_live_workflow_and_datasource_lookups_ignore_other_projects():
    from codemie_iac.plan_apply.lookup import LIVE_FINDERS

    client = FakeClient(
        workflows=FakeWorkflows(
            items=[
                SimpleNamespace(name="w", project="other"),
                SimpleNamespace(name="w", project=TARGET),
            ]
        ),
        datasources=FakeDatasources(
            items=[
                SimpleNamespace(name="d", project_name="other"),
                SimpleNamespace(name="d", project_name=TARGET),
            ]
        ),
    )
    assert len(LIVE_FINDERS[DocumentKind.WORKFLOW](client, TARGET, "w")) == 1
    assert len(LIVE_FINDERS[DocumentKind.DATASOURCE](client, TARGET, "d")) == 1
