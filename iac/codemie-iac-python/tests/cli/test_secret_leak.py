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

"""A secret-bearing credential never reaches text or JSON output."""

import json

from codemie_sdk.exceptions import ApiError

from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.cli.render import render_apply_result, render_error, render_plan
from codemie_iac.plan_apply import (
    ApplyResult,
    Difference,
    Plan,
    PlatformRejectionError,
)

SECRET = "s3cr3t-token-value"


def _failure():
    cause = ApiError(
        f"rejected token {SECRET}",
        status_code=422,
        response={"errors": [{"field": "token", "message": f"bad {SECRET}"}]},
    )
    return PlatformRejectionError(
        "platform_rejection", "integration", "int1", cause, secrets=[SECRET]
    )


def test_failing_apply_error_hides_secret_in_both_forms():
    for as_json in (False, True):
        out = render_error(
            _failure(), json_output=as_json, status=ExitStatus.APPLY_FAILED
        )
        assert SECRET not in out
        assert "[redacted]" in out


def test_extra_secrets_scrubbed_from_plan_values():
    plan = Plan(
        differences=[
            Difference(field="x", document_value=f"v-{SECRET}", live_value="y")
        ]
    )
    for as_json in (False, True):
        out = render_plan(
            plan,
            json_output=as_json,
            status=ExitStatus.CHANGES_PENDING,
            secrets=[SECRET],
        )
        assert SECRET not in out


def test_extra_secrets_scrubbed_from_apply_result():
    result = ApplyResult(id=f"id-{SECRET}", created=True, uncomparable=[f"f-{SECRET}"])
    for as_json in (False, True):
        out = render_apply_result(
            result, json_output=as_json, status=ExitStatus.SUCCESS, secrets=[SECRET]
        )
        assert SECRET not in out
        if as_json:
            json.loads(out)
