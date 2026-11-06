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

from .bulk_create import (
    BulkCreator,
    BulkCreateReport,
    CreatedEntity,
    FailedEntity,
)
from .credentials import EnvCredentialResolver, SecretValue
from .errors import (
    ApplyError,
    FieldError,
    PlatformRejectionError,
    UnresolvableCredentialError,
    UnresolvedReferenceError,
)
from .field_policy import FIELD_POLICIES, FieldPolicy
from .guards import guard_datasource_identity, guard_supported
from .kinds import ADAPTERS, KindAdapter, adapter_for
from .lookup import NameLookup
from .ordering import DependencyGraph
from .single_apply import (
    ApplyResult,
    CannotCompare,
    Difference,
    Plan,
    SingleEntityPlanner,
    diff,
)

__all__ = [
    "ADAPTERS",
    "FIELD_POLICIES",
    "ApplyError",
    "ApplyResult",
    "BulkCreateReport",
    "BulkCreator",
    "CannotCompare",
    "CreatedEntity",
    "DependencyGraph",
    "Difference",
    "EnvCredentialResolver",
    "FailedEntity",
    "FieldError",
    "FieldPolicy",
    "KindAdapter",
    "NameLookup",
    "Plan",
    "PlatformRejectionError",
    "SecretValue",
    "SingleEntityPlanner",
    "UnresolvableCredentialError",
    "UnresolvedReferenceError",
    "adapter_for",
    "diff",
    "guard_datasource_identity",
    "guard_supported",
]
