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
from .init_command import init_command
from .render import render_error
from .target_config import ConfigError, TargetConfig

__all__ = ["main"]


def _add_plan(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("file", type=Path, help="document file to compare")
    sub.add_argument("--id", dest="entity_id", default=None, help="entity id")


def _add_apply(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("path", type=Path, help="document file or directory")
    sub.add_argument("--id", dest="entity_id", default=None, help="entity id")


def _add_init(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--force", action="store_true", help="overwrite an existing file")


def _run_init(args: argparse.Namespace, **context: Any) -> ExitStatus:
    return ExitStatus(init_command(args.force, **context))


def _run_plan(args: argparse.Namespace, **context: Any) -> ExitStatus:
    return plan_command(args.file, args.entity_id, **context)


def _run_apply(args: argparse.Namespace, **context: Any) -> ExitStatus:
    return apply_command(args.path, args.entity_id, **context)


# name -> (help, argument registrar, runner); extend to add commands.
#: name -> (help text, argument registrar, runner, needs_target)
_COMMANDS: dict[str, tuple[str, Callable, Callable, bool]] = {
    "plan": ("Show the diff against a live entity", _add_plan, _run_plan, True),
    "apply": ("Apply documents to the platform", _add_apply, _run_apply, True),
    "init": ("Write a codemie.yaml template", _add_init, _run_init, False),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemie-iac")
    parser.add_argument("--project", default=None, help="target project")
    parser.add_argument("-c", "--config", default=None, help="codemie.yaml path")
    parser.add_argument("--env-file", default=None, help=".env path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, register, _, _) in _COMMANDS.items():
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


def _check_usage(args: argparse.Namespace) -> None:
    """Reject bad argument combinations before any network call is made."""
    if args.command == "plan" and not args.entity_id:
        raise ConfigError("plan requires --id of the entity to compare against")
    if args.command == "apply" and args.entity_id and args.path.is_dir():
        raise ConfigError("--id cannot be combined with a directory")


def _print_warnings(warnings: Sequence[str]) -> None:
    for text in dict.fromkeys(warnings):
        sys.stderr.write(f"warning: {text}\n")


def _connect(args: argparse.Namespace) -> tuple[TargetConfig, Any]:
    """Resolve the target and build the client; warnings are printed first."""
    try:
        target = TargetConfig.resolve(args.project, args.config, env_file=args.env_file)
    except Exception as exc:  # noqa: BLE001 - rendered by type name only
        _print_warnings(getattr(exc, "warnings", ()))
        raise
    _print_warnings(target.warnings)
    return target, target.build_client()


def _context(args: argparse.Namespace, needs_target: bool) -> dict[str, Any]:
    context: dict[str, Any] = {"json_output": args.json, "out": sys.stdout}
    if not needs_target:
        return {**context, "config_path": args.config}
    target, client = _connect(args)
    return {
        **context,
        "project": target.project,
        "environ": target.environment,
        "client": client,
    }


def _dispatch(args: argparse.Namespace) -> ExitStatus:
    _, _, runner, needs_target = _COMMANDS[args.command]
    try:
        _check_usage(args)
        context = _context(args, needs_target)
    except Exception as exc:  # noqa: BLE001 - rendered by type name only
        return _fail(exc, args, ExitStatus.CONFIG_ERROR)
    try:
        return runner(args, **context)
    except ConfigError as exc:
        return _fail(exc, args, ExitStatus.CONFIG_ERROR)
    except Exception as exc:  # noqa: BLE001 - rendered by type name only
        return _fail(exc, args, ExitStatus.APPLY_FAILED)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI and return the process exit code."""
    try:
        args = _parse(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return int(_dispatch(args))
