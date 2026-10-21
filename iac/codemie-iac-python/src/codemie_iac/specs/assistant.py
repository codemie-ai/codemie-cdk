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

"""Spec that narrows ``codemie_sdk.models.assistant.AssistantCreateRequest``
(== ``AssistantRequestBase``) for IaC documents.

Drops platform-assigned fields (``id``, ``created_by``). ``tools_tokens_size_limit``
(CR-009, reopened) is kept, as a plain ``int | None``, at both the top level
of ``AssistantSpec`` and on ``MCPServerDetailsSpec`` -- an earlier pass
dropped both as "platform-computed", which traced into the codemie backend
(``rest_api/models/assistant.py``'s ``AssistantRequest``/``MCPServerDetails``,
``assistant_version_service.py``, and the ``add_tools_tokens_size_limit_to_assistants``
migration) turned out to be wrong: it is a genuine, user-settable, persisted
field on both the assistant and (independently) each MCP server -- the
assistant-level value overrides the per-MCP-server one when set
(``assistant_agent.py``/``langgraph_agent.py``: "Assistant-level tool output
token limit overrides per-tool defaults (incl. per-MCP-server) when set"),
which only makes sense if both are real, independently authorable values, not
one computed and the other not. Dropping either loses user data on
round-trip -- the same bug class as CR-007/CR-011. Narrows every field that
can carry or reference a secret:

- ``MCPServerConfig.auth_token`` (a raw secret string in the SDK model)
  narrows to ``CredentialRef``, so a plain string can never be embedded.
  ``from_entity`` has no natural ``credential_key`` for this one field (it
  is not a ``{key, value}`` pair like ``Integration.credential_values``),
  so it uses a fixed ``"auth_token"`` key scoped by *both* the owning
  assistant's name and the MCP server's own ``name`` as the identifier
  (CR-005, reopened): server name alone is not unique across assistants,
  so two unrelated MCP servers that happen to share a name would otherwise
  collide onto the identical ``CredentialRef`` -- cross-wiring their real
  secrets at resolution time.
- ``MCPServerConfig.env``/``headers``/``args``/``url`` and
  ``MCPServerDetails.arguments``/``mcp_connect_url`` (CR-008, a
  decision_needed finding resolved here, now extended to every field of
  this shape -- a secret can land in any of them, not just ``env``/
  ``headers``): these are plain strings (or a list of them, for ``args``)
  in the SDK and a realistic channel for passing an MCP server a secret
  (API key, token, a signed URL). Forcing every value through
  ``CredentialRef`` would break legitimate non-secret entries (e.g.
  ``{"DEBUG": "true"}``, or a plain ``npx`` arg), so each one is typed
  ``CredentialRef | str`` with ``union_mode="left_to_right"``: a value
  already shaped like a reference (``"env:SOME_REF"``) is parsed as a
  ``CredentialRef``; anything else stays a plain string. This reuses the
  exact same ``<source>:<identifier>`` convention ``IntegrationSpec`` and
  ``MCPServerConfigSpec.auth_token`` already use to mean "this is a
  credential reference, not a literal value". This is a best-effort,
  whole-value match only -- it narrows a value that *is* a reference, it
  does not scan free text for one, so a secret embedded inside a larger
  string (e.g. an ``args`` entry like ``"--token=sk-live-123"``, or a
  query parameter on ``url``) is not caught and is written to the file as
  plain text; the module's own README section says so explicitly.
  ``from_entity`` coerces each raw ``env``/``headers`` value to ``str``
  first (CR-004, reopened: ``env`` is typed ``dict[str, Any]`` in the SDK
  and permits a bool/int/None that would otherwise crash the union with a
  raw ``ValidationError``; ``headers`` is already ``dict[str, str]``
  upstream, so the same coercion is applied for uniformity but is always a
  no-op there) before it reaches that union.
- ``MCPServerDetails.mcp_connect_auth_token`` (a whole ``Integration``
  reference in the SDK model) narrows to a plain ``str`` holding just the
  referenced integration's name, to be resolved later by a
  ``ReferenceResolver`` against a ``Bundle``.
- ``ToolKitDetails``/``ToolDetails``/``MCPServerDetails.settings`` (each a
  whole ``Integration`` reference, CR-007) narrow the same way
  ``mcp_connect_auth_token`` does: a plain ``str`` holding the referenced
  integration's name, resolved later via ``ReferenceResolver`` -- not
  dropped, since dropping silently loses configuration AC1 requires be
  recoverable. All four of these narrowing sites raise (CR-003, reopened)
  rather than silently narrowing to ``None`` when the referenced
  ``Integration`` has no ``alias`` -- an alias-less reference's ``.alias``
  is ``None``, which would otherwise be indistinguishable from "no
  integration configured at all", silently losing a real link.
"""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codemie_sdk.models.assistant import (
    AssistantCreateRequest,
    Context,
    HedgingConfig,
    Integration,
    MCPServerConfig,
    MCPServerDetails,
    PromptVariable,
    ToolCallPolicy,
    ToolDetails,
    ToolKitDetails,
    ToolPermissionsConfig,
)

