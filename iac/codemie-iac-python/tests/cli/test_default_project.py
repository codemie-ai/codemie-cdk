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

"""A document's project is optional and defaults to the CLI target project."""

import io

import pytest

from codemie_iac import serializer
from codemie_iac.cli.commands.apply import apply_command
from codemie_iac.cli.commands.plan import plan_command
from codemie_iac.cli.documents import apply_default_project
from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.envelope import Bundle, Document, DocumentKind
from codemie_iac.plan_apply.guards import SPEC_PROJECT_FIELDS
from codemie_iac.schema import DocumentValidationError, validate_document
from tests.plan_apply.fakes import FakeAssistants, FakeClient
from tests.plan_apply.test_single_entity_apply import _live

TARGET = "proj"

_SPECS = {
    "assistant": (
        {"name": "a", "description": "d", "system_prompt": "p", "llm_model_type": "g"},
        "project",
    ),
    "skill": (
        {
            "name": "skill-s",
            "description": "A valid skill description",
            "content": "c" * 100,
        },
        "project",
    ),
    "integration": (
        {
            "alias": "jira",
            "credential_type": "Jira",
            "credential_values": [],
            "setting_type": "project",
        },
        "project_name",
    ),
    "datasource": (
        {
            "name": "ds",
            "description": "d",
            "type": "code",
            "link": "https://x/r.git",
            "branch": "main",
            "index_type": "code",
        },
        "project_name",
    ),
    "datasource-jira": (
        {"name": "ds", "description": "d", "type": "knowledge_base_jira"},
        "project_name",
    ),
}


def _raw(label, **extra):
    spec, field = _SPECS[label]
    kind = label.split("-")[0]
    spec = {**spec, **extra}
    return (
        {
            "version": "v1",
            "meta": {"kind": kind, "name": spec.get("name") or spec["alias"]},
            "spec": spec,
        },
        field,
    )


def _doc(label, **extra) -> Document:
    raw, field = _raw(label, **extra)
    return Document.model_validate(raw)


@pytest.mark.parametrize("label", list(_SPECS))
def test_document_without_project_validates_and_loads(label):
    raw, field = _raw(label)
    validate_document(raw)
    document = Document.model_validate(raw)
    assert getattr(document.spec, field) is None


@pytest.mark.parametrize("label", list(_SPECS))
def test_wrong_typed_project_still_fails_validation(label):
    raw, field = _raw(label, **{_SPECS[label][1]: 5})
    with pytest.raises(DocumentValidationError):
        validate_document(raw)


@pytest.mark.parametrize("label", list(_SPECS))
def test_project_not_required_in_json_schema(label):
    from pydantic import TypeAdapter

    from codemie_iac.envelope import _SPEC_BY_KIND

    raw, field = _raw(label)
    schema = TypeAdapter(_SPEC_BY_KIND[raw["meta"]["kind"]]).json_schema()
    definition = schema
    if "$ref" in schema:
        definition = schema["$defs"][schema["$ref"].rsplit("/", 1)[1]]
    if "oneOf" in definition or "anyOf" in definition:
        branches = definition.get("oneOf") or definition["anyOf"]
        assert branches
        for branch in branches:
            branch = schema["$defs"][branch["$ref"].rsplit("/", 1)[1]]
            assert field not in branch.get("required", [])
    else:
        assert field not in definition.get("required", [])


@pytest.mark.parametrize("label", list(_SPECS))
def test_helper_fills_missing_project_without_mutating(label):
    original = _doc(label)
    field = _SPECS[label][1]
    (filled,) = apply_default_project([original], TARGET)
    assert getattr(filled.spec, field) == TARGET
    assert getattr(original.spec, field) is None
    assert field == SPEC_PROJECT_FIELDS[original.meta.kind]


@pytest.mark.parametrize("label", list(_SPECS))
def test_helper_leaves_explicit_project_untouched(label):
    field = _SPECS[label][1]
    same = _doc(label, **{field: TARGET})
    other = _doc(label, **{field: "elsewhere"})
    assert apply_default_project([same, other], TARGET) == [same, other]


def test_helper_ignores_kinds_without_project():
    category = Document.model_validate(
        {
            "version": "v1",
            "meta": {"kind": "category", "name": "c"},
            "spec": {"name": "c", "description": "d"},
        }
    )
    assert category.meta.kind is DocumentKind.CATEGORY
    assert apply_default_project([category], TARGET) == [category]


def _file(tmp_path, *docs, name="a.yaml"):
    path = tmp_path / name
    path.write_text(serializer.to_yaml(Bundle(list(docs))))
    return path


def _apply(path, entity_id=None, client=None):
    out = io.StringIO()
    status = apply_command(
        path, entity_id, json_output=False, project=TARGET, client=client, out=out
    )
    return status, out.getvalue()


def test_apply_file_without_project_creates_in_target(tmp_path):
    client = FakeClient()
    status, text = _apply(_file(tmp_path, _doc("assistant")), client=client)
    assert status == ExitStatus.SUCCESS, text
    (call,) = client.assistants.calls_to("create")
    assert call.args[0].project == TARGET


def test_apply_file_with_other_project_is_refused(tmp_path):
    client = FakeClient()
    doc = _doc("assistant", project="elsewhere")
    status, text = _apply(_file(tmp_path, doc), client=client)
    assert status != ExitStatus.SUCCESS
    assert "project_mismatch" in text
    assert not client.assistants.calls_to("create")


def test_plan_without_project_compares_against_target(tmp_path):
    client = FakeClient(assistants=FakeAssistants(get=_live()))
    out = io.StringIO()
    status = plan_command(
        _file(tmp_path, _doc("assistant")),
        "asst-1",
        json_output=False,
        project=TARGET,
        client=client,
        out=out,
    )
    assert "project_mismatch" not in out.getvalue()
    assert status in (ExitStatus.NOTHING_TO_DO, ExitStatus.CHANGES_PENDING)


def test_plan_with_other_project_is_refused(tmp_path):
    client = FakeClient(assistants=FakeAssistants(get=_live()))
    out = io.StringIO()
    plan_command(
        _file(tmp_path, _doc("assistant", project="elsewhere")),
        "asst-1",
        json_output=False,
        project=TARGET,
        client=client,
        out=out,
    )
    assert "project_mismatch" in out.getvalue()


def test_bulk_directory_apply_fills_every_document(tmp_path):
    _file(tmp_path, _doc("assistant"), name="a.yaml")
    _file(tmp_path, _doc("skill"), name="b.yaml")
    _file(tmp_path, _doc("datasource"), name="c.yaml")
    client = FakeClient()
    status, text = _apply(tmp_path, client=client)
    assert status == ExitStatus.SUCCESS, text
    assert client.assistants.calls_to("create")[0].args[0].project == TARGET
    assert client.skills.calls_to("create")[0].args[0].project == TARGET
    assert client.datasources.calls[0].args[0].project_name == TARGET


@pytest.mark.parametrize("label", list(_SPECS))
def test_roundtrip_with_and_without_project(label):
    field = _SPECS[label][1]
    for document in (_doc(label), _doc(label, **{field: TARGET})):
        bundle = Bundle([document])
        assert serializer.from_yaml(serializer.to_yaml(bundle)) == bundle
