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

"""Process exit statuses of the plan/apply CLI and the exception mapping."""

from enum import IntEnum

from pydantic import ValidationError

from ..plan_apply.errors import (
    ApplyError,
    PlatformRejectionError,
    UnresolvableCredentialError,
    UnresolvedReferenceError,
)
from ..resolver import ReferenceResolutionError
from ..schema import DocumentValidationError
from ..serializer import DocumentParseError
from .documents import InvalidDocumentError
from .target_config import ConfigError

__all__ = ["ExitStatus", "exit_status_for"]


class ExitStatus(IntEnum):
    """Exit codes; ``NOTHING_TO_DO`` is an alias of ``SUCCESS``."""

    SUCCESS = 0
    NOTHING_TO_DO = 0
    CHANGES_PENDING = 1
    APPLY_FAILED = 2
    UNRESOLVED_INPUT = 3
    CONFIG_ERROR = 4
    INVALID_DOCUMENT = 5


#: Checked in order: subclasses of ``ApplyError`` precede ``ApplyError``
#: itself, which the guards raise for unsupported or inconsistent documents.
_MAPPING: tuple[tuple[tuple[type[BaseException], ...], ExitStatus], ...] = (
    ((ConfigError,), ExitStatus.CONFIG_ERROR),
    (
        (UnresolvedReferenceError, UnresolvableCredentialError),
        ExitStatus.UNRESOLVED_INPUT,
    ),
    ((PlatformRejectionError,), ExitStatus.APPLY_FAILED),
    (
        (
            ApplyError,
            DocumentParseError,
            DocumentValidationError,
            ValidationError,
            ReferenceResolutionError,
            InvalidDocumentError,
        ),
        ExitStatus.INVALID_DOCUMENT,
    ),
)


def exit_status_for(
    exc: BaseException, default: ExitStatus | None = None
) -> ExitStatus:
    """Return the exit status for ``exc``; ``default`` if unknown, else raise it."""
    for types, status in _MAPPING:
        if isinstance(exc, types):
            return status
    if default is None:
        raise exc
    return default
