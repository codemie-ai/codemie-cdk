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

"""Minimal ``.env`` reader (no ``${}`` expansion, no new dependency)."""

import re
from typing import Optional

__all__ = ["parse_env_text", "read_env_file"]

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EXPORT = re.compile(r"^export\s+")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_line(raw: str) -> Optional[tuple[str, str]]:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, _, value = _EXPORT.sub("", line).partition("=")
    key = key.strip()
    if not _KEY.match(key):
        return None
    return key, _unquote(value.strip())


def parse_env_text(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines; later duplicates win, bad lines are skipped."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        parsed = _parse_line(raw)
        if parsed:
            values[parsed[0]] = parsed[1]
    return values


def read_env_file(path: str) -> dict[str, str]:
    """Read and parse ``path``; raises ``OSError`` / ``UnicodeDecodeError``."""
    with open(path, encoding="utf-8") as handle:
        return parse_env_text(handle.read())