from ..credentials import CredentialRef
from .datasource import _is_env_reference, _literal_secret_paths, _looks_secret

# CR-008: see module docstring. Declared once and reused by both `env` and
# `headers` below.
_EnvOrHeaderValue = Annotated[CredentialRef | str, Field(union_mode="left_to_right")]


def _integration_reference_name(
    integration: Integration | None, *, context: str
) -> str | None:
    """Narrow an ``Integration`` reference to its alias (CR-003).

    ``None`` means "no reference configured" and passes through unchanged.
    A referenced ``Integration`` that has no alias is a different, unsafe-
    to-narrow case -- silently returning ``None`` there would be
    indistinguishable from no reference at all, losing the link entirely
    rather than just the secret.
    """
    if integration is None:
        return None
    if integration.alias is None:
        raise ValueError(
            f"{context} references an Integration with no alias; cannot "
            "narrow it to a resolvable name"
        )
    return integration.alias


def _coerce_env_value(value: object) -> str:
    """Coerce a raw MCP env/header value to ``str`` (CR-004).

    The SDK types this field ``dict[str, Any]`` -- permissive enough to
    legitimately carry a bool/int/None, which would otherwise crash the
    ``CredentialRef | str`` union with a raw pydantic ``ValidationError``
    instead of converting cleanly. Matches how a process environment
    actually consumes a value: always a string.
    """
    return "" if value is None else str(value)


