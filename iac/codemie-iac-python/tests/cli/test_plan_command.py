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

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from codemie_iac import serializer
from codemie_iac.cli.commands import plan as plan_module
from codemie_iac.cli.commands.plan import plan_command
from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.envelope import Bundle
from tests.plan_apply.fakes import FakeAssistants, FakeClient
from tests.plan_apply.test_single_entity_plan import (
    _assistant,
    _live_assistant,
)


def _write(tmp_path: Path, *docs) -> Path:
    path = tmp_path / "doc.yaml"
    path.write_text(serializer.to_yaml(Bundle(list(docs))))
    return path


def _client(**live):
    return FakeClient(
        assistants=FakeAssistants(get=SimpleNamespace(**_live_assistant(**live)))
    )


def _run(file, entity_id="asst-1", client=None, json_output=False):
    out = io.StringIO()
    status = plan_command(
        file,
        entity_id,
        json_output=json_output,
        project="proj",
        client=client or _client(),
        out=out,
    )
    return status, out.getvalue()


def test_differences_give_changes_pending_and_field_diff(tmp_path):
    status, text = _run(
        _write(tmp_path, _assistant()), client=_client(system_prompt="edited")
    )
    assert status == ExitStatus.CHANGES_PENDING == 1
    assert "system_prompt" in text and "edited" in text


def test_json_output_has_differences(tmp_path):
    status, text = _run(
        _write(tmp_path, _assistant()),
        client=_client(system_prompt="edited"),
        json_output=True,
    )
    assert status == 1
    assert json.loads(text)["differences"][0]["field"] == "system_prompt"


def test_no_differences_gives_nothing_to_do(tmp_path):
    status, text = _run(_write(tmp_path, _assistant()))
    assert status == ExitStatus.NOTHING_TO_DO == 0
    assert "No differences" in text


def test_only_cannot_compare_gives_zero_with_warnings(tmp_path, monkeypatch):
    from codemie_iac.plan_apply import CannotCompare, Plan

    class _Planner:
        def __init__(self, client):
            pass

        def plan(self, document, entity_id, project):
            return Plan(
                differences=[],
                cannot_compare=[
                    CannotCompare(field="credentials.token", reason="masked")
                ],
            )

    monkeypatch.setattr(plan_module, "SingleEntityPlanner", _Planner)
    status, text = _run(_write(tmp_path, _assistant()))
    assert status == 0
    assert "warning: cannot compare credentials.token" in text


def test_missing_id_is_config_error_before_reading(tmp_path):
    status, text = _run(tmp_path / "does-not-exist.yaml", entity_id=None)
    assert status == ExitStatus.CONFIG_ERROR == 4
    assert text


@pytest.mark.parametrize("count", [0, 2])
def test_wrong_document_count_is_invalid_document(tmp_path, count):
    docs = [_assistant() for _ in range(count)]
    status, text = _run(_write(tmp_path, *docs))
    assert status == ExitStatus.INVALID_DOCUMENT == 5
    assert text


def test_no_credential_resolver_is_constructed(tmp_path, monkeypatch):
    built = []

    class _Spy:
        def __init__(self, *a, **k):
            built.append(1)

    monkeypatch.setattr(plan_module, "EnvCredentialResolver", _Spy, raising=False)
    seen = {}
    real = plan_module.SingleEntityPlanner

    def _planner(*args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return real(*args, **kwargs)

    monkeypatch.setattr(plan_module, "SingleEntityPlanner", _planner)
    _run(_write(tmp_path, _assistant()))
    assert built == []
    assert len(seen["args"]) == 1 and seen["kwargs"] == {}
