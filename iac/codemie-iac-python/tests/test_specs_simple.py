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

import pytest
from pydantic import ValidationError

from codemie_sdk.models.categories import CategoryCreateRequest
from codemie_sdk.models.integration import (
    CredentialTypes,
    CredentialValues,
    Integration,
    IntegrationType,
)
from codemie_sdk.models.skill import SkillCreateRequest

from codemie_iac.credentials import CredentialRef
from codemie_iac.specs.integration import IntegrationSpec, CredentialRefEntry
from codemie_iac.specs.skill import SkillSpec
from codemie_iac.specs.category import CategorySpec


def test_roundtrip_integration():
    spec = IntegrationSpec(
        project_name="demo",
        alias="my-jira",
        default=True,
        is_global=False,
        credential_type=CredentialTypes.JIRA,
        credential_values=[
            CredentialRefEntry(
                key="api_token",
                ref=CredentialRef.from_entity("jira_prod", "api_token"),
            )
        ],
        setting_type=IntegrationType.PROJECT,
    )
    assert IntegrationSpec.model_validate(spec.model_dump()) == spec


def test_roundtrip_skill():
    spec = SkillSpec(
        name="x",
        description="d",
        content="c",
        project="p",
    )
    assert SkillSpec.model_validate(spec.model_dump()) == spec


def test_roundtrip_category():
    spec = CategorySpec(name="x")
    assert CategorySpec.model_validate(spec.model_dump()) == spec


def test_unknown_field_rejected():
    with pytest.raises(ValidationError, match="(?i)extra"):
        SkillSpec(
            name="x",
            description="d",
            content="c",
            project="p",
            bogus_field="x",
        )


def test_integration_credentials_are_refs():
    spec = IntegrationSpec(
        project_name="demo",
        credential_type=CredentialTypes.JIRA,
        credential_values=[
            CredentialRefEntry(
                key="api_token",
                ref=CredentialRef.from_entity("jira_prod", "api_token"),
            )
        ],
    )
    assert IntegrationSpec.model_validate(spec.model_dump()) == spec

    with pytest.raises(ValidationError):
        CredentialRefEntry(key="api_token", ref="not-a-ref")


def test_category_spec_from_entity():
    category = CategoryCreateRequest(
        name="support", description="Support team resources"
    )
    spec = CategorySpec.from_entity(category)
    assert spec == CategorySpec(name="support", description="Support team resources")


def test_skill_spec_from_entity():
    skill = SkillCreateRequest(
        name="changelog-writer",
        description="Writes a changelog entry from a diff",
        content="Summarize the given diff as one changelog line.",
        project="my-project",
    )
    spec = SkillSpec.from_entity(skill)
    assert spec == SkillSpec(
        name=skill.name,
        description=skill.description,
        content=skill.content,
        project=skill.project,
        visibility=skill.visibility,
        categories=skill.categories,
        enabled_builtin_subagents=skill.enabled_builtin_subagents,
    )


def test_integration_spec_from_entity_never_reads_credential_value():
    integration = Integration(
        project_name="my-project",
        alias="fe-confluence-prod",
        credential_type=CredentialTypes.CONFLUENCE,
        credential_values=[CredentialValues(key="api_token", value="a-real-secret")],
    )
    spec = IntegrationSpec.from_entity(integration)
    assert spec.credential_values == [
        CredentialRefEntry(
            key="api_token",
            ref=CredentialRef.from_entity("fe-confluence-prod", "api_token"),
        )
    ]


def test_integration_spec_from_entity_raises_when_alias_is_none_with_credentials():
    """CR-006: an alias-less integration with credentials to narrow has no
    unique identifier to build a CredentialRef from -- raising, rather than
    falling back to a shared literal, prevents two different alias-less
    integrations from silently colliding onto the same CredentialRef.
    """
    integration = Integration(
        project_name="my-project",
        alias=None,
        credential_type=CredentialTypes.CONFLUENCE,
        credential_values=[CredentialValues(key="fe_fallback_key", value="secret")],
    )
    with pytest.raises(ValueError, match="requires an alias"):
        IntegrationSpec.from_entity(integration)


def test_integration_spec_from_entity_allows_alias_none_with_no_credentials():
    """An alias-less integration with nothing to narrow has no identifier to
    collide over, so it is not rejected.
    """
    integration = Integration(
        project_name="my-project",
        alias=None,
        credential_type=CredentialTypes.CONFLUENCE,
        credential_values=[],
    )
    spec = IntegrationSpec.from_entity(integration)
    assert spec.credential_values == []


def test_skill_allows_at_most_three_categories():
    from codemie_iac.specs.skill import SkillSpec

    base = dict(name="s", description="d", content="c", project="p")
    SkillSpec(categories=["a", "b", "c"], **base)
    with pytest.raises(ValidationError):
        SkillSpec(categories=["a", "b", "c", "d"], **base)
