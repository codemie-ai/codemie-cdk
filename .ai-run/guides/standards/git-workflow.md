# Git workflow

Sources: `CONTRIBUTING.md`, `docs/RELEASING.md`, `.github/workflows/pr-title-lint.yml`. The repository is public, so most rules below keep internal data out of it.

## Branches

- Branch from `main`.
- Name: `<type>/<short-description>`, for example `feat/dry-run-summary` or `docs/cdk-agent-guides`.
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- No ticket key in the branch name.
- External contributors work from a fork (`CONTRIBUTING.md`, "How to Contribute").

## Commits and PR title

- Use Conventional Commits: `<type>(<optional scope>): <description>`, for example `fix(import): handle empty response`.
- CI checks the PR title only (`.github/workflows/pr-title-lint.yml`). Commit messages are not checked, but follow the same format.
- No ticket key in a commit message, PR title or PR body. External contributors link their GitHub issue with `Closes #N`.
- One focused change per PR. Say what changed and why.
- A PR needs one approval from a collaborator with write access and green CI.

## Content rules

No credentials, private hostnames, ticket keys or personal e-mail addresses in the tree, a commit or a PR. Use placeholders such as `https://codemie.example.com`. The "Internal references" CI job scans the tree (`CONTRIBUTING.md`, "Internal References and Secrets").

## Merge strategy

Squash merge: the PR title becomes the commit subject on `main`, with a `(#N)` suffix. The repository settings allow squash and rebase and do not allow merge commits (`allow_merge_commit=false`, `squash_merge_commit_title=PR_TITLE`), and the history of `main` is all squash commits. The PR title is therefore the only message that reaches `main`, so it must follow Conventional Commits. A merge to `main` never releases anything.

## Releases

Follow `docs/RELEASING.md`. This guide does not restate the steps.

## Internal sync

The internal sync is stopped. The guides in `.ai-run/guides` are edited in this repository, and no other copy is the source of truth. The `.internal-sync` file is a leftover; do not edit it.

## Anti-patterns

| Avoid | Use |
|---|---|
| A ticket key as PR title prefix | `fix(import): handle empty response` |
| `fixed stuff` as a PR title | `<type>(<scope>): <description>` with an allowed type |
| A tracker URL or an internal hostname in code, docs or a test | `https://codemie.example.com` |
| A version change in a release PR for a patch release | The tag names the version. Change `package.json` only for a new `MAJOR.MINOR` line (`docs/RELEASING.md`, "How versions work") |
| `git add -A` after a local install | Stage named files. Do not stage `package-lock.json` |

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `PR Title` check fails | The title does not match Conventional Commits | Edit the title. The check runs again on `edited` |
| `Internal references` check fails | The tree has an internal reference | Replace it with a placeholder |
| `Security` check fails on a false positive | A value looks like a secret | Read `.gitleaks.toml` for the stopwords, and ask a maintainer before you add one |
| `package-lock.json` is untracked after a local install | The package keeps no lockfile, and it has no ignore rule | Do not commit it. Delete it, or leave it unstaged |
| `dist/`, `__pycache__/` or a virtualenv is untracked under `iac/codemie-iac-python` | The root `.gitignore` covers agent state only. The Node.js package has its own `.gitignore` | Do not stage these paths |