def _narrow_auth_config(
    value: Any, identifier: str, key: str = "auth_config", under_secret: bool = False
) -> Any:
    """Copy ``value``, replacing each non-empty literal string under a
    secret-looking key with an ``env:`` reference built from ``identifier``
    and the key path (the secret itself never reaches the document)."""
    if isinstance(value, dict):
        return {
            k: _narrow_auth_config(
                v, identifier, f"{key}_{k}", under_secret or _looks_secret(k)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _narrow_auth_config(v, identifier, f"{key}_{i}", under_secret)
            for i, v in enumerate(value)
        ]
    if under_secret and isinstance(value, str) and value:
        if not _is_env_reference(value):
            return CredentialRef.from_entity(identifier, key).root
    return value


class ContextSpec(BaseModel):
    """Copies ``codemie_sdk.models.assistant.Context`` verbatim."""

    model_config = ConfigDict(extra="forbid")

    context_type: str
    name: str

    @classmethod
    def from_entity(cls, context: Context) -> "ContextSpec":
        return cls(context_type=context.context_type, name=context.name)


class PromptVariableSpec(BaseModel):
    """Copies ``codemie_sdk.models.assistant.PromptVariable`` verbatim."""

    model_config = ConfigDict(extra="forbid")

    key: str
    description: str | None = None
    default_value: str

    @classmethod
    def from_entity(cls, variable: PromptVariable) -> "PromptVariableSpec":
        return cls(
            key=variable.key,
            description=variable.description,
            default_value=variable.default_value,
        )


class ToolPermissionsConfigSpec(BaseModel):
    """Copies ``codemie_sdk.models.assistant.ToolPermissionsConfig`` verbatim."""

    model_config = ConfigDict(extra="forbid")

    tool_call_policy: ToolCallPolicy = ToolCallPolicy.AUTO_APPROVE
    allow_override: bool = True

    @classmethod
    def from_entity(cls, config: ToolPermissionsConfig) -> "ToolPermissionsConfigSpec":
        return cls(
            tool_call_policy=config.tool_call_policy,
            allow_override=config.allow_override,
        )


class ToolDetailsSpec(BaseModel):
    """Narrows ``codemie_sdk.models.assistant.ToolDetails``.

    ``settings`` (a whole ``Integration`` reference) narrows to a plain
    ``str`` holding that integration's name (CR-007), resolved later by a
    ``ReferenceResolver`` -- mirroring how ``mcp_connect_auth_token`` is
    narrowed below, rather than being dropped.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str | None = None
    settings_config: bool = False
    user_description: str | None = None
    settings: str | None = None
    auto_credentials_lookup: bool = True

    @classmethod
    def from_entity(cls, tool: ToolDetails) -> "ToolDetailsSpec":
        return cls(
            name=tool.name,
            label=tool.label,
            settings_config=tool.settings_config,
            user_description=tool.user_description,
            settings=_integration_reference_name(
                tool.settings, context=f"ToolDetails {tool.name!r}.settings"
            ),
            auto_credentials_lookup=tool.auto_credentials_lookup,
        )


class ToolKitDetailsSpec(BaseModel):
    """Narrows ``codemie_sdk.models.assistant.ToolKitDetails``.

    ``settings`` narrows to the referenced integration's name (CR-007), as
    on ``ToolDetailsSpec``.
    """

    model_config = ConfigDict(extra="forbid")

    toolkit: str
    tools: list[ToolDetailsSpec] = Field(default_factory=list)
    label: str = ""
    settings_config: bool = False
    is_external: bool = False
    settings: str | None = None
    auto_credentials_lookup: bool = True

    @classmethod
    def from_entity(cls, toolkit: ToolKitDetails) -> "ToolKitDetailsSpec":
        return cls(
            toolkit=toolkit.toolkit,
            tools=[ToolDetailsSpec.from_entity(tool) for tool in toolkit.tools],
            label=toolkit.label,
            settings_config=toolkit.settings_config,
            is_external=toolkit.is_external,
            settings=_integration_reference_name(
                toolkit.settings,
                context=f"ToolKitDetails {toolkit.toolkit!r}.settings",
            ),
            auto_credentials_lookup=toolkit.auto_credentials_lookup,
        )


class MCPServerConfigSpec(BaseModel):
    """Narrows ``codemie_sdk.models.assistant.MCPServerConfig``.

    ``auth_token`` narrows from a raw secret string to ``CredentialRef``.
    """

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    command: str | None = None
    url: _EnvOrHeaderValue | None = None
    args: list[_EnvOrHeaderValue] = Field(default_factory=list)
    headers: dict[str, _EnvOrHeaderValue] = Field(default_factory=dict)
    env: dict[str, _EnvOrHeaderValue] = Field(default_factory=dict)
    type: str | None = None
    auth_token: CredentialRef | None = None
    single_usage: bool = False
    tools: list[str] | None = None
    audience: str | None = None
    auth_config: dict[str, Any] | None = None

    @field_validator("auth_config")
    @classmethod
    def _no_literal_secrets_in_auth_config(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        paths = list(_literal_secret_paths(value or {}, "auth_config"))
        if paths:
            raise ValueError(
                f"secret-looking setting(s) {', '.join(paths)} must be env: "
                "references, not literal values"
            )
        return value

    @classmethod
    def from_entity(
        cls, config: MCPServerConfig, *, assistant_name: str, server_name: str
    ) -> "MCPServerConfigSpec":
        """``assistant_name`` + ``server_name`` together identify the owning
        MCP server for the ``CredentialRef`` built for ``auth_token`` -- the
        one field here with no natural ``{key, value}`` pair of its own (see
        module docstring). Server name alone is not unique across assistants
        (CR-005): two different MCP servers that happen to share a name
        would otherwise collide onto the same CredentialRef.
        """
        return cls(
            command=config.command,
            url=config.url,
            args=config.args or [],
            headers={
                k: _coerce_env_value(v) for k, v in (config.headers or {}).items()
            },
            env={k: _coerce_env_value(v) for k, v in (config.env or {}).items()},
            type=config.type,
            auth_token=(
                CredentialRef.from_entity(
                    f"{assistant_name}_{server_name}", "auth_token"
                )
                if config.auth_token is not None
                else None
            ),
            single_usage=config.single_usage,
            tools=config.tools,
            audience=config.audience,
            auth_config=_narrow_auth_config(
                config.auth_config, f"{assistant_name}_{server_name}"
            ),
        )


class MCPServerDetailsSpec(BaseModel):
    """Narrows ``codemie_sdk.models.assistant.MCPServerDetails``.

    ``tools_tokens_size_limit`` (CR-009, reopened) is kept as a plain
    ``int | None`` -- a genuine, independently user-settable per-MCP-server
    default token limit (see module docstring), not platform-computed.
    Narrows ``settings`` (CR-007) and ``mcp_connect_auth_token`` -- both
    whole ``Integration`` references in the SDK model -- to the referenced
    integration's name (resolved later by a ``ReferenceResolver``).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    enabled: bool
    mcp_config_id: str | None = None
    use_custom_config: bool = False
    config: MCPServerConfigSpec | None = None
    mcp_connect_url: _EnvOrHeaderValue | None = None
    tools_tokens_size_limit: int | None = None
    command: str | None = None
    arguments: _EnvOrHeaderValue | None = None
    settings: str | None = None
    integration_alias: str | None = None
    mcp_connect_auth_token: str | None = None
    resolve_dynamic_values_in_arguments: bool = False
    tools: list[str] | None = None

    @classmethod
    def from_entity(
        cls, server: MCPServerDetails, *, assistant_name: str
    ) -> "MCPServerDetailsSpec":
        """``assistant_name`` is the owning assistant's name, threaded down
        to ``MCPServerConfigSpec.from_entity`` to scope the ``auth_token``
        ``CredentialRef`` identifier (CR-005).
        """
        return cls(
            name=server.name,
            description=server.description,
            enabled=server.enabled,
            mcp_config_id=server.mcp_config_id,
            use_custom_config=server.use_custom_config,
            config=(
                MCPServerConfigSpec.from_entity(
                    server.config,
                    assistant_name=assistant_name,
                    server_name=server.name,
                )
                if server.config is not None
                else None
            ),
            mcp_connect_url=server.mcp_connect_url,
            tools_tokens_size_limit=server.tools_tokens_size_limit,
            command=server.command,
            arguments=server.arguments,
            settings=_integration_reference_name(
                server.settings, context=f"MCPServerDetails {server.name!r}.settings"
            ),
            integration_alias=server.integration_alias,
            mcp_connect_auth_token=_integration_reference_name(
                server.mcp_connect_auth_token,
                context=f"MCPServerDetails {server.name!r}.mcp_connect_auth_token",
            ),
            resolve_dynamic_values_in_arguments=server.resolve_dynamic_values_in_arguments,
            tools=server.tools,
        )


class AssistantSpec(BaseModel):
    """Narrows ``codemie_sdk.models.assistant.AssistantCreateRequest``.

    Drops platform-assigned ``id``/``created_by`` from ``AssistantBase``.
    ``tools_tokens_size_limit`` (CR-009, reopened) is kept as a plain
    ``int | None`` -- confirmed against the codemie backend to be a
    genuine, user-settable, persisted field (see module docstring), not
    platform-computed; dropping it silently loses an assistant's configured
    tool-output token limit on round-trip.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    icon_url: str | None = None
    system_prompt: str
    project: str
    context: list[ContextSpec] = Field(default_factory=list)
    llm_model_type: str
    toolkits: list[ToolKitDetailsSpec] = Field(default_factory=list)
    conversation_starters: list[str] = Field(default_factory=list)
    shared: bool = False
    is_react: bool = False
    is_global: bool | None = False
    categories: list[str] = Field(default_factory=list)
    slug: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    tools_tokens_size_limit: int | None = None
    mcp_servers: list[MCPServerDetailsSpec] = Field(default_factory=list)
    assistant_ids: list[str] = Field(default_factory=list)
    enabled_builtin_subagents: list[str] | None = None
    prompt_variables: list[PromptVariableSpec] = Field(default_factory=list)
    skip_integration_validation: bool | None = False
    tool_permissions: ToolPermissionsConfigSpec | None = None
    hedging_config: HedgingConfig | None = None
    interactive_enabled: bool = False
    enable_image_generation: bool | None = False
    file_attachment_enabled: bool | None = None

    @classmethod
    def from_entity(cls, request: AssistantCreateRequest) -> "AssistantSpec":
        return cls(
            name=request.name,
            description=request.description,
            icon_url=request.icon_url,
            system_prompt=request.system_prompt,
            project=request.project,
            context=[ContextSpec.from_entity(c) for c in request.context],
            llm_model_type=request.llm_model_type,
            toolkits=[ToolKitDetailsSpec.from_entity(t) for t in request.toolkits],
            conversation_starters=request.conversation_starters,
            shared=request.shared,
            is_react=request.is_react,
            is_global=request.is_global,
            categories=request.categories,
            slug=request.slug,
            temperature=request.temperature,
            top_p=request.top_p,
            tools_tokens_size_limit=request.tools_tokens_size_limit,
            mcp_servers=[
                MCPServerDetailsSpec.from_entity(s, assistant_name=request.name)
                for s in request.mcp_servers
            ],
            assistant_ids=request.assistant_ids,
            enabled_builtin_subagents=request.enabled_builtin_subagents,
            prompt_variables=[
                PromptVariableSpec.from_entity(p) for p in request.prompt_variables
            ],
            skip_integration_validation=request.skip_integration_validation,
            hedging_config=request.hedging_config,
            # The SDK request reads a stored null as None; the platform treats it as off.
            interactive_enabled=bool(request.interactive_enabled),
            enable_image_generation=request.enable_image_generation,
            file_attachment_enabled=request.file_attachment_enabled,
            tool_permissions=(
                ToolPermissionsConfigSpec.from_entity(request.tool_permissions)
                if request.tool_permissions is not None
                else None
            ),
        )
