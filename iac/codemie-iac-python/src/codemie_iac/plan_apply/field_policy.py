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

"""Hand-written, explicit field policies for the single-entity diff.

For every kind (and every datasource ``type``) each field of the live SDK
response is classified exactly once:

- ``deny``: server-managed or otherwise not authored by the IaC document
  (ids, audit stamps, counters, indexing state, ciphertext...). Ignored by
  the diff.
- ``comparable``: a candidate for comparison against the document spec.

The lists are written by hand on purpose, not derived from the SDK write
models: a new server-managed response field must be classified explicitly
rather than silently become a perpetual "difference".

Names refer to the *flattened* live view built by ``single_apply`` (datasource
sub-objects such as ``jira``/``code`` are merged into the top level, and
``google_doc_link`` is also exposed as ``google_doc``). The sub-object keys
themselves are therefore in ``deny``.
"""

from pydantic import BaseModel, ConfigDict

from ..envelope import Document, DocumentKind

__all__ = ["FIELD_POLICIES", "FieldPolicy", "policy_for"]


class FieldPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deny: frozenset[str]
    comparable: frozenset[str]


def _policy(deny: str, comparable: str) -> FieldPolicy:
    return FieldPolicy(
        deny=frozenset(deny.split()), comparable=frozenset(comparable.split())
    )


_ASSISTANT = _policy(
    # Assistant response: ids, audit stamps, usage statistics, derived values.
    deny="id created_by system_prompt_history created_date updated_date creator "
    "user_abilities display_name version_count unique_users_count "
    "unique_likes_count unique_dislikes_count clone_count",
    comparable="name description icon_url system_prompt project llm_model_type "
    "toolkits conversation_starters shared is_react is_global slug temperature "
    "top_p tools_tokens_size_limit context mcp_servers assistant_ids "
    "skill_ids enabled_builtin_subagents prompt_variables categories tool_permissions "
    "hedging_config interactive_enabled enable_image_generation "
    "file_attachment_enabled",
)

_SKILL = _policy(
    # slug/icon_url/mcp_servers/display_name are not authored by SkillSpec;
    # bundle_warning is a server note about the skill bundle.
    deny="id display_name created_date created_by updated_date is_attached "
    "reactions_count assistants_count mcp_servers slug icon_url bundle_warning",
    comparable="name description project visibility categories "
    "enabled_builtin_subagents content",
)

_WORKFLOW = _policy(
    deny="id created_date update_date created_by display_name required_variables",
    comparable="project name description yaml_config mode shared icon_url start_hint",
)

_CATEGORY = _policy(
    deny="id marketplace_count project_count",
    comparable="name description",
)

_INTEGRATION = _policy(
    deny="id date update_date user_id",
    comparable="project_name alias default is_global credential_type "
    "credential_values setting_type",
)

# Server-managed datasource state shared by every type. ``error``,
# ``updated_by`` and ``ciphertext`` are raw backend keys the SDK model ignores
# but which may still reach a dict-based live view.
_DS_DENY = (
    "id status created_date created_by update_date updated_date "
    "last_reindex_date error_message user_abilities processing_info "
    "processed_documents tokens_usage completed complete_state current_state "
    "ciphertext code git_faq jira confluence azure_devops_wiki "
    "azure_devops_work_item xwiki svn sharepoint xray provider"
)
# ``timezone`` is only exposed alongside a ``cron_expression`` (see
# ``_datasource_view``): without a schedule the backend reports a default.
_DS_COMMON = (
    "project_name name description type embeddings_model setting_id "
    "shared_with_project cron_expression timezone"
)


def _datasource(
    comparable: str = "", extra_deny: str = "", not_comparable: str = ""
) -> FieldPolicy:
    """``not_comparable`` names common fields the type's update cannot carry:
    they leave the comparable set and join the deny list."""
    dropped = set(not_comparable.split())
    deny = f"{_DS_DENY} {extra_deny} {not_comparable}".split()
    # Only Google datasources author a document link (and its ``google_doc``
    # alias, which the flattened live view derives from ``google_doc_link``).
    if "google_doc_link" not in comparable.split():
        deny.extend(("google_doc_link", "google_doc"))
    return _policy(
        deny=" ".join(deny),
        comparable=" ".join(
            [t for t in _DS_COMMON.split() if t not in dropped] + comparable.split()
        ),
    )


_CONFLUENCE = (
    "cql include_restricted_content include_archived_content include_attachments "
    "include_comments keep_markdown_format keep_newlines max_pages pages_per_request"
)

FIELD_POLICIES: dict[str, FieldPolicy] = {
    DocumentKind.ASSISTANT.value: _ASSISTANT,
    DocumentKind.SKILL.value: _SKILL,
    DocumentKind.WORKFLOW.value: _WORKFLOW,
    DocumentKind.CATEGORY.value: _CATEGORY,
    DocumentKind.INTEGRATION.value: _INTEGRATION,
    # Datasource types, keyed by spec ``type``.
    "code": _datasource(
        "link branch index_type files_filter summarization_model prompt docs_generation"
    ),
    "knowledge_base_git_faq": _datasource(
        "link branch files_filter embedding_model", extra_deny="error"
    ),
    "knowledge_base_jira": _datasource("jql custom_fields"),
    "knowledge_base_confluence": _datasource(_CONFLUENCE),
    "llm_routing_google": _datasource("google_doc google_doc_link", extra_deny="error"),
    "knowledge_base_azure_devops_wiki": _datasource(
        "wiki_query organization project wiki_name"
    ),
    "knowledge_base_azure_devops_work_item": _datasource(
        "wiql_query organization project"
    ),
    "knowledge_base_xwiki": _datasource("space wiki"),
    # The SVN update request cannot change the index type: create-only.
    "svn": _datasource(
        "link branch files_filter prompt docs_generation", extra_deny="index_type"
    ),
    "knowledge_base_sharepoint": _datasource(
        "site_url include_pages include_documents include_lists max_file_size_mb "
        "files_filter embedding_model auth_type oauth_client_id oauth_tenant_id",
        # The OAuth access token is transient: the platform never returns it.
        extra_deny="access_token",
    ),
    # The Xray update route does not store an embedding model: create-only.
    "knowledge_base_xray": _datasource(
        "jql", extra_deny="embedding_model", not_comparable="embeddings_model"
    ),
    # ``settings`` is derived from the live provider base/create params (see
    # ``single_apply._flatten_live``); the raw params and provider id are
    # server-shaped and denied.
    "provider": _datasource(
        "settings",
        extra_deny="toolkit_id provider_name provider_id base_params create_params",
        # The provider request takes no schedule.
        not_comparable="cron_expression timezone",
    ),
    "knowledge_base_file": _datasource(extra_deny="error updated_by"),
}


def policy_for(document: Document) -> FieldPolicy:
    """The policy for a document: by datasource ``type``, else by kind."""
    kind = document.meta.kind
    key = document.spec.type if kind is DocumentKind.DATASOURCE else kind.value
    return FIELD_POLICIES[key]
