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

    name: str
    description: str
    content: str
    project: str
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
