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

import re
import threading
from pydantic import RootModel, model_validator

# CR-001: the shape check alone (`<alnum>+:<alnum/underscore>+`) accepts any
# colon-delimited literal with a lowercase-alnum prefix -- including a secret
# string that happens to be formatted that way. Restricting the prefix to a
# known, closed set of reference sources means an arbitrary literal cannot
# coincidentally satisfy the reference shape; "env" is the only source this
# module currently produces (via `from_entity`).
_REF_PATTERN = re.compile(r"^(?P<source>[a-z0-9]+):(?P<identifier>[A-Za-z0-9_]+)$")
_KNOWN_SOURCES = frozenset({"env"})

# CR-002: `from_entity`'s sanitization is intentionally lossy (distinct
# identifiers that differ only in punctuation collapse to the same output --
# see test_from_entity_sanitizes_non_alphanumeric), so two genuinely distinct
# (identifier, credential_key) pairs can collide onto the same CredentialRef
# string. The information needed to detect that (the original, pre-sanitized
# pair) only exists at the moment `from_entity` is called -- once a Bundle
# holds the final ref string, that provenance is gone. This process-lifetime
# registry remembers which pair produced which ref string, and raises if a
# *different* pair ever produces one already claimed by another pair. Calling
# `from_entity` again with the exact same pair (determinism, AC8) is not a
# collision and never raises.
_SEEN_REFS_LOCK = threading.Lock()
_SEEN_REFS: dict[str, tuple[str, str]] = {}

_MASK_LENGTHS = frozenset({8, 10})


def is_mask(value: object) -> bool:
    """True for the all-asterisk placeholder the platform returns for secrets."""
    return (
        isinstance(value, str) and len(value) in _MASK_LENGTHS and set(value) == {"*"}
    )


class CredentialRef(RootModel[str]):
    @model_validator(mode="after")
    def _check_format(self) -> "CredentialRef":
        match = _REF_PATTERN.fullmatch(self.root)
        if not match or match.group("source") not in _KNOWN_SOURCES:
            raise ValueError(
                "CredentialRef must match '<source>:<identifier>' with a "
                f"known source {sorted(_KNOWN_SOURCES)!r}, got {self.root!r}"
            )
        return self

    @classmethod
    def from_entity(cls, identifier: str, credential_key: str) -> "CredentialRef":
        def sanitize(value: str) -> str:
            return re.sub(r"[^A-Za-z0-9]+", "_", value)

        sanitized_id = sanitize(identifier).upper()
        sanitized_key = sanitize(credential_key).upper()
        if not any(c.isalnum() for c in sanitized_id) or not any(
            c.isalnum() for c in sanitized_key
        ):
            raise ValueError(
                "CredentialRef.from_entity requires identifier and "
                "credential_key to each contain at least one alphanumeric "
                f"character, got identifier={identifier!r}, "
                f"credential_key={credential_key!r}"
            )

        ref_string = f"env:{sanitized_id}_{sanitized_key}"
        pair = (identifier, credential_key)
        with _SEEN_REFS_LOCK:
            existing = _SEEN_REFS.get(ref_string)
            if existing is not None and existing != pair:
                raise ValueError(
                    f"CredentialRef collision: identifier/credential_key "
                    f"pairs {existing!r} and {pair!r} both sanitize to "
                    f"{ref_string!r}; use more distinguishable identifiers "
                    "or credential keys."
                )
            _SEEN_REFS[ref_string] = pair
        return cls(ref_string)


def reset_registry() -> None:
    """Clear the process-lifetime collision registry (CR-001).

    ``_SEEN_REFS`` otherwise accumulates for the lifetime of the process,
    with no bound and no scoping to any particular ``Bundle``. A long-running
    host that builds many logically unrelated ``Bundle``s over its lifetime
    should call this between them: without it, memory grows without bound,
    and two unrelated batches that happen to reuse the same
    ``(identifier, credential_key)`` pair for genuinely different secrets
    would spuriously collide -- or silently share a ref -- across batches
    that have nothing to do with each other.
    """
    with _SEEN_REFS_LOCK:
        _SEEN_REFS.clear()
