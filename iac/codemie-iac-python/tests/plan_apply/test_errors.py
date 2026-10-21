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

import json

import pytest

from codemie_sdk.exceptions import ApiError, CodeMieError

from codemie_iac.plan_apply.errors import (
    ApplyError,
    FieldError,
    PlatformRejectionError,
    scrub,
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
    assert err.status_code == 500
    assert err.structured_errors is None
    assert err.reason == str(cause) == "boom"


def test_platform_rejection_without_response():
    err = PlatformRejectionError(
        "platform_rejection", "assistant", "a1", ApiError("bad")
    )
    assert err.structured_errors is None


def _http_error(status, body, message="boom"):
    import requests

    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    return requests.HTTPError(message, response=response)


def test_platform_rejection_parses_fastapi_validation_errors():
    cause = _http_error(
        422,
        {
            "detail": [
                {"loc": ["body", "name"], "msg": "too long"},
                {"loc": ["body", "llm", 0], "msg": "unknown"},
            ]
        },
    )
    err = PlatformRejectionError("platform_rejection", "assistant", "a1", cause)
    assert err.status_code == 422
    assert err.structured_errors == [
        FieldError(field="name", message="too long"),
        FieldError(field="llm.0", message="unknown"),
    ]


def test_platform_rejection_parses_the_backend_error_envelope():
    cause = _http_error(
        400, {"error": {"message": "Invalid", "details": "bad name", "help": None}}
    )
    err = PlatformRejectionError("platform_rejection", "assistant", "a1", cause)
    assert err.structured_errors == [
        FieldError(field="(request)", message="Invalid: bad name")
    ]


def test_platform_rejection_does_not_keep_the_original_exception():
    cause = _http_error(500, {})
    err = PlatformRejectionError("platform_rejection", "assistant", "a1", cause)
    assert not hasattr(err, "cause")


def test_platform_rejection_ignores_malformed_field_errors():
    cause = ApiError("invalid", response={"detail": [{"loc": ["x"]}, "junk", 3]})
    err = PlatformRejectionError("platform_rejection", "assistant", "a1", cause)
    assert err.structured_errors is None


@pytest.mark.parametrize(
    "form",
    [
        'p@ss/w&rd"x',  # raw
        'p@ss/w&rd\\"x',  # JSON-escaped
        "p%40ss%2Fw%26rd%22x",  # URL-encoded
        "cEBzcy93JnJkIng=",  # base64 of the bare value
    ],
)
def test_scrub_replaces_common_encodings_of_a_secret(form):
    assert scrub(f"echo {form} end", ['p@ss/w&rd"x']) == "echo [redacted] end"
