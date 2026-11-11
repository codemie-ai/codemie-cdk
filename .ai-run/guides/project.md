# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | CodeMie CDK | `README.md` |
| Repository/package | `codemie-cdk`; packages `@codemieai/cdk` (`iac/codemie-iac-nodejs`) and `codemie-cdk-python` (`iac/codemie-iac-python`) | `iac/codemie-iac-nodejs/package.json`, `iac/codemie-iac-python/pyproject.toml` |
| Project code/key | none | user decision |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Jira for maintainers; GitHub Issues for external contributors (`Closes #N`) |
| Key/prefix | `EPMCDME-NNNNN` placeholder only. Never write a real key in this repository |

## Ticket Adapter

**Status**: configured
**Adapter**: the `codemie-jira-assistant` CodeMie assistant, for maintainers only
**Lookup**: ask the assistant for the ticket `EPMCDME-NNNNN` with summary, description, acceptance criteria and links
**Create**: send the assistant the complete story file content and ask it to create the ticket
**Output**: the ticket key in the form `EPMCDME-NNNNN`
**Comment**: ask the assistant to add a comment with the given text to the ticket `EPMCDME-NNNNN`

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | `https://github.com/codemie-ai/codemie-cdk` |
| Default target branch | `main` |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: GitHub CLI (`gh`)
**Instructions**: create the PR with `gh pr create --base main`. The PR title follows Conventional Commits and has no ticket key (`.ai-run/guides/standards/git-workflow.md`)

## Complexity Scoring

**Status**: not configured
**Field**: not configured
**Format**: not configured
