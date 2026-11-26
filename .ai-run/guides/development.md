# Development

Commands are in `.ai-run/guides/quality-gates.md`. Lint and format rules are in `.ai-run/guides/standards/code-quality.md`.

## Naming

| Item | Node.js | Python |
|---|---|---|
| Module file | `camelCase.ts`, such as `lib/stateManager.ts` | `snake_case.py`, such as `serializer.py` |
| Class | `PascalCase` (`StateManager`) | `PascalCase`, `Spec` suffix for resources (`AssistantSpec`) |
| Constants | `UPPER_SNAKE` groups `as const` (`lib/constants.ts`) | `_UPPER_SNAKE` for module-private (`credentials.py`) |

Keep a command in its own file with a core function and a `main` wrapper (see `destroy.ts`).

Node.js import order: `node:` built-ins, a blank line, third-party packages, a blank line, then relative imports. Biome requires the `node:` prefix.

## Error handling

### Node.js

| Avoid | Prefer |
|---|---|
| A message with no context | Name the resource or the endpoints, and include the cause (`createClient` in `lib/clientFactory.ts`) |
| A silent continue after a per-resource failure | Count the failure, go on, and throw at the end (`deploy.ts`) |
| `process.exit` in core logic | Throw. Only the `main` wrapper exits (`destroy.ts`). `runCommandWithSpinner` (`lib/commandSpinner.ts`) intercepts the exit |
| A custom error parser for API errors | `logApiErrorDetails` (`lib/apiErrorLogger.ts`) |

The package uses plain `Error` with a clear message and has no custom error classes.

### Python

| Avoid | Prefer |
|---|---|
| A third-party exception that reaches the caller | A domain error such as `DocumentParseError` (`serializer.py`) |
| A raw `TypeError` or `AttributeError` on bad input | Guard the input, and let pydantic report the field (`envelope.py`) |
| A field that is dropped quietly | `extra="forbid"` on each model |

## Logging

| Avoid | Prefer |
|---|---|
| `console.log` | `logger` (`lib/logger.ts`). Biome forbids console use |
| A write that breaks the spinner | The logger pauses the spinner |
| A secret in a message | Log names and ids only |

A `biome-ignore` comment states its reason.

## Async

| Need | Use |
|---|---|
| Limit parallel calls | `createConcurrentLimiter` (default 5, `lib/rateLimitUtils.ts`) |
| Timeout on a fetch | `withTimeout` with a `TIMEOUTS_MS` value (`lib/timeoutUtils.ts`) |
| Retry on 429, 5xx, timeout | `withRetry` (`lib/rateLimitUtils.ts`) |

`useAwait` is an error in TypeScript files. An `async` function must contain `await`.

## Configuration

- Use `AppConfig` for all paths. Do not hard-code `codemie.yaml` or `.codemie/state.json`.
- `${VAR}` with no default and no value fails the load, with the config path in the error. There is no escape syntax (`iac/codemie-iac-nodejs/README.md`).
- Variables for the platform are in `iac/codemie-iac-nodejs/.env.template`.

## Dependencies

| Package | Rule | Where |
|---|---|---|
| Node.js | No lockfile. Do not add one | `CONTRIBUTING.md`, `.github/workflows/ci.yml` |
| Node.js | `codemie-sdk` uses a range, so a new SDK can break the build. A weekly job checks this | `package.json`, `.github/workflows/drift.yml` |
| Node.js | `zod` and `@biomejs/biome` use exact versions | `package.json` |
| Python | `codemie-sdk-python` uses an exact version and `poetry.lock` is committed | `pyproject.toml` |

## Testing

No test needs a platform, and there is no end-to-end suite in this repository.

| Package | Location | Name |
|---|---|---|
| Node.js | Beside the source file | `<module>.test.ts` (`testMatch` in `jest.config.ts`) |
| Python | `tests/` for documents and Specs; `tests/plan_apply/` for the plan and apply engine | `test_<area>.py` |

