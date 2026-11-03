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

"""Entrypoint of the ``codemie-iac`` command line."""

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from .commands.apply import apply_command
from .commands.plan import plan_command
from .exit_status import ExitStatus
from .render import render_error
from .target_config import TargetConfig

__all__ = ["main"]


def _add_plan(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("file", type=Path, help="document file to compare")
    sub.add_argument("--id", dest="entity_id", default=None, help="entity id")


def _add_apply(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("path", type=Path, help="document file or directory")
    sub.add_argument("--id", dest="entity_id", default=None, help="entity id")


def _run_plan(args: argparse.Namespace, **context: Any) -> ExitStatus:
    context.pop("environ", None)  # plan never resolves credentials
    return plan_command(args.file, args.entity_id, **context)


def _run_apply(args: argparse.Namespace, **context: Any) -> ExitStatus:
    return apply_command(args.path, args.entity_id, **context)


# name -> (help, argument registrar, runner); extend to add commands.
_COMMANDS: dict[str, tuple[str, Callable, Callable]] = {
    "plan": ("Show the diff against a live entity", _add_plan, _run_plan),
    "apply": ("Apply documents to the platform", _add_apply, _run_apply),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemie-iac")
    parser.add_argument("--project", default=None, help="target project")
    parser.add_argument("-c", "--config", default=None, help="codemie.yaml path")
    parser.add_argument("--env-file", default=None, help=".env path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, register, _) in _COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text)
        register(sub)
        sub.add_argument("--json", action="store_true", help="JSON output")
    return parser


def _parse(argv: Optional[Sequence[str]]) -> Optional[argparse.Namespace]:
    try:
        return _build_parser().parse_args(argv)
    except SystemExit as exc:
        if exc.code in (0, None):
            raise
        raise SystemExit(int(ExitStatus.CONFIG_ERROR)) from None


def _fail(exc: Exception, args: argparse.Namespace, status: ExitStatus) -> ExitStatus:
    sys.stdout.write(render_error(exc, json_output=args.json, status=status))
    return status


def _dispatch(args: argparse.Namespace) -> ExitStatus:
    try:
        target = TargetConfig.resolve(args.project, args.config, env_file=args.env_file)
        client = target.build_client()
    except Exception as exc:  # noqa: BLE001 - rendered by type name only
        return _fail(exc, args, ExitStatus.CONFIG_ERROR)
    runner = _COMMANDS[args.command][2]
    try:
        return runner(
            args,
            json_output=args.json,
            project=target.project,
            environ=target.environment,
            client=client,
            out=sys.stdout,
        )
    except Exception as exc:  # noqa: BLE001 - rendered by type name only
        return _fail(exc, args, ExitStatus.APPLY_FAILED)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI and return the process exit code."""
    try:
        args = _parse(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return int(_dispatch(args))
