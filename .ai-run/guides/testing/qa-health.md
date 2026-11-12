# QA Health

**Last assessed**: 2026-11-12
**Coverage**: Node.js 88.8% lines, 80.5% branches; Python 98% statements. High for unit tests, none for live-platform behaviour.

Figures come from a local run on 2026-11-12: `npx jest --silent --coverage` in `iac/codemie-iac-nodejs` (44 suites, 1031 tests passed) and `poetry run pytest tests/ --cov=codemie_iac` in `iac/codemie-iac-python` (841 tests passed, 1 skipped). CI does not publish coverage, so re-run these commands for current numbers.

## Coverage Summary

| Module / area | Coverage | Notes |
|---|---|---|
| Node.js, all of `src/` (measured files) | 88.8% lines, 80.5% branches, 93.5% functions | `src/cli/**` and test files are excluded (`collectCoverageFrom` in `iac/codemie-iac-nodejs/jest.config.ts`) |
| Node.js `src/cli/index.ts` | not measured | Command wiring only; behaviour is tested through the command modules |
| Node.js `src/deploy.ts` | 85.4% lines, 74.5% branches | Largest module; guards are tested (`deploy --replace-skill-group` in `src/deploy.test.ts`) |
| Node.js `src/lib/**` | mostly above 89% lines | Lower files are listed below |
| Python `src/codemie_iac/**` | 98% statements (2482 statements, 40 missed) | Branch coverage not measured |
| Python `src/codemie_iac/cli/__main__.py` | 0% | Five-line entry point; `cli/main.py` is at 100% |

## Risky Untested Areas

Modules with low coverage that carry logic:

| Path | Coverage | Risk reason |
|---|---|---|
| `iac/codemie-iac-nodejs/src/destroy.ts` | 85.1% lines, 60.9% branches | Deletes every managed resource on the platform; four in ten branches are not run |
| `iac/codemie-iac-nodejs/src/lib/cleanupManager.ts` | 75.8% lines, 70.4% branches | Deletes resources on the platform; used by `deploy.ts`, `destroy.ts` and `preview.ts`, and decides what counts as "not found" |
| `iac/codemie-iac-nodejs/src/backup.ts` | 80.3% lines, 49.5% branches | Writes backups with sensitive data; half the branches are not run |
| `iac/codemie-iac-nodejs/src/lib/backupTransaction.ts` | 80.0% lines, 67.6% branches | Tracks and resumes a partial backup (`transaction.json`) |
| `iac/codemie-iac-nodejs/src/preview.ts` | 80.2% lines, 64.3% branches | Shows what deploy will change; a wrong preview hides a destructive change |
| `iac/codemie-iac-nodejs/src/validate.ts` | 47.4% lines, 45.7% branches | Command module; the rules themselves are in `src/lib/validationUtils.ts`, which has its own tests |
| `iac/codemie-iac-nodejs/src/lib/commandSpinner.ts` | 69.6% lines, 49.2% branches | Output only; low risk |

## Known Test Debt

- No end-to-end or contract test against a real CodeMie platform. A change in platform API behaviour shows up only in a manual run (`.ai-run/guides/development.md`, "Testing").
- The Node.js coverage threshold (50%, `coverageThreshold` in `jest.config.ts`) is not enforced: CI runs `npm test`, not `npm run test:ci` (job `test`, step "Unit tests" in `.github/workflows/ci.yml`).
- The Python package has no coverage threshold and no type checker in CI (`.ai-run/guides/quality-gates.md`).
- `npm test` uses `--passWithNoTests` (the `test` script in `iac/codemie-iac-nodejs/package.json`), so a run with zero tests is green.
- The Node.js package has no lockfile. Every CI run resolves dependencies fresh; the weekly `.github/workflows/drift.yml` job checks the newest `codemie-sdk` in range.
- `@swc/jest` does not type-check tests; only `npx tsc --noEmit` catches type errors in test files.

## Recent Test Activity

Most recently added or modified test files (`git log --diff-filter=AM -n 5 --name-only`):

- `iac/codemie-iac-python/tests/cli/test_apply_command.py`
- `iac/codemie-iac-python/tests/cli/test_complexity.py`
- `iac/codemie-iac-python/tests/cli/test_default_project.py`
- `iac/codemie-iac-python/tests/cli/test_env_file.py`
- `iac/codemie-iac-python/tests/cli/test_exit_codes.py`
