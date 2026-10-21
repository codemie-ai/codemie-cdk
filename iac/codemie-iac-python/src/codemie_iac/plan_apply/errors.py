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

"""Structured errors raised by the plan/apply layer."""

from collections.abc import Iterable
from typing import Any

from codemie_sdk.exceptions import ApiError, CodeMieError
from pydantic import BaseModel, ConfigDict

__all__ = [
    "ApplyError",
    "FieldError",
    "PlatformRejectionError",
    "UnresolvableCredentialError",
    "UnresolvedReferenceError",
    "scrub",
]

_REDACTED = "[redacted]"


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """``text`` with every known secret value replaced by a placeholder."""
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, _REDACTED)
    return text


_ERROR_LIST_KEYS = ("errors", "details", "detail")


class FieldError(BaseModel):
    """A single field-level problem reported by the platform."""

    model_config = ConfigDict(extra="forbid")

    field: str
    message: str


class ApplyError(CodeMieError):
    """Base error for a failure while planning or applying one entity."""

    def __init__(
        self, error_type: str, entity_kind: str, entity_name: str, reason: str
    ):
        self.error_type = error_type
        self.entity_kind = entity_kind
        self.entity_name = entity_name
        self.reason = reason
        super().__init__(f"{entity_kind}/{entity_name}: {reason}")


class UnresolvedReferenceError(ApplyError):
    """A reference to another entity could not be resolved."""


class UnresolvableCredentialError(ApplyError):
    """A credential value could not be resolved."""


def _parse_item(item: Any, secrets: Iterable[str]) -> FieldError | None:
    if not isinstance(item, dict):
        return None
    field, message = item.get("field"), item.get("message")
    if isinstance(field, str) and isinstance(message, str):
        return FieldError(field=scrub(field, secrets), message=scrub(message, secrets))
    return None


def _parse_field_errors(
    response: Any, secrets: Iterable[str] = ()
) -> list[FieldError] | None:
    """Extract field errors as returned (secrets scrubbed); None when none."""
    if not isinstance(response, dict):
        return None
    for key in _ERROR_LIST_KEYS:
        items = response.get(key)
        if isinstance(items, list):
            parsed = [fe for fe in (_parse_item(i, secrets) for i in items) if fe]
            if parsed:
                return parsed
    return None


class PlatformRejectionError(ApplyError):
    """The platform rejected a create/update call."""

    def __init__(
        self,
        error_type: str,
        entity_kind: str,
        entity_name: str,
        cause: ApiError,
        secrets: Iterable[str] = (),
    ):
        secrets = tuple(secrets)
        self.cause = cause
        self.structured_errors: list[FieldError] | None = _parse_field_errors(
            getattr(cause, "response", None), secrets
        )
        super().__init__(
            error_type, entity_kind, entity_name, scrub(str(cause), secrets)
        )
