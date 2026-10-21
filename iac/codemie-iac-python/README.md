# codemie-iac-python

A small Python package that turns CodeMie resources (assistants, datasources,
integrations, skills, categories, workflows) into plain YAML documents you can
commit to a repo, and reads those documents back.

Most of the library works offline, with no network and no running backend. The
one exception is `codemie_iac.plan_apply`, which talks to the platform, and only
through the `codemie_sdk` services (see "Plan and apply against the platform"
below). Nothing else in the package makes a network call.

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
- Create a whole bundle on the platform, in dependency order, and plan or
  apply a single document against one existing entity
  (`codemie_iac.plan_apply`).

## What it can't do yet

- No command-line tool. This is a library you import, not something you run
  from a terminal (a CLI is planned for a later release).
- `apply` never deletes anything, and bulk apply only creates. See "Plan and
  apply against the platform" and "Not supported" below.

## Install

The IaC needs `codemie-sdk-python` 0.3.0 or newer (svn, SharePoint, Xray and
provider datasource support).

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

A datasource is one of thirteen kinds (code, Jira, Confluence, svn, SharePoint,
Xray, provider, ...), each with
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

Each of the other kinds has the matching `*DatasourceSpec.from_entity(request)`.

The svn, SharePoint, Xray and provider kinds in document form (svn,
SharePoint and Xray may carry a `setting_id`, the alias of an integration in
the bundle or live in the target project; a provider datasource may not, as the
platform does not store one):

```yaml
spec: {type: svn, name: svn_kb, project_name: my-project, description: d,
       link: "https://svn.example.com/repo", branch: trunk, index_type: code}
spec: {type: knowledge_base_sharepoint, name: sp_kb, project_name: my-project,
       description: d, site_url: "https://example.sharepoint.com/sites/x",
       auth_type: integration, setting_id: my-sharepoint-integration}
spec: {type: knowledge_base_xray, name: xray_kb, project_name: my-project,
       description: d, jql: "project = X"}
spec: {type: provider, name: prov_kb, project_name: my-project, description: d,
       provider_name: my-provider, toolkit_id: my-toolkit,
       settings: {region: eu, api_key: "env:PROVIDER_API_KEY"}}
```

The `region` literal above passes the offline name check and is accepted at plan/apply only when `provider_secret_lookup=`
reports that `region` is not secret (see below); without a lookup it must be an
`env:` reference too.

- **SharePoint OAuth uses an `access_token` reference.** The `oauth_codemie`
  and `oauth_custom` auth types need an access token, which the platform never
  stores or returns. A document carries it as `access_token: env:NAME`. The
  token is optional in a document (an exported one has none), but creating such a
  datasource, or updating it with a reindex, fails without it; a literal token
  is rejected without echoing it. The value is read from the environment on
  create and update. It is listed as not comparable in a plan.
  `auth_type`, `oauth_client_id` and `oauth_tenant_id` are compared.
- **Provider secret settings are `env:` references.** Two checks apply.
  Offline, `ProviderDatasourceSpec` makes a best-effort, name-based check: a
  literal string under a secret-looking setting name (a whole name part such as
  `password`, `secret`, `token`, `apikey`, `credential`, `passphrase`, or
  `api`/`private`/`access`/`secret`/`auth` + `key`, or `client` + `secret`,
  after splitting on punctuation and camelCase) is rejected, naming the
  document and the setting path such as `settings.auth.api_key`, never the
  value. `key_prefix`, `tokenizer` and `region` are not flagged, and `env:`
  references, empty strings and non-strings pass. At plan or apply, before any
  write, the platform's provider schema decides authoritatively which settings
  are secret; a literal value in such a setting is rejected, naming the field,
  including under names the offline check does not recognise. The value is read from the
  environment only when writing and never appears in plans, errors or logs.
  Pass `provider_secret_lookup=` to `BulkCreator` / `SingleEntityPlanner` (a
  callable `(provider_name, toolkit_id) -> secret setting names`, normally
  built from the provider schema). The lookup belongs to that planner or
  creator only. Without one, or if it fails or returns something other than a
  collection of names (a bare string, non-string names), the check fails
  closed: every non-empty string provider setting must be an `env:`
  reference, and the error says the schema lookup was unavailable and why (no
  lookup configured, or the exception type the lookup raised). Settings without
  a string (numbers, booleans, lists of numbers) are not checked; a list or map
  is checked per string it contains. A lookup that returns an empty collection
  is an answer, not a failure: the schema marks no setting secret. No caller
  in this package supplies a lookup, so unless you pass one, a literal such as
  `region: eu` is refused and must be an `env:` reference.
  `name`, `project_name`, `setting_id`, `description` and
  `project_space_visible` are reserved and rejected inside `settings`.
  Every `env:` reference in the settings is checked before the first write,
  not only the ones the schema calls secret.
