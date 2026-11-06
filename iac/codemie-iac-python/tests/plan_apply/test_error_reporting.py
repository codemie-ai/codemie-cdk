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


"""Failures are reported without leaking a secret."""

import pytest
from codemie_sdk.exceptions import ApiError
from pydantic import BaseModel
from codemie_iac.envelope import DocumentKind
from codemie_iac.plan_apply import bulk_create
from codemie_iac.plan_apply.bulk_create import BulkCreator
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import ApplyError, PlatformRejectionError
from codemie_iac.plan_apply.kinds import _build
from codemie_iac.plan_apply.single_apply import SingleEntityPlanner
from codemie_iac.specs.category import CategorySpec
from .fakes import (
    FakeAssistants,
    FakeClient,
)

from .write_helpers import (
    CREDS,
    SECRET,
    TARGET,
    _assistant,
    _doc,
    _mcp_assistant,
    _real_http_error,
)


def test_invalid_body_reason_never_contains_input_values():
    class Req(BaseModel):
        count: int

    with pytest.raises(ApplyError) as info:
        _build(Req, {"count": SECRET}, _assistant())
    text = f"{info.value} {info.value.reason} {info.value.__cause__!r}"
    assert SECRET not in text
    assert "count" in info.value.reason


def test_platform_rejection_scrubs_revealed_secrets():
    cause = ApiError(f"bad token {SECRET}", 422)
    cause.response = {"detail": [{"loc": ["body", "f"], "msg": f"x {SECRET}"}]}
    error = PlatformRejectionError(
        "platform_rejection", "assistant", "a", cause, [SECRET]
    )
    assert SECRET not in f"{error} {error.reason} {error.structured_errors}"


def test_bulk_failure_reason_does_not_leak_revealed_secret():
    client = FakeClient(
        assistants=FakeAssistants(create=ApiError(f"echo {SECRET}", 422))
    )
    creator = BulkCreator(client, credentials=EnvCredentialResolver(CREDS))
    report = creator.create_all([_mcp_assistant()], TARGET)
    assert report.failed.error_type == "platform_rejection"
    assert SECRET not in report.model_dump_json()


def test_bulk_real_http_error_becomes_a_scrubbed_platform_rejection():
    client = FakeClient(
        assistants=FakeAssistants(create=_real_http_error(f"422 for {SECRET}"))
    )
    creator = BulkCreator(client, credentials=EnvCredentialResolver(CREDS))
    report = creator.create_all([_mcp_assistant()], TARGET)
    assert report.failed.error_type == "platform_rejection"
    assert report.failed.structured_errors[0].field == "token"
    assert SECRET not in report.model_dump_json()


def test_single_apply_real_http_error_is_scrubbed_and_not_chained():
    client = FakeClient(
        assistants=FakeAssistants(create=_real_http_error(f"422 for {SECRET}"))
    )
    planner = SingleEntityPlanner(client, EnvCredentialResolver(CREDS))
    with pytest.raises(PlatformRejectionError) as info:
        planner.apply(_mcp_assistant(), None, TARGET)
    error = info.value
    assert SECRET not in f"{error} {error.reason} {error.structured_errors}"
    assert error.__cause__ is None and error.__context__ is None


def test_unexpected_error_keeps_created_list_and_reports_failure(monkeypatch):
    original = bulk_create.build_resolved

    def flaky(document, ctx):
        if document.meta.name == "second":
            raise RuntimeError("boom")
        return original(document, ctx)

    monkeypatch.setattr(bulk_create, "build_resolved", flaky)
    docs = [
        _doc(DocumentKind.CATEGORY, "cat", CategorySpec(name="cat")),
        _assistant("second"),
    ]
    report = BulkCreator(FakeClient()).create_all(docs, TARGET)
    assert [e.name for e in report.created] == ["cat"]
    assert report.failed.name == "second"
    assert report.failed.error_type == "apply_failed"
