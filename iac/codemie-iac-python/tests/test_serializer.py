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
from codemie_sdk.builders.workflow.definition import (
    WorkflowAssistant,
    WorkflowDefinition,
)
from codemie_sdk.models.workflow import WorkflowMode
from codemie_iac.envelope import Bundle, Document, DocumentMeta
from codemie_iac.serializer import to_yaml, from_yaml
from codemie_iac.specs.skill import SkillSpec
from codemie_iac.specs.workflow import WorkflowSpec


@pytest.fixture
def sample_bundle() -> Bundle:
    doc = Document.model_validate(
        {
            "version": "v1",
            "meta": {"kind": "category", "name": "cat1"},
            "spec": {"name": "cat1", "description": "A category"},
        }
    )
    return Bundle([doc])


def test_to_yaml_is_byte_identical_across_calls(sample_bundle):
    assert to_yaml(sample_bundle) == to_yaml(sample_bundle)


def test_roundtrip_bundle(sample_bundle):
    assert from_yaml(to_yaml(sample_bundle)) == sample_bundle


def test_from_yaml_rejects_unknown_field():
    text = "version: v1\nmeta:\n  kind: skill\n  name: x\nspec:\n  name: x\n  description: d\n  content: c\n  project: p\n  bogus: 1\n"
    with pytest.raises(ValidationError, match="bogus"):
        from_yaml(text)


def test_roundtrip_preserves_explicit_none_over_a_non_none_default():
    """Regression: `exclude_none=True` dropped an explicitly-`None` field
    whose class default isn't `None` (e.g. SkillSpec.visibility defaults to
    PROJECT), so `from_yaml` reloaded it as that default instead of `None` --
    breaking `from_yaml(to_yaml(b)) == b` and making a second dump differ."""
    doc = Document(
        version="v1",
        meta=DocumentMeta(kind="skill", name="s1"),
        spec=SkillSpec(
            name="skill-one",
            description="A valid skill description",
            content="c" * 100,
            project="p",
            visibility=None,
        ),
    )
    bundle = Bundle([doc])

    restored = from_yaml(to_yaml(bundle))

    assert restored == bundle
    assert restored.root[0].spec.visibility is None
    assert to_yaml(restored) == to_yaml(bundle)


def test_roundtrip_preserves_explicit_none_in_embedded_workflow_definition():
    workflow = WorkflowDefinition(
        name="wf1",
        mode=WorkflowMode.SEQUENTIAL,
        assistants={
            "a": WorkflowAssistant(
                id="a", system_prompt="p", limit_tool_output_tokens=None
            )
        },
    )
    doc = Document(
        version="v1",
        meta=DocumentMeta(kind="workflow", name="wf1"),
        spec=WorkflowSpec.from_entity(workflow),
    )
    bundle = Bundle([doc])

    restored = from_yaml(to_yaml(bundle))

    assert restored == bundle
    assert (
        restored.root[0].spec.workflow.assistants["a"].limit_tool_output_tokens is None
    )
