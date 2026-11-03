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

import pytest
from codemie_sdk.exceptions import ApiError

from codemie_iac import serializer
from codemie_iac.cli.commands.apply import apply_command
from codemie_iac.cli.exit_status import ExitStatus
from codemie_iac.envelope import Bundle
from codemie_iac.specs.integration import CredentialRefEntry
from tests.plan_apply.fakes import Call, FakeAssistants, FakeClient, FakeIntegrations
from tests.plan_apply.test_bulk_create import (
    IdAssistants,
    _assistant as _named_assistant,
    _integration,
    _writes,
)
from tests.plan_apply.test_single_entity_apply import _assistant, _live


def _write(path: Path, *docs) -> Path:
    path.write_text(serializer.to_yaml(Bundle(list(docs))))
    return path


def _run(path, entity_id=None, client=None, json_output=False):
    out = io.StringIO()
    status = apply_command(
        path,
        entity_id,
        json_output=json_output,
        project="proj",
        client=client or FakeClient(),
        out=out,
    )
    return status, out.getvalue()


def test_file_with_id_updates_and_exits_zero(tmp_path):
    client = FakeClient(assistants=FakeAssistants(get=_live(system_prompt="old")))
    status, text = _run(_write(tmp_path / "a.yaml", _assistant()), "asst-1", client)
    assert status == ExitStatus.SUCCESS == 0
    assert len(client.assistants.calls_to("update")) == 1
    assert "updated" in text


def test_unchanged_rerun_prints_no_change_made(tmp_path):
    client = FakeClient(assistants=FakeAssistants(get=_live()))
    status, text = _run(_write(tmp_path / "a.yaml", _assistant()), "asst-1", client)
    assert status == 0
    assert "no change made" in text
    assert client.assistants.calls_to("update") == []


def test_file_without_id_prints_new_id(tmp_path):
    status, text = _run(_write(tmp_path / "a.yaml", _assistant()))
    assert status == 0
    assert "asst-1" in text


def test_directory_bulk_creates_every_yaml_file(tmp_path):
    _write(tmp_path / "a.yaml", _named_assistant("a"))
    _write(tmp_path / "b.yaml", _named_assistant("b"))
    client = FakeClient(assistants=IdAssistants())
    status, text = _run(tmp_path, client=client)
    assert status == 0
    assert len(client.assistants.calls_to("create")) == 2
    assert "id-a" in text and "id-b" in text


def test_directory_with_id_is_config_error(tmp_path):
    _write(tmp_path / "a.yaml", _named_assistant("a"))
    client = FakeClient(assistants=IdAssistants())
    status, text = _run(tmp_path, "asst-1", client)
    assert status == ExitStatus.CONFIG_ERROR == 4
    assert text
    assert _writes(client) == []


