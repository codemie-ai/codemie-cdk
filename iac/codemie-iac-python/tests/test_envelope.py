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
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta, Bundle
from codemie_iac.serializer import from_yaml, to_yaml
from codemie_iac.specs.category import CategorySpec


def test_unknown_field_in_spec_is_named():
    with pytest.raises(ValidationError, match="bogus_field"):
        Document.model_validate(
            {
                "version": "v1",
                "meta": {"kind": "skill", "name": "x"},
                "spec": {
                    "name": "x",
                    "description": "d",
                    "content": "c",
                    "project": "p",
                    "bogus_field": 1,
                },
            }
        )


def test_bundle_roundtrip_mixed_kinds():
    category_doc = Document.model_validate(
        {
            "version": "v1",
            "meta": {"kind": "category", "name": "cat1"},
            "spec": {"name": "cat1", "description": "A category"},
        }
    )
    skill_doc = Document.model_validate(
        {
            "version": "v1",
            "meta": {"kind": "skill", "name": "skill1"},
            "spec": {
                "name": "skill1",
                "description": "d",
                "content": "c",
                "project": "p",
            },
        }
    )
    bundle = Bundle([category_doc, skill_doc])
    assert Bundle.model_validate(bundle.model_dump()) == bundle


def test_document_meta_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        DocumentMeta(kind="not_a_real_kind", name="x")


def test_document_meta_kind_is_document_kind_enum():
    """A plain string still coerces, but the stored value is a DocumentKind."""
    meta = DocumentMeta(kind="category", name="x")
    assert meta.kind is DocumentKind.CATEGORY
    assert meta.kind == "category"


def test_document_meta_accepts_document_kind_member_directly():
    meta = DocumentMeta(kind=DocumentKind.WORKFLOW, name="x")
    assert meta.kind is DocumentKind.WORKFLOW


def test_document_rejects_extra_top_level_field():
    with pytest.raises(ValidationError):
        Document.model_validate(
            {
                "version": "v1",
                "meta": {"kind": "category", "name": "x"},
                "spec": {"name": "x", "description": "d"},
                "unexpected_top_level_field": 1,
            }
        )


def test_document_rejects_spec_instance_mismatched_with_kind():
    """Regression: a Document built from model instances (every README
    example's style) skipped kind/spec dispatch entirely, so a `spec` of the
    wrong type for `meta.kind` validated -- then `to_yaml` wrote a
    kind/body mismatch that `from_yaml` rejected on its own output."""
    with pytest.raises(ValidationError, match="skill"):
        Document(
            version="v1",
            meta=DocumentMeta(kind="skill", name="n"),
            spec=CategorySpec(name="c"),
        )


def test_document_rejects_spec_dict_mismatched_with_kind():
    """Same bug as above, reached via the exact repro from the review
    comment: `meta` passed as an already-built model instance alongside a
    raw dict `spec` -- the dispatch validator's `isinstance(meta, dict)`
    guard skipped dispatch entirely because `meta` wasn't a dict, even
    though `spec` was, letting pydantic's union resolution match `{"name":
    "c"}` against `CategorySpec` (the only member it satisfies) while
    `meta.kind` said "skill"."""
    with pytest.raises(ValidationError, match="skill"):
        Document(
            version="v1",
            meta=DocumentMeta(kind="skill", name="n"),
            spec={"name": "c"},
        )


def test_document_meta_unhashable_kind_raises_validation_error():
    """Regression: `meta: {kind: ["x"]}` raised a raw `TypeError:
    unhashable type` from the dict lookup instead of a clean
    `ValidationError`."""
    with pytest.raises(ValidationError):
        Document.model_validate(
            {
                "version": "v1",
                "meta": {"kind": ["x"], "name": "n"},
                "spec": {"name": "c"},
            }
        )


_JIRA_DATASOURCE_DOC = {
    "version": "v1",
    "meta": {"kind": "datasource", "name": "kb"},
    "spec": {
        "type": "knowledge_base_jira",
        "name": "kb",
        "project_name": "p",
        "description": "d",
        "jql": "project = X",
    },
}


def test_datasource_document_validates():
    """Regression: a valid datasource document crashed with a raw
    `TypeError: Subscripted generics cannot be used with class and instance
    checks`, because `DatasourceSpec` is an annotated union and the
    kind/spec match check ran `isinstance` against it."""
    doc = Document.model_validate(_JIRA_DATASOURCE_DOC)
    assert doc.meta.kind is DocumentKind.DATASOURCE
    assert doc.spec.type == "knowledge_base_jira"


def test_datasource_document_round_trips_through_yaml():
    bundle = Bundle([Document.model_validate(_JIRA_DATASOURCE_DOC)])
    assert from_yaml(to_yaml(bundle)) == bundle


def test_datasource_kind_with_other_kinds_spec_is_rejected():
    skill_doc = {
        "version": "v1",
        "meta": {"kind": "skill", "name": "x"},
        "spec": {"name": "x", "description": "d", "content": "c", "project": "p"},
    }
    skill = Document.model_validate(skill_doc)
    with pytest.raises(ValidationError, match="requires spec to be"):
        Document(
            version="v1",
            meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name="x"),
            spec=skill.spec,
        )
