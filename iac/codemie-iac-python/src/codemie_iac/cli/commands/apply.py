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

"""The ``apply`` command: create or update entities from YAML documents."""

from pathlib import Path
from collections.abc import Mapping
from typing import Any, TextIO

from ...plan_apply import BulkCreator, EnvCredentialResolver, SingleEntityPlanner
from ..documents import (
    InvalidDocumentError,
    apply_default_project,
    read_bundle,
    single_document,
)
from ..exit_status import ExitStatus, exit_status_for
from ..render import render_apply_result, render_bulk_report, render_error
from ..target_config import ConfigError

__all__ = ["apply_command"]


def _apply_directory(
    path: Path,
    entity_id: str | None,
    json_output: bool,
    project: str,
    client: Any,
    out: TextIO,
    credentials: EnvCredentialResolver,
) -> ExitStatus:
    if entity_id:
        raise ConfigError("--id cannot be combined with a directory")
    files = sorted(
        file
        for pattern in ("*.yaml", "*.yml")
        for file in path.glob(pattern)
        if file.is_file()
    )
    if not files:
        raise InvalidDocumentError(f"no .yaml/.yml documents found in {path}")
    documents = apply_default_project(
        (document for file in files for document in read_bundle(file)), project
    )
    report = BulkCreator(client, credentials=credentials).create_all(documents, project)
    status = ExitStatus.APPLY_FAILED if report.failed else ExitStatus.SUCCESS
    out.write(
        render_bulk_report(
            report,
            json_output=json_output,
            status=status,
            secrets=credentials.revealed_values(),
        )
    )
    return status


def _apply_file(
    path: Path,
    entity_id: str | None,
    json_output: bool,
    project: str,
    client: Any,
    out: TextIO,
    credentials: EnvCredentialResolver,
) -> ExitStatus:
    (document,) = apply_default_project([single_document(read_bundle(path))], project)
    result = SingleEntityPlanner(client, credentials=credentials).apply(
        document, entity_id, project
    )
    out.write(
        render_apply_result(
            result,
            json_output=json_output,
            status=ExitStatus.SUCCESS,
            secrets=credentials.revealed_values(),
        )
    )
    return ExitStatus.SUCCESS


def apply_command(
    path: Path,
    entity_id: str | None,
    *,
    json_output: bool,
    project: str,
    client: Any,
    out: TextIO,
    environ: Mapping[str, str] | None = None,
) -> ExitStatus:
    """Apply a file (create/update one entity) or a directory (bulk create).

    ``environ`` is what ``env:NAME`` credential references read (default: the process environment).
    """
    credentials = EnvCredentialResolver(environ)
    handler = _apply_directory if path.is_dir() else _apply_file
    try:
        return handler(path, entity_id, json_output, project, client, out, credentials)
    except Exception as exc:  # noqa: BLE001 - unmapped errors become APPLY_FAILED
        status = exit_status_for(exc, default=ExitStatus.APPLY_FAILED)
        out.write(
            render_error(
                exc,
                json_output=json_output,
                status=status,
                secrets=credentials.revealed_values(),
            )
        )
        return status
