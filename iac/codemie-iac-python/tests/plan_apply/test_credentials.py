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
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply import credentials as creds
from codemie_iac.plan_apply.credentials import (
    SECRET_FIELDS,
    EnvCredentialResolver,
    SecretValue,
)
from codemie_iac.plan_apply.errors import UnresolvableCredentialError
from codemie_iac.plan_apply.single_apply import (
    _credential_findings,
    _settings_findings,
)
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
    assert [r.root for r in EnvCredentialResolver().collect_refs(spec)] == ["env:A"]


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
    names = {r.root for r in EnvCredentialResolver().collect_refs(spec)}
    assert names == {"env:U", "env:ARG", "env:H", "env:E", "env:TOK"}


def test_collect_refs_none_for_plain_spec():
    assert EnvCredentialResolver().collect_refs(object()) == []


def _ds_doc(type_, **extra):
    raw = {"name": "ds_one", "project_name": "p", "description": "d", "type": type_}
    raw.update(extra)
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name="ds_one"),
        spec=raw,
    )


def _provider(**settings):
    return _ds_doc("provider", provider_name="acme", toolkit_id="tk", settings=settings)


pytestmark = pytest.mark.usefixtures("no_lookup")


def test_secret_fields_table_covers_datasource_kinds():
    assert set(SECRET_FIELDS) >= {"provider", "svn", "knowledge_base_xray"}


def test_provider_literal_secret_rejected_naming_setting_not_value():
    doc = _provider(pat=SECRET, index="idx")
    with pytest.raises(UnresolvableCredentialError) as ei:
        EnvCredentialResolver().collect_refs(doc.spec)
    assert "pat" in ei.value.reason
    assert "ds_one" in str(ei.value)
    assert SECRET not in str(ei.value)
    assert SECRET not in ei.value.reason


def test_provider_env_ref_collected_and_resolved():
    doc = _provider(api_key="env:ACME_KEY", index="env:ACME_INDEX")
    refs = EnvCredentialResolver().collect_refs(doc.spec)
    assert [r.root for r in refs] == ["env:ACME_KEY", "env:ACME_INDEX"]
    assert (
        EnvCredentialResolver({"ACME_KEY": SECRET}).resolve(refs[0]).reveal() == SECRET
    )


def test_provider_without_schema_fails_closed_for_any_literal():
    # No schema lookup installed: even a benign-looking name is rejected.
    with pytest.raises(UnresolvableCredentialError) as ei:
        EnvCredentialResolver().collect_refs(_provider(pat=SECRET).spec)
    assert "pat" in ei.value.reason and SECRET not in ei.value.reason


def test_provider_schema_overrides_name_heuristics():
    resolver = EnvCredentialResolver(provider_secret_lookup=lambda p, t: ["pat"])
    # max_tokens is not schema-secret: a literal is fine; pat is: rejected.
    assert resolver.collect_refs(_provider(max_tokens=5).spec) == []
    with pytest.raises(UnresolvableCredentialError):
        resolver.collect_refs(_provider(pat=SECRET).spec)


def test_provider_secret_keys_from_injected_schema_lookup():
    seen = []

    def lookup(provider_name, toolkit_id):
        seen.append((provider_name, toolkit_id))
        return ["custom_field"]

    resolver = EnvCredentialResolver(provider_secret_lookup=lookup)
    with pytest.raises(UnresolvableCredentialError) as ei:
        resolver.collect_refs(_provider(custom_field=SECRET).spec)
    assert "custom_field" in ei.value.reason and SECRET not in ei.value.reason
    assert seen == [("acme", "tk")]
    refs = resolver.collect_refs(_provider(custom_field="env:CF").spec)
    assert [r.root for r in refs] == ["env:CF"]


def test_provider_lookup_failure_fails_closed():
    def broken(provider_name, toolkit_id):
        raise RuntimeError("offline")

    resolver = EnvCredentialResolver(provider_secret_lookup=broken)
    with pytest.raises(UnresolvableCredentialError):
        resolver.collect_refs(_provider(whatever=SECRET).spec)


def test_unknown_schema_skips_values_that_cannot_hold_a_secret():
    spec = _provider(max_tokens=5, enabled=True, ratio=0.5, note=None, ids=[1, 2]).spec
    assert EnvCredentialResolver().collect_refs(spec) == []


def test_unknown_schema_still_rejects_containers_holding_strings():
    for value in (["a-literal"], {"nested": SECRET}):
        with pytest.raises(UnresolvableCredentialError) as ei:
            EnvCredentialResolver().collect_refs(_provider(opts=value).spec)
        assert "opts" in ei.value.reason and SECRET not in ei.value.reason


def test_unknown_schema_accepts_containers_of_env_refs():
    spec = _provider(opts={"k": "env:A"}, many=["env:B", 3]).spec
    assert [r.root for r in EnvCredentialResolver().collect_refs(spec)] == [
        "env:A",
        "env:B",
    ]


