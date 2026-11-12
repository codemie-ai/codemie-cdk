# Safety No-Go List

Hard refusals for every AI agent in this repository, Claude Code included. Do not do these things, even when a task seems to need them. If a task needs one, stop and ask the user to do it.

`.claude/settings.json` blocks the usual spellings of this list in Claude Code: "Files never read or changed" and "Commands never run" are in `permissions.deny`, and "Actions that always need a person" are in `permissions.ask`, so the user confirms each one. The file is a guard, not a security boundary: a shell glob, a script, a subprocess or another spelling can get past it (see "Limits"). Other agents (Codex, Gemini, Copilot and others) do not read that file. All agents must follow this guide. When you change one, change the other in the same PR.

The reasons behind these rules (secrets, guards in the code, the public repository, the pipeline) are in `.ai-run/guides/security.md`. This guide lists only the refusals.

## Files never read or changed

| Path | Rule | Why |
|---|---|---|
| `.env`, `.env.local`, `.env.*.local`, `.env.prod*`, `.env.dev*`, `.env.stag*`, `.env.uat*`, `.env.qa*`, `.env.test*`, `*.env` (any folder) | No read, no edit | They hold the platform URL and client secret or password. Any file passed to `codemie-iac --env-file` is an env file, whatever its name (`iac/codemie-iac-python/README.md`). `.env.template` and `.env.example` have placeholders only and stay readable |
| `backups/**` | No read, no edit | `codemie-cdk backup` writes platform data, including sensitive values, there (`iac/codemie-iac-nodejs/.gitignore`) |
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
| `git push --force`, `git push -f`, `git push <remote> +<branch>` (also with `git -C <dir>`) | Rewrites shared history and can delete other people's commits. `--force-with-lease` on your own feature branch is in "Actions that always need a person" |
| `git reset --hard` (flag in any position, also with `git -C <dir>`) | Discards uncommitted work with no undo |
| `git clean` (any form, the dry run `-n` too) | Deletes untracked files with no undo; with `-x` also ignored files such as `.env` and `backups/` |
| `git commit ... --no-verify`, any command with `--no-verify` | Skips the hooks that guard the commit |

## Actions that always need a person

An agent does not run these on its own. The user runs them, or confirms each one after checking the target environment. Claude Code asks before each one (`permissions.ask`).

| Action | Why |
|---|---|
| `codemie-cdk deploy`, `codemie-cdk destroy`, in any spelling: `npx`, `npm exec`, a path to the binary, `node .../cli/index.js`, `tsx src/cli/index.ts` | They create, change or delete resources on a live platform with the credentials in `.env`. `destroy --force` and `deploy --prune` delete with no prompt (`.ai-run/guides/security.md`, "Destructive operations") |
| `codemie-iac ... apply`, in any spelling: `poetry run`, a path to the binary, `python -m codemie_iac.cli` | Creates or updates entities on a live platform with no prompt (`.ai-run/guides/security.md`, "Destructive operations"; `iac/codemie-iac-python/README.md`, "Plan and apply against the platform") |
| `npm publish`, `poetry publish`, `twine upload`, `gh release create`, `gh workflow run` | A release is public and cannot be taken back. Releases go through `.github/workflows/publish.yml` and `.github/workflows/publish-python.yml` (`docs/RELEASING.md`) |
| `terraform apply`, `destroy`, `import`, `force-unlock`, `state rm`, `state push` | Changes real infrastructure or its state. The repository has no Terraform; the rule stops an agent from changing outside infrastructure from here |
| `kubectl apply`, `kubectl delete`, `helm install`, `helm upgrade`, `helm uninstall` | Changes a live cluster |
| `aws ... delete*`, `az ... delete*` | Deletes cloud resources |
| `git push --force-with-lease` | Allowed only on your own feature branch, after the user confirms. Never on `main` |
| `rm -r`, `rm -R`, `rm --recursive` (any flag order) | Recursive delete with no undo. Delete named files instead |
| An edit of `.github/workflows/**` or `.gitleaks.toml` | Changes the pipeline or the secrets scan for every contributor (`.ai-run/guides/security.md`) |

The read-only platform commands (`codemie-cdk backup`, `import`, `preview`; `codemie-iac plan`) are not on the deny list, but they still connect to a live platform. Run them only when the user asks and names the environment (`AGENTS.md`, "Live platform").

## Limits

`.claude/settings.json` matches command text and file paths. It does not stop every way to do the same thing. The rule is the intent, not the pattern: do not get around it. Known gaps:

- A Bash rule matches the whole command text, and the part before the first `*` is literal. Only the spellings in the file are matched. Other spellings, for example `rm -vrf`, an alias, a shell function, a script or a subprocess, are not. A command that matches no rule still goes to the normal permission prompt, but it runs with no prompt in `bypassPermissions` mode or under a broad allow rule such as `Bash(npx *)`.
- Claude Code loads the project `.claude/settings.json` only when the session starts at the repository root. A session started in `iac/<package>` has no deny list and no ask list from this file. Start Claude Code at the root.
- The path rules are anchored to the repository root (`/**/...`), so a `cd` into a package does not change them. Do not change them to `**/...`: that form is relative to the current folder.
- Do not add a `!` exception (for example `Read(!/**/.env.example)`) to a root-anchored rule. Claude Code ignores it, and the rule blocks the excepted file too. List the blocked names instead of a broad `.env.*`.
- A PreToolUse hook that reads the command tokens is a stronger check. It is a possible follow-up.
