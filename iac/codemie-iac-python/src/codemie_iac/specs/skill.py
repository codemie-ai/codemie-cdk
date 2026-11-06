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

"""Spec that mirrors ``codemie_sdk.models.skill.SkillCreateRequest`` for IaC documents.

No credential-bearing fields exist on ``SkillCreateRequest``, so this is a
verbatim copy of its fields plus ``extra="forbid"``.
"""

from pydantic import BaseModel, ConfigDict, Field

from codemie_sdk.models.skill import SkillCreateRequest, SkillVisibility


class SkillSpec(BaseModel):
    """Narrowed view of ``SkillCreateRequest``."""

    model_config = ConfigDict(extra="forbid")

    # Bounds mirror the platform's SkillCreateRequest; the SDK model does not
    # enforce them, so without them a bad document only fails with a 422.
    name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
    description: str = Field(..., min_length=10, max_length=1000)
    content: str = Field(..., min_length=100)
    project: str | None = None
    visibility: SkillVisibility | None = SkillVisibility.PROJECT
    categories: list[str] | None = Field(default_factory=list, max_length=3)
    enabled_builtin_subagents: list[str] | None = None

    @classmethod
    def from_entity(cls, skill: SkillCreateRequest) -> "SkillSpec":
        return cls(
            name=skill.name,
            description=skill.description,
            content=skill.content,
            project=skill.project,
            visibility=skill.visibility,
            categories=skill.categories,
            enabled_builtin_subagents=skill.enabled_builtin_subagents,
        )