- **Provider settings are compared key by key.** A key holding an `env:`
  reference, or masked on the platform, is reported as not comparable
  (`settings.<key>`); changes to the other keys still show in the plan.
  `toolkit_id` cannot change: a different one is refused, recreate the
  datasource.
  On update, settings the document leaves out keep their live values (the
  platform would otherwise reset them to the schema default). A provider
  document takes no `cron_expression` or `timezone`, and a setting value that
  starts with `env:` but is not a valid reference (`env:my-region`, `ENV:FOO`)
  is rejected.
- **Create-only and optional fields.** An Xray `embedding_model` is used on
  create only (the update route does not store it) and is not compared. An svn
  `branch` left out is `trunk` on create and the stored branch on update.
- **Reindexing follows the plan.** As for code and Git FAQ datasources, an svn
  update that changes only metadata (description, visibility, schedule) is sent
  with `skip_reindex`. A SharePoint or Xray update that changes a source field
  (`site_url`, `include_*`, `files_filter`, `jql`, auth fields, embedding model,
  `setting_id`) is sent with `full_reindex`; for an OAuth SharePoint datasource
  that needs the `access_token`. `force=True` reindexes.
- **Provider settings are validated at plan time, not offline.** The settings
  are free-form and schema-driven, so offline validation covers only the
  envelope and that secret settings are `env:` references. Unknown or missing
  provider settings are reported at plan time from the platform's provider
  schema. svn, SharePoint and Xray are fully validated offline.
- **Skill categories are values.** A skill's `categories` are entries of the
  platform's fixed list (at most 3), sent as written; unlike an assistant's
  categories they are not Category documents and create no dependency.
- **Fields of the export round trip.** Documents also carry toolkit and tool
  `auto_credentials_lookup`, an assistant's `hedging_config`,
  `interactive_enabled`, `enable_image_generation` and `file_attachment_enabled`,
  an inline MCP config's `audience` and `auth_config` (a secret-looking entry
  must be an `env:` reference), a workflow's `start_hint` and its engine
  switches (compared through `yaml_config`).
- A datasource create answers with a message only, so apply looks the new
  datasource up by project and name and returns its id. If the platform does
  not list it yet, the page cap (20 pages of 100) is exhausted, or the lookup
  fails, the datasource is reported as created without an id and a warning is
  logged (datasource, project and exception type only); the apply does not fail.
  A provider datasource is updated by its platform id.

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

`AssistantSpec.skill_ids` lists the skills attached to the assistant. Each
entry is a reference resolved when the document is applied (see below), and
an omitted field means no skills. The assistant request of the installed
`codemie-sdk-python` must carry `skill_ids`; if it does not, applying an
assistant that lists skills fails (`unsupported_sdk`) before anything is
written, instead of creating the assistant without its skills.

**Resolving skill and datasource references.** An assistant's `skill_ids` and
a workflow agent's `skill_ids` and `datasource_ids` are written as names. Each
value is resolved in this order: (1) a document with that name in the bundle
wins, even if the value looks like an id; (2) otherwise the name is looked up
in the target project; (3) otherwise a value shaped like a platform id (UUID)
is sent unchanged, so documents holding raw ids keep working; (4) otherwise,
or when a name matches more than one entity, the apply fails with an error
naming the reference and the document holding it, before anything is written.
In-bundle skills and datasources are created before the assistant or workflow
that uses them.

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
later, when `plan_apply` publishes the workflow.

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

## Plan and apply against the platform

`codemie_iac.plan_apply` is the only part of this package that talks to the
platform. It does so by calling `codemie_sdk` services (you pass in the SDK
client); the rest of the library stays offline. Ground rules:

