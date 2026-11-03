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

import copy
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

from pydantic import BaseModel
from pydantic_core import core_schema

from ..credentials import CredentialRef
from .errors import UnresolvableCredentialError

__all__ = [
    "MCP_REF_FIELDS",
    "SECRET_FIELDS",
    "EnvCredentialResolver",
    "ProviderSecretLookup",
    "SecretValue",
]

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


# --- datasource secret fields ----------------------------------------------

# (provider_name, toolkit_id) -> names of settings the platform provider schema
# marks secret (parameter_type == SECRET). Injected by the caller that can reach
# the platform. While it is unset or failing, provider settings fail closed:
# every non-empty string setting must be an env: reference.
ProviderSecretLookup = Callable[[str, str], Iterable[str]]


def _schema_secret_keys(
    spec: Any, lookup: ProviderSecretLookup | None
) -> tuple[frozenset[str] | None, str]:
    """Secret setting names per the platform provider schema and, when the
    schema is unavailable, ``None`` plus the reason (never the error text,
    which could echo a value).

    The result must be a collection of names. A bare string would split into
    characters, so it counts as "schema unavailable", like any non-string
    member. An empty collection is a valid answer: the schema marks no
    setting secret."""
    if lookup is None:
        return None, "no lookup configured"
    try:
        keys = lookup(spec.provider_name, spec.toolkit_id)
        if isinstance(keys, (str, bytes)):
            return None, f"lookup returned {type(keys).__name__}, not a collection"
        names = frozenset(keys)
    except Exception as exc:  # noqa: BLE001 - any lookup failure means "schema unknown"
        return None, f"lookup raised {type(exc).__name__}"
    if not all(isinstance(name, str) for name in names):
        return None, "lookup returned a non-string name"
    return names, ""


def _string_leaves(value: Any) -> Iterator[Any]:
    """The leaves of ``value`` that could be a secret or an ``env:`` reference."""
    return (
        leaf
        for leaf in _walk(value)
        if isinstance(leaf, (str, CredentialRef)) and leaf != ""
    )


def _provider_secret_settings(
    spec: Any, lookup: ProviderSecretLookup | None
) -> Iterator[tuple[str, Any, str]]:
    """Schema-secret settings as ``(name, value, note)``. With the schema
    unavailable every setting is in doubt, so must be an ``env:`` reference,
    except values that hold no string (int, bool, float, None, containers of
    those): those can be neither a secret string nor a reference. A dict or
    list is in doubt per string leaf it contains."""
    schema_keys, why = _schema_secret_keys(spec, lookup)
    settings = getattr(spec, "settings", None) or {}
    if schema_keys is not None:
        for name, value in settings.items():
            if name in schema_keys:
                yield name, value, ""
        return
    note = f"; the provider schema lookup was unavailable ({why})"
    for name, value in settings.items():
        for leaf in _string_leaves(value):
            yield name, leaf, note


def _sharepoint_secrets(
    spec: Any, lookup: ProviderSecretLookup | None
) -> Iterator[tuple[str, Any, str]]:
    yield "access_token", getattr(spec, "access_token", None), ""


def _no_secret_settings(
    spec: Any, lookup: ProviderSecretLookup | None
) -> Iterator[tuple[str, Any, str]]:
    return iter(())


# Keyed by datasource ``type``; svn and xray have no secret fields. SharePoint
# carries its transient OAuth ``access_token`` as an ``env:`` reference.
SECRET_FIELDS: dict[
    str,
    Callable[[Any, ProviderSecretLookup | None], Iterable[tuple[str, Any, str]]],
] = {
    "provider": _provider_secret_settings,
    "svn": _no_secret_settings,
    "knowledge_base_sharepoint": _sharepoint_secrets,
    "knowledge_base_xray": _no_secret_settings,
}


def _require_ref(spec: Any, setting: str, value: Any, note: str = "") -> Any:
    """``value`` when it is an ``env:`` reference; otherwise reject, naming the
    setting but never echoing the value."""
    if _as_ref(value) is None:
        raise UnresolvableCredentialError(
            "literal_secret",
            "datasource",
            str(getattr(spec, "name", "")),
            f"secret setting {setting!r} must be an env: reference, "
            f"not a literal value{note}",
        )
    return value


def _iter_datasource_secrets(
    spec: Any, lookup: ProviderSecretLookup | None
) -> Iterator[Any]:
    extract = SECRET_FIELDS.get(getattr(spec, "type", None), _no_secret_settings)
    for setting, value, note in extract(spec, lookup):
        if value not in (None, ""):
            yield _require_ref(spec, setting, value, note)


def _iter_provider_setting_refs(spec: Any) -> Iterator[Any]:
    """Every string leaf of the provider settings: the request body reveals
    all ``env:`` references, so preflight must check all of them, not only the
    ones the schema calls secret."""
    if getattr(spec, "type", None) == "provider":
        yield from _string_leaves(getattr(spec, "settings", None) or {})


def _iter_candidates(spec: Any, lookup: ProviderSecretLookup | None) -> Iterator[Any]:
    for entry in getattr(spec, "credential_values", None) or []:
        yield getattr(entry, "ref", None)
    yield from _iter_datasource_secrets(spec, lookup)
    yield from _iter_provider_setting_refs(spec)
    for server in _iter_servers(spec):
        yield from _iter_config_values(server)


class EnvCredentialResolver:
    """Resolves ``env:NAME`` references from an environment mapping."""

    def __init__(
        self,
        environ: Mapping[str, str] | None = None,
        provider_secret_lookup: ProviderSecretLookup | None = None,
    ):
        self._environ = os.environ if environ is None else environ
        self._revealed: set[str] = set()
        self._provider_secret_lookup = provider_secret_lookup

    def with_provider_secret_lookup(
        self, lookup: ProviderSecretLookup | None
    ) -> "EnvCredentialResolver":
        """A resolver with ``lookup``; the original is not modified. The copy
        shares the environment and the revealed-values set, so error scrubbing
        still sees every value handed out."""
        other = copy.copy(self)
        other._provider_secret_lookup = lookup
        return other

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

    def collect_refs(self, spec: Any) -> list[CredentialRef]:
        """All distinct credential refs in a spec, in first-seen order."""
        seen: dict[str, CredentialRef] = {}
        for candidate in _iter_candidates(spec, self._provider_secret_lookup):
            ref = _as_ref(candidate)
            if ref is not None:
                seen.setdefault(ref.root, ref)
        return list(seen.values())