def test_known_schema_still_rejects_a_non_string_secret_value():
    resolver = EnvCredentialResolver(provider_secret_lookup=lambda p, t: ["pin"])
    with pytest.raises(UnresolvableCredentialError):
        resolver.collect_refs(_provider(pin=1234).spec)


def test_error_says_no_lookup_is_configured():
    with pytest.raises(UnresolvableCredentialError) as ei:
        EnvCredentialResolver().collect_refs(_provider(region=SECRET).spec)
    assert "schema lookup was unavailable" in ei.value.reason
    assert "no lookup configured" in ei.value.reason
    assert "region" in ei.value.reason and SECRET not in str(ei.value)


def test_error_names_the_lookup_exception_type_but_not_its_text_or_the_value():
    def broken(provider_name, toolkit_id):
        raise RuntimeError(f"offline {SECRET}")

    resolver = EnvCredentialResolver(provider_secret_lookup=broken)
    with pytest.raises(UnresolvableCredentialError) as ei:
        resolver.collect_refs(_provider(region=SECRET).spec)
    assert "schema lookup was unavailable" in ei.value.reason
    assert "RuntimeError" in ei.value.reason
    assert SECRET not in str(ei.value) and SECRET not in repr(ei.value)


def test_known_schema_error_has_no_unavailable_note():
    resolver = EnvCredentialResolver(provider_secret_lookup=lambda p, t: ["pat"])
    with pytest.raises(UnresolvableCredentialError) as ei:
        resolver.collect_refs(_provider(pat=SECRET).spec)
    assert "unavailable" not in ei.value.reason


@pytest.mark.parametrize(
    "type_,extra",
    [
        ("svn", {"link": "https://s/r"}),
        ("knowledge_base_xray", {"jql": "project = X"}),
        ("knowledge_base_sharepoint", {"site_url": "https://x.sharepoint.com"}),
    ],
)
def test_other_datasources_produce_no_candidates(type_, extra):
    doc = _ds_doc(type_, **extra)
    assert list(creds._iter_candidates(doc.spec, None)) == []
    assert EnvCredentialResolver().collect_refs(doc.spec) == []


def test_credential_findings_flags_provider_secret_without_value():
    doc = _provider(api_key="env:ACME_KEY")
    live = {"settings": {"api_key": "********"}}
    findings = _settings_findings(
        doc, live, EnvCredentialResolver({"ACME_KEY": SECRET})
    )
    assert [f.field for f in findings] == ["settings.api_key"]
    assert SECRET not in findings[0].reason


def test_credential_findings_rejects_provider_literal_secret():
    doc = _provider(pat=SECRET)
    with pytest.raises(UnresolvableCredentialError) as ei:
        _settings_findings(doc, {"settings": {}}, EnvCredentialResolver({}))
    assert "pat" in ei.value.reason and SECRET not in str(ei.value)


def test_credential_findings_empty_for_svn():
    doc = _ds_doc("svn", link="https://s/r")
    assert _credential_findings(doc, EnvCredentialResolver({})) == []


def test_lookup_returning_a_bare_string_counts_as_schema_unavailable():
    # frozenset("api_key") would be single characters and let a literal pass.
    resolver = EnvCredentialResolver(provider_secret_lookup=lambda p, t: "region")
    with pytest.raises(UnresolvableCredentialError) as ei:
        resolver.collect_refs(_provider(region=SECRET).spec)
    assert "schema lookup was unavailable" in ei.value.reason
    assert "str" in ei.value.reason and SECRET not in str(ei.value)


def test_lookup_returning_non_string_names_counts_as_schema_unavailable():
    resolver = EnvCredentialResolver(provider_secret_lookup=lambda p, t: [1, 2])
    with pytest.raises(UnresolvableCredentialError) as ei:
        resolver.collect_refs(_provider(region=SECRET).spec)
    assert "schema lookup was unavailable" in ei.value.reason


def test_empty_lookup_result_means_the_schema_marks_nothing_secret():
    # An authoritative answer, not a failure: literals are accepted.
    resolver = EnvCredentialResolver(provider_secret_lookup=lambda p, t: [])
    assert resolver.collect_refs(_provider(region=SECRET).spec) == []


def test_each_resolver_keeps_its_own_lookup():
    lenient = EnvCredentialResolver(provider_secret_lookup=lambda p, t: [])
    strict = EnvCredentialResolver()
    assert lenient.collect_refs(_provider(region=SECRET).spec) == []
    with pytest.raises(UnresolvableCredentialError):
        strict.collect_refs(_provider(region=SECRET).spec)


def test_with_provider_secret_lookup_leaves_the_original_unchanged_and_shares_reveals():
    base = EnvCredentialResolver({"A": "v"})
    derived = base.with_provider_secret_lookup(lambda p, t: [])
    with pytest.raises(UnresolvableCredentialError):
        base.collect_refs(_provider(region=SECRET).spec)
    derived.resolve(CredentialRef("env:A"))
    assert base.revealed_values() == frozenset({"v"})
