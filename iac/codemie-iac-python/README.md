# codemie-iac-python

A small Python package that turns CodeMie resources (assistants, datasources,
integrations, skills, categories, workflows) into plain YAML documents you can
commit to a repo, and reads those documents back.

It does not talk to the CodeMie platform. Everything here works offline, with
no network and no running backend.

## Why this exists

Today the only way to describe a CodeMie resource outside the UI is to hand-write
YAML or call the API directly. This package gives you typed, validated building
blocks for that YAML instead, plus two safety rules baked in:

- **No secrets in the file, for the fields this package recognizes as
  credential-shaped.** Those are stored as references (`env:SOME_NAME`),
  never as real values — and a handful of them (`auth_token`,
  `Integration.credential_values`) are *typed* that way, so a literal value
  can't be constructed at all. A few others (`env`, `headers`, `args`, `url`,
  `arguments`, `mcp_connect_url` on an MCP server) are best-effort,
  whole-value matches only: a value already shaped like a reference is
  recognized, but this package does not scan arbitrary strings for secrets,
  so one embedded inside a larger value (e.g. `--token=sk-live-...` in an
  `args` entry, or a signed query parameter on a `url`) is written to the
  file as plain text. See "Credential narrowing for inline MCP servers"
  below for the exact fields.
- **No silent typos.** An unknown or misspelled field fails loudly, naming the
  field, instead of being quietly dropped.

## What it can do right now

- Build a `Document` for one resource (assistant, datasource, integration,
  skill, category, or workflow) — always a single file, workflows included.
- Group several documents into a `Bundle`.
- Write a `Bundle` to YAML and read it back, byte-for-byte stable.
- Validate a YAML document against a packaged JSON Schema, offline.
- Resolve a reference like "the integration named X" within a bundle.

## What it can't do yet

- No command-line tool. This is a library you import, not something you run
  from a terminal (a CLI is planned for a later release).
- No `plan` / `apply`. Nothing here creates or updates anything on the
  platform.
- No reading credentials from the environment. That also comes later, as part
  of `apply`.

## Install

This package lives next to the Node IaC tool, under `iac/codemie-iac-python`.
It depends on the local `codemie-sdk-python` package, so install both from
this repo with Poetry:

```bash
cd iac/codemie-iac-python
poetry install
```

## Documents and bundles

Three types tie everything together:

- **`Spec`** — one class per resource kind (`CategorySpec`, `AssistantSpec`, ...).
  This holds the resource's actual fields — the same data you'd send to the
  platform to create it. Build one with `SomeSpec.from_entity(entity)` from
  the matching `codemie_sdk` model, or with plain keyword arguments. See
  "One example per asset kind" below for how to build each one.
- **`Document`** — wraps one `Spec` plus `meta`. This is the unit that gets
  saved to disk.
- **`Bundle`** — an ordered list of `Document`s. It can mix kinds — an
  assistant, a datasource, a skill, all in one list.

### `DocumentMeta`: a label, not platform data

`meta` is a small `DocumentMeta` object with two fields: `kind` (which
`Spec` type this document holds) and `name`. `name` here is **not** a
resource field — it's just a label you pick so this document can be found
inside a `Bundle`. `ReferenceResolver.resolve(kind, name)` matches on it;
nothing else reads it, and nothing checks it against anything inside `spec`.

`kind` is a `DocumentKind` enum (`DocumentKind.CATEGORY`,
`DocumentKind.ASSISTANT`, ...) — one of the six fixed values, used in every
example below. You can pass the plain string instead (`kind="category"`);
pydantic converts it to the matching `DocumentKind` member for you, and an
unrecognized string is rejected the same way either form would be.

In most examples below, `meta.name` is set to the same string as the
resource's own name (`spec.name`), simply because that's the clearest thing
to do — not because the code requires it. The Integration example makes the
difference concrete: `IntegrationSpec` has no `name` field at all (it uses
`alias` instead), so `meta.name` is set from `integration.alias` there.
Pick whatever label makes the document easy to find; `spec` is what actually
describes the resource.

The rest of this section covers what you can do once you have a `Bundle`.

### Save to YAML, and read it back

```python
from codemie_iac import to_yaml, from_yaml

text = to_yaml(bundle)
bundle_again = from_yaml(text)
assert bundle_again == bundle
```

Writing the same bundle twice always produces the exact same text, so diffs
in version control only show real changes.

### Validate a document offline

