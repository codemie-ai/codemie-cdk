# Contributing

Contributions are welcome. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before you start.

This repository contains two packages, each in its own folder under `iac/`:

- `iac/codemie-iac-nodejs`: `@codemieai/cdk` (TypeScript, Node.js 22)
- `iac/codemie-iac-python`: `codemie-cdk-python` (Python 3.12)

## How to Contribute

1. Fork `codemie-ai/codemie-cdk` on GitHub.
2. Clone your fork and create a branch: `git checkout -b my-feature-branch`.
3. Make your change and add or update tests.
4. Run the checks (see below).
5. Push the branch to your fork and open a pull request against `main`.

## Pull Requests

- The PR title must follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<optional scope>): <description>`, for example `feat(deploy): add dry-run summary` or `fix(import): handle empty response`.
- Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- Keep a PR focused on one change. Describe what changed and why.
- Individual commit messages are not checked.

## Review Rule

Every PR needs one approval from any collaborator with write access before it can be merged. All CI checks must pass.

## Local Checks

Run the checks in the folder of the package you changed.

Node.js package. It has no lockfile, so install the dependencies fresh:

```bash
cd iac/codemie-iac-nodejs
npm install
npm run lint
npm test
npm run build
```

Python package:

```bash
cd iac/codemie-iac-python
poetry install
poetry run ruff check .
poetry run ruff format --check .
poetry run pytest tests/
```

CI runs the same steps (Node.js 22 and the Python on the runner).

## Internal References and Secrets

CI scans the tree for internal references and for secrets. Do not commit credentials, private hostnames, ticket keys, or personal e-mail addresses. Use placeholders such as `https://codemie.example.com` in examples and tests.

## Reporting Issues

Use GitHub Issues for bugs and feature requests. For security problems, follow [SECURITY.md](SECURITY.md).
