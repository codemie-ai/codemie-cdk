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
from codemie_iac.schema import (
    validate_document,
    DocumentValidationError,
    document_json_schema,
)


def test_document_json_schema_is_a_dict():
    schema = document_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema or "$defs" in schema


def test_valid_document_passes():
    sample_document_dict = {
        "version": "v1",
        "meta": {"kind": "category", "name": "cat1"},
        "spec": {"name": "cat1", "description": "A category"},
    }
    validate_document(sample_document_dict)  # no raise


def test_malformed_document_names_json_path():
    bad = {"version": "v1", "meta": {"kind": "skill"}, "spec": {}}  # meta.name missing
    with pytest.raises(DocumentValidationError) as exc:
        validate_document(bad)
    assert "meta" in exc.value.json_path


def test_assistant_schema_exposes_skill_ids():
    from codemie_iac.specs.assistant import AssistantSpec

    assert "skill_ids" in AssistantSpec.model_json_schema()["properties"]