Coverage excludes `src/cli/**`, so test behaviour through the command modules.

### Jest

| Setting | Effect |
|---|---|
| `resetMocks`, `restoreMocks` | Mock setup is cleared before each test. Set return values in `beforeEach` or in the test, not at module level |
| `@swc/jest` transform | Tests do not type-check. Run the type check as well |
| `ora` mapped to a mock | Spinner output is inert in tests (`src/test/oraMock.ts`) |
| `.js` suffix stripped | Relative imports resolve to `.ts` |

| Avoid | Prefer |
|---|---|
| A real `CodeMieClient` | `jest.mock('./lib/clientFactory')` and an in-memory client (`deploy.test.ts`) |
| A mock of `fs` for state and config behaviour | A real temp dir from `fs.mkdtempSync` (`destroy.test.ts`) |
| A real `process.exit` | Replace it with `jest.fn()` and restore it after |
| A hand-written assistant or skill object | `createMockAssistant`, `createMockSkill` (`src/testFixtures.ts`) |

### pytest

| Avoid | Prefer |
|---|---|
| A test that depends on the network | Build the document in the test. For `plan_apply`, use the recording fakes of the SDK services (`FakeClient` in `tests/plan_apply/fakes.py`). Everything works offline |
| Assert on a field only | Test the round trip and byte stability (`tests/test_serializer.py`) |
| A shared global between tests that use credential refs | Call `reset_registry` for a clean collision registry (`credentials.py`) |

Fixtures are local to the test module, except in `tests/plan_apply/`: `conftest.py`, and the shared modules `fakes.py`, `helpers.py` and `write_helpers.py`. Regression tests for review findings keep the finding id in the test name (`tests/test_review_fixes.py`).

### Coverage

The global Node.js threshold is 50% for branches, functions, lines and statements (`jest.config.ts`). It applies only to the coverage scripts, and CI runs the plain test script, so CI does not enforce it. The Python package has no threshold.

### Writing a test

1. Add a failure case and a success case. For a change to deploy, check the state file and the client calls.
2. For a destructive path, test the guard, for example the deploy refusal without `--yes-replace-skills`.
3. For a config change, test the order of the loader steps (`lib/codemieConfigLoader.test.ts`).
4. For a checksum change, confirm that a config with equal meaning keeps the same hash (`lib/checksumUtils.test.ts`). A changed hash marks a resource as changed on the next deploy.
5. For a Python Spec change, test an unknown field and the `from_entity` path (`tests/test_specs_simple.py`).
6. Use placeholders such as `https://codemie.example.com` in fixtures.

### Test problems

| Problem | Cause | Fix |
|---|---|---|
| A mock returns `undefined` | `resetMocks` cleared it | Move the setup into `beforeEach` |
| No log output from the code under test | The test script uses `--silent` | Run Jest on that file without the flag |
| Tests pass with zero tests run | `--passWithNoTests` | Check the path filter |
| An ESM dependency fails to parse | Not in the transform allow-list | Add it to `transformIgnorePatterns` in `jest.config.ts` |

## Documentation that is out of date

Do not use these statements as instructions. Check the code.

| Statement | Fact |
|---|---|
| Scripts `validate`, `preview`, `deploy`, `destroy`, `backup` (Node.js README) | No scripts with these names. The commands exist in the CLI (`src/cli/index.ts`) |
| A `compile` script and prompt compilation (Node.js README) | No such script and no compile module in `src/` |
| A `type-check` script (Node.js README) | The script is `types:check` |
| GitLab CI examples (Node.js README) | They describe a consumer pipeline. This repository uses GitHub Actions |

## Don't do

- Do not edit `dist/`. `tsup` generates it.
- Do not change `version` in `package.json` for a patch release. The tag sets it (`docs/RELEASING.md`, "How versions work").
- Do not call the platform from the Python package outside `plan_apply/`.
