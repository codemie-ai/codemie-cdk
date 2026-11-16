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

"""The ``export`` command: write one live entity as a YAML document."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from ...envelope import Bundle
from ...export import export_document
from ...serializer import to_yaml
from ..exit_status import ExitStatus, exit_status_for
from ..render import render_error

__all__ = ["export_command"]


def export_command(
    kind: str,
    entity_id: str,
    out_path: str | None,
    *,
    project: str,
    client: Any,
    out: TextIO,
    environ: Mapping[str, str] | None = None,
    json_output: bool = False,
) -> ExitStatus:
    """Write entity ``entity_id`` as YAML to ``out_path`` or to ``out``.

    Nothing is written unless the fetch, parse and serialise all succeed.
    ``json_output``, ``project`` and ``environ`` are accepted for the shared
    command context and ignored.
    """
    try:
        text = to_yaml(Bundle([export_document(client, kind, entity_id)]))
        if out_path:
            Path(out_path).write_text(text)
        else:
            out.write(text)
    except Exception as exc:  # noqa: BLE001 - unmapped errors become APPLY_FAILED
        status = exit_status_for(exc, default=ExitStatus.APPLY_FAILED)
        out.write(render_error(exc, json_output=False, status=status))
        return status
    return ExitStatus.SUCCESS
