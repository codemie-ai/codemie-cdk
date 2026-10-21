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

import base64
import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, quote_plus

import requests
from codemie_sdk.exceptions import ApiError, CodeMieError
from pydantic import BaseModel, ConfigDict

__all__ = [
    "PLATFORM_ERRORS",
    "ApplyError",
    "FieldError",
    "PlatformRejectionError",
    "UnresolvableCredentialError",
    "UnresolvedReferenceError",
    "scrub",
]

_REDACTED = "[redacted]"

#: What a rejected platform call raises. The SDK calls ``raise_for_status()``,
#: so in practice it is ``requests.HTTPError``; ``ApiError`` is kept for
#: callers (and fakes) that raise the SDK's own error type.
PLATFORM_ERRORS = (ApiError, requests.HTTPError)


def _forms(secret: str) -> set[str]:
    """The secret as it may appear in a response: raw, JSON-escaped,
    URL-encoded and base64 (standard and URL-safe) of the bare value.

    A composite encoding (``base64("user:secret")`` for basic auth) is not
    covered: the other half is unknown here.
    """
    raw = secret.encode()
    return {
        secret,
        json.dumps(secret)[1:-1],
        quote(secret, safe=""),
        quote_plus(secret),
        base64.b64encode(raw).decode(),
        base64.urlsafe_b64encode(raw).decode(),
    }


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """``text`` with every known secret value (in its common encodings)
    replaced by a placeholder."""
    forms = {f for s in secrets if s for f in _forms(s) if f}
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, _REDACTED)
    return text


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


_GENERAL = "(request)"


def _loc_field(loc: Any) -> str:
    parts = [str(p) for p in loc if p != "body"] if isinstance(loc, list) else []
    return ".".join(parts) or _GENERAL


def _fastapi_errors(detail: Any, secrets: Iterable[str]) -> list[FieldError]:
    """FastAPI validation errors: ``detail: [{loc, msg}]`` (or a plain string)."""
    if isinstance(detail, str):
        return [FieldError(field=_GENERAL, message=scrub(detail, secrets))]
    found = []
    for item in detail if isinstance(detail, list) else []:
        if isinstance(item, dict) and isinstance(item.get("msg"), str):
            found.append(
                FieldError(
                    field=scrub(_loc_field(item.get("loc")), secrets),
                    message=scrub(item["msg"], secrets),
                )
            )
    return found


def _backend_errors(error: Any, secrets: Iterable[str]) -> list[FieldError]:
    """The backend envelope: ``{"error": {"message", "details", "help"}}``."""
    if not isinstance(error, dict) or not isinstance(error.get("message"), str):
        return []
    message = error["message"]
    details = error.get("details")
    if isinstance(details, str) and details:
        message = f"{message}: {details}"
    return [FieldError(field=_GENERAL, message=scrub(message, secrets))]


def _parse_field_errors(
    body: Any, secrets: Iterable[str] = ()
) -> list[FieldError] | None:
    """Field errors as the backend sends them (secrets scrubbed); None when none."""
    if not isinstance(body, dict):
        return None
    parsed = _fastapi_errors(body.get("detail"), secrets) or _backend_errors(
        body.get("error"), secrets
    )
    return parsed or None


def _status_and_body(cause: Exception) -> tuple[int | None, Any]:
    if isinstance(cause, requests.HTTPError):
        response = cause.response
        if response is None:
            return None, None
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, None
    return getattr(cause, "status_code", None), getattr(cause, "response", None)


class PlatformRejectionError(ApplyError):
    """The platform rejected a create/update call.

    Keeps only the scrubbed message, the HTTP status and the parsed field
    errors; the original exception (whose request body holds the resolved
    credentials) is deliberately not kept, so a printed traceback cannot
    show it.
    """

    def __init__(
        self,
        error_type: str,
        entity_kind: str,
        entity_name: str,
        cause: ApiError | requests.HTTPError,
        secrets: Iterable[str] = (),
    ):
        secrets = tuple(secrets)
        self.status_code, body = _status_and_body(cause)
        self.structured_errors: list[FieldError] | None = _parse_field_errors(
            body, secrets
        )
        super().__init__(
            error_type, entity_kind, entity_name, scrub(str(cause), secrets)
        )
