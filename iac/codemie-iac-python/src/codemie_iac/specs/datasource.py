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

"""Spec that narrows the ``codemie_sdk.models.datasource`` request classes
(subclasses of ``BaseDataSourceRequest``, plus the provider request) for IaC
documents.

Datasources authenticate via a referenced integration (``setting_id``, a
plain string naming/identifying an integration) rather than an inline
secret. Two places carry secrets and narrow them to ``env:`` references: the
SharePoint ``access_token`` (a ``CredentialRef``; the OAuth token is transient
and the platform never returns it) and the free-form
``ProviderDatasourceSpec.settings`` map. For ``settings``, the values the
platform provider schema marks secret must be ``env:`` references, enforced
authoritatively by credential scanning (``plan_apply.credentials.SECRET_FIELDS``)
at plan/apply; here only a best-effort name heuristic rejects literals under
secret-looking setting names.
``DatasourceSpec`` is a ``type``-discriminated union over the thirteen
per-kind ``*DatasourceSpec`` classes below.
"""

import re
from collections.abc import Iterator
from itertools import pairwise
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from codemie_sdk.models.datasource import (
    AzureDevOpsWikiDataSourceRequest,
    AzureDevOpsWorkItemDataSourceRequest,
    BaseDataSourceRequest,
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

from ..credentials import CredentialRef


def _base_kwargs(request: BaseDataSourceRequest) -> dict:
    """Fields every ``*DatasourceSpec`` shares with its ``*DataSourceRequest``."""
    return {
        "name": request.name,
        "project_name": request.project_name,
        "description": request.description,
        "shared_with_project": request.shared_with_project,
        "setting_id": request.setting_id,
        "cron_expression": request.cron_expression,
        "timezone": request.timezone,
    }


class _DatasourceSpecBase(BaseModel):
    """Shared fields from ``BaseDataSourceRequest``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    project_name: str
    description: str
    shared_with_project: bool = False
    setting_id: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None


class CodeDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``CodeDataSourceRequest`` (type=``code``)."""

    type: Literal["code"] = "code"
    link: str | None = None
    branch: str | None = None
    index_type: str | None = None
    files_filter: str | None = ""
    embeddings_model: str | None = None
    summarization_model: str | None = None
    prompt: str | None = None
    docs_generation: bool = False

    @classmethod
    def from_entity(cls, request: CodeDataSourceRequest) -> "CodeDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            link=request.link,
            branch=request.branch,
            index_type=request.index_type,
            files_filter=request.files_filter,
            embeddings_model=request.embeddings_model,
            summarization_model=request.summarization_model,
            prompt=request.prompt,
            docs_generation=request.docs_generation,
        )


class GitFaqDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``GitFaqDataSourceRequest`` (type=``knowledge_base_git_faq``)."""

    type: Literal["knowledge_base_git_faq"] = "knowledge_base_git_faq"
    link: str | None = None
    branch: str | None = None
    files_filter: str | None = None
    embedding_model: str | None = None

    @classmethod
    def from_entity(cls, request: GitFaqDataSourceRequest) -> "GitFaqDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            link=request.link,
            branch=request.branch,
            files_filter=request.files_filter,
            embedding_model=request.embedding_model,
        )


class JiraDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``JiraDataSourceRequest`` (type=``knowledge_base_jira``)."""

    type: Literal["knowledge_base_jira"] = "knowledge_base_jira"
    jql: str | None = None
    custom_fields: list[str] | None = None

    @classmethod
    def from_entity(cls, request: JiraDataSourceRequest) -> "JiraDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            jql=request.jql,
            custom_fields=request.custom_fields,
        )


class ConfluenceDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``ConfluenceDataSourceRequest`` (type=``knowledge_base_confluence``)."""

    type: Literal["knowledge_base_confluence"] = "knowledge_base_confluence"
    cql: str | None = None
    include_restricted_content: bool | None = None
    include_archived_content: bool | None = None
    include_attachments: bool | None = None
    include_comments: bool | None = None
    keep_markdown_format: bool | None = None
    keep_newlines: bool | None = None
    max_pages: int | None = None
    pages_per_request: int | None = None

    @classmethod
    def from_entity(
        cls, request: ConfluenceDataSourceRequest
    ) -> "ConfluenceDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            cql=request.cql,
            include_restricted_content=request.include_restricted_content,
            include_archived_content=request.include_archived_content,
            include_attachments=request.include_attachments,
            include_comments=request.include_comments,
            keep_markdown_format=request.keep_markdown_format,
            keep_newlines=request.keep_newlines,
            max_pages=request.max_pages,
            pages_per_request=request.pages_per_request,
        )


class GoogleDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``GoogleDataSourceRequest`` (type=``llm_routing_google``)."""

    type: Literal["llm_routing_google"] = "llm_routing_google"
    google_doc: str | None = None

    @classmethod
    def from_entity(cls, request: GoogleDataSourceRequest) -> "GoogleDatasourceSpec":
        return cls(**_base_kwargs(request), google_doc=request.google_doc)


class FileDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``FileDataSourceRequest`` (type=``knowledge_base_file``).

    No extra fields beyond the base.
    """

    type: Literal["knowledge_base_file"] = "knowledge_base_file"

    @classmethod
    def from_entity(cls, request: FileDataSourceRequest) -> "FileDatasourceSpec":
        return cls(**_base_kwargs(request))


class AzureDevOpsWikiDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``AzureDevOpsWikiDataSourceRequest`` (type=``knowledge_base_azure_devops_wiki``)."""

    type: Literal["knowledge_base_azure_devops_wiki"] = (
        "knowledge_base_azure_devops_wiki"
    )
    wiki_query: str | None = None
    organization: str | None = None
    project: str | None = None
    wiki_name: str | None = None

    @classmethod
    def from_entity(
        cls, request: AzureDevOpsWikiDataSourceRequest
    ) -> "AzureDevOpsWikiDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            wiki_query=request.wiki_query,
            organization=request.organization,
            project=request.project,
            wiki_name=request.wiki_name,
        )


class AzureDevOpsWorkItemDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``AzureDevOpsWorkItemDataSourceRequest`` (type=``knowledge_base_azure_devops_work_item``)."""

    type: Literal["knowledge_base_azure_devops_work_item"] = (
        "knowledge_base_azure_devops_work_item"
    )
    wiql_query: str | None = None
    organization: str | None = None
    project: str | None = None

    @classmethod
    def from_entity(
        cls, request: AzureDevOpsWorkItemDataSourceRequest
    ) -> "AzureDevOpsWorkItemDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            wiql_query=request.wiql_query,
            organization=request.organization,
            project=request.project,
        )


class XWikiDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``XWikiDataSourceRequest`` (type=``knowledge_base_xwiki``)."""

    type: Literal["knowledge_base_xwiki"] = "knowledge_base_xwiki"
    space: str | None = None
    wiki: str | None = None

    @classmethod
    def from_entity(cls, request: XWikiDataSourceRequest) -> "XWikiDatasourceSpec":
        return cls(**_base_kwargs(request), space=request.space, wiki=request.wiki)


class SvnDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``SvnDataSourceRequest`` (type=``svn``)."""

    type: Literal["svn"] = "svn"
    link: str = Field(..., min_length=1, max_length=1000)
    branch: str | None = Field(None, min_length=1, max_length=1000)
    index_type: Literal["code", "summary", "chunk-summary"] = "code"
    files_filter: str | None = None
    embeddings_model: str | None = None
    prompt: str | None = None
    docs_generation: bool | None = None

    @classmethod
    def from_entity(cls, request: SvnDataSourceRequest) -> "SvnDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            link=request.link,
            branch=request.branch,
            index_type=request.index_type.value,
            files_filter=request.files_filter,
            embeddings_model=request.embeddings_model,
            prompt=request.prompt,
            docs_generation=request.docs_generation,
        )


class SharepointDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``SharePointDataSourceRequest`` (type=``knowledge_base_sharepoint``).

    ``access_token`` (needed by the ``oauth_*`` auth types, never stored by the
    platform) narrows to a ``CredentialRef``: it is read from the environment
    when writing and is not part of the live state. It is optional in the
    document: an exported OAuth document carries none, and the SDK requires it
    only on create and on an update that reindexes.
    """

    type: Literal["knowledge_base_sharepoint"] = "knowledge_base_sharepoint"
    site_url: str = Field(..., pattern=r"^https://\S+$", max_length=1000)
    include_pages: bool | None = None
    include_documents: bool | None = None
    include_lists: bool | None = None
    max_file_size_mb: int | None = Field(None, ge=1, le=500)
    files_filter: str | None = None
    auth_type: Literal["integration", "oauth_codemie", "oauth_custom"] | None = None
    oauth_client_id: str | None = None
    oauth_tenant_id: str | None = None
    access_token: CredentialRef | None = None
    embedding_model: str | None = None

    @field_validator("access_token", mode="before")
    @classmethod
    def _token_is_a_reference(cls, value: Any) -> Any:
        # Checked here, not by ``CredentialRef``, whose error text echoes the value.
        if isinstance(value, str) and not _is_env_reference(value):
            raise ValueError("access_token must be an env: reference, not a literal")
        return value

    @classmethod
    def from_entity(
        cls, request: SharePointDataSourceRequest
    ) -> "SharepointDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            site_url=request.site_url,
            include_pages=request.include_pages,
            include_documents=request.include_documents,
            include_lists=request.include_lists,
            max_file_size_mb=request.max_file_size_mb,
            files_filter=request.files_filter,
            auth_type=request.auth_type,
            oauth_client_id=request.oauth_client_id,
            oauth_tenant_id=request.oauth_tenant_id,
            access_token=(
                CredentialRef.from_entity(request.name, "access_token")
                if request.access_token
                else None
            ),
            embedding_model=request.embedding_model,
        )


class XrayDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``XrayDataSourceRequest`` (type=``knowledge_base_xray``)."""

    type: Literal["knowledge_base_xray"] = "knowledge_base_xray"
    jql: str = Field(..., min_length=1)
    embedding_model: str | None = None

    @classmethod
    def from_entity(cls, request: XrayDataSourceRequest) -> "XrayDatasourceSpec":
        return cls(
            **_base_kwargs(request),
            jql=request.jql,
            embedding_model=request.embedding_model,
        )


#: Document-level fields that must not be smuggled in through ``settings``.
RESERVED_PROVIDER_SETTINGS = frozenset(
    {"name", "project_name", "setting_id", "description", "project_space_visible"}
)

# Name heuristic for secret-looking provider settings. Mirrors the backend
# exporter's ``iac_export/exporters/datasource/provider.py`` (RESERVED_PROVIDER_SETTINGS,
# _SECRET_TOKENS, _looks_secret): change both together; ``tests/test_specs_datasource.py``
# pins the shared vectors. Names are matched whole-token on purpose, so short
# words such as ``key`` or ``pass`` (``primary_key``, ``bypass``) are not flagged.
# Best effort and offline
# only: the platform provider schema, consulted at plan/apply before any write
# (``plan_apply.credentials``), is the authoritative gate and also catches
# secrets stored under names this list does not recognise.
_SECRET_TOKENS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "apikey",
        "credential",
        "credentials",
        "passphrase",
    }
)
_SECRET_TOKEN_PAIRS = frozenset(
    {
        ("api", "key"),
        ("private", "key"),
        ("access", "key"),
        ("secret", "key"),
        ("auth", "key"),
        ("client", "secret"),
    }
)


def _key_tokens(key: str) -> list[str]:
    """Lower-case tokens of ``key``, split on non-alphanumerics and camelCase."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", spaced) if t]


def _looks_secret(key: Any) -> bool:
    """Whether the setting name looks like a secret (whole-token match)."""
    tokens = _key_tokens(str(key))
    return any(t in _SECRET_TOKENS for t in tokens) or any(
        pair in _SECRET_TOKEN_PAIRS for pair in pairwise(tokens)
    )


def _is_env_reference(value: str) -> bool:
    try:
        CredentialRef(value)
    except ValueError:
        return False
    return True


