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
"""Complexity gate: no function in the CLI package exceeds mccabe 15."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

__all__ = []

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    importlib.util.find_spec("ruff") is None,
    reason="ruff is not importable in this environment",
)
def test_cli_functions_within_complexity_gate():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "C901",
            "src/codemie_iac/cli",
        ],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
