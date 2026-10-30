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

"""The ``plan`` command: diff one document against one live entity."""

from pathlib import Path
from typing import Any, TextIO

from ...plan_apply import Plan, SingleEntityPlanner
from ..documents import apply_default_project, read_bundle, single_document
from ..exit_status import ExitStatus, exit_status_for
from ..render import render_error, render_plan
from ..target_config import ConfigError

__all__ = ["plan_command"]


def _plan_status(plan: Plan) -> ExitStatus:
    return ExitStatus.CHANGES_PENDING if plan.differences else ExitStatus.NOTHING_TO_DO


def _compute_plan(file: Path, entity_id: str, project: str, client: Any) -> Plan:
    if not entity_id:
        raise ConfigError("plan requires --id of the entity to compare against")
    (document,) = apply_default_project([single_document(read_bundle(file))], project)
    return SingleEntityPlanner(client).plan(document, entity_id, project)


def plan_command(
    file: Path,
    entity_id: str | None,
    *,
    json_output: bool,
    project: str,
    client: Any,
    out: TextIO,
) -> ExitStatus:
    """Write the plan of ``file`` against entity ``entity_id`` to ``out``."""
    try:
        plan = _compute_plan(file, entity_id, project, client)
    except Exception as exc:  # noqa: BLE001 - unmapped errors become APPLY_FAILED
        status = exit_status_for(exc, default=ExitStatus.APPLY_FAILED)
        out.write(render_error(exc, json_output=json_output, status=status))
        return status
    status = _plan_status(plan)
    out.write(render_plan(plan, json_output=json_output, status=status))
    return status
