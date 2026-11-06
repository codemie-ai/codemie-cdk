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

"""Tests for the CLI exit-status contract."""

import pytest
from pydantic import BaseModel, ValidationError

from codemie_iac.cli.exit_status import ExitStatus, exit_status_for
from codemie_iac.plan_apply.errors import (
    ApplyError,
    PlatformRejectionError,
    UnresolvableCredentialError,
    UnresolvedReferenceError,
)
from codemie_iac.resolver import ReferenceResolutionError
from codemie_iac.schema import DocumentValidationError
from codemie_iac.serializer import DocumentParseError
from codemie_sdk.exceptions import ApiError


class _Model(BaseModel):
    value: int


def _pydantic_error() -> ValidationError:
    try:
        _Model.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError")


def _apply(cls):
    return cls("t", "assistant", "a", "reason")


def test_enum_values():
    assert {s.name: s.value for s in ExitStatus} == {
        "SUCCESS": 0,
        "CHANGES_PENDING": 1,
        "APPLY_FAILED": 2,
        "UNRESOLVED_INPUT": 3,
        "CONFIG_ERROR": 4,
        "INVALID_DOCUMENT": 5,
    }
    assert ExitStatus.NOTHING_TO_DO is ExitStatus.SUCCESS
    assert ExitStatus.NOTHING_TO_DO == 0


CASES = [
    (lambda: _apply(UnresolvedReferenceError), ExitStatus.UNRESOLVED_INPUT),
    (lambda: _apply(UnresolvableCredentialError), ExitStatus.UNRESOLVED_INPUT),
    (
        lambda: PlatformRejectionError("t", "assistant", "a", ApiError("boom")),
        ExitStatus.APPLY_FAILED,
    ),
    (lambda: _apply(ApplyError), ExitStatus.INVALID_DOCUMENT),
    (lambda: DocumentParseError("bad yaml"), ExitStatus.INVALID_DOCUMENT),
    (lambda: DocumentValidationError("$.x", "bad"), ExitStatus.INVALID_DOCUMENT),
    (_pydantic_error, ExitStatus.INVALID_DOCUMENT),
    (
        lambda: ReferenceResolutionError("assistant", "a", False),
        ExitStatus.INVALID_DOCUMENT,
    ),
]


@pytest.mark.parametrize("make,expected", CASES)
def test_exit_status_for(make, expected):
    assert exit_status_for(make()) is expected


def test_unknown_exception_is_raised():
    exc = RuntimeError("unexpected")
    with pytest.raises(RuntimeError) as info:
        exit_status_for(exc)
    assert info.value is exc
