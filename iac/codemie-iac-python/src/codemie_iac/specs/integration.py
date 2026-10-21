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

"""Spec that narrows ``codemie_sdk.models.integration.Integration`` for IaC documents.

Drops the platform-assigned fields (``id``, ``date``, ``update_date``,
``user_id``) and replaces ``credential_values`` with a list of
``CredentialRefEntry`` so no secret value can ever be embedded in a document.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from codemie_sdk.models.integration import CredentialTypes, Integration, IntegrationType

from ..credentials import CredentialRef


class CredentialRefEntry(BaseModel):
    """A single credential field, pointing at a secret by reference only."""

    model_config = ConfigDict(extra="forbid")

    key: str
    ref: CredentialRef


class IntegrationSpec(BaseModel):
    """Narrowed, secret-free view of ``Integration``."""

    model_config = ConfigDict(extra="forbid")

    project_name: str | None = None
    alias: str | None = None
    default: bool = False
    is_global: bool | None = False
    credential_type: CredentialTypes
    credential_values: list[CredentialRefEntry]
    setting_type: IntegrationType = Field(default=IntegrationType.USER)

    @model_validator(mode="after")
    def _check_unique_credential_keys(self) -> "IntegrationSpec":
        """Reject duplicate ``key`` values across ``credential_values`` (CR-010).

        Without this, two entries with the same ``key`` but different
        ``ref``s are accepted silently, leaving which ``CredentialRefEntry``
        a downstream consumer resolves for that key ambiguous.
        """
        keys = [entry.key for entry in self.credential_values]
        seen: set[str] = set()
        duplicates = {key for key in keys if key in seen or seen.add(key)}
        if duplicates:
            raise ValueError(
                f"credential_values has duplicate key(s): {sorted(duplicates)!r}"
            )
        return self

    @classmethod
    def from_entity(cls, integration: Integration) -> "IntegrationSpec":
        """Narrow a live ``Integration``, never reading any credential value.

        Uses ``integration.alias`` as the identifier fed to
        ``CredentialRef.from_entity`` for every credential key. An
        alias-less integration with credentials to narrow is rejected
        (CR-006) rather than falling back to a shared literal: two
        different alias-less integrations would otherwise collide onto the
        identical ``CredentialRef``, silently pointing two real secrets at
        the same environment variable. An alias-less integration with no
        credentials to narrow has no identifier to collide over, so it is
        left alone.
        """
        if integration.alias is None and integration.credential_values:
            raise ValueError(
                "IntegrationSpec.from_entity requires an alias to derive "
                "CredentialRefs for a non-empty credential_values; got "
                "alias=None"
            )
        identifier = integration.alias or "integration"
        return cls(
            project_name=integration.project_name,
            alias=integration.alias,
            default=integration.default,
            is_global=integration.is_global,
            credential_type=integration.credential_type,
            credential_values=[
                CredentialRefEntry(
                    key=cred.key,
                    ref=CredentialRef.from_entity(identifier, cred.key),
                )
                for cred in integration.credential_values
            ],
            setting_type=integration.setting_type,
        )
