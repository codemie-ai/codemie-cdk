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

"""Document envelope types shared by all IaC document kinds.

``DocumentMeta`` carries the document's ``kind``/``name`` discriminator,
``Document`` wraps a concrete ``*Spec`` payload with that metadata, and
``Bundle`` is an ordered collection of ``Document`` instances (potentially
mixing different ``kind``s) that round-trips through ``model_dump``.
"""

from enum import Enum
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, RootModel, TypeAdapter, model_validator

from .specs.assistant import AssistantSpec
from .specs.category import CategorySpec
from .specs.datasource import DatasourceSpec
from .specs.integration import IntegrationSpec
from .specs.skill import SkillSpec
from .specs.workflow import WorkflowSpec


class DocumentKind(str, Enum):
    """The closed set of resource kinds a ``Document`` can hold.

    Unlike ``*Spec.type`` (e.g. ``DatasourceSpec``'s nine-way discriminator),
    this is not a pydantic discriminated-union tag -- ``Document._dispatch_spec``
    below looks ``meta.kind`` up in ``_SPEC_BY_KIND`` manually, before pydantic's
    own union resolution ever runs (see that method's docstring for why). So
    there is no discriminated-union convention pulling this towards ``Literal``;
    it is just a fixed vocabulary, which is what ``Enum`` is for.
    """

    ASSISTANT = "assistant"
    DATASOURCE = "datasource"
    INTEGRATION = "integration"
    SKILL = "skill"
    CATEGORY = "category"
    WORKFLOW = "workflow"


_SPEC_BY_KIND = {
    DocumentKind.ASSISTANT: AssistantSpec,
    DocumentKind.DATASOURCE: DatasourceSpec,
    DocumentKind.INTEGRATION: IntegrationSpec,
    DocumentKind.SKILL: SkillSpec,
    DocumentKind.CATEGORY: CategorySpec,
    DocumentKind.WORKFLOW: WorkflowSpec,
}


def _spec_classes(spec_type) -> tuple[type, ...]:
    """Concrete spec classes behind a ``_SPEC_BY_KIND`` entry.

    ``isinstance`` rejects a subscripted generic, and ``DatasourceSpec`` is an
    ``Annotated[Union[...]]`` of per-type specs, so unwrap it into the plain
    member classes. A plain class unwraps to itself.
    """
    if get_origin(spec_type) is Union:
        return tuple(
            cls for member in get_args(spec_type) for cls in _spec_classes(member)
        )
    args = get_args(spec_type)
    if args:  # Annotated[X, ...] -> its first argument is the wrapped type
        return _spec_classes(args[0])
    return (spec_type,)


# Validation errors must never echo input values: a datasource document can
# carry a literal secret that the offline name check rejects.
_HIDE_INPUT = ConfigDict(hide_input_in_errors=True)


def _spec_adapter(spec_cls: Any) -> TypeAdapter:
    """Adapter for ``spec_cls``; unions (not plain models) accept a config."""
    if isinstance(spec_cls, type):
        return TypeAdapter(spec_cls)
    return TypeAdapter(spec_cls, config=_HIDE_INPUT)


class DocumentMeta(BaseModel):
    """Discriminator metadata attached to every ``Document``."""

    model_config = ConfigDict(extra="forbid")

    kind: DocumentKind
    name: str


class Document(BaseModel):
    """A single IaC document: version, metadata, and a kind-specific spec.

    ``meta.kind`` is the real discriminator for ``spec`` -- several Spec
    classes share field names (e.g. ``name``/``description``), so letting
    pydantic's own union resolution try each member in turn could silently
    pick the wrong one, or surface an unhelpful "no match in union" error
    instead of naming the actual offending field. The before-validator below
    uses ``meta.kind`` to select and pre-validate the correct Spec class
    before pydantic's union logic ever runs, so an unknown field inside
    ``spec`` is reported by that Spec's own ``extra="forbid"`` validation
    (naming the field) rather than by the union as a whole.
    """

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    version: str
    meta: DocumentMeta
    spec: (
        AssistantSpec
        | DatasourceSpec
        | IntegrationSpec
        | SkillSpec
        | CategorySpec
        | WorkflowSpec
    )

    @model_validator(mode="before")
    @classmethod
    def _dispatch_spec(cls, data):
        if isinstance(data, dict) and isinstance(data.get("spec"), dict):
            # CR-003: `meta` can be present but not a dict (e.g. a malformed
            # hand-edited document with `meta: "oops"`) -- `.get("kind")` on
            # a non-dict truthy value raises an uncaught AttributeError
            # instead of letting normal field validation report a clean
            # ValidationError naming `meta`. Guard explicitly instead.
            meta = data.get("meta")
            kind = meta.get("kind") if isinstance(meta, dict) else None
            # `kind` is still caller-controlled, untyped data at this point
            # (e.g. `meta: {kind: ["x"]}`) -- `dict.get` on an unhashable
            # value raises a raw TypeError instead of a clean ValidationError
            # naming `meta.kind`, which normal field validation produces once
            # this before-validator steps aside and lets it run.
            try:
                spec_cls = _SPEC_BY_KIND.get(kind)
            except TypeError:
                spec_cls = None
            if spec_cls is not None:
                data = {
                    **data,
                    "spec": _spec_adapter(spec_cls).validate_python(data["spec"]),
                }
        return data

    @model_validator(mode="after")
    def _check_spec_matches_kind(self) -> "Document":
        """Reject a `spec` whose type doesn't match `meta.kind`.

        `_dispatch_spec` above only resolves `spec`'s type when it arrives as
        a raw dict (the YAML-loading path). A `Document` built from model
        instances skips that dispatch entirely, and pydantic's union
        resolution accepts a value that's already an instance of one of the
        union's members as-is -- so `Document(meta=DocumentMeta(kind="skill",
        ...), spec=CategorySpec(...))` would otherwise validate with a
        `spec` that doesn't match its own `meta.kind`, and `to_yaml` would
        write a kind/body mismatch that `from_yaml` then rejects.
        """
        expected = _SPEC_BY_KIND[self.meta.kind]
        classes = _spec_classes(expected)
        if not isinstance(self.spec, classes):
            names = " | ".join(cls.__name__ for cls in classes)
            raise ValueError(
                f"meta.kind={self.meta.kind.value!r} requires spec to be a "
                f"{names}, got {type(self.spec).__name__}"
            )
        return self


class Bundle(RootModel[list[Document]]):
    """An ordered collection of ``Document`` instances, possibly mixed-kind."""

    def __iter__(self):
        return iter(self.root)

    def __len__(self):
        return len(self.root)
