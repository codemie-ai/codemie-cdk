# AGENTS.md

Primary AI entrypoint for `codemie-cdk`. Load the relevant `.ai-run/guides/` file before changing code.

## Guide Imports

| Category | Guide Path | Purpose |
|---|---|---|
| Project | .ai-run/guides/project.md | Identity, tracker, source control, ticket and PR adapters |
| Architecture | .ai-run/guides/architecture.md | The two packages, deploy flow, SDK client, retry, release facts |
| Development | .ai-run/guides/development.md | Errors, logging, async, dependencies, Jest and pytest patterns |
| Security | .ai-run/guides/security.md | Secrets, destructive commands, public repository rules, pipeline |
| Quality gates | .ai-run/guides/quality-gates.md | Exact lint, type, test and build commands per package |
| Code quality | .ai-run/guides/standards/code-quality.md | Biome and ruff rules, type rules, licence headers |
| Git workflow | .ai-run/guides/standards/git-workflow.md | Branches, commits, pull requests |

## Task Classifier

| Category | User Intent | Example Requests | P0 Guide | P1 Guide |
|---|---|---|---|---|
| CLI / deploy logic | Change a command or the deploy flow | "add a deploy flag", "fix import of skills" | .ai-run/guides/architecture.md | .ai-run/guides/development.md |
| New resource kind | Add a resource type or field | "support a new resource" | .ai-run/guides/architecture.md | .ai-run/guides/development.md |
| Python documents | Change Specs or YAML round trip | "add a field to AssistantSpec" | .ai-run/guides/architecture.md | .ai-run/guides/standards/code-quality.md |
| SDK / platform calls | Change client use, retry or timeouts | "SDK update broke the build" | .ai-run/guides/architecture.md | .ai-run/guides/development.md |
| Tests | Write or fix tests | "add tests for prune" | .ai-run/guides/development.md | .ai-run/guides/quality-gates.md |
| Security | Secrets, guards, CI hardening | "handle this credential" | .ai-run/guides/security.md | .ai-run/guides/standards/git-workflow.md |
| CI / release | Workflows and publishing | "change the publish job" | .ai-run/guides/quality-gates.md | .ai-run/guides/security.md |
| Review workflow | Branch, commit, PR | "open a PR" | .ai-run/guides/standards/git-workflow.md | .ai-run/guides/project.md |

## Critical Rules

| Rule | Trigger | Action |
|---|---|---|
| Check Guides First | ANY task | Match request to category and load the P0 guide before searching broadly |
| Testing | "write tests" / "run tests" | Only write or run tests when requested or when needed for verification |
| Git Operations | "commit" / "push" / "PR" | Only then; load `.ai-run/guides/standards/git-workflow.md` |
| Shell | ANY shell command | Use bash/Linux-compatible syntax |
| Live platform | Any `codemie` command that connects to a platform | Do not run it unless the user asks; load `.ai-run/guides/security.md` |
| Public repository | Any content that goes into the tree, a commit or a PR | Load the content rules in `.ai-run/guides/standards/git-workflow.md` first |
| Scope | Any change | Find the package first; the two packages have separate gates and rules |

## Commands

| Need | Source Guide | Source Evidence | Notes |
|---|---|---|---|
| Lint / format / types | .ai-run/guides/quality-gates.md | iac/codemie-iac-nodejs/package.json, .github/workflows/ci.yml | Load guide before running |
| Tests | .ai-run/guides/quality-gates.md | CONTRIBUTING.md, .github/workflows/ci.yml | Load guide before running |
| Build | .ai-run/guides/quality-gates.md | iac/codemie-iac-nodejs/package.json, .github/workflows/ci.yml | Load guide before running |
| Git / review workflow | .ai-run/guides/standards/git-workflow.md | CONTRIBUTING.md | Load guide before git operations |
| Release | docs/RELEASING.md | .github/workflows/publish.yml | Only on explicit request |
