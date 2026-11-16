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
import requests
from pydantic import ValidationError

from codemie_iac.cli.commands.export import export_command
from codemie_iac.envelope import Document, DocumentKind
from codemie_iac.export import export_document
from tests.plan_apply.fakes import FakeClient, FakeExport

CATEGORY = {
    "version": "v1",
    "meta": {"kind": "category", "name": "cat1"},
    "spec": {"name": "cat1", "description": "A category"},
}


def test_returns_validated_document():
    client = FakeClient(export=FakeExport({("category", "c1"): CATEGORY}))
    assert export_document(client, DocumentKind.CATEGORY, "c1") == (
        Document.model_validate(CATEGORY)
    )


def test_http_error_propagates():
    with pytest.raises(requests.HTTPError):
        export_document(FakeClient(), "category", "missing")


def test_invalid_document_raises_validation_error():
    bad = {**CATEGORY, "spec": {**CATEGORY["spec"], "bogus": 1}}
    client = FakeClient(export=FakeExport({("category", "c1"): bad}))
    with pytest.raises(ValidationError):
        export_document(client, "category", "c1")


def test_out_file_is_utf8_with_non_ascii(tmp_path, monkeypatch):
    import io
    import locale

    monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **k: "cp1252")
    doc = {**CATEGORY, "spec": {**CATEGORY["spec"], "description": "Категория \u2713"}}
    client = FakeClient(export=FakeExport({("category", "c1"): doc}))
    target = tmp_path / "out.yaml"
    export_command(
        "category", "c1", str(target), project="p", client=client, out=io.StringIO()
    )
    assert "Категория \u2713" in target.read_text(encoding="utf-8")
