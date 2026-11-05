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

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from codemie_sdk.builders.workflow.definition import WorkflowDefinition
from codemie_sdk.models.assistant import MCPServerConfig

from ..credentials import CredentialRef
from .assistant import MCPServerConfigSpec
from .datasource import _literal_secret_paths
from .integration import CredentialRefEntry


class WorkflowSpec(BaseModel):
    """Wraps a workflow's typed definition for IaC documents.

    Embeds ``WorkflowDefinition`` directly rather than pointing at a sibling
    file holding the backend's flattened ``yaml_config`` text (CR-011/CR-012,
    superseded) -- a workflow document is one file, like every other kind.
    ``name``/``description``/``shared``/``icon_url`` all live on ``workflow``
    itself, so nothing is duplicated onto a sibling field that could drift
    out of sync with it, and nothing (icon_url included) has a separate path
    to be dropped from on round-trip.

    This package never re-derives the inner shape: ``WorkflowDefinition`` is
    the SDK's own typed model, unchanged. Deriving the backend's
    flattened ``yaml_config`` string (``workflow.to_yaml_config()``) is left
    to whichever future ``apply`` story actually talks to the platform --
    nothing here pre-renders or stores that string.

    ``credential_values`` (CR-007, reopened) narrows every credential-bearing
    field an inline MCP server's ``config`` can carry -- not just
    ``auth_token`` -- by reusing ``MCPServerConfigSpec.from_entity`` wholesale.
    This only became possible once ``WorkflowMCPServer.config`` was retyped
    from a bare ``dict`` to ``MCPServerConfig`` (the same type
    ``MCPServerDetails.config`` already has on the backend and on
    ``AssistantCreateRequest.mcp_servers[].config``) -- an earlier pass
    left it untyped even though the model it needed already
    lived in this same SDK package. With a real schema to narrow against,
    there is no longer a residual gap: every field ``MCPServerConfigSpec``
    recognizes elsewhere (``auth_token``, and any ``env``/``headers`` value
    already shaped like a reference) is narrowed here too, the identical way.

    That narrowing only runs inside ``from_entity``, though: ``workflow``'s
    field type is ``WorkflowDefinition`` itself (unmodified, per the module
    docstring above), so a ``WorkflowSpec`` built directly from model
    instances, or loaded via ``from_yaml``/``validate_document``, has no
    type-level guard on ``auth_token`` the way ``AssistantSpec``'s embedded
    ``MCPServerConfigSpec.auth_token: CredentialRef | None`` does. The
    ``_check_auth_tokens_are_reference_shaped`` validator below re-checks
    that one invariant at the value level on every construction path, not
    just ``from_entity``'s. ``env``/``headers``/``args``/``url``/
    ``arguments``/``mcp_connect_url`` are deliberately not re-checked here:
    per ``MCPServerConfigSpec``'s own docstring, those are a best-effort,
    whole-value match, never enforced -- the same tolerance applies here for
    the same reason, not a separate, inconsistent guarantee for this kind.
    """

    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowDefinition
    credential_values: list[CredentialRefEntry] = Field(default_factory=list)
    start_hint: str | None = None

    @model_validator(mode="after")
    def _check_auth_tokens_are_reference_shaped(self) -> "WorkflowSpec":
        for assistant in self.workflow.assistants.values():
            for server in assistant.mcp_servers:
                self._check_auth_config(assistant, server)
                token = server.config.auth_token if server.config else None
                if token is None:
                    continue
                try:
                    CredentialRef.model_validate(token)
                except ValidationError as exc:
                    raise ValueError(
                        f"assistant {assistant.id!r} MCP server "
                        f"{server.name!r} has a literal auth_token; use a "
                        "CredentialRef-shaped reference (e.g. 'env:NAME') "
                        "instead of embedding the secret"
                    ) from exc
        return self

    @staticmethod
    def _check_auth_config(assistant: Any, server: Any) -> None:
        auth_config = server.config.auth_config if server.config else None
        paths = list(_literal_secret_paths(auth_config or {}, "auth_config"))
        if paths:
            raise ValueError(
                f"assistant {assistant.id!r} MCP server {server.name!r}: "
                f"secret-looking setting(s) {', '.join(paths)} must be env: "
                "references, not literal values"
            )

    @classmethod
    def from_entity(cls, workflow: WorkflowDefinition) -> "WorkflowSpec":
        """Rebuilds each touched layer via ``model_copy(update=...)`` rather
        than mutating ``server``/``assistant``/``workflow`` in place.

        ``WorkflowMCPServer``, ``WorkflowAssistant`` and ``WorkflowDefinition``
        are frozen -- assigning to an existing instance's
        field (e.g. ``server.config = ...``) raises. ``model_copy`` builds a
        new instance with just the one field swapped and everything else
        (``server.name``/``.enabled``/``.command``, the assistant's other
        fields, the definition's other assistants/states) carried over
        unchanged, without re-running validators a second time.
        """
        credential_values: list[CredentialRefEntry] = []
        new_assistants: dict = {}
        for assistant_key, assistant in workflow.assistants.items():
            new_servers = []
            for server in assistant.mcp_servers:
                if server.config is None:
                    new_servers.append(server)
                    continue
                narrowed_config = MCPServerConfigSpec.from_entity(
                    server.config,
                    assistant_name=f"{workflow.name}_{assistant_key}",
                    server_name=server.name,
                )
                if narrowed_config.auth_token is not None:
                    identifier = f"{workflow.name}_{assistant_key}_{server.name}"
                    credential_values.append(
                        CredentialRefEntry(
                            key=identifier, ref=narrowed_config.auth_token
                        )
                    )
                new_config = MCPServerConfig.model_validate(
                    narrowed_config.model_dump(mode="json")
                )
                new_servers.append(server.model_copy(update={"config": new_config}))
            new_assistants[assistant_key] = assistant.model_copy(
                update={"mcp_servers": new_servers}
            )
        narrowed = workflow.model_copy(update={"assistants": new_assistants})
        return cls(workflow=narrowed, credential_values=credential_values)
