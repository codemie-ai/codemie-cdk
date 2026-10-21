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

import pytest
from pydantic import BaseModel

from codemie_iac.credentials import CredentialRef
from codemie_iac.plan_apply.credentials import EnvCredentialResolver, SecretValue
from codemie_iac.plan_apply.errors import UnresolvableCredentialError
from codemie_iac.specs.assistant import (
    AssistantSpec,
    MCPServerConfigSpec,
    MCPServerDetailsSpec,
)
from codemie_iac.specs.integration import CredentialRefEntry, IntegrationSpec

SECRET = "s3cr3t-value-xyz"


def _ref(name: str = "MY_TOKEN") -> CredentialRef:
    return CredentialRef(f"env:{name}")


def test_resolve_returns_masked_secret():
    secret = EnvCredentialResolver({"MY_TOKEN": SECRET}).resolve(_ref())
    assert isinstance(secret, SecretValue)
    assert secret.reveal() == SECRET
    assert SECRET not in repr(secret)
    assert SECRET not in str(secret)
    assert SECRET not in f"{secret}"
    assert SECRET not in f"{secret!r}"


def test_secret_not_in_pydantic_dump():
    class Holder(BaseModel):
        s: SecretValue

    holder = Holder(s=SecretValue(SECRET))
    assert SECRET not in str(holder.model_dump())
    assert SECRET not in holder.model_dump_json()
    assert SECRET not in repr(holder)


def test_missing_var_raises_naming_ref_only():
    with pytest.raises(UnresolvableCredentialError) as ei:
        EnvCredentialResolver({}).resolve(_ref())
    assert "env:MY_TOKEN" in ei.value.reason
    assert ei.value.error_type == "unresolvable_credential"


def test_empty_var_is_unresolvable():
    resolver = EnvCredentialResolver({"MY_TOKEN": ""})
    assert resolver.is_resolvable(_ref()) is False
    with pytest.raises(UnresolvableCredentialError):
        resolver.resolve(_ref())


def test_is_resolvable_true_when_set():
    assert EnvCredentialResolver({"MY_TOKEN": "x"}).is_resolvable(_ref()) is True


def test_collect_refs_integration():
    spec = IntegrationSpec(
        project_name="p",
        credential_type="Jira",
        credential_values=[CredentialRefEntry(key="k", ref=_ref("A"))],
    )
    assert [r.root for r in EnvCredentialResolver.collect_refs(spec)] == ["env:A"]


def test_collect_refs_assistant_mcp():
    cfg = MCPServerConfigSpec(
        url=_ref("U"),
        args=["plain", _ref("ARG")],
        headers={"h": _ref("H")},
        env={"e": _ref("E")},
        auth_token=_ref("TOK"),
    )
    spec = AssistantSpec.model_construct(
        mcp_servers=[MCPServerDetailsSpec.model_construct(config=cfg)]
    )
    names = {r.root for r in EnvCredentialResolver.collect_refs(spec)}
    assert names == {"env:U", "env:ARG", "env:H", "env:E", "env:TOK"}


def test_collect_refs_none_for_plain_spec():
    assert EnvCredentialResolver.collect_refs(object()) == []
