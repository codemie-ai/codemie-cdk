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

"""``codemie-iac init``: write a ``codemie.yaml`` template."""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional, TextIO

from .config_model import ENVIRONMENT_KEYS, ConfigError
from .target_config import DEFAULT_CONFIG_PATH

__all__ = ["init_command", "render_template"]

#: Example variable names; the user may rename them in the generated file.
_PROJECT_VARIABLE = "CODEMIE_PROJECT"


def _variable(key: str) -> str:
    name = key.upper()
    return name if name.startswith("CODEMIE_") else f"CODEMIE_{name}"


def render_template() -> str:
    """Build the file from the model's fields so it cannot drift from the model."""
    lines = [
        "# Values come from the shell or .env through ${NAME}; rename the variables freely.",
        "project:",
        f"  name: ${{{_PROJECT_VARIABLE}:-}}",
        "environment:",
    ]
    lines += [f"  {key}: ${{{_variable(key)}:-}}" for key in ENVIRONMENT_KEYS]
    return "\n".join(lines) + "\n"


def _create(path: Path, text: str) -> None:
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        raise ConfigError(f"{path} already exists; use --force to replace it") from None
    except OSError:
        raise ConfigError(f"Cannot write {path}") from None


def _replace(path: Path, text: str) -> None:
    try:
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=".codemie-init-"
        )
    except OSError:
        raise ConfigError(f"Cannot write {path}") from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except OSError:
        Path(temp_name).unlink(missing_ok=True)
        raise ConfigError(f"Cannot write {path}") from None
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def init_command(
    force: bool,
    *,
    config_path: Optional[str],
    json_output: bool,
    out: TextIO,
) -> int:
    """Write the template to ``config_path``; refuse to overwrite without force."""
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    (_replace if force else _create)(path, render_template())
    if json_output:
        out.write(json.dumps({"path": str(path)}) + "\n")
    else:
        out.write(f"Wrote {path}\n")
    return 0