def test_unresolved_credential_names_reference_and_writes_nothing(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    integ = _integration(values=[CredentialRefEntry(key="t", ref="env:MISSING_VAR")])
    _write(tmp_path / "a.yaml", integ)
    client = FakeClient()
    status, text = _run(tmp_path, client=client)
    assert status == ExitStatus.UNRESOLVED_INPUT == 3
    assert "env:MISSING_VAR" in text
    assert _writes(client) == []


def test_single_file_unresolved_credential_gives_three(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    integ = _integration(values=[CredentialRefEntry(key="t", ref="env:MISSING_VAR")])
    client = FakeClient()
    status, text = _run(_write(tmp_path / "a.yaml", integ), client=client)
    assert status == 3
    assert "env:MISSING_VAR" in text
    assert _writes(client) == []


def test_platform_rejection_gives_two_with_field_errors(tmp_path):
    cause = ApiError(
        "invalid",
        status_code=422,
        response={"detail": [{"loc": ["body", "name"], "msg": "too long"}]},
    )
    client = FakeClient(assistants=FakeAssistants(create=cause))
    status, text = _run(_write(tmp_path / "a.yaml", _assistant()), client=client)
    assert status == ExitStatus.APPLY_FAILED == 2
    assert "name" in text and "too long" in text


def test_bulk_failure_gives_two_with_created_and_field_errors(tmp_path):
    for name in ("a", "b"):
        _write(tmp_path / f"{name}.yaml", _named_assistant(name))
    client = FakeClient(assistants=IdAssistants(fail_on="b"))
    status, text = _run(tmp_path, client=client)
    assert status == 2
    assert "id-a" in text
    assert "platform_rejection" in text


@pytest.mark.parametrize("count", [0, 2])
def test_wrong_document_count_gives_five(tmp_path, count):
    docs = [_assistant() for _ in range(count)]
    status, text = _run(_write(tmp_path / "a.yaml", *docs))
    assert status == ExitStatus.INVALID_DOCUMENT == 5
    assert text


SECRET = "s3cr3t-resolved-value-42"


class _LeakyIntegrations(FakeIntegrations):
    """Fails like a platform that echoes the submitted credential value."""

    def create(self, settings):
        self.calls.append(Call("create", (settings,), {}))
        raise ApiError(
            f"rejected {SECRET}",
            status_code=422,
            response={"detail": [{"loc": ["body", "token"], "msg": f"bad {SECRET}"}]},
        )


class _EchoIntegrations(FakeIntegrations):
    """Succeeds but returns the submitted credential value as the id."""

    def create(self, settings):
        self.calls.append(Call("create", (settings,), {}))
        return {"id": f"int-{SECRET}"}


def _secret_integration():
    return _integration(values=[CredentialRefEntry(key="t", ref="env:LEAK_VAR")])


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("as_dir", [False, True])
def test_failed_create_never_prints_resolved_credential(
    tmp_path, monkeypatch, as_json, as_dir
):
    monkeypatch.setenv("LEAK_VAR", SECRET)
    path = _write(tmp_path / "a.yaml", _secret_integration())
    client = FakeClient(integrations=_LeakyIntegrations())
    status, text = _run(
        tmp_path if as_dir else path, client=client, json_output=as_json
    )
    assert status == ExitStatus.APPLY_FAILED
    assert client.integrations.calls_to("create")
    assert SECRET not in text
    if as_json:
        json.loads(text)


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("as_dir", [False, True])
def test_echoed_credential_in_result_is_scrubbed(
    tmp_path, monkeypatch, as_json, as_dir
):
    monkeypatch.setenv("LEAK_VAR", SECRET)
    path = _write(tmp_path / "a.yaml", _secret_integration())
    client = FakeClient(integrations=_EchoIntegrations())
    status, text = _run(
        tmp_path if as_dir else path, client=client, json_output=as_json
    )
    assert status == ExitStatus.SUCCESS
    assert "int-" in text
    assert SECRET not in text
    if as_json:
        json.loads(text)


def test_empty_directory_gives_five_naming_directory(tmp_path):
    client = FakeClient(assistants=IdAssistants())
    status, text = _run(tmp_path, client=client)
    assert status == ExitStatus.INVALID_DOCUMENT == 5
    assert str(tmp_path) in text and ".yaml" in text
    assert _writes(client) == []


def test_directory_with_only_subdirectory_named_yaml_gives_five(tmp_path):
    (tmp_path / "x.yaml").mkdir()
    status, _ = _run(tmp_path, client=FakeClient(assistants=IdAssistants()))
    assert status == 5


def test_directory_processes_yml_files(tmp_path):
    _write(tmp_path / "a.yml", _named_assistant("a"))
    client = FakeClient(assistants=IdAssistants())
    status, text = _run(tmp_path, client=client)
    assert status == 0
    assert "id-a" in text


def test_directory_ignores_subdirectory_named_yaml(tmp_path):
    (tmp_path / "x.yaml").mkdir()
    _write(tmp_path / "a.yaml", _named_assistant("a"))
    client = FakeClient(assistants=IdAssistants())
    status, _ = _run(tmp_path, client=client)
    assert status == 0
    assert len(client.assistants.calls_to("create")) == 1


def test_credentials_come_from_given_environ_not_process_env(tmp_path, monkeypatch):
    monkeypatch.delenv("LEAK_VAR", raising=False)
    path = _write(tmp_path / "a.yaml", _secret_integration())
    client = FakeClient(integrations=_EchoIntegrations())
    out = io.StringIO()
    status = apply_command(
        path,
        None,
        json_output=False,
        project="proj",
        client=client,
        out=out,
        environ={"LEAK_VAR": SECRET},
    )
    assert status == ExitStatus.SUCCESS
    assert client.integrations.calls_to("create")
    assert SECRET not in out.getvalue()
