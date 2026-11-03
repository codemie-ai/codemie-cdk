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

"""Text and JSON rendering of plan/apply results and errors.

Every renderer returns a ``str``. Only engine-scrubbed fields (``reason``,
``structured_errors``) are used for errors, never ``str(exc)``; the final
output is additionally passed through ``scrub()`` with any extra ``secrets``.
"""

import json
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from ..plan_apply import (
    ApplyError,
    ApplyResult,
    BulkCreateReport,
    Plan,
)
from ..plan_apply.errors import platform_detail, scrub
from .documents import InvalidDocumentError
from .exit_status import ExitStatus
from .target_config import ConfigError

__all__ = [
    "render_apply_result",
    "render_bulk_report",
    "render_error",
    "render_plan",
]


def _scrub_value(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return scrub(value, secrets)
    if isinstance(value, dict):
        return {
            _scrub_value(k, secrets): _scrub_value(v, secrets) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(v, secrets) for v in value]
    return value


def _emit_json(payload: dict, status: ExitStatus, secrets: Iterable[str]) -> str:
    payload = {
        **payload,
        "status": ExitStatus(status).name.lower(),
        "exit_code": int(status),
    }
    return json.dumps(_scrub_value(payload, tuple(secrets)), indent=2, default=str)


def _emit_text(lines: list[str], secrets: Iterable[str]) -> str:
    return scrub("\n".join(lines), tuple(secrets))


def _val(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _field_error_lines(errors: Any, indent: str = "  ") -> list[str]:
    return [f"{indent}- {e.field}: {e.message}" for e in errors or []]


def render_plan(
    plan: Plan,
    *,
    json_output: bool,
    status: ExitStatus,
    secrets: Iterable[str] = (),
) -> str:
    """Render a plan: differences, and ``cannot_compare`` as warnings."""
    if json_output:
        return _emit_json(plan.model_dump(mode="json"), status, secrets)
    lines = ["No differences." if plan.is_empty else "Differences:"]
    for d in plan.differences:
        lines.append(f"  {d.field}")
        lines.append(f"    document: {_val(d.document_value)}")
        lines.append(f"    live:     {_val(d.live_value)}")
    lines += [
        f"warning: cannot compare {c.field}: {c.reason}" for c in plan.cannot_compare
    ]
    return _emit_text(lines, secrets)


def _id_suffix(entity_id: str | None) -> str:
    # The platform does not return an id for every kind (e.g. integrations).
    return f" (id: {entity_id})" if entity_id else ""


def _apply_headline(result: ApplyResult) -> str:
    if result.created:
        return f"created{_id_suffix(result.id)}"
    if not result.changed:
        return f"no change made{_id_suffix(result.id)}"
    return f"updated{_id_suffix(result.id)}"


def render_apply_result(
    result: ApplyResult,
    *,
    json_output: bool,
    status: ExitStatus,
    secrets: Iterable[str] = (),
) -> str:
    """Render a single-entity apply outcome."""
    if json_output:
        return _emit_json(result.model_dump(mode="json"), status, secrets)
    lines = [_apply_headline(result)]
    lines += [f"warning: could not compare {f}" for f in result.uncomparable]
    return _emit_text(lines, secrets)


def render_bulk_report(
    report: BulkCreateReport,
    *,
    json_output: bool,
    status: ExitStatus,
    secrets: Iterable[str] = (),
) -> str:
    """Render a bulk create report: created entities and the first failure."""
    if json_output:
        return _emit_json(report.model_dump(mode="json"), status, secrets)
    lines = [f"created {len(report.created)}:"]
    lines += [f"  {c.kind.value}/{c.name}{_id_suffix(c.id)}" for c in report.created]
    failed = report.failed
    if failed is not None:
        lines.append(f"failed: {failed.kind.value}/{failed.name} [{failed.error_type}]")
        lines.append(f"  reason: {failed.reason}")
        lines += _field_error_lines(failed.structured_errors)
    return _emit_text(lines, secrets)


def _validation_reason(exc: ValidationError) -> str:
    """``loc: message`` per problem; never the offending input value."""
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
    )


def _error_payload(exc: BaseException) -> dict:
    if isinstance(exc, ApplyError):
        errors = getattr(exc, "structured_errors", None)
        return {
            "error_type": exc.error_type,
            "kind": exc.entity_kind,
            "name": exc.entity_name,
            "reason": exc.reason,
            "structured_errors": (
                [e.model_dump(mode="json") for e in errors] if errors else None
            ),
        }
    if isinstance(exc, (ConfigError, InvalidDocumentError)):
        reason = str(exc)
    elif isinstance(exc, ValidationError):
        reason = _validation_reason(exc)
    else:
        reason = platform_detail(exc)  # the HTTP response body, scrubbed on emit
    return {"error_type": type(exc).__name__, "reason": reason}


def _error_lines(exc: BaseException, payload: dict) -> list[str]:
    if isinstance(exc, ApplyError):
        lines = [
            f"error: {payload['kind']}/{payload['name']} [{payload['error_type']}]",
            f"  reason: {payload['reason']}",
        ]
        return lines + _field_error_lines(getattr(exc, "structured_errors", None))
    if payload["reason"]:
        return [f"error: {payload['error_type']}: {payload['reason']}"]
    return [f"error: {payload['error_type']}"]


def render_error(
    exc: BaseException,
    *,
    json_output: bool,
    status: ExitStatus,
    secrets: Iterable[str] = (),
) -> str:
    """Render an error from its scrubbed fields; never ``str(exc)``.

    Only ``ConfigError`` and ``InvalidDocumentError`` (documented secret-free)
    expose their message.
    """
    payload = _error_payload(exc)
    if json_output:
        return _emit_json(payload, status, secrets)
    return _emit_text(_error_lines(exc, payload), secrets)
