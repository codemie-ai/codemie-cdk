# QA Strategy

**Last assessed**: 2026-11-09

The repository has two packages under `iac/`, and each has its own test suite. All tests are offline unit tests: no test connects to a CodeMie platform, and there is no end-to-end suite. The exact gate commands are in `.ai-run/guides/quality-gates.md`. The test patterns are in `.ai-run/guides/development.md` ("Testing").

## Test Frameworks

| Framework | Type | Config file | Test directories |
|---|---|---|---|
| Jest 30 with the `@swc/jest` transform | unit | `iac/codemie-iac-nodejs/jest.config.ts` | `iac/codemie-iac-nodejs/src/**` (beside the source file) |
| pytest with `pytest-cov` | unit | `iac/codemie-iac-python/pyproject.toml` (no `[tool.pytest]` section, defaults apply) | `iac/codemie-iac-python/tests/`, `iac/codemie-iac-python/tests/cli/`, `iac/codemie-iac-python/tests/plan_apply/` |

Counts on 2026-11-09: Jest 42 suites, 998 tests. pytest 801 tests.

## Test Types in Use

### Unit Tests

Node.js package (`@codemieai/cdk`):

- **Location**: `iac/codemie-iac-nodejs/src/**/*.test.ts`, beside the module under test
- **Pattern**: `<module>.test.ts` (`testMatch` at `iac/codemie-iac-nodejs/jest.config.ts:25`)
- **Run command**: `npm test` in `iac/codemie-iac-nodejs` (CI: `.github/workflows/ci.yml:95`)
- **Example**: `iac/codemie-iac-nodejs/src/deploy.test.ts:2860` (the `--replace-skill-group` guard: no client call and no state change without `--yes-replace-skills`)

Python package (`codemie-iac-python`):

- **Location**: `iac/codemie-iac-python/tests/`
- **Pattern**: `test_<area>.py`, functions `test_<behaviour>`
- **Run command**: `poetry run pytest tests/` in `iac/codemie-iac-python` (CI: `.github/workflows/ci.yml:149`)
- **Example**: `iac/codemie-iac-python/tests/test_serializer.py:40` (YAML output is byte-identical across calls)

### Integration Tests

- **Location**: none detected. The closest layer is `iac/codemie-iac-python/tests/plan_apply/`, which runs the plan and apply engine against recording fakes of the SDK services (`FakeClient` at `iac/codemie-iac-python/tests/plan_apply/fakes.py:261`). In the Node.js package, the command modules run against a mocked client factory (`jest.mock('./lib/clientFactory')` at `iac/codemie-iac-nodejs/src/deploy.test.ts:28`) and a real temp dir.
- **Pattern**: n/a
- **Run command**: n/a. These tests run with the unit test commands above.

### End-to-End Tests

- **Location**: none detected
- **Tool**: none detected
- **Run command**: n/a. The commands that connect to a platform (`codemie-cdk deploy`, `destroy`, `backup`, `import`, `preview`; `codemie-iac plan`, `apply`) are not run in CI and are not a verification step for agents (`.ai-run/guides/quality-gates.md`, `.ai-run/guides/safety-no-go.md`).

## Coverage Targets

- **Line coverage target**: Node.js 50% global (`iac/codemie-iac-nodejs/jest.config.ts:28-35`). It applies only to `npm run test:ci` and `npm run test:coverage`. CI runs `npm test`, so CI does not enforce it. Python: not configured.
- **Branch coverage target**: Node.js 50% global, same limits as above. Python: not configured.
- **Coverage command**: Node.js `npm run test:coverage` (excludes `src/cli/**` and test files, `jest.config.ts:11`). Python `poetry run pytest tests/ --cov=codemie_iac` (`pytest-cov` is a dev dependency, `pyproject.toml:18`; no script or CI step).

## What a change must include

