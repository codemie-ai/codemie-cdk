# Architecture

## Overview

The repository holds two independent packages. They share no code and have no workspace manifest. Each has its own dependencies and CI job.

| Package | Path | Role | Talks to the platform |
|---|---|---|---|
| `@codemieai/cdk` | `iac/codemie-iac-nodejs` | The `codemie-cdk` CLI and a library. Deploys YAML to the platform (`bin` in `package.json`) | Yes, through `codemie-sdk` |
| `codemie-cdk-python` | `iac/codemie-iac-python` | Library. Turns resources into YAML documents, reads them back, and plans or applies them on the platform (`iac/codemie-iac-python/README.md`) | Only `codemie_iac.plan_apply`, through `codemie_sdk` services |

The two packages use different document shapes. The Node.js package reads one `codemie.yaml` with `$import` and `$ref`. The Python package uses `version`/`meta`/`spec` documents (`Document` in `iac/codemie-iac-python/src/codemie_iac/envelope.py`). A file for one package is not valid for the other.

## Node.js components (`iac/codemie-iac-nodejs`)

| Path | Responsibility |
|---|---|
| `src/cli/index.ts` | Commander commands. Parses options, builds `AppConfig`, calls a command `main` |
| `src/{deploy,preview,validate,import,backup,destroy,init}.ts` | One file per command. Each exports the core function and a `main` wrapper |
| `src/index.ts` | Public library API |
| `src/appConfig/` | Paths for config, state and backups (`configLoader.ts`) |
| `src/lib/` | Loader, state, checksums, converters, resolvers, retry, logging |
| `src/types/codemieConfig.ts` | Types for the config and the state file |
| `examples/` | Sample YAML. Biome format does not cover it |

## Python components (`iac/codemie-iac-python`)

| Path | Responsibility |
|---|---|
| `src/codemie_iac/envelope.py` | `Document`, `DocumentMeta`, `DocumentKind`, `Bundle` |
| `src/codemie_iac/specs/` | One Spec module per resource kind |
| `src/codemie_iac/serializer.py` | `to_yaml`, `from_yaml` |
| `src/codemie_iac/schema.py` | JSON Schema and offline validation |
| `src/codemie_iac/resolver.py` | Lookup by kind and name within one `Bundle` |
| `src/codemie_iac/credentials.py` | `CredentialRef`, the `env:NAME` reference type |
| `src/codemie_iac/plan_apply/` | Plan and apply against the platform: bulk create (`BulkCreator`), single-entity plan and apply (`SingleEntityPlanner`), credential resolution (`EnvCredentialResolver`), scrubbed errors. The only module that calls the platform |
| `src/codemie_iac/__init__.py` | Public API |

## Data flow: `codemie-cdk deploy`

All functions are in `iac/codemie-iac-nodejs/src`.

1. `loadConfig` (`lib/codemieConfigLoader.ts`) reads YAML, then resolves `$import`, substitutes `${VAR}`, expands skill `source_dir`, applies datasource defaults and resolves `$ref`. The order matters.
2. `validateSkillDescriptions` runs before the client is created.
3. `createClient` (`lib/clientFactory.ts`) connects.
4. `CleanupManager` (`lib/cleanupManager.ts`) finds orphans: resources in state but not in config.
5. Resources deploy in fixed order in `deploy.ts`: datasources, skills, assistants, workflows. Later kinds refer to the ids of earlier kinds. Assistants sort by dependency.
6. With `--prune`, orphans are deleted last, so skills can detach first.
7. `--replace-skill-group` is a separate path that returns early.

## Key abstractions

| Abstraction | Rule | Where |
|---|---|---|
| State file | Maps a resource name to its platform id and checksum. Default path is `.codemie/state.json` | `appConfig/defaultConfig.ts`, `lib/stateManager.ts` |
| Checksums | Decide create, update or unchanged. Assistant config is normalized before hash, so equal meaning gives an equal hash | `lib/checksumUtils.ts`, `lib/codemieConfigChecksums.ts` |
| Converters | Map IaC types to SDK types | `lib/converters.ts` |
| `Document` dispatch | `meta.kind` selects the Spec before pydantic union logic runs, so errors name the bad field | `Document` in `envelope.py` |
| Round trip | `from_yaml(to_yaml(b)) == b`. Do not add `exclude_none` | `to_yaml` in `serializer.py` |

## Dependency rules

| Avoid | Prefer |
|---|---|
| A new `new CodeMieClient` call | `createClient` |
| A command file that imports another command file | Shared code in `src/lib/`. Only `src/index.ts` and `src/cli/index.ts` import the command modules |
| A network or file call in the Python package outside `plan_apply/` | Keep it offline. Resolution works only within the given `Bundle` (`resolver.py`). Platform calls go only through the `codemie_sdk` client that the caller passes to `plan_apply` |
| A Spec that imports `envelope.py` | `envelope.py` imports the specs |

## Adding a resource kind

Node.js package. Each place handles kinds explicitly:

1. Types and state: `src/types/codemieConfig.ts` and `src/lib/stateManager.ts`.
2. Import type list: `src/lib/resourceTypes.ts`.
3. Checksum: `src/lib/codemieConfigChecksums.ts`.
4. Deploy function and its place in the order: `src/deploy.ts`.
5. Preview, orphan cleanup, destroy, backup and import, with tests beside each file.

Python package:

