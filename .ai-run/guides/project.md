# Project

This repository holds two infrastructure-as-code packages for the CodeMie platform.

| Package | Path | Registry name | Language |
|---------|------|---------------|----------|
| Node.js CLI and library | `iac/codemie-iac-nodejs` | `@codemieai/cdk` | TypeScript, npm |
| Python IaC library | `iac/codemie-iac-python` | `codemie-iac-python` (not published) | Python 3.12, Poetry |

Each package has its own dependencies and CI job. Commands: `quality-gates.md`. Layout: `architecture.md`.

## Ticket Adapter

- Tracker: Jira.
- Tool: the `codemie-jira-assistant` CodeMie assistant.
- Ticket keys look like `EPMCDME-NNNNN`. Use only this placeholder form in files, commits, branches and PRs of this repository. Never write a real key.
- Lookup, create and comment: call the assistant with the key or the ticket payload.
- External contributors do not need Jira. They use GitHub Issues, and a PR closes its issue with `Closes #N`.

## MR Adapter

- Host: GitHub, organisation `codemie-ai`, repository `codemie-cdk`, default branch `main`.
- Create a pull request with `gh pr create --base main`.
- The PR title follows Conventional Commits. See `git-workflow.md`.

## Non-goals

The monorepo `evaluation/`, `examples/`, `qa-factory` and `docs` content is out of scope for these guides.

## Related repositories

The platform backend, the UI, the SDK and the test harness are separate repositories. A change to a platform catalog (tool names, integration types, credential types) may also need a change in the backend or the SDK. This repository follows them; it does not drive them.
