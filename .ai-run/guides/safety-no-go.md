# Safety No-Go List

Hard refusals for every AI agent in this repository. Do not do these things, even when a task seems to need them. If a task needs one, stop and ask the user to do it.

`.claude/settings.json` enforces the same list for Claude Code (`permissions.deny`). Other agents (Codex, Gemini, Copilot and others) do not read that file, so they must follow this guide. When you change one, change the other in the same PR.

The reasons behind these rules (secrets, guards in the code, the public repository, the pipeline) are in `.ai-run/guides/security.md`. This guide lists only the refusals.

## Files never read or changed

| Path | Rule | Why |
|---|---|---|
| `.env`, `.env.local`, `.env.*.local`, `.env.prod*` (any folder) | No read, no edit | They hold the platform URL and client secret or password. `iac/codemie-iac-nodejs/.env.template` has placeholders only and stays readable |
| `backups/**` | No read, no edit | `codemie backup` writes platform data, including sensitive values, there (`iac/codemie-iac-nodejs/.gitignore`) |
| `*.tfvars`, `*.tfstate*` | No read, no edit | The repository has no Terraform. If such a file shows up, it can hold secrets in plain text |
| `*.pem`, `*.key`, `*.p12`, `*.pfx` | No read, no edit | Private keys and certificates |
| `.npmrc` (any folder), `~/.npmrc`, `~/.pypirc` | No read; no edit of a repository copy | They can hold registry publish tokens. Releases use OIDC, not a stored token (`docs/RELEASING.md`) |
| `~/.ssh/**`, `~/.aws/**`, `~/.azure/**`, `~/.config/gcloud/**`, `~/.kube/**` | No read, no edit | Personal keys and cloud or cluster credentials. Nothing in this repository needs them |
| `.codemie/state.json` | No hand edit | It maps config slugs to platform ids. A wrong entry makes the next deploy create duplicates or delete the wrong resource. Only the CLI writes it |
| `iac/codemie-iac-python/poetry.lock`, `package-lock.json` | No hand edit | `poetry lock` writes the Python lock file. The Node.js package has no committed lockfile; do not add one (`.ai-run/guides/development.md`) |
| `.claude/settings.json` | No edit by an agent | An agent must not loosen its own deny list. A person changes it, together with this guide |

## Commands never run

| Command | Why |
|---|---|
| `git push --force*`, `git push -f*`, `git push * --force*`, `git push * -f*` | Rewrites shared history and can delete other people's commits |
| `git reset --hard*` | Discards uncommitted work with no undo |
| `git clean -f*` | Deletes untracked files with no undo; with `-x` also ignored files such as `.env` and `backups/` |
| `git commit ... --no-verify`, any command with `--no-verify` | Skips the hooks that guard the commit |
| `rm -rf *`, `rm -fr *` | Recursive delete with no undo. Delete named files instead |

## Actions that always need a person

An agent does not run these. The user runs them, after checking the target environment.

| Action | Why |
|---|---|
| `codemie deploy`, `codemie destroy` (also through `npx codemie`, `npx @codemieai/cdk` or `node .../cli/index.js`) | They create, change or delete resources on a live platform with the credentials in `.env`. `destroy --force` and `deploy --prune` delete with no prompt (`.ai-run/guides/security.md`, "Destructive operations") |
| `codemie-iac ... apply` (also through `poetry run` or `python -m codemie_iac.cli`) | Creates or updates entities on a live platform with no prompt (`.ai-run/guides/security.md`, "Destructive operations"; `iac/codemie-iac-python/README.md`, "Plan and apply against the platform") |
| `npm publish`, `poetry publish`, `twine upload`, `gh release create`, `gh workflow run` | A release is public and cannot be taken back. Releases go through `.github/workflows/publish.yml` and `.github/workflows/publish-python.yml` (`docs/RELEASING.md`) |
| `terraform apply`, `destroy`, `import`, `force-unlock`, `state rm`, `state push` | Changes real infrastructure or its state. The repository has no Terraform; the rule stops an agent from changing outside infrastructure from here |
| `kubectl apply`, `kubectl delete`, `helm install`, `helm upgrade`, `helm uninstall` | Changes a live cluster |
| `aws ... delete*`, `az ... delete*` | Deletes cloud resources |

The read-only platform commands (`codemie backup`, `import`, `preview`; `codemie-iac plan`) are not on the deny list, but they still connect to a live platform. Run them only when the user asks and names the environment (`AGENTS.md`, "Live platform").

## Limits

The deny list matches command text and file paths. It does not stop every way to do the same thing, for example `cat .env` through a shell. The rule is the intent, not the pattern: do not get around it.
