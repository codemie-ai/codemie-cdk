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

from types import SimpleNamespace

import pytest
from codemie_sdk.exceptions import ApiError
from pydantic import ValidationError

from codemie_iac.envelope import Document, DocumentKind, DocumentMeta
from codemie_iac.plan_apply.bulk_create import ResolveContext
from codemie_iac.plan_apply.credentials import EnvCredentialResolver
from codemie_iac.plan_apply.errors import (
    PlatformRejectionError,
    UnresolvedReferenceError,
)
from codemie_iac.plan_apply.existing import existing_category
from codemie_iac.plan_apply.lookup import NameLookup
from codemie_iac.plan_apply.single_apply import ApplyResult
from codemie_iac.specs.category import CategorySpec
from codemie_iac.specs.skill import SkillSpec

from .fakes import FakeCategories, FakeClient

TARGET = "proj"


def _category(description=None):
    spec = CategorySpec(name="x", description=description)
    return Document(
        version="v1", meta=DocumentMeta(kind=DocumentKind.CATEGORY, name="x"), spec=spec
    )


def _ctx(client):
    return ResolveContext(NameLookup([], TARGET, client), EnvCredentialResolver())


def _client(**responses):
    return FakeClient(categories=FakeCategories(**responses))


def _item(id_="cat-9"):
    return SimpleNamespace(id=id_, name="x")


def test_differing_description_is_reported_by_field_name():
    client = _client(
        get_categories=[_item()],
        get_category=SimpleNamespace(id="cat-9", name="x", description="old"),
    )
    assert existing_category(_ctx(client), _category("new")) == (
        "cat-9",
        ["description"],
    )


def test_equal_description_has_no_differences_though_list_item_lacks_it():
    client = _client(
        get_categories=[_item()],
        get_category=SimpleNamespace(id="cat-9", name="x", description="same"),
    )
    assert existing_category(_ctx(client), _category("same")) == ("cat-9", [])


def test_unknown_name_returns_none():
    client = _client(get_categories=[])
    assert existing_category(_ctx(client), _category()) is None


def test_entity_vanishing_between_list_and_get_returns_none():
    client = _client(get_categories=[_item()], get_category=None)
    assert existing_category(_ctx(client), _category()) is None


def test_non_category_kind_returns_none():
    skill = Document(
        version="v1",
        meta=DocumentMeta(kind=DocumentKind.SKILL, name="sk-x"),
        spec=SkillSpec(
            name="sk-x", description="a long description", content="c" * 100
        ),
    )
    client = _client(get_categories=[_item()])
    assert existing_category(_ctx(client), skill) is None
    assert client.categories.calls == []


def test_listing_failure_is_a_platform_rejection_and_nothing_is_created():
    client = _client(get_categories=ApiError("boom", 500))
    with pytest.raises(PlatformRejectionError):
        existing_category(_ctx(client), _category())
    assert client.categories.calls_to("create_category") == []


def test_same_name_twice_is_ambiguous_and_nothing_is_created():
    client = _client(get_categories=[_item("a"), _item("b")])
    with pytest.raises(UnresolvedReferenceError):
        existing_category(_ctx(client), _category())
    assert client.categories.calls_to("create_category") == []


def test_skipped_result_cannot_also_be_created():
    with pytest.raises(ValidationError):
        ApplyResult(id="1", created=True, skipped=True)
