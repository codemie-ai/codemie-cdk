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
from pydantic import ConfigDict, TypeAdapter, ValidationError

from codemie_sdk.models.datasource import (
    AzureDevOpsWikiDataSourceRequest,
    AzureDevOpsWorkItemDataSourceRequest,
    CodeDataSourceRequest,
    ConfluenceDataSourceRequest,
    FileDataSourceRequest,
    GitFaqDataSourceRequest,
    GoogleDataSourceRequest,
    JiraDataSourceRequest,
    ProviderDataSourceRequest,
    SharePointDataSourceRequest,
    SvnDataSourceRequest,
    XrayDataSourceRequest,
    XWikiDataSourceRequest,
)

from codemie_iac.specs.datasource import (
    AzureDevOpsWikiDatasourceSpec,
    AzureDevOpsWorkItemDatasourceSpec,
    CodeDatasourceSpec,
    ConfluenceDatasourceSpec,
    DatasourceSpec,
    FileDatasourceSpec,
    GitFaqDatasourceSpec,
    GoogleDatasourceSpec,
    JiraDatasourceSpec,
    ProviderDatasourceSpec,
    SharepointDatasourceSpec,
    SvnDatasourceSpec,
    XrayDatasourceSpec,
    XWikiDatasourceSpec,
)
from codemie_iac.envelope import Document, DocumentKind, DocumentMeta

_adapter = TypeAdapter(DatasourceSpec)


