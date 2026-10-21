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

from codemie_sdk.exceptions import ApiError, CodeMieError

from codemie_iac.plan_apply.errors import (
    ApplyError,
    FieldError,
    PlatformRejectionError,
    UnresolvableCredentialError,
    UnresolvedReferenceError,
)


def test_apply_error_attributes_and_hierarchy():
    err = UnresolvedReferenceError(
        "unresolved_reference", "assistant", "a1", "no such datasource"
    )
    assert isinstance(err, ApplyError) and isinstance(err, CodeMieError)
    assert (err.error_type, err.entity_kind, err.entity_name, err.reason) == (
        "unresolved_reference",
        "assistant",
        "a1",
        "no such datasource",
    )
    assert "assistant" in str(err) and "a1" in str(err)
    assert isinstance(
        UnresolvableCredentialError("unresolvable_credential", "integration", "i", "r"),
        ApplyError,
    )


def test_platform_rejection_without_field_errors():
    cause = ApiError("boom", status_code=500, response={"message": "x"})
    err = PlatformRejectionError("platform_rejection", "assistant", "a1", cause)
    assert err.cause is cause
    assert err.structured_errors is None
    assert err.reason == str(cause) == "boom"


def test_platform_rejection_without_response():
    err = PlatformRejectionError(
        "platform_rejection", "assistant", "a1", ApiError("bad")
    )
    assert err.structured_errors is None


def test_platform_rejection_exposes_field_errors_verbatim():
    cause = ApiError(
        "invalid",
        status_code=422,
        response={
            "errors": [
                {"field": "name", "message": "too long"},
                {"field": "llm", "message": "unknown"},
            ]
        },
    )
    err = PlatformRejectionError("platform_rejection", "assistant", "a1", cause)
    assert err.structured_errors == [
        FieldError(field="name", message="too long"),
        FieldError(field="llm", message="unknown"),
    ]


def test_platform_rejection_ignores_malformed_field_errors():
    cause = ApiError("invalid", response={"errors": [{"field": "x"}, "junk", 3]})
    err = PlatformRejectionError("platform_rejection", "assistant", "a1", cause)
    assert err.structured_errors is None