1. Add `specs/<kind>.py` with `extra="forbid"` and `from_entity`.
2. Add the kind to `DocumentKind`, `_SPEC_BY_KIND` and the `spec` union in `envelope.py`.
3. Export it from `__init__.py` and add tests.
4. Register it in each per-kind table of `plan_apply/`: `kinds.ADAPTERS`, `lookup.LIVE_FINDERS`, `bulk_create._RESOLVED_BUILDERS`, `guards._SPEC_NAME_FIELDS`, `field_policy.FIELD_POLICIES`, and the project and reference-edge tables where they apply. `tests/plan_apply/test_kind_tables.py` lists every table and fails when one is missing.

Python datasource type (a new `type` value, not a new kind):

1. Add the Spec class with its `type` literal to the `DatasourceSpec` union in `specs/datasource.py`.
2. Add its adapter to `kinds.DATASOURCE_ADAPTERS` and its field policy to `field_policy.FIELD_POLICIES`. `test_kind_tables.py` checks that each adapter has a policy.

## Configuration

The Node.js package reads credentials from the environment through `${VAR}` in `codemie.yaml` (`iac/codemie-iac-nodejs/.env.template`). The CLI finds the project root by a walk up to `codemie.yaml`, unless `-c` or `-d` is given. `SAMPLE_DEPLOY=1` turns off orphan deletion in `deploy.ts`.

## SDK client

| Service | Used by | Through |
|---|---|---|
| CodeMie platform API and its auth server | Node.js package | `codemie-sdk` |
| `codemie_sdk` models and services | Python package. Models build a Spec; only `plan_apply/` calls the platform, through the client that the caller passes in | `codemie-sdk-python` |
| `codemie-ai/ci-workflows` | CI and release | Reusable workflows and `check_version.py` |

| Avoid | Prefer |
|---|---|
| A direct HTTP call to the platform | A `codemie-sdk` service method |
| A new client in a command | `createClient`. It adds both URLs to a failure message |
| A list call with a manual page loop | Helpers in `lib/paginationUtils.ts` |
| A name lookup per skill | `SkillNameIndex` in `lib/paginationUtils.ts` |

Error handling:

- A failed API call goes through `logApiErrorDetails` (`lib/apiErrorLogger.ts`). It reads the SDK `statusCode` first, then the Axios shape.
- A delete of a missing resource counts as success (`cleanupManager.ts`, `deploy.ts`).
- The not-found and retry checks read error message text. A new SDK error format can break them without a compile error.

### Retry

`withRetry` (`lib/rateLimitUtils.ts`) handles 429, 5xx, timeout, `ECONNRESET` and `ECONNREFUSED`, with exponential backoff from 1 second and 3 attempts (`RETRY_ATTEMPTS`, `RETRY_DELAY_MS` in `lib/constants.ts`). Today `backup.ts` uses it and `deploy.ts` does not. Before you add retry to a create call, check that a repeat cannot create a duplicate.

`createConcurrentLimiter` caps parallel requests at 5.

### Timeouts

Fetch timeouts are 30 seconds per resource type in `TIMEOUTS_MS` (`lib/constants.ts`). Apply them with `withTimeout` (`lib/timeoutUtils.ts`).

### SDK version policy

| Package | Policy | Where |
|---|---|---|
| Node.js | Range `>=0.1.0 <1.0.0` for `codemie-sdk`, no lockfile | `iac/codemie-iac-nodejs/package.json` |
| Python | Exact pin `codemie-sdk-python = "0.1.713"`, `poetry.lock` committed. The reason for the pin is unknown | `iac/codemie-iac-python/pyproject.toml` |

With the wide Node.js range, each install can get a newer SDK. CI reports the installed version (step "Report installed codemie-sdk version" in `.github/workflows/ci.yml`), and a weekly job runs all checks on the newest version in range (`.github/workflows/drift.yml`). When the SDK adds or changes a field, update `lib/converters.ts` and the checksum normalization in `lib/checksumUtils.ts`.

The Python Specs restate SDK fields with `extra="forbid"`. A change of the pinned version needs a review of each Spec.

## Release

Steps are in `docs/RELEASING.md`. Facts that code changes can break:

| Topic | Fact |
|---|---|
| Trigger | A published GitHub Release with a `cdk-v` tag starts `publish.yml` (`.github/workflows/publish.yml`, job `verify`, line 37). A merge to `main` never releases |
| Version | The tag names the version. `package.json` holds only `MAJOR.MINOR.0` |
| Pre-release | `cdk-vX.Y.Z-rcN` publishes under the npm dist-tag `rc` (`.github/workflows/publish.yml`, line 151) |
| `verify` job | Has no secrets. It checks the tag, lints, tests, builds and packs |
| `publish` job | Uses OIDC through the reusable workflow `codemie-ai/ci-workflows` `reusable-publish-npm.yml@main`. `id-token: write` is set on this job only (`.github/workflows/publish.yml`, lines 145-148) |
| Version check | `check_version.py` is downloaded from `ci-workflows@main` at run time. It is unpinned, a known exposure (`.github/workflows/publish.yml`, lines 81-84) |
| Manual dispatch | A real publish needs `dry_run` off, the word `publish` in the `publish` input, and a run from `main` |
| Python package | Not published. CI checks and builds it only (`docs/RELEASING.md`) |

## Related repositories

The platform backend, the UI, the SDK and the test harness are separate repositories. A change to a platform catalog (tool names, integration types, credential types) may also need a change in the backend or the SDK. This repository follows them; it does not drive them.