def test_roundtrip_code():
    spec = CodeDatasourceSpec(
        name="code_ds",
        project_name="proj1",
        description="Code datasource",
        shared_with_project=True,
        setting_id="int-123",
        cron_expression="0 0 * * *",
        timezone="UTC",
        type="code",
        link="https://github.com/org/repo",
        branch="main",
        index_type="code",
        files_filter="*.py",
        embeddings_model="text-embedding-3-small",
        summarization_model="gpt-4o",
        prompt="Summarize the code",
        docs_generation=True,
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_git_faq():
    spec = GitFaqDatasourceSpec(
        name="git_faq_ds",
        project_name="proj1",
        description="Git FAQ datasource",
        shared_with_project=False,
        setting_id="int-456",
        cron_expression=None,
        timezone="UTC",
        type="knowledge_base_git_faq",
        link="https://github.com/org/repo",
        branch="main",
        files_filter="*.md",
        embedding_model="text-embedding-3-small",
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_jira():
    spec = JiraDatasourceSpec(
        name="jira_ds",
        project_name="proj1",
        description="Jira datasource",
        shared_with_project=True,
        setting_id="int-789",
        type="knowledge_base_jira",
        jql="project = ABC",
        custom_fields=["customfield_100", "customfield_200"],
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_confluence():
    spec = ConfluenceDatasourceSpec(
        name="confluence_ds",
        project_name="proj1",
        description="Confluence datasource",
        shared_with_project=False,
        setting_id="int-321",
        type="knowledge_base_confluence",
        cql="space = DEV",
        include_restricted_content=False,
        include_archived_content=True,
        include_attachments=True,
        include_comments=False,
        keep_markdown_format=True,
        keep_newlines=False,
        max_pages=100,
        pages_per_request=25,
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_google():
    spec = GoogleDatasourceSpec(
        name="google_ds",
        project_name="proj1",
        description="Google docs datasource",
        shared_with_project=True,
        setting_id="int-654",
        type="llm_routing_google",
        google_doc="https://docs.google.com/document/d/abc123",
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_file():
    spec = FileDatasourceSpec(
        name="file_ds",
        project_name="proj1",
        description="File datasource",
        shared_with_project=False,
        setting_id=None,
        type="knowledge_base_file",
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_azure_devops_wiki():
    spec = AzureDevOpsWikiDatasourceSpec(
        name="ado_wiki_ds",
        project_name="proj1",
        description="Azure DevOps Wiki datasource",
        shared_with_project=True,
        setting_id="int-987",
        type="knowledge_base_azure_devops_wiki",
        wiki_query="path:Home",
        organization="my-org",
        project="my-project",
        wiki_name="MyWiki",
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_azure_devops_work_item():
    spec = AzureDevOpsWorkItemDatasourceSpec(
        name="ado_wi_ds",
        project_name="proj1",
        description="Azure DevOps Work Item datasource",
        shared_with_project=False,
        setting_id="int-111",
        type="knowledge_base_azure_devops_work_item",
        wiql_query="SELECT * FROM WorkItems",
        organization="my-org",
        project="my-project",
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_roundtrip_xwiki():
    spec = XWikiDatasourceSpec(
        name="xwiki_ds",
        project_name="proj1",
        description="xWiki datasource",
        shared_with_project=True,
        setting_id="int-222",
        type="knowledge_base_xwiki",
        space="Main",
        wiki="xwiki",
    )
    dumped = spec.model_dump()
    assert _adapter.validate_python(dumped) == spec


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        _adapter.validate_python(
            {"type": "not_a_real_type", "name": "x", "description": "d"}
        )


def test_code_spec_from_entity():
    request = CodeDataSourceRequest(
        name="my_code_kb",
        project_name="my-project",
        description="Code knowledge base",
        link="https://github.com/org/repo",
        branch="main",
    )
    spec = CodeDatasourceSpec.from_entity(request)
    assert spec == CodeDatasourceSpec(
        name=request.name,
        project_name=request.project_name,
        description=request.description,
        shared_with_project=request.shared_with_project,
        setting_id=request.setting_id,
        cron_expression=request.cron_expression,
        timezone=request.timezone,
        link=request.link,
        branch=request.branch,
        index_type=request.index_type,
        files_filter=request.files_filter,
        embeddings_model=request.embeddings_model,
        summarization_model=request.summarization_model,
        prompt=request.prompt,
        docs_generation=request.docs_generation,
    )


def test_git_faq_spec_from_entity():
    request = GitFaqDataSourceRequest(
        name="git_faq_kb",
        project_name="my-project",
        description="Git FAQ knowledge base",
        link="https://github.com/org/repo",
        branch="main",
    )
    spec = GitFaqDatasourceSpec.from_entity(request)
    assert spec.link == request.link
    assert spec.embedding_model == request.embedding_model


def test_jira_spec_from_entity():
    request = JiraDataSourceRequest(
        name="jira_kb",
        project_name="my-project",
        description="Jira knowledge base",
        jql="project = PROJ",
        setting_id="jira-prod",
    )
    spec = JiraDatasourceSpec.from_entity(request)
    assert spec.jql == request.jql
    assert spec.setting_id == "jira-prod"


def test_confluence_spec_from_entity():
    request = ConfluenceDataSourceRequest(
        name="confluence_kb",
        project_name="my-project",
        description="Confluence knowledge base",
        cql="space = DEV",
    )
    spec = ConfluenceDatasourceSpec.from_entity(request)
    assert spec.cql == request.cql


def test_google_spec_from_entity():
    request = GoogleDataSourceRequest(
        name="google_kb",
        project_name="my-project",
        description="Google docs knowledge base",
        google_doc="https://docs.google.com/document/d/abc123",
    )
    spec = GoogleDatasourceSpec.from_entity(request)
    assert spec.google_doc == request.google_doc


def test_file_spec_from_entity():
    request = FileDataSourceRequest(
        name="file_kb", project_name="my-project", description="File knowledge base"
    )
    spec = FileDatasourceSpec.from_entity(request)
    assert spec.name == request.name


def test_azure_devops_wiki_spec_from_entity():
    request = AzureDevOpsWikiDataSourceRequest(
        name="ado_wiki_kb",
        project_name="my-project",
        description="Azure DevOps wiki knowledge base",
        wiki_query="path:Home",
        organization="my-org",
        project="my-project",
        wiki_name="MyWiki",
    )
    spec = AzureDevOpsWikiDatasourceSpec.from_entity(request)
    assert spec.wiki_name == request.wiki_name


def test_azure_devops_work_item_spec_from_entity():
    request = AzureDevOpsWorkItemDataSourceRequest(
        name="ado_wi_kb",
        project_name="my-project",
        description="Azure DevOps work item knowledge base",
        wiql_query="SELECT * FROM WorkItems",
        organization="my-org",
        project="my-project",
    )
    spec = AzureDevOpsWorkItemDatasourceSpec.from_entity(request)
    assert spec.wiql_query == request.wiql_query


def test_xwiki_spec_from_entity():
    request = XWikiDataSourceRequest(
        name="xwiki_kb",
        project_name="my-project",
        description="xWiki knowledge base",
        space="Main",
        wiki="xwiki",
    )
    spec = XWikiDatasourceSpec.from_entity(request)
    assert spec.space == request.space
    assert spec.wiki == request.wiki


_NEW_KINDS = {
    "svn": (SvnDatasourceSpec, {"link": "https://svn.example.com/repo"}, "link"),
    "knowledge_base_sharepoint": (
        SharepointDatasourceSpec,
        {"site_url": "https://example.sharepoint.com/sites/x"},
        "site_url",
    ),
    "knowledge_base_xray": (XrayDatasourceSpec, {"jql": "project = X"}, "jql"),
}


def _raw(type_, **extra):
    return {
        "name": "ds_one",
        "project_name": "proj",
        "description": "d",
        "type": type_,
        **extra,
    }


def _document(raw):
    return Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name=raw["name"]),
        spec=raw,
    )


@pytest.mark.parametrize("type_", list(_NEW_KINDS))
def test_new_kind_roundtrips_through_union(type_):
    cls, required, _ = _NEW_KINDS[type_]
    spec = cls(name="ds_one", project_name="proj", description="d", **required)
    assert spec.type == type_
    assert _adapter.validate_python(spec.model_dump()) == spec


def test_roundtrip_provider():
    spec = ProviderDatasourceSpec(
        name="prov_ds",
        project_name="proj",
        description="d",
        provider_name="acme",
        toolkit_id="tk-1",
        settings={"index": "x", "api_key": "env:ACME_KEY"},
    )
    assert spec.type == "provider"
    assert _adapter.validate_python(spec.model_dump()) == spec


@pytest.mark.parametrize("type_", list(_NEW_KINDS))
def test_new_kind_unknown_key_rejected_naming_key(type_):
    _, required, _ = _NEW_KINDS[type_]
    with pytest.raises(ValidationError, match="bogus_key"):
        _document(_raw(type_, bogus_key=1, **required))


def test_provider_unknown_key_rejected():
    with pytest.raises(ValidationError, match="bogus_key"):
        _document(_raw("provider", provider_name="a", toolkit_id="t", bogus_key=1))


@pytest.mark.parametrize("type_", list(_NEW_KINDS))
def test_new_kind_missing_required_setting_names_setting(type_):
    _, _, setting = _NEW_KINDS[type_]
    with pytest.raises(ValidationError, match=setting):
        _document(_raw(type_))


def test_sharepoint_access_token_is_an_env_reference():
    doc = _document(
        _raw(
            "knowledge_base_sharepoint",
            site_url="https://example.sharepoint.com",
            auth_type="oauth_custom",
            access_token="env:TOK",
        )
    )
    assert doc.spec.access_token.root == "env:TOK"


@pytest.mark.parametrize("auth_type", ["oauth_codemie", "oauth_custom"])
def test_sharepoint_oauth_without_access_token_is_accepted(auth_type):
    # An exported document carries no token; the SDK asks for it on create and
    # on a reindexing update, not the document model.
    doc = _document(
        _raw(
            "knowledge_base_sharepoint",
            site_url="https://example.sharepoint.com",
            auth_type=auth_type,
        )
    )
    assert doc.spec.access_token is None


def test_sharepoint_literal_access_token_is_rejected():
    with pytest.raises(ValidationError) as err:
        _document(
            _raw(
                "knowledge_base_sharepoint",
                site_url="https://example.sharepoint.com",
                auth_type="oauth_custom",
                access_token="literal-token-value",
            )
        )
    assert "literal-token-value" not in str(err.value)


def test_svn_branch_is_optional_and_stays_unset():
    spec = SvnDatasourceSpec(
        name="ds_one", project_name="p", description="d", link="https://s/r"
    )
    assert spec.branch is None
    assert (
        SvnDatasourceSpec.model_validate({**spec.model_dump(), "branch": None}).branch
        is None
    )


def test_svn_spec_from_entity():
    request = SvnDataSourceRequest(
        name="svn_kb",
        project_name="p",
        description="d",
        link="https://s/r",
        branch="b1",
        files_filter="*.c",
        embeddings_model="emb",
        prompt="pr",
        docs_generation=True,
        index_type="code",
        setting_id="int-1",
    )
    spec = SvnDatasourceSpec.from_entity(request)
    assert (spec.link, spec.branch, spec.files_filter) == ("https://s/r", "b1", "*.c")
    assert (spec.embeddings_model, spec.prompt) == ("emb", "pr")
    assert spec.docs_generation is True
    assert spec.setting_id == "int-1"


def test_sharepoint_spec_from_entity():
    request = SharePointDataSourceRequest(
        name="sp_kb",
        project_name="p",
        description="d",
        site_url="https://x.sharepoint.com",
        include_pages=True,
        include_documents=False,
        include_lists=True,
        max_file_size_mb=10,
        files_filter="*.docx",
        auth_type="oauth_custom",
        oauth_client_id="cid",
        oauth_tenant_id="tid",
        access_token="transient",
        embedding_model="emb",
        setting_id="int-2",
    )
    spec = SharepointDatasourceSpec.from_entity(request)
    assert spec.site_url == "https://x.sharepoint.com"
    assert (spec.include_pages, spec.include_documents, spec.include_lists) == (
        True,
        False,
        True,
    )
    assert spec.max_file_size_mb == 10
    assert spec.auth_type == "oauth_custom"
    assert spec.access_token.root.endswith("ACCESS_TOKEN")
    assert (spec.oauth_client_id, spec.oauth_tenant_id) == ("cid", "tid")
    assert spec.embedding_model == "emb"
    assert spec.setting_id == "int-2"


def test_xray_spec_from_entity():
    request = XrayDataSourceRequest(
        name="xray_kb",
        project_name="p",
        description="d",
        jql="project = X",
        embedding_model="emb",
        setting_id="int-3",
    )
    spec = XrayDatasourceSpec.from_entity(request)
    assert (spec.jql, spec.embedding_model, spec.setting_id) == (
        "project = X",
        "emb",
        "int-3",
    )


def test_provider_spec_from_entity():
    request = ProviderDataSourceRequest(
        name="prov_kb",
        project_name="p",
        description="d",
        project_space_visible=True,
        provider_name="acme",
        toolkit_id="tk",
        settings={"a": 1},
    )
    spec = ProviderDatasourceSpec.from_entity(request)
    assert (spec.name, spec.project_name, spec.setting_id) == ("prov_kb", "p", None)
    assert spec.shared_with_project is True and spec.description == "d"
    assert (spec.provider_name, spec.toolkit_id, spec.settings) == (
        "acme",
        "tk",
        {"a": 1},
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "knowledge_base_sharepoint", "site_url": "http://x"},
        {
            "type": "knowledge_base_sharepoint",
            "site_url": "https://x",
            "max_file_size_mb": 501,
        },
        {
            "type": "knowledge_base_sharepoint",
            "site_url": "https://x",
            "max_file_size_mb": 0,
        },
        {"type": "svn", "link": ""},
        {"type": "svn", "link": "x" * 1001},
        {"type": "knowledge_base_xray", "jql": ""},
        {
            "type": "provider",
            "provider_name": "p",
            "toolkit_id": "t",
            "settings": {"name": "x"},
        },
        {
            "type": "provider",
            "provider_name": "p",
            "toolkit_id": "t",
            "settings": {"setting_id": "x"},
        },
        {
            "type": "provider",
            "provider_name": "p",
            "toolkit_id": "t",
            "setting_id": "int",
        },
    ],
)
def test_sdk_constraints_and_reserved_keys_rejected_offline(raw):
    base = {"name": "ds_one", "project_name": "p", "description": "d"}
    with pytest.raises(ValidationError):
        TypeAdapter(DatasourceSpec).validate_python({**base, **raw})


# ---- offline, name-based literal-secret rejection for provider settings ----

_LITERAL = "s3cr3t-value-xyz"


_HIDE = ConfigDict(hide_input_in_errors=True)  # what the envelope applies


def _provider_raw(settings):
    return {
        "type": "provider",
        "name": "prov_ds",
        "project_name": "p",
        "description": "d",
        "provider_name": "acme",
        "toolkit_id": "tk",
        "settings": settings,
    }


@pytest.mark.parametrize(
    "settings,path",
    [
        ({"api_key": _LITERAL}, "settings.api_key"),
        ({"apiKey": _LITERAL}, "settings.apiKey"),
        ({"password": _LITERAL}, "settings.password"),
        ({"client_secret": _LITERAL}, "settings.client_secret"),
        ({"auth": {"api_key": _LITERAL}}, "settings.auth.api_key"),
        ({"creds": {"token": [_LITERAL]}}, "settings.creds.token[0]"),
        ({"X-Private-Key": _LITERAL}, "settings.X-Private-Key"),
        ({"AWSAccessKey": _LITERAL}, "settings.AWSAccessKey"),
        ({"vault": {"password": {"value": _LITERAL}}}, "settings.vault.password.value"),
    ],
)
def test_provider_literal_secret_rejected_offline_naming_path_not_value(settings, path):
    with pytest.raises(ValidationError) as ei:
        TypeAdapter(DatasourceSpec, config=_HIDE).validate_python(
            _provider_raw(settings)
        )
    text = str(ei.value)
    assert path in text and "prov_ds" in text
    assert _LITERAL not in text and _LITERAL not in repr(ei.value)
    assert _LITERAL not in str(ei.value.errors(include_input=False))


@pytest.mark.parametrize("meta", [{"kind": "datasource", "name": "prov_ds"}, None])
def test_provider_literal_secret_rejected_through_document_envelope(meta):
    meta = meta or DocumentMeta(kind=DocumentKind.DATASOURCE, name="prov_ds")
    with pytest.raises(ValidationError) as ei:
        Document(
            version="v1",
            meta=meta,
            spec=_provider_raw({"api_key": _LITERAL}),
        )
    assert "settings.api_key" in str(ei.value)
    assert _LITERAL not in str(ei.value) and _LITERAL not in repr(ei.value)


@pytest.mark.parametrize(
    "settings",
    [
        {"api_key": "env:ACME_KEY"},
        {"auth": {"password": "env:ACME_PW"}},
        {"tokens": ["env:A", "env:B"]},
        {"key_prefix": "abc-"},
        {"monkey": "banana"},
        {"tokenizer": "cl100k"},
        {"region": "eu-west-1"},
        {"api_key": ""},
        {"password": 1234},
        {"token": True, "secret": None},
        {"max_tokens": 5, "keys": ["a", "b"]},
    ],
)
def test_provider_secret_named_settings_accepted_when_safe(settings):
    spec = TypeAdapter(DatasourceSpec).validate_python(_provider_raw(settings))
    assert spec.settings == settings


def test_literal_under_non_heuristic_name_passes_offline_but_fails_at_plan_apply():
    from codemie_iac.plan_apply.credentials import EnvCredentialResolver
    from codemie_iac.plan_apply.errors import UnresolvableCredentialError

    doc = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name="prov_ds"),
        spec=_provider_raw({"pat": _LITERAL}),
    )
    resolver = EnvCredentialResolver(
        provider_secret_lookup=lambda provider_name, toolkit_id: ["pat"]
    )
    with pytest.raises(UnresolvableCredentialError) as ei:
        resolver.collect_refs(doc.spec)
    assert "pat" in ei.value.reason and _LITERAL not in str(ei.value)


@pytest.mark.parametrize("type_", list(_NEW_KINDS))
def test_secret_named_setting_check_does_not_affect_other_kinds(type_):
    _, required, _ = _NEW_KINDS[type_]
    # Other kinds forbid unknown keys, but must never fail on the secret rule.
    raw = _raw(type_, **required)
    assert _document(raw).spec.type == type_


@pytest.mark.parametrize("field", ["cron_expression", "timezone"])
def test_provider_schedule_fields_are_rejected(field):
    value = "0 0 * * *" if field == "cron_expression" else "UTC"
    with pytest.raises(ValidationError, match="not supported for provider"):
        _document({**_provider_raw({"region": "eu"}), field: value})


@pytest.mark.parametrize(
    "bad", ["env:my-region", "env:MY.VAR", "ENV:FOO", "env:FOO ", " env:FOO", "env:"]
)
def test_provider_setting_starting_with_env_but_malformed_is_rejected(bad):
    with pytest.raises(ValidationError, match="not a valid reference") as ei:
        _document(_provider_raw({"region": bad}))
    assert "settings.region" in str(ei.value)


def test_provider_setting_malformed_reference_is_found_in_containers():
    with pytest.raises(ValidationError, match=r"settings\.opts\[1\]"):
        _document(_provider_raw({"opts": ["env:OK", "env:no-good"]}))


def test_provider_setting_valid_reference_and_plain_text_are_accepted():
    doc = _document(_provider_raw({"region": "env:REGION", "note": "environment"}))
    assert doc.spec.settings["note"] == "environment"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("api_key", True),
        ("apiKey", True),
        ("clientSecret", True),
        ("access_token", True),
        ("password", True),
        ("pwd", False),
        ("pass", False),
        ("key", False),
        ("jwt", False),
        ("primary_key", False),
        ("region", False),
    ],
)
def test_secret_name_vectors_match_the_backend_exporter(name, expected):
    # Shared vectors for the exporter's copy of the heuristic. Names it does not
    # recognise are covered by the schema check at plan/apply.
    from codemie_iac.specs.datasource import _looks_secret

    assert _looks_secret(name) is expected