def _malformed_reference_paths(value: Any, path: str) -> Iterator[str]:
    """Paths of string leaves that start with ``env:`` (any case, leading
    blanks allowed) yet are not a valid reference."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _malformed_reference_paths(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _malformed_reference_paths(item, f"{path}[{index}]")
    elif (
        isinstance(value, str)
        and value.lstrip().lower().startswith("env:")
        and not _is_env_reference(value)
    ):
        yield path


def _literal_secret_paths(
    value: Any, path: str, under_secret: bool = False
) -> Iterator[str]:
    """Paths of non-empty, non-reference string leaves under a secret-named key."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _literal_secret_paths(
                item, f"{path}.{key}", under_secret or _looks_secret(key)
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _literal_secret_paths(item, f"{path}[{index}]", under_secret)
    elif (
        under_secret
        and isinstance(value, str)
        and value
        and not _is_env_reference(value)
    ):
        yield path


class ProviderDatasourceSpec(_DatasourceSpecBase):
    """Narrows ``ProviderDataSourceRequest`` (type=``provider``).

    ``settings`` is free-form; which entries are secret is decided by the
    platform provider schema (see ``plan_apply.credentials``).
    """

    type: Literal["provider"] = "provider"
    provider_name: str
    toolkit_id: str
    settings: dict[str, Any] = {}

    # Keeps pydantic from echoing ``settings`` (and any literal secret in it)
    # in validation error text.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    @field_validator("settings")
    @classmethod
    def _no_reserved_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        clash = sorted(set(value) & RESERVED_PROVIDER_SETTINGS)
        if clash:
            raise ValueError(
                f"settings must not contain reserved document keys: {', '.join(clash)}"
            )
        return value

    @model_validator(mode="after")
    def _no_setting_id(self) -> "ProviderDatasourceSpec":
        if self.setting_id is not None:
            raise ValueError(
                f"datasource {self.name!r}: setting_id is not supported for "
                "provider datasources; the platform does not store it"
            )
        return self

    @model_validator(mode="after")
    def _no_schedule(self) -> "ProviderDatasourceSpec":
        if self.cron_expression is not None or self.timezone is not None:
            raise ValueError(
                f"datasource {self.name!r}: cron_expression and timezone are not "
                "supported for provider datasources; the platform takes no schedule"
            )
        return self

    @model_validator(mode="after")
    def _no_malformed_references(self) -> "ProviderDatasourceSpec":
        paths = list(_malformed_reference_paths(self.settings, "settings"))
        if paths:
            raise ValueError(
                f"datasource {self.name!r}: {', '.join(paths)} starts with 'env:' "
                "but is not a valid reference (env:NAME, letters, digits and "
                "underscores only); the platform would receive it as literal text"
            )
        return self

    @model_validator(mode="after")
    def _no_literal_secret_settings(self) -> "ProviderDatasourceSpec":
        paths = list(_literal_secret_paths(self.settings, "settings"))
        if paths:
            raise ValueError(
                f"datasource {self.name!r}: secret-looking setting(s) "
                f"{', '.join(paths)} must be env: references, not literal values"
            )
        return self

    @classmethod
    def from_entity(
        cls,
        request: ProviderDataSourceRequest,
    ) -> "ProviderDatasourceSpec":
        return cls(
            name=request.name,
            project_name=request.project_name,
            description=request.description,
            shared_with_project=request.project_space_visible,
            provider_name=request.provider_name,
            toolkit_id=request.toolkit_id,
            settings=dict(request.settings),
        )


DatasourceSpec = Annotated[
    Union[
        CodeDatasourceSpec,
        GitFaqDatasourceSpec,
        JiraDatasourceSpec,
        ConfluenceDatasourceSpec,
        GoogleDatasourceSpec,
        FileDatasourceSpec,
        AzureDevOpsWikiDatasourceSpec,
        AzureDevOpsWorkItemDatasourceSpec,
        XWikiDatasourceSpec,
        SvnDatasourceSpec,
        SharepointDatasourceSpec,
        XrayDatasourceSpec,
        ProviderDatasourceSpec,
    ],
    Field(discriminator="type"),
]