- **Platform ids are passed in and returned, never stored.** A document never
  contains a platform id and nothing is written to a file. Ids are held in
  memory for one run, substituted into request bodies, and handed back in the
  result.
- **Apply never deletes anything.** Not in bulk, not for a single entity.
- **Bulk apply is create-only and dependency-ordered.** An entity whose name
  or content equals an existing one is still created; there is no dedupe, no
  update, and no scoped apply. All checks (dependency cycles, unsupported
  kinds, unresolved references, unresolvable credentials) run before the first
  write, so a bad bundle fails without creating anything.
- **Single-entity plan/apply works by id.** You give the id of the live
  entity; `plan` diffs the document against it with no writes, and `apply`
  updates it (or creates it when no id is given).
- Credential references (`env:NAME`) are resolved from the environment at
  apply time (`plan` does not need them: an unset variable is reported as an
  unresolvable `CannotCompare`). Masked live values are reported as
  `CannotCompare`, never as a difference, and no secret value appears in any
  result.
- **An empty plan sends no write.** Fields that cannot be compared (a rotated
  secret, a masked value) do not make a plan non-empty; `apply` lists them in
  `ApplyResult.uncomparable`. Pass `force=True` to write the full document
  anyway, e.g. to rotate a secret.
- **A document's `meta.name` must equal the entity's own name** (the spec
  `name`, the workflow's `name`, or the integration's `alias`). References and
  the live lookup go by `meta.name`, while the platform uses the spec name, so
  a difference is refused with `name_mismatch` before anything is written.
- **Updates avoid needless reindexing.** A code datasource whose plan differs
  only in metadata (description, visibility, schedule) is updated with
  `skip_reindex`. A Git FAQ datasource with a changed source field (`link`,
  `branch`, `files_filter`, `setting_id`) is sent whole with `full_reindex`;
  otherwise its source fields are left out, because the backend rejects them
  without a full reindex. `force=True` writes everything and reindexes.
- **Rejected calls are scrubbed.** A platform rejection (the SDK raises
  `requests.HTTPError`) becomes a `PlatformRejectionError` holding only the
  status, a scrubbed message and the parsed field errors; the original
  exception, whose request holds the resolved credentials, is not kept.
  Secrets are also replaced in their JSON-escaped, URL-encoded and base64
  forms. The SDK itself logs request bodies at `DEBUG` level, credentials
  included, so keep the `codemie_sdk` logger above `DEBUG` while applying.

```python
from codemie_sdk import CodeMieClient
from codemie_iac import from_yaml
from codemie_iac.plan_apply import BulkCreator, SingleEntityPlanner

client = CodeMieClient(...)          # your usual SDK client
bundle = from_yaml(open("bundle.yaml").read())

# Create everything in the bundle, dependencies first.
report = BulkCreator(client).create_all(bundle, target="my-project")
for item in report.created:
    print(item.kind, item.name, item.id)   # ids come back to you
if report.failed:                           # stops at the first failure
    print(report.failed.error_type, report.failed.reason)

# One entity, by id.
planner = SingleEntityPlanner(client)
document = next(iter(bundle))
plan = planner.plan(document, entity_id="<platform id>", target="my-project")
for d in plan.differences:
    print(d.field, d.document_value, d.live_value)
if not plan.is_empty:
    result = planner.apply(document, entity_id="<platform id>", target="my-project")
    print(result.id, result.created)
```

`target` is the project the entities live in. Failures raise or report an
`ApplyError` (`PlatformRejectionError`, `UnresolvedReferenceError`,
`UnresolvableCredentialError`) that names the entity kind and name.

## Not supported

Some things are refused up front, with a clear error, before anything is
written.

**A datasource cannot be renamed or moved to another project.** If the
document's datasource name or project differs from the live datasource you
point `plan`/`apply` at, you get:

```
datasource/<name>: renaming or moving a datasource is not supported: document is '<name>' in project '<project>', live is '<live name>' in project '<live project>'
```

(error type `datasource_identity_mismatch`). Instead, create a new datasource
with the new name or project, then update the assistants that use the old one
so they point at the new one.

**File datasources cannot be created or updated.** A document carries no file
content, so there is nothing to upload. You get:

