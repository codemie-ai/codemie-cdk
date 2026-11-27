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

import pytest
from pydantic import ValidationError
from codemie_iac.credentials import CredentialRef, is_mask


def test_from_entity_is_deterministic():
    a = CredentialRef.from_entity("jira_prod", "api_token")
    b = CredentialRef.from_entity("jira_prod", "api_token")
    assert a == b == CredentialRef("env:JIRA_PROD_API_TOKEN")


def test_from_entity_sanitizes_non_alphanumeric():
    ref = CredentialRef.from_entity("jira-prod!", "api.token")
    assert ref.root == "env:JIRA_PROD__API_TOKEN"


def test_rejects_literal_value():
    with pytest.raises(ValidationError):
        CredentialRef("not-a-reference")


def test_from_entity_signature_has_no_value_parameter():
    import inspect

    params = inspect.signature(CredentialRef.from_entity).parameters
    assert list(params) == ["identifier", "credential_key"]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("*" * 8, True),
        ("*" * 10, True),
        ("*" * 7, False),
        ("*" * 11, False),
        ("****a***", False),
        (None, False),
        (8, False),
    ],
)
def test_is_mask(value, expected):
    assert is_mask(value) is expected
