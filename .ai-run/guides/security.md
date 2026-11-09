# Security

This repository is a public client tool. It has no server, routes, database or session layer. The risks are secret leaks, destructive platform operations and the supply chain.

The list of files, commands and actions an agent must refuse is in `.ai-run/guides/safety-no-go.md`. `.claude/settings.json` enforces it for Claude Code.

## Authentication

The Node.js package authenticates through `codemie-sdk`, with client credentials or username and password (`iac/codemie-iac-nodejs/.env.template`). TLS verification is on (`createClient` in `lib/clientFactory.ts`). Do not add an option that turns it off (`SECURITY.md`).

## Secrets

| Avoid | Prefer |
|---|---|
| A real value in `codemie.yaml` | `${VAR}` substitution (`lib/codemieConfigLoader.ts`, `lib/backupYamlGenerator.ts`) |
| A committed `.env` | `.env.template` with placeholders. `.env` has an ignore rule in the package `.gitignore` |
| A committed backup | `backups/` has an ignore rule in the package `.gitignore`, because it holds sensitive data |
| A secret value in a Python document | `CredentialRef` (`env:NAME`). Only the `env` source is known (`credentials.py`, `specs/integration.py`) |

In `plan_apply`, `env:NAME` references are resolved from the environment only at apply time. No secret value goes into a result. A platform rejection becomes `PlatformRejectionError` with a scrubbed message, and the original exception is not kept (`plan_apply/errors.py`). Keep both rules when you change this code. The SDK logs request bodies at `DEBUG` level, credentials included, so the engine raises the `codemie_sdk.utils.http` logger to `INFO` during a write (`iac/codemie-iac-python/README.md`).

Limit: in the Python package, some MCP fields are whole-value matches only. A secret inside a larger string is written as plain text (`iac/codemie-iac-python/README.md`). Do not describe these fields as safe.

The ignore rules for `backups/` and `.env` are in the Node.js package. The root `.gitignore` covers agent state only.

## Destructive operations

These commands change or delete resources on a live platform. An agent must not run them unless the user asks and names the target environment.

| Command | Guard |
|---|---|
| `codemie-cdk destroy` | Must type `destroy`. `--force` skips the prompt (`src/destroy.ts`) |
| `codemie-cdk deploy --prune` | Without the flag, orphans are reported and kept (`src/deploy.ts`) |
| `codemie-cdk deploy --replace-skill-group` | Refuses without `--yes-replace-skills`. Skills get new ids (`src/deploy.ts`) |
| Python `BulkCreator.create_all`, `SingleEntityPlanner.apply` | No prompt. They create or update entities with the client the caller passes in. They never delete. `plan` makes no write (`iac/codemie-iac-python/README.md`) |

When you change these paths, keep the guard before the first platform call, and add a test for it. Do not make a destructive behaviour the default.

## Input validation

| Layer | Rule |
|---|---|
| App config | zod schema (`src/appConfig/configSchema.ts`) |
| Node.js config | `validateConfig`, slug uniqueness, skill limits (`src/validate.ts`, `src/lib/validationUtils.ts`) |
| `$import` files | Cycle tracking by visited files (`src/lib/configImports.ts`) |
| Datasource references | `setting_id` must be a string (`src/lib/codemieConfigLoader.ts`) |
| Python documents | pydantic with `extra="forbid"`, `yaml.safe_load_all`, JSON Schema (`envelope.py`, `serializer.py`, `schema.py`) |

## Public repository rules

No credentials, private hostnames, ticket keys or personal e-mail addresses in the tree. CI scans for internal references and secrets (`.github/workflows/ci.yml`, jobs `internal-refs` and `secrets-detection`). Report a vulnerability through a GitHub Security Advisory, not a public issue (`SECURITY.md`).

## Dependency and pipeline security

| Control | Where |
|---|---|
| Third-party actions are pinned by commit SHA | `.github/workflows/ci.yml` |
| Workflows use `contents: read` by default | `.github/workflows/ci.yml` (line 9), `.github/workflows/publish.yml` (line 22) |
| Checkout uses `persist-credentials: false` | `.github/workflows/ci.yml` |
| npm publish uses OIDC with no stored token. Only the `publish` job has `id-token: write` | `.github/workflows/publish.yml` (lines 145-148), `docs/RELEASING.md` |
| The `verify` job has no secrets | `docs/RELEASING.md` ("Checks before anything is published") |
| A real publish needs a Release on `main`, or a manual run from `main` with `dry_run` off and the word `publish` | `.github/workflows/publish.yml` (lines 51-79) |
| CodeQL runs on three languages | `.github/workflows/codeql.yml` |

Known exposures:

- The Node.js package has no lockfile.
- Reusable workflows reference `codemie-ai/ci-workflows` at `@main` (`.github/workflows/ci.yml`, `.github/workflows/publish.yml`).
- `publish.yml` downloads `check_version.py` from `ci-workflows@main` at run time, unpinned (lines 81-84).

Do not add new unpinned references. Release steps: `docs/RELEASING.md`.

## Anti-patterns

| Avoid | Prefer |
|---|---|
| A log line with a credential or the whole config | Log names and ids. `logApiErrorDetails` prints API response data, so do not pass secrets into requests that echo them |
| `verify_ssl: false` | Keep the default in `createClient` |
| A real tenant URL in an example | `https://codemie.example.com` (`.env.template`) |
