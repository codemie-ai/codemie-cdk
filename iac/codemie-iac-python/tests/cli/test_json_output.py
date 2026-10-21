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

"""Text and JSON renderings carry the same facts and JSON round-trips."""

import json

from codemie_sdk.exceptions import ApiError

from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.cli.render import (
    render_apply_result,
    render_bulk_report,
    render_error,
    render_plan,
)
from codemie_iac.plan_apply import (
    ApplyResult,
    BulkCreateReport,
    CannotCompare,
    CreatedEntity,
    Difference,
    FailedEntity,
    FieldError,
    Plan,
    PlatformRejectionError,
    UnresolvedReferenceError,
)
from codemie_iac.envelope import DocumentKind


def _plan():
    return Plan(
        differences=[
            Difference(field="description", document_value="new", live_value="old")
        ],
        cannot_compare=[
            CannotCompare(field="credentials.token", reason="secret not comparable")
        ],
    )


def test_plan_text_lists_difference_and_warning():
    text = render_plan(_plan(), json_output=False, status=ExitStatus.CHANGES_PENDING)
    assert "description" in text and "new" in text and "old" in text
    assert "warning" in text.lower() and "credentials.token" in text


def test_plan_json_round_trips_with_status():
    data = json.loads(
        render_plan(_plan(), json_output=True, status=ExitStatus.CHANGES_PENDING)
    )
    assert data["differences"][0] == {
        "field": "description",
        "document_value": "new",
        "live_value": "old",
    }
    assert data["cannot_compare"][0]["field"] == "credentials.token"
    assert data["status"] == "changes_pending" and data["exit_code"] == 1


def test_apply_created_text_and_json():
    result = ApplyResult(id="id-9", created=True)
    assert "id-9" in render_apply_result(
        result, json_output=False, status=ExitStatus.SUCCESS
    )
    data = json.loads(
        render_apply_result(result, json_output=True, status=ExitStatus.SUCCESS)
    )
    assert data["id"] == "id-9" and data["created"] is True and data["exit_code"] == 0


def test_apply_unchanged_says_no_change_made():
    result = ApplyResult(
        id="id-1", created=False, changed=False, uncomparable=["credentials.token"]
    )
    text = render_apply_result(result, json_output=False, status=ExitStatus.SUCCESS)
    assert "no change made" in text and "credentials.token" in text
    data = json.loads(
        render_apply_result(result, json_output=True, status=ExitStatus.SUCCESS)
    )
    assert data["changed"] is False and data["uncomparable"] == ["credentials.token"]


def test_apply_updated_text():
    result = ApplyResult(id="id-1", created=False)
    text = render_apply_result(result, json_output=False, status=ExitStatus.SUCCESS)
    assert "updated" in text.lower() and "no change made" not in text


def _report():
    return BulkCreateReport(
        created=[CreatedEntity(kind=DocumentKind.ASSISTANT, name="a1", id="i1")],
        failed=FailedEntity(
            kind=DocumentKind.SKILL,
            name="s1",
            error_type="platform_rejection",
            reason="bad request",
            structured_errors=[FieldError(field="name", message="too long")],
        ),
    )


def test_bulk_report_text_and_json_agree():
    text = render_bulk_report(
        _report(), json_output=False, status=ExitStatus.APPLY_FAILED
    )
    for fact in ("a1", "i1", "s1", "bad request", "name", "too long"):
        assert fact in text
    data = json.loads(
        render_bulk_report(_report(), json_output=True, status=ExitStatus.APPLY_FAILED)
    )
    assert data["created"][0]["name"] == "a1"
    assert data["failed"]["structured_errors"][0]["message"] == "too long"
    assert data["exit_code"] == 2 and data["status"] == "apply_failed"


def test_bulk_report_success_has_no_failure():
    report = BulkCreateReport(created=[], failed=None)
    data = json.loads(
        render_bulk_report(report, json_output=True, status=ExitStatus.SUCCESS)
    )
    assert data["failed"] is None


def test_error_platform_rejection_text_and_json():
    exc = PlatformRejectionError(
        "platform_rejection",
        "assistant",
        "a1",
        ApiError(
            "rejected",
            status_code=422,
            response={"detail": [{"loc": ["body", "name"], "msg": "bad"}]},
        ),
    )
    text = render_error(exc, json_output=False, status=ExitStatus.APPLY_FAILED)
    for fact in ("assistant", "a1", "rejected", "name", "bad"):
        assert fact in text
    data = json.loads(
        render_error(exc, json_output=True, status=ExitStatus.APPLY_FAILED)
    )
    assert data["kind"] == "assistant" and data["name"] == "a1"
    assert data["structured_errors"] == [{"field": "name", "message": "bad"}]
    assert data["exit_code"] == 2


def test_error_unresolved_reference_names_reference():
    exc = UnresolvedReferenceError(
        "unresolved_reference", "integration", "my-int", "not found"
    )
    text = render_error(exc, json_output=False, status=ExitStatus.UNRESOLVED_INPUT)
    assert "my-int" in text and "not found" in text
    data = json.loads(
        render_error(exc, json_output=True, status=ExitStatus.UNRESOLVED_INPUT)
    )
    assert data["name"] == "my-int" and data["reason"] == "not found"
    assert data["error_type"] == "unresolved_reference" and data["exit_code"] == 3


def test_error_other_exception_never_uses_message():
    class Odd(Exception):
        pass

    text = render_error(
        Odd("token=hunter2"), json_output=False, status=ExitStatus.INVALID_DOCUMENT
    )
    assert "hunter2" not in text and "Odd" in text