```
datasource/<name>: datasource type 'knowledge_base_file': file datasources are not supported
```

(error type `unsupported_datasource_type`). In a bulk run this is caught
before the first write, so nothing is created.

A datasource's `setting_id` is read as the alias of an integration (in the
bundle or live in the target project) and replaced by its platform id on
write.

**An entity in another project is never overwritten.** Planning or applying an
update to an entity whose live project differs from the target fails with
`project_mismatch` (for a datasource it is `datasource_identity_mismatch`, see
above), and so does a document (assistant, skill, integration, datasource)
whose own project is not the target, in single apply and in bulk preflight.

**The project of a document is optional.** `AssistantSpec.project`,
`SkillSpec.project`, `IntegrationSpec.project_name` and every datasource's
`project_name` default to `None`. The CLI fills an omitted one with the target
project before planning or applying (single file and every document of a
directory); the engine itself (`BulkCreator`, `SingleEntityPlanner`) does not,
so library callers must set it. A project that is named and differs from the
target is refused (`project_mismatch`).

## Where things live

```
src/codemie_iac/
  envelope.py        # Document, DocumentMeta, DocumentKind, Bundle
  credentials.py     # CredentialRef
  resolver.py        # ReferenceResolver
  serializer.py      # to_yaml / from_yaml
  schema.py          # document_json_schema, validate_document
  specs/             # one Spec class per resource kind
  plan_apply/        # bulk create and single-entity plan/apply (uses codemie_sdk)
```

## CLI

```
codemie-iac [--project NAME] [-c/--config codemie.yaml] [--env-file PATH] plan <file> --id <id> [--json]
codemie-iac [--project NAME] [-c/--config codemie.yaml] [--env-file PATH] apply <path> [--id <id>] [--json]
```

Global flags `--project`, `-c/--config` and `--env-file` go BEFORE the
subcommand; `--json` goes after it.

The `project` of a document (`project_name` for integrations and datasources)
is optional and defaults to the target project. A different explicit value is
refused with `project_mismatch`.

`.env`: if `./.env` exists in the current directory it is read (a missing one is
ignored); `--env-file PATH` reads that file instead (missing or unreadable is a
config error, exit 4). Lines are `KEY=VALUE`; blank lines, `#` comments and an
optional `export ` prefix are handled, matching single/double quotes around the
value are stripped, `${}` is not expanded, and lines with an invalid key are
skipped. Variables already set in the real environment always win; `.env` only
fills in unset ones (nothing is written to `os.environ`). `${NAME}` references
in `codemie.yaml` see the merged values, and so do `env:NAME` credential references
in `apply` (so a secret like `JIRA_PROD_API_TOKEN` can live in `.env`).

Exit codes: 0 success / nothing to do, 1 changes pending, 2 apply failed,
3 unresolved input, 4 config error, 5 invalid document.

Environment variables: `CODEMIE_API_URL`, `CODEMIE_AUTH_URL`, `CODEMIE_REALM`,
`CODEMIE_CLIENT_ID`, `CODEMIE_CLIENT_SECRET`, `CODEMIE_USERNAME`,
`CODEMIE_PASSWORD`, `CODEMIE_JWT_TOKEN`, `CODEMIE_PROJECT`,
`CODEMIE_VERIFY_SSL` (default `true`; `false` disables TLS verification).

`codemie.yaml` keys: `project.name`; an `environment:` mapping with
`codemie_api_url`, `auth_server_url`, `auth_realm_name`, `client_id`,
`client_secret`, `username`, `password`, `jwt_token`; and the legacy `api:`
mapping (`url`, `auth_url`, `realm`) as a fallback. Precedence per key: flag >
environment variable (real environment, then `.env`) > `environment:` > `api:`.

String values may reference environment variables: `${NAME}` or
`${NAME:-default}`. An unset or empty variable without a default gives an empty
string, which counts as "not set". A `$` not followed by `{` is left as is.

```yaml
environment:
  codemie_api_url: ${CODEMIE_API_URL:-}
  jwt_token: ${CODEMIE_JWT_TOKEN:-}
```

With a JWT (`CODEMIE_JWT_TOKEN` / `jwt_token`) the token is sent as a static
bearer token and only the API URL is required. Without one, the API URL, auth
URL and realm are required, plus client credentials or username/password.