| Change | Required verification |
|---|---|
| Node.js source | A test beside the module, then `npm run lint`, `npm test` (read the test count) and `npm run build` |
| Python source | A test in `tests/` (or `tests/plan_apply/` for the engine), then `ruff check`, `ruff format --check`, `pytest tests/` and `poetry build` |
| A destructive path (prune, destroy, skill group replace, apply) | A test that the guard refuses before the first platform call (`iac/codemie-iac-nodejs/src/deploy.test.ts:2860`) |
| A secret path | A test that the value does not reach output or errors (`iac/codemie-iac-python/tests/cli/test_secret_leak.py:44`) |
| Docs or workflows only | The CI-only gates (PR title, internal references, secrets detection) and a manual search of the diff for credentials, private hostnames and ticket keys |

Run only the gates of the package you changed. A live platform run is a manual step for a person, not a gate.

## Conventions

- **Test file naming**: Node.js `<module>.test.ts`; Python `test_<area>.py`
- **Test file location**: Node.js co-located with source; Python in a `tests/` directory
- **Test style**: Node.js `describe`/`it` (`iac/codemie-iac-nodejs/src/validate.test.ts:46`); Python plain `test_*` functions with pytest fixtures (`iac/codemie-iac-python/tests/plan_apply/conftest.py:13`)
- **Source docs scanned**: `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `iac/codemie-iac-nodejs/README.md`, `iac/codemie-iac-python/README.md`, `.ai-run/guides/*.md`. No skills or selector conventions (no UI)
- **Naming / selector conventions (from docs)**:
  - Regression tests for review findings keep the finding id in the test name (`iac/codemie-iac-python/tests/test_review_fixes.py:45`)
  - Use placeholders such as `https://codemie.example.com` in fixtures (`CONTRIBUTING.md`, `.ai-run/guides/development.md`)
- **Architecture notes (from docs)**:
  - Two independent packages with separate gates; no root manifest (`.ai-run/guides/quality-gates.md`)
  - Node.js coverage excludes `src/cli/**`, so test behaviour through the command modules (`jest.config.ts:11`)
- **Testing guidance (from docs)**:
  - `resetMocks` and `restoreMocks` are on (`jest.config.ts:26-27`): set mock return values in `beforeEach` or in the test
  - `@swc/jest` does not type-check, so also run `npx tsc --noEmit`
  - Build mock entities with `createMockAssistant` and `createMockSkill` (`iac/codemie-iac-nodejs/src/testFixtures.ts:13`, `:38`)
  - For a checksum change, check that a config with equal meaning keeps the same hash (`iac/codemie-iac-nodejs/src/lib/checksumUtils.test.ts:52`)

## Anti-Patterns (observed in this codebase)

| Bad | Better | Why |
|---|---|---|
| Trust a green `npm test` without the count | Read the `Tests:` line | The script uses `--passWithNoTests` (`iac/codemie-iac-nodejs/package.json:46`), so a wrong path filter passes with zero tests |
| A mock return value set at module level | Set it in `beforeEach` | `resetMocks: true` clears it before each test (`jest.config.ts:27`) |
| A real `CodeMieClient` in a test | `jest.mock('./lib/clientFactory')` (`src/deploy.test.ts:28`) | A real client connects to a platform |
| A mock of `fs` for state behaviour | A real temp dir from `fs.mkdtempSync` (`src/deploy.test.ts:89`) | The state file and config are read back as on disk |
| A Python test that calls the network | `FakeClient` (`tests/plan_apply/fakes.py:261`) | The suite must work offline |

## Code Repositories

Application/feature source repositories that will be tested (not test-only repos). Recorded for
qa-e2e-generator to search merge requests/commits by ticket ID — not scanned for conventions.

- **codemie-cdk**: https://github.com/codemie-ai/codemie-cdk

## External Sources

### Test Case Management

- **System**: none. Bugs and feature requests go to GitHub Issues (`CONTRIBUTING.md`); test cases are not kept outside the code.
- **Adapter**: not available

> **No MCP adapter detected** for a test case system. Test cases live only as automated tests in this repository.

### QA Documentation

- **System**: within repo
- **Adapter**: not configured
- **Paths**: `.ai-run/guides/testing/qa-strategy.md`, `.ai-run/guides/testing/qa-health.md`, `.ai-run/guides/development.md` ("Testing"), `.ai-run/guides/quality-gates.md`

### External Test Repositories

none