```python
from codemie_iac import validate_document, DocumentValidationError

try:
    validate_document({"version": "v1", "meta": {"kind": "category", "name": "x"}})
except DocumentValidationError as exc:
    print(exc.errors)  # every problem found, not just the first one
```

No network call is made — the schema ships inside the package.

### Credentials are references, never values

A credential field never holds a secret. It holds a reference such as
`env:JIRA_PROD_API_TOKEN`, built by `CredentialRef.from_entity(identifier,
credential_key)`. That function never reads the real secret value — only the
identifier and the key — so the same two inputs always produce the same
reference. See the Integration example below for it in context.

### Finding things by name inside a bundle

```python
from codemie_iac import ReferenceResolver

resolver = ReferenceResolver(bundle)
support_category = resolver.resolve("category", "support")
```

This only looks inside the bundle you pass in — it never reaches the
platform or other files.

## One example per asset kind

Each example below does the same two steps: describe the asset with its
`codemie_sdk` model (the same model you'd use to call the platform), then
convert it to the matching IaC `Spec` with that `Spec`'s own
`from_entity(...)` classmethod, and render it to YAML.

`from_entity` does the field mapping once, inside the package, instead of
every caller re-deriving it. For the credential-bearing kinds (Integration,
and Assistant's MCP/toolkit integration references) it does the same
narrowing shown explicitly elsewhere in this README — it just does it
internally, never reading an actual secret value. If you'd rather build a
`Spec` by hand (no entity object, or a one-off that doesn't map cleanly to
an existing SDK model), every field is still a plain, settable keyword
argument — `from_entity` is a convenience, not the only way in.

### Category

```python
from codemie_sdk.models.categories import CategoryCreateRequest
from codemie_iac import Document, DocumentMeta, DocumentKind, Bundle, to_yaml
from codemie_iac.specs.category import CategorySpec

category = CategoryCreateRequest(name="support", description="Support team resources")

doc = Document(
    version="v1",
    meta=DocumentMeta(kind=DocumentKind.CATEGORY, name=category.name),
    spec=CategorySpec.from_entity(category),
)
print(to_yaml(Bundle([doc])))
```

### Skill

```python
from codemie_sdk.models.skill import SkillCreateRequest
from codemie_iac import Document, DocumentMeta, DocumentKind, Bundle, to_yaml
from codemie_iac.specs.skill import SkillSpec

skill = SkillCreateRequest(
    name="changelog-writer",
    description="Writes a changelog entry from a diff",
    content="Summarize the given diff as one changelog line.",
    project="my-project",
)

doc = Document(
    version="v1",
    meta=DocumentMeta(kind=DocumentKind.SKILL, name=skill.name),
    spec=SkillSpec.from_entity(skill),
)
print(to_yaml(Bundle([doc])))
```

### Integration

`IntegrationSpec.from_entity` never reads the real credential value — it
only ever sees the integration's `alias` and each credential entry's `key`,
the same two inputs you'd pass to `CredentialRef.from_entity` by hand:

```python
from codemie_sdk.models.integration import Integration, CredentialTypes, CredentialValues
from codemie_iac import Document, DocumentMeta, DocumentKind, Bundle, to_yaml
from codemie_iac.specs.integration import IntegrationSpec

integration = Integration(
    project_name="my-project",
    alias="jira-prod",
    credential_type=CredentialTypes.JIRA,
    credential_values=[CredentialValues(key="api_token", value="<kept out of the document>")],
)

doc = Document(
    version="v1",
    meta=DocumentMeta(kind=DocumentKind.INTEGRATION, name=integration.alias),
    spec=IntegrationSpec.from_entity(integration),
)
print(to_yaml(Bundle([doc])))
```

### Datasource

A datasource is one of nine kinds (code, Jira, Confluence, ...), each with
its own `*Spec` class. This example uses the code-repository kind:

```python
from codemie_sdk.models.datasource import CodeDataSourceRequest
from codemie_iac import Document, DocumentMeta, DocumentKind, Bundle, to_yaml
from codemie_iac.specs.datasource import CodeDatasourceSpec

datasource = CodeDataSourceRequest(
    name="my_code_kb",
    project_name="my-project",
    description="Code knowledge base",
    link="https://github.com/org/repo",
    branch="main",
)

doc = Document(
    version="v1",
    meta=DocumentMeta(kind=DocumentKind.DATASOURCE, name=datasource.name),
    spec=CodeDatasourceSpec.from_entity(datasource),
)
print(to_yaml(Bundle([doc])))
```

Each of the other eight kinds has the matching `*DatasourceSpec.from_entity(request)`.

### Assistant

```python
from codemie_sdk.models.assistant import AssistantCreateRequest
from codemie_iac import Document, DocumentMeta, DocumentKind, Bundle, to_yaml
from codemie_iac.specs.assistant import AssistantSpec

assistant = AssistantCreateRequest(
    name="release-notes-writer",
    description="Writes release notes from merged PRs",
    system_prompt="You write concise, user-facing release notes.",
    project="my-project",
    llm_model_type="gpt-4o",
)

doc = Document(
    version="v1",
    meta=DocumentMeta(kind=DocumentKind.ASSISTANT, name=assistant.name),
    spec=AssistantSpec.from_entity(assistant),
)
print(to_yaml(Bundle([doc])))
```

`AssistantSpec` has more fields than this (toolkits, MCP servers, prompt
variables, ...). `from_entity` narrows all of them: a toolkit's or MCP
server's referenced `Integration` becomes just its name, and an MCP
server's `auth_token` becomes a `CredentialRef` keyed by that server's own
name — the same narrowing shown in the Integration example, just applied
automatically.

`AssistantSpec.deselected_default_tools` lists default datasource tools to
switch off (`get_repository_file_tree`, `search_code_repo`, `search_kb`).
Empty or absent means all default tools are on, and the key is omitted from
the YAML when the list is empty. The field is declared locally and read from
the request with `getattr`; raise the `codemie-sdk-python` floor once a
release ships `deselected_default_tools`.


### Workflow

A workflow is built with the SDK's own `WorkflowBuilder`, not hand-filled
field by field like the other five kinds. `WorkflowSpec` wraps the resulting
`WorkflowDefinition` directly — one file, same as every other kind:

```python
from codemie_sdk.builders.workflow.builder import WorkflowBuilder
from codemie_sdk.builders.workflow.definition import WorkflowNextState
from codemie_sdk.models.workflow import WorkflowMode
from codemie_iac import Document, DocumentMeta, DocumentKind, Bundle, to_yaml
from codemie_iac.specs.workflow import WorkflowSpec

workflow = (
    WorkflowBuilder("release-notes")
        .with_description("Generate release notes from merged PRs")
        .with_mode(WorkflowMode.SEQUENTIAL)
        .add_assistant("writer", system_prompt="Summarize the given PRs as release notes.")
        .add_state("draft", "writer", "Draft the release notes", next=WorkflowNextState())
        .render()
)

doc = Document(
    version="v1",
    meta=DocumentMeta(kind=DocumentKind.WORKFLOW, name=workflow.name),
    spec=WorkflowSpec.from_entity(workflow),
)
print(to_yaml(Bundle([doc])))
```

`name`, `description`, `shared`, and `icon_url` all come from `workflow`
itself — nothing is copied onto a sibling field, so nothing can drift out of
sync with it. The platform's own flattened `yaml_config` text
(`workflow.to_yaml_config()`) is not generated here at all; that happens
later, whenever a future `apply` step actually publishes the workflow.

**Credential narrowing for inline MCP servers.** An inline assistant's MCP
server config (`WorkflowMCPServer.config`) is typed `MCPServerConfig` — the
same model `MCPServerDetails.config` already uses on `AssistantCreateRequest`
— so `WorkflowSpec.from_entity` narrows it by reusing
`MCPServerConfigSpec.from_entity` wholesale: `auth_token` becomes a
`CredentialRef` (also listed in `credential_values`, same `{key, ref}` shape
as `IntegrationSpec.credential_values`), and any `env`/`headers`/`args`/
`url` value already shaped like a reference (`"env:SOME_REF"`) is recognized
too — the same narrowing `AssistantSpec` gets for its own MCP servers,
nothing weaker. `auth_token` is also re-checked on every `WorkflowSpec`,
including one built directly from model instances or loaded from a file, not
just one produced by `from_entity` — a literal value there is always
rejected. The `env`/`headers`/`args`/`url` fields are not: as noted above,
narrowing them is a best-effort, whole-value match, never an enforced
guarantee.

## Where things live

```
src/codemie_iac/
  envelope.py        # Document, DocumentMeta, DocumentKind, Bundle
  credentials.py     # CredentialRef
  resolver.py        # ReferenceResolver
  serializer.py      # to_yaml / from_yaml
  schema.py          # document_json_schema, validate_document
  specs/             # one Spec class per resource kind
```