### Examples

Example documents live in [`examples`](examples). Each file in
the groups below is one document, except that `batch/` is a folder meant to
be applied together.

**Single mode: one file, one document.**

```
codemie-iac --project my-project plan examples/simple/assistant.yaml --id <id>
codemie-iac --project my-project apply examples/simple/assistant.yaml
```

**Batch mode: a directory.** `apply <dir>` creates every `*.yaml` / `*.yml`
file directly in that directory (not recursive), in dependency order, so
documents may reference each other by name (the `batch/` example:
integration, datasource, category, assistant).

```
codemie-iac --project my-project apply examples/batch
```

**Create:** `apply <file>` without `--id`, or `apply <dir>`.

```
codemie-iac --project my-project apply examples/simple/skill.yaml
```

**Update:** `apply <file> --id <id>` updates the existing asset with that
platform id. `plan <file> --id <id>` shows the changes without applying them
(exit code 1 when changes are pending); add `--json` for machine-readable
output.

```
codemie-iac --project my-project apply examples/simple/skill.yaml --id <id>
codemie-iac --project my-project plan examples/simple/skill.yaml --id <id>
codemie-iac --project my-project plan examples/simple/skill.yaml --id <id> --json
```

Global flags (`--project`, `-c`) go before the subcommand, `--json` after it.
Credentials in the examples are `env:NAME` references; export those variables
before applying. IDs inside workflows (`workflow_id`, `datasource_ids`,
`skill_ids`) are placeholders, or names of skills and datasources that are
resolved at apply time.

**Example files**

Simple (one per asset type):

- [`simple/assistant.yaml`](examples/simple/assistant.yaml)
- [`simple/category.yaml`](examples/simple/category.yaml)
- [`simple/datasource.yaml`](examples/simple/datasource.yaml)
- [`simple/integration.yaml`](examples/simple/integration.yaml)
- [`simple/skill.yaml`](examples/simple/skill.yaml)
- [`simple/workflow.yaml`](examples/simple/workflow.yaml)

Assistant with one integration:

- [`assistant-integrations/assistant_with_datasource.yaml`](examples/assistant-integrations/assistant_with_datasource.yaml)
- [`assistant-integrations/assistant_with_mcp_server.yaml`](examples/assistant-integrations/assistant_with_mcp_server.yaml)
- [`assistant-integrations/assistant_with_tool.yaml`](examples/assistant-integrations/assistant_with_tool.yaml)

Workflow node types:

- [`workflow-nodes/assistant_state.yaml`](examples/workflow-nodes/assistant_state.yaml)
- [`workflow-nodes/sub_workflow_state.yaml`](examples/workflow-nodes/sub_workflow_state.yaml)
- [`workflow-nodes/tool_state.yaml`](examples/workflow-nodes/tool_state.yaml)
- [`workflow-nodes/transform_node.yaml`](examples/workflow-nodes/transform_node.yaml)

Workflow routing styles:

- [`workflow-routing/condition.yaml`](examples/workflow-routing/condition.yaml)
- [`workflow-routing/iterator.yaml`](examples/workflow-routing/iterator.yaml)
- [`workflow-routing/next_state.yaml`](examples/workflow-routing/next_state.yaml)
- [`workflow-routing/parallel_next_states.yaml`](examples/workflow-routing/parallel_next_states.yaml)
- [`workflow-routing/switch.yaml`](examples/workflow-routing/switch.yaml)

Workflow inline assistants:

- [`workflow-assistants/with_datasource_ids.yaml`](examples/workflow-assistants/with_datasource_ids.yaml)
- [`workflow-assistants/with_skill_ids.yaml`](examples/workflow-assistants/with_skill_ids.yaml)
- [`workflow-assistants/with_tools.yaml`](examples/workflow-assistants/with_tools.yaml)

Batch folder (related documents):

- [`batch/01-integration.yaml`](examples/batch/01-integration.yaml)
- [`batch/02-datasource.yaml`](examples/batch/02-datasource.yaml)
- [`batch/03-category.yaml`](examples/batch/03-category.yaml)
- [`batch/04-assistant.yaml`](examples/batch/04-assistant.yaml)
