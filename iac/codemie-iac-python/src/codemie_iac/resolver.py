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

"""Reference resolution within a Bundle context.

Resolves (kind, name) references to specific Documents within a Bundle.
No file I/O or platform calls — resolution happens only within the passed-in Bundle.
"""

from .envelope import Bundle, Document


class ReferenceResolutionError(ValueError):
    """Raised when a reference cannot be uniquely resolved within a Bundle."""

    def __init__(self, kind: str, name: str, ambiguous: bool):
        reason = "ambiguous" if ambiguous else "unresolvable"
        super().__init__(
            f"{reason} reference: no unique {kind} named {name!r} in bundle"
        )
        self.kind = kind
        self.name = name
        self.ambiguous = ambiguous


class ReferenceResolver:
    """Resolves (kind, name) references to Documents within a Bundle."""

    def __init__(self, bundle: Bundle):
        self._bundle = bundle

    def resolve(self, kind: str, name: str) -> Document:
        """Resolve a reference to a unique Document.

        Args:
            kind: The document kind (e.g., "integration", "skill")
            name: The document name to match

        Returns:
            The unique Document matching both kind and name

        Raises:
            ReferenceResolutionError: If zero or multiple matches are found
        """
        matches = [
            d for d in self._bundle if d.meta.kind == kind and d.meta.name == name
        ]
        if len(matches) != 1:
            raise ReferenceResolutionError(kind, name, ambiguous=len(matches) > 1)
        return matches[0]
