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

"""Credential resolution that never leaks secret values."""

import os
from collections.abc import Iterator, Mapping
from typing import Any

from pydantic import BaseModel
from pydantic_core import core_schema

from ..credentials import CredentialRef
from .errors import UnresolvableCredentialError

__all__ = ["MCP_REF_FIELDS", "EnvCredentialResolver", "SecretValue"]

_MASK = "***"


class SecretValue:
    """Holds a secret; repr/str/format are masked, ``reveal()`` returns it."""

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"SecretValue({_MASK})"

    def __str__(self) -> str:
        return _MASK

    def __format__(self, format_spec: str) -> str:
        return _MASK

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda _v: _MASK
            ),
        )

    def __reduce__(self) -> Any:
        raise TypeError("SecretValue cannot be pickled")


def _as_ref(value: Any) -> CredentialRef | None:
    if isinstance(value, CredentialRef):
        return value
    if isinstance(value, str):
        try:
            return CredentialRef(value)
        except ValueError:
            return None
    return None


#: MCP server fields that can carry credential refs. The same list drives
#: collection (preflight, redaction) and revealing (request bodies), so a ref
#: is never revealed without having been collected, or the other way round.
MCP_REF_FIELDS = ("config", "mcp_connect_url", "arguments", "command")


def _walk(value: Any) -> Iterator[Any]:
    """Every leaf (string or ``CredentialRef``) of a nested value."""
    if isinstance(value, BaseModel) and not isinstance(value, CredentialRef):
        for name in type(value).model_fields:
            yield from _walk(getattr(value, name, None))
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def _iter_config_values(server: Any) -> Iterator[Any]:
    for field in MCP_REF_FIELDS:
        yield from _walk(getattr(server, field, None))


def _iter_servers(spec: Any) -> Iterator[Any]:
    yield from getattr(spec, "mcp_servers", None) or []
    workflow = getattr(spec, "workflow", None)
    assistants = getattr(workflow, "assistants", None) or {}
    for assistant in assistants.values():
        yield from getattr(assistant, "mcp_servers", None) or []


def _iter_candidates(spec: Any) -> Iterator[Any]:
    for entry in getattr(spec, "credential_values", None) or []:
        yield getattr(entry, "ref", None)
    for server in _iter_servers(spec):
        yield from _iter_config_values(server)


class EnvCredentialResolver:
    """Resolves ``env:NAME`` references from an environment mapping."""

    def __init__(self, environ: Mapping[str, str] | None = None):
        self._environ = os.environ if environ is None else environ
        self._revealed: set[str] = set()

    def revealed_values(self) -> frozenset[str]:
        """Secret values handed out so far, for scrubbing error text."""
        return frozenset(self._revealed)

    @staticmethod
    def _var_name(ref: CredentialRef) -> str:
        return ref.root.split(":", 1)[1]

    def is_resolvable(self, ref: CredentialRef) -> bool:
        return bool(self._environ.get(self._var_name(ref)))

    def resolve(self, ref: CredentialRef) -> SecretValue:
        value = self._environ.get(self._var_name(ref))
        if not value:
            raise UnresolvableCredentialError(
                "unresolvable_credential",
                "credential",
                ref.root,
                f"credential reference {ref.root!r} is unset or empty",
            )
        self._revealed.add(value)
        return SecretValue(value)

    @staticmethod
    def collect_refs(spec: Any) -> list[CredentialRef]:
        """All distinct credential refs in a spec, in first-seen order."""
        seen: dict[str, CredentialRef] = {}
        for candidate in _iter_candidates(spec):
            ref = _as_ref(candidate)
            if ref is not None:
                seen.setdefault(ref.root, ref)
        return list(seen.values())
