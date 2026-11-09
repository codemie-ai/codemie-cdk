# Codemie Infrastructure as Code

Infrastructure as Code solution for managing Codemie AI assistants, datasources, and workflows through declarative YAML configuration.

## 🎯 What This Solves

### Key Problems

**1. Access Control Limitations** 🔒  
In Codemie UI, only resource creators can modify assistants and workflows. Team members cannot contribute improvements even when they have ideas.

**2. Limited Execution History Visibility** 👁️  
Only the creator can see execution history of assistants and workflows - even administrators lack access. This makes debugging and monitoring difficult for the team.

**3. No Custom Validation** ✅  
Changes go live immediately without additional checks. There's no way to enforce team-specific validation rules or quality gates before deployment.

### What IaC Enables

**Democratic Access**  
Anyone can propose changes via pull requests. Changes are reviewed and deployed by a service account with full access to all resources and their execution history.

**Custom Validation Pipeline**  
Add your own validation rules in CI/CD - from simple YAML checks to AI-powered prompt reviews. Nothing deploys until it passes your criteria.

**Team Visibility**  
Service account has access to execution history of all assistants and workflows, enabling team-wide monitoring, debugging, and analytics.

### Additional Benefits

- **Code Review Process** - Changes reviewed before going live, improving quality
- **DRY Configuration** - `$ref` mechanism eliminates duplication (define once, use everywhere)
- **Automated Deployment** - CI/CD integration removes manual steps and human errors
- **Audit Trail** - Git history shows who changed what and why
- **Environment Consistency** - Same configuration can be deployed to dev/staging/prod or can be used by other teams

## Overview

This IaC solution enables version-controlled, reproducible deployment of Codemie resources using a GitOps approach. Changes are detected via SHA256 checksums, and resources are managed by their human-readable names.

## Installation

```bash
npm install
```

### Environment Variables

Create a `.env` file in the project root:

```bash
CODEMIE_API_URL=https://your-instance.codemie.ai/api
CODEMIE_AUTH_URL=https://your-keycloak.auth.com
CODEMIE_REALM=codemie
CODEMIE_CLIENT_ID=your-client-id
CODEMIE_CLIENT_SECRET=your-client-secret
```

**⚠️ Security: DO NOT commit `.env` to Git!**

The `.env` file is already added to `.gitignore` and should never be committed to the repository.

**For local development:**
- Each developer creates their own `.env` file locally with actual credentials
- Copy the template above and replace with your values
- Use your own credentials (do not share them via Git)
- Optional: Create `.env.example` in your project (template without actual secrets) to help team members

**For CI/CD (GitLab):**
- Add environment variables in GitLab: **Settings → CI/CD → Variables**
- Add each variable separately:
  - `CODEMIE_API_URL`
  - `CODEMIE_AUTH_URL`
  - `CODEMIE_REALM`
  - `CODEMIE_CLIENT_ID`
  - `CODEMIE_CLIENT_SECRET` (mark as **Masked**)

**Substitution in `codemie.yaml`:**
- `${VAR}` and `${VAR:-default}` are substituted in every string value of the configuration, including values nested inside lists such as `resources.skills` or `resources.datasources`.
- A `${VAR}` without a default whose variable is not set fails the load with an error naming the configuration path, for example `resources.datasources[0].name`. Use `${VAR:-default}` where a value is optional, or `${VAR:-}` to substitute an empty string.
- Escape a placeholder with an extra `$`: `$${VAR}` produces literal `${VAR}` without looking up the variable, even if it is set locally. This also preserves default expressions: `$${VAR:-default}` produces `${VAR:-default}`.
- Escaped placeholders and ordinary substitutions can appear in the same string. Substitution happens once; emitted placeholders and environment variable values are not expanded again. Dollar signs outside placeholder expressions are unchanged.

For example, an MCP server can receive a placeholder for CodeMie to resolve later, without requiring a local npm token:

```yaml
config:
  env:
    NPM_TOKEN: '$${NPM_TOKEN}'
```

## Quick Start

```bash
# Initialize a new Codemie IaC project (creates .env and codemie.yaml via wizard)
codemie init

# Full validation with API connectivity check (default, recommended)
npm run validate

# Basic validation only (fast, no API connection)
npm run validate:basic

# Preview changes
npm run preview

# Deploy resources
npm run deploy

# Deploy resources and delete orphaned ones
npm run deploy -- --prune

# Remove all IaC-managed resources
npm run destroy

# Create backup of all resources
npm run backup

# Use external config file to override default names and locations for: codemie.yaml, .codemie/state.json, backups
npm run <command>  --config codemie/iac.json
```
**Note:** All commands work identically whether you use monolithic configuration or modular imports - the `$import` directives are automatically resolved during config loading.

### Project Initialization (`codemie init`)

Use the interactive wizard to scaffold a project:

```bash
codemie init
```

What it does:
- Creates a `.env` template (with a safety prompt if it already exists)
- Generates a minimal `codemie.yaml` using your project name and description
- Saves an optional `appConfig` file when you pick non-default paths for config/state/backups
- Prints next steps to validate and deploy

If `.env` or `codemie.yaml` already exist, the wizard asks before overwriting and will keep your files if you decline.

**Config file structure:**
```json
{
  "rootDir": "root/of/working/directory",
  "codemieConfig": "path/to/codemie.yaml",
  "codemieState": "path/to/state.json",
  "backupsDirectory": "path/to/backups"
}
```
It is not mandatory to provide all fields - any missing fields will use default values.

**Default Config:**
```json
{
  "rootDir": ".",
  "codemieConfig": "codemie.yaml",
  "codemieState": ".codemie/state.json",
  "backupsDirectory": "backups"
}
```


**Validation types:**
- **Full validation** (`npm run validate`) checks:
  - `codemie.yaml` syntax is valid
  - All referenced files exist
  - Required fields are present
  - No cyclic dependencies in sub-assistants
  - Assistants with sub-assistants cannot be sub-assistants themselves
  - **Plus API checks:**
    - Slug conflicts with existing assistants in Codemie (if slugs are provided)
    - Ensures your slugs are globally unique before deployment

- **Basic validation** (`npm run validate:basic`) skips API checks (faster, no credentials needed)

### CLI Usage

The tool provides a unified `codemie` command for all operations:

```bash
# Show help and available commands
codemie --help

# Deploy resources
codemie deploy
codemie deploy --prune
codemie deploy --skip-datasources

# Other commands
codemie backup
codemie destroy --force
codemie preview
codemie validate --check-api

# Import a single resource from the Codemie platform
codemie import <type> <slug>
codemie import assistant my-assistant
codemie import workflow 11111111-1111-1111-1111-111111111111
codemie import assistant my-assistant --update  # refresh an already-managed resource in place
codemie import assistant my-assistant --with-skills  # also import the project-owned skills it references
# <type> is one of: assistant, datasource, workflow, skill
# <slug> is a resource slug or name; for assistant and workflow it may also be a platform UUID

# Run a command from a subdirectory of the project, or against another project entirely
codemie validate --root-dir ../another-project
```

**`--with-skills` (assistants only).** An imported assistant references its skills by name, so a
deploy fails if one of those skills belongs to this project but is not in `resources.skills` yet.
With `--with-skills`, each referenced skill that the project owns and does not manage yet is
imported too - `skills/<name>.skill.md` plus a `resources.skills` entry, exactly as
`codemie import skill` would write it - so the assistant deploys with no manual skill import.
Skills owned by other projects keep landing in `imported.skills` as references, and a skill the
configuration already names is left untouched (also under `--update`, which refreshes the
assistant only). On any other resource type the flag is ignored with a warning.

**Note:** Every command finds the project root automatically by walking up from the current
directory looking for `codemie.yaml`, so you can run `codemie` from any subdirectory of your
project. Pass `-d, --root-dir <path>` to point at a different project root instead. `codemie init`
never auto-detects an existing project - it always scaffolds in the current directory unless
`-d` is given. `-c, --config` and `-d, --root-dir` are independent: a `-c` file wins only where it
declares `rootDir` itself, otherwise an explicit `-d` still applies.

**For local development**, npm scripts provide convenient shortcuts:
```bash
npm run deploy    # → codemie deploy
npm run backup    # → codemie backup
npm run destroy   # → codemie destroy --force
```

## 🔄 Migrating Existing Resources to IaC

If you already have assistants, datasources, and workflows created in Codemie UI, use the backup command to migrate them to IaC management:

```bash
npm run backup
```

### What It Does

**Automated Export:**
- Fetches all resources from your Codemie platform (assistants, datasources, workflows, integrations)
- Generates IaC configuration files in `backups/YYYY-MM-DDTHH-MM-SS/` directory:
  - `codemie.yaml` - Main configuration with all resources (MCP servers use integration aliasing)
  - `state.json` - State file with resource IDs and checksums
  - `system_prompts/*.prompt.md` - Assistant system prompts
  - `workflows/*.yaml` - Workflow definitions
  - `openapi_specs/*.json` - OpenAPI tool specifications

**Transaction Safety:**
- Atomic backup process with rollback on failure
- Resume capability - if backup is interrupted, rerunning continues from last checkpoint
- Temporary directory used during backup (`.temp-*`) - moved to final location only on success
- Progress tracking with `transaction.json` checkpoint file

**Type-Safe Conversions:**
- SDK response types → IaC resource formats with proper field mapping
- Workflow YAML includes assistant ID → name resolution for readability

### Migration Workflow

**Step 1: Create Backup**
```bash
npm run backup
```

Output:
```
🗄️  Creating backup of all Codemie resources...

🔌 Connecting to Codemie API...
✓ Connected to Codemie API

📁 Temporary backup directory: backups/.temp-2025-01-27

🤖 Fetching assistants...
   Found 15 assistant(s)
   • TAD BA Helper (ast-123)
   • TAD Code Analyst (ast-456)
   ...
✓ Backed up 15 assistant(s)

📊 Fetching datasources...
   Found 8 datasource(s)
✓ Backed up 8 datasource(s)

🔄 Fetching workflows...
   Found 3 workflow(s)
✓ Backed up 3 workflow(s)

🔄 Finalizing backup...
✓ Backup finalized at backups/2025-01-27T14-30-45

==================================================
📊 Backup Summary:

  🤖 Assistants: 15
  📊 Datasources: 8
  🔄 Workflows: 3
  🔌 Integrations: 5

  📁 Location: backups/2025-01-27T14-30-45
```

**Step 2: Review Generated Files**

```bash
cd backups/2025-01-27T14-30-45
ls -la
```

Files created:
```
codemie.yaml         # Main IaC configuration
state.json           # Resource state (IDs, checksums)
system_prompts/      # Assistant system prompts
  tad-ba-helper.prompt.md
  tad-code-analyst.prompt.md
workflows/           # Workflow definitions
  code-review-workflow.yaml
openapi_specs/       # OpenAPI tool specs
```

**Step 3: Copy to Your IaC Project**

```bash
# Option A: Replace entire configuration
cp backups/2025-01-27T14-30-45/* ./
mv backups/2025-01-27T14-30-45/system_prompts/* system_prompts/
mv backups/2025-01-27T14-30-45/workflows/* workflows/
mv backups/2025-01-27T14-30-45/openapi_specs/* openapi_specs/

# Option B: Merge specific resources into existing config
# Manually copy needed sections from backups/2025-01-27T14-30-45/codemie.yaml
```

**Step 4: Validate & Deploy**

```bash
npm run validate  # Check configuration
npm run preview      # Preview (should show "No changes")
npm run deploy    # Deploy (updates state file with current checksums)
```

### Troubleshooting

**Backup Interrupted?**
- Just run `npm run backup` again - it will resume from last checkpoint
- Transaction file (`transaction.json`) tracks progress
- Temporary directory (`.temp-*`) will be cleaned up automatically

**Backup Failed Completely?**
- Check `.temp-*` directory exists - if yes, partial backup was attempted
- Error message will indicate which resource failed
- Temporary directory will be automatically cleaned up (rollback)
- Fix the issue and rerun backup

**Code Datasource Missing Repository Link?**
- Some code datasources may show warning: `⚠️ Code datasource missing repository link`
- SDK sometimes doesn't return `code.link` field
- Manually add `link: https://github.com/...` in `codemie.yaml` datasource section

**Workflow Assistant IDs Not Resolved?**
- If workflow YAML contains `assistant_id: ast-xxx` instead of assistant name
- This happens when assistant doesn't exist in backup (e.g., deleted or from another project)
- Manually replace with correct assistant name or ID in workflow YAML file

**All MCP Assistants Show as Changed After an Upgrade?**
- After upgrading to the release that normalizes MCP configuration, MCP server configuration is normalized before hashing, so every assistant with `mcp_servers` gets a new `configChecksum` once
- `preview` and `deploy` list each of them under `⚠️  UPDATE:` as `- assistant:<name>` with `Prompt or configuration changed` and no per-field diff
- Expected, not a configuration error - `deploy` stores the new `configChecksum` in `.codemie/state.json` and the next run reports them as unchanged

**Resume From Specific Point?**
- Transaction file tracks what's completed: `transaction.json`
- Contains: `completed: ['ast-1', 'ast-2']` and `failed: [{id: 'ast-3', error: '...'}]`
- To force fresh backup: delete `backups/YYYY-MM-DDTHH-MM-SS/transaction.json` before rerunning

## 📝 Prompt Compilation System

The repository includes an **automated prompt compilation system** for managing complex prompts with reusable components and configuration.

### When to Use Compilation

**Use template-based compilation for:**
- Prompts with shared components (includes)
- Multiple configuration variants
- Team collaboration on modular components
- Complex prompts that benefit from DRY principles

**Use direct editing for:**
- Simple, self-contained prompts
- Quick changes or updates
- Prompts that don't need shared components

### Quick Start

```bash
# Compile specific agent
npm run compile -- --prompt tad-ba-helper

# Compile all prompts
npm run compile:all

# Check if compiled files are up-to-date
npm run compile:check

# Verbose output
npm run compile:all -- --verbose
```

> **Note:** Compilation functionality is available only as internal npm scripts. The compile command is not exposed in the published `codemie-iac` package, which focuses exclusively on infrastructure management (deploy, validate, preview, destroy, backup).

### Directory Structure

```
prompt_source/              # Source templates
├── shared/                 # Shared includes
│   ├── jira-processing.include.md
│   └── confluence-processing.include.md
└── {agent-name}/           # Agent directory
    ├── {agent}.prompt.md       # Template with placeholders
    ├── {agent}.config.yaml     # Configuration values
    └── {agent}.requirements.md # Requirements doc

system_prompts/             # Ready-to-deploy prompts
├── README.md               # Documentation
└── *.prompt.md             # Final prompts (some auto-compiled)
```

### Placeholder Types

The compilation system handles three types of placeholders:

1. **Config Placeholders** - `{config.key}`
   - Resolved during compilation from `.config.yaml`
   - Example: `{team_ids.prescreening}` → `91267`

2. **Runtime Variables** - `{{system}}`
   - Preserved for Codemie platform (resolved at runtime)
   - Example: `{{current_user}}`, `{{date}}`

3. **Documentation Examples** - `<example>`
   - Part of prompt text, never resolved
   - Example: `<param_name>`, `<user_id>`

### Example Template

**Source:** `prompt_source/my-agent/my-agent.prompt.md`
```markdown
---
prompt_name: My Agent
prompt_version: 1.0.0
---

# Instructions

{include:jira-processing}

Use team ID: {team_ids.my_team}
Current user: {{current_user}}
```

**Config:** `prompt_source/my-agent/my-agent.config.yaml`
```yaml
prompt_version: 1.0.0

team_ids:
  my_team: "12345"
```

**Compiled:** `system_prompts/my-agent/my-agent.prompt.md`
```markdown
---
prompt_name: My Agent
prompt_version: 1.0.0
---

# Instructions

[Full content of jira-processing.include.md inserted here]

Use team ID: 12345
Current user: {{current_user}}
```

### CI/CD Integration

Compilation is **fully automated** in the deployment pipeline:

1. **Compile Stage** - Runs before validation
2. **Validation** - Checks for unresolved placeholders
3. **Deployment** - Deploys compiled prompts
4. **Auto-Commit** - CI commits compiled files back to repository

**Workflow:**
- Edit source files in `prompt_source/`
- Push to repository
- CI automatically compiles and deploys
- Compiled files updated in `system_prompts/`

### Extensible Architecture

The compilation system uses a **plugin-based architecture** for easy extension:

- **ProcessorPlugin** - Custom content transformations
- **ValidatorPlugin** - Custom validation rules
- **Type-safe** - Full TypeScript support
- **Well-documented** - See `ARCHITECTURE.md` for details

For complete documentation:
- **Source Templates**: `prompt_source/README.md`
- **System Prompts**: `system_prompts/README.md`
- **Architecture**: `ARCHITECTURE.md`
- **Development Guide**: `CONTRIBUTING.md`

## Configuration Structure

All resources are defined in `codemie.yaml`:

```yaml
version: 1

project:
  name: my-project
  description: Your project description

environment:
  codemie_api_url: ${CODEMIE_API_URL}
  # ... other env vars

imported:
  integrations:    # Platform integrations (referenced via $ref)
  assistants:      # Existing assistants (for workflows)
  datasources:     # Existing datasources

resources:
  datasources:     # Datasources to create/manage
  assistants:      # Assistants to create/manage
  workflows:       # Workflows to create/manage
```

For detailed examples of each resource type, see:
- `examples/datasource-examples.yaml` - All datasource types with field descriptions
- `examples/assistant-examples.yaml` - Assistant patterns and configurations
- `examples/toolkit-examples.yaml` - All toolkit configurations
- `examples/workflow-examples.yaml` - Workflow patterns and structures
- `examples/skill-examples.yaml` - Skill patterns, including expanding a folder of skill directories

## 📁 Configuration Organization

### Modular Configuration with `$import`

For large projects, you can split configuration into multiple files using the `$import` directive. The ConfigLoader automatically resolves imports and supports three organization styles:

#### Style 1: Monolithic

Keep everything in one file - perfect for small projects:

```yaml
# codemie.yaml
version: 1
project:
  name: my-project

resources:
  datasources:
    - name: repo-1
      type: code
      link: https://github.com/org/repo-1
    - name: repo-2
      type: code
      link: https://github.com/org/repo-2
  
  assistants:
    - name: Assistant 1
      prompt: ./system_prompts/assistant-1.prompt.md
      model: gpt-4o
```

#### Style 2: Grouped Resources

Group related resources in array files:

```yaml
# codemie.yaml
resources:
  datasources:
    - $import: configs/datasources/all-repos.yaml
    - $import: configs/datasources/knowledge-bases.yaml
  
  assistants:
    - $import: configs/assistants/ba-team.yaml
    - $import: configs/assistants/dev-team.yaml
```

```yaml
# configs/datasources/all-repos.yaml
- name: repo-1
  type: code
  link: https://github.com/org/repo-1

- name: repo-2
  type: code
  link: https://github.com/org/repo-2

- name: repo-3
  type: code
  link: https://github.com/org/repo-3
```

```yaml
# configs/assistants/ba-team.yaml
- name: BA Reviewer
  prompt: ./system_prompts/ba-reviewer.prompt.md
  model: claude-3-7

- name: BA Helper
  prompt: ./system_prompts/ba-helper.prompt.md
  model: gpt-4.1
  sub_assistants:
    - BA Reviewer
```

#### Style 3: Individual Files

Each resource in a separate file for maximum modularity:

```yaml
# codemie.yaml
resources:
  datasources:
    - $import: configs/datasources/repo-1.yaml
    - $import: configs/datasources/repo-2.yaml
    - $import: configs/datasources/jira-kb.yaml
  
  assistants:
    - $import: configs/assistants/ba-reviewer.yaml
    - $import: configs/assistants/ba-helper.yaml
    - $import: configs/assistants/code-reviewer.yaml
```

```yaml
# configs/datasources/repo-1.yaml
name: repo-1
type: code
description: Repository 1
link: https://github.com/org/repo-1
branch: main
```

```yaml
# configs/assistants/ba-reviewer.yaml
name: BA Reviewer
description: Reviews BA artifacts
prompt: ./system_prompts/ba-reviewer.prompt.md
model: claude-3-7
shared: true
toolkits:
  - toolkit: Project Management
    tools:
      - $ref: tool_definitions.jira_tool
```

#### Style 4: Hybrid

Mix all approaches based on your needs:

```yaml
# codemie.yaml
resources:
  datasources:
    # Inline for quick tests
    - name: test-repo
      type: code
      link: https://github.com/org/test
    
    # Array import for simple repos
    - $import: configs/datasources/simple-repos.yaml
    
    # Individual files for critical resources
    - $import: configs/datasources/production-jira.yaml
    - $import: configs/datasources/production-confluence.yaml
  
  assistants:
    # Team groups
    - $import: configs/assistants/ba-team.yaml
    - $import: configs/assistants/dev-team.yaml
    
    # VIP assistants separately
    - $import: configs/assistants/ceo-assistant.yaml
```

### Import Features

**Object Imports:**
```yaml
# Import entire sections
tool_definitions:
  $import: configs/shared/tool-definitions.yaml

datasource_defaults:
  $import: configs/shared/datasource-defaults.yaml
```

**Circular Import Protection:**
- Automatically detects circular dependencies (file-a → file-b → file-a)
- Throws clear error with import chain: `Circular import detected: [file-a.yaml, file-b.yaml, file-a.yaml]`
- Allows same file in different branches (tree structure, not linear chain)

**Nested Imports:**
```yaml
# configs/datasources/all-repos.yaml
- $import: base-repos.yaml  # Import from same directory
- name: additional-repo
  type: code
  link: https://github.com/org/additional
```

**Cross-Project Reuse:**
```yaml
# Project A
resources:
  assistants:
    - $import: ../shared-assistants/code-reviewer.yaml
    - $import: configs/assistants/project-a-specific.yaml

# Project B
resources:
  assistants:
    - $import: ../shared-assistants/code-reviewer.yaml
    - $import: configs/assistants/project-b-specific.yaml
```

### Recommended Structure

```
project-root/
├── codemie.yaml                 # Main config (imports only)
├── configs/
│   ├── project.yaml            # Project metadata
│   ├── environment.yaml        # Environment variables
│   ├── imported.yaml           # Imported resources
│   ├── shared/
│   │   ├── tool-definitions.yaml
│   │   └── datasource-defaults.yaml
│   ├── datasources/
│   │   ├── repos/
│   │   │   ├── frontend-repos.yaml
│   │   │   └── backend-repos.yaml
│   │   └── knowledge-bases/
│   │       ├── jira-production.yaml
│   │       └── confluence-production.yaml
│   ├── assistants/
│   │   ├── ba-team/
│   │   │   ├── ba-reviewer.yaml
│   │   │   └── ba-helper.yaml
│   │   └── dev-team/
│   │       ├── code-reviewer.yaml
│   │       └── codebase-digger.yaml
│   └── workflows/
│       ├── test-automation.yaml
│       └── release-notes.yaml
├── system_prompts/
│   └── *.prompt.md
└── workflows/
    └── *.yaml
```

## 🧩 Skills Configuration

Skills are defined under `resources.skills`. Two shapes are supported, and you can mix both in the same list.

#### Single-File Skill

The original shape — one entry, one `.skill.md` file:

```yaml
resources:
  skills:
    - name: code-review-checklist
      description: Checklist the assistant walks through when reviewing a pull request
      file: ./skills/code-review-checklist.skill.md
      categories: [review, quality]
      visibility: project
```

- `name` (required): unique skill name.
- `description` (required): 10-1000 characters — see "Description length validation" below.
- `file` (or inline `content`, see below): at least one of the two is required. A skill expanded from `source_dir` carries both — `file` points at its `SKILL.md` and `content` holds the body.
- `categories` (optional): array of category labels.
- `visibility` (optional): `project` or `public` (default: `project`).

#### A Folder of Skill Directories (`source_dir`)

For a directory that already holds one subdirectory per skill (the layout used by skill authoring tools), point `source_dir` at it instead of listing every skill by hand:

```yaml
resources:
  skills:
    - source_dir: ./skills/engineering
      ignore_file: ./skills/engineering/.codemie-skills-ignore.yaml
      categories: [engineering]
      visibility: project
      group: engineering-team
```

```
skills/engineering/
├── code-review-checklist/
│   └── SKILL.md
├── incident-runbook/
│   └── SKILL.md
└── draft-idea/            # no SKILL.md here → skipped silently
    └── notes.md
```

```yaml
# skills/engineering/.codemie-skills-ignore.yaml
skills:
  - draft-idea
```

Behavior:
- Each **immediate** subdirectory of `source_dir` that directly contains a `SKILL.md` becomes one skill entry. Subdirectories without a `SKILL.md` are skipped silently. There is no recursion into deeper levels.
- Skills are expanded in sorted order of their subdirectory names, so two loads of the same folder always produce identical results.
- `SKILL.md` may start with `---`-delimited YAML front matter (a UTF-8 BOM and CRLF line endings are tolerated). `name` is taken from the front matter, falling back to the directory name when absent. `description` is taken from the front matter. Everything after the front matter becomes the skill's content.
- `ignore_file` (optional) points at a YAML file shaped `skills: [<dirName>, ...]`; the listed directory names are skipped during expansion.
- `categories`, `visibility` and `group` on the `source_dir` entry are inherited by every skill expanded from it. `group` is a label only — it never splits or migrates anything, and it is intentionally excluded from change detection, so relabelling a skill does not mark it as changed. The one command that reads it is `deploy --replace-skill-group` (see "Replacing a Whole Skill Group" below).
- A `source_dir` that does not exist is a configuration error naming both the resolved path and the offending `source_dir` entry. A missing or malformed `ignore_file`, and malformed `SKILL.md` front matter, fail the same way — naming the file at fault.
- Skill names must be unique across every `source_dir` and every hand-written entry. A duplicate is a configuration error naming the name and both sources that produced it.
- Names produced by expansion must be kebab-case, 3-64 characters, starting and ending with a letter or digit. This rule only applies to skills expanded from `source_dir` — existing hand-written skill names in the single-file shape are unaffected.
- Every other file in a skill's subdirectory ships with it as a companion file — see "Companion Files" below.

#### Companion Files

A skill whose `file` points at a `SKILL.md` — every skill expanded from `source_dir`, plus any hand-written entry that points at one — ships the rest of its directory too. Every other file beneath that directory, at any depth, becomes a **companion file** that travels with the skill to the platform:

```
skills/engineering/code-review-checklist/
├── SKILL.md                  # the skill's own content, never a companion file
├── .codemie-exclude          # optional, never shipped itself
├── checklist.md              # companion file
├── templates/pr-body.md      # companion file (the relative path is preserved)
└── assets/diagram.png        # companion file (binary → shipped base64)
```

A skill in the single-file shape (`file: ./skills/foo.skill.md`) or with inline `content` has no companion files.

**Always excluded**, whatever patterns you write: `SKILL.md` and `.codemie-exclude` themselves, the directories `node_modules`, `.git` and `evals`, and the lockfiles `package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lockb`, `composer.lock`, `Gemfile.lock`, `Cargo.lock` and `poetry.lock`. Symlinks — to files or directories — are skipped rather than followed.

**`.codemie-exclude`** is optional and is read only from the skill's own directory (one placed deeper in the tree is not read). Patterns go one per line and are matched against skill-relative POSIX paths:

| Pattern | Matches |
|---------|---------|
| `docs/secret.txt` | that exact path |
| `vendor/lib` | `vendor/lib` itself and everything beneath it |
| `build/` | everything beneath `build/` — a trailing slash marks a directory prefix |
| `secret.txt` | a file named `secret.txt` at any depth — a pattern without `/` matches the basename |
| `*.log` | `*` matches any run of characters except `/` |
| `docs/**/notes.md` | `**` crosses `/` |
| `file?.txt` | `?` is exactly one character, never `/` |
| `{foo,bar}.txt` | `{a,b}` is alternation |
| `# draft/` | nothing — a line whose first non-whitespace character is `#` is a comment |

Blank lines are ignored, and every other character is literal (the `.` in `file.txt` is a dot, not "any character").

**Text and binary files are detected automatically.** Content that contains no NUL byte and round-trips exactly as UTF-8 is sent as text, byte-identical to the file on disk; anything else — a binary asset, or text in a legacy single-byte encoding — is base64-encoded, so it survives deploy and backup byte-for-byte. The MIME type is derived from the file extension, falling back to `application/octet-stream`.

**Companion files are tracked in state by checksum.** `.codemie/state.json` records one content hash per companion file plus one aggregate checksum — never the file bodies. Adding, editing or removing a companion file therefore marks the skill as changed in `preview` (which names the files added, removed and modified) and triggers an update in `deploy`, even when `SKILL.md` itself is untouched. Removing the last companion file clears the skill's companion files on the platform. When state cannot say what the platform holds — a skill recovered by name after an "already exists" create, or a state entry written before companion files were tracked — the platform's own list is read first, so stale companions are cleared rather than left behind.

**`backup` and `import` keep the layout.** For a skill that has companion files, `codemie backup` writes `skills/<name>/SKILL.md` with the companion files beside it under their original relative paths, decoding base64 ones back to bytes; a skill with no companion files keeps the flat `skills/<name>.skill.md` layout (content files are written for project-owned skills only). `codemie import` fetches a skill's companion files as well and writes those same two layouts, so a backed-up or imported skill redeploys with its companions intact.

**A failed companion lookup never touches the platform's files.** When that lookup cannot be answered — a timeout, a server error, or a platform without the companion-files endpoint — `deploy` warns, naming the skill and the reason, and updates the skill without the `companion_files` field, leaving whatever the platform holds untouched instead of failing the skill.

**Only the `SKILL.md` layout manages companion files.** If a managed entry points at a flat `skills/<name>.skill.md` while the platform skill has companion files, `codemie import --update` refreshes the content file, warns, and deliberately records no companion hashes in state: those files stay on the platform, unmanaged locally. Point the entry at a `skills/<name>/SKILL.md` layout to manage them.

#### Description Length Validation

**Behavior change:** a skill description outside **10-1000 characters** now fails locally — in `validate`, `preview` and `deploy` — naming the skill, its actual length and the allowed range. Previously an out-of-range description reached the platform and failed there with an opaque API error. There is no placeholder description and no truncation: an out-of-range description is always an error, for both shapes above.

Running `codemie validate --check-api` additionally checks each skill's *content* length against the platform's own configured limits, which are read live from the API rather than hard-coded in the CLI.

#### Replacing a Whole Skill Group (`--replace-skill-group`)

Some skill sets are regenerated as a whole — a large skill split differently, for example — and have to be deleted and recreated under the same names. `deploy` updates skills in place and `--prune` only removes skills that left the config, so neither detaches and recreates a set of skills. `--replace-skill-group` does:

```bash
# See what would happen first
codemie preview --replace-skill-group github-copilot

# Then run it (the confirmation flag is mandatory)
codemie deploy --replace-skill-group github-copilot --yes-replace-skills
```

**Group membership comes only from the `group` field** — the label persisted in `.codemie/state.json` or the one on the `resources.skills` entry (including a `group` inherited from a `source_dir` entry). Skill names are never pattern-matched against the group name: a skill called `github-copilot--body-1` is not part of the group unless it carries the label.

What a run does, in order:

1. **Refuses without `--yes-replace-skills`** — nothing is touched, no API call is made. A group name that matches an `imported.skills` entry, or that matches no skill at all, is refused the same way.
2. **Detaches** every selected skill from every state-managed assistant and every assistant in `imported.assistants`, before the first delete.
3. **Deletes** the selected skills and drops their state entries. A delete failure aborts the run then and there, so no skill is recreated while part of the group is still on the platform; fix the platform error and rerun.
4. **Deploys only that group's skills and the assistants that reference them** (plus those assistants' `sub_assistants`, so dependency resolution still works), letting the normal attachment sync reattach the recreated skills. An assistant's `skills` entries are matched against the group case-insensitively, the same way validation accepts them. **Datasources and workflows are not deployed** — `resources.datasources` and `imported.datasources` are still read, so an assistant's `datasource_names` resolve — `--prune` is ignored, and no other resource type is created, updated or deleted.

`preview --replace-skill-group <group>` reports the same set of skills as the deploy: one delete per selected skill and one create per config entry of the group.

> ⚠️ **Recreated skills get new platform ids.** Anything that references them by id rather than by name does not follow the change. In particular, another IaC project that references these skills through its own `imported.skills` keeps the old ids and must be updated (re-import the skill, or update the id by hand) after a replacement run.

## 📁 File Structure

```
assistant-resources/
├── codemie.yaml                 # Main IaC configuration
├── .codemie/
│   └── state.json              # Deployment state (committed to Git)
├── system_prompts/
│   └── *.prompt.md             # Prompt content files
├── workflows/
│   └── *.yaml                  # Workflow definitions
├── examples/                    # Configuration examples (reference)
│   ├── datasource-examples.yaml
│   ├── assistant-examples.yaml
│   ├── toolkit-examples.yaml
│   ├── workflow-examples.yaml
│   └── skill-examples.yaml
└── src/                        # IaC implementation
```

## Key Features

### Modular Configuration with `$import`

Organize your configuration across multiple files for better maintainability and team collaboration. The `$import` directive automatically resolves imports during config loading:

```yaml
# Main config - clean and organized
resources:
  datasources:
    - $import: configs/datasources/repo-1.yaml  # Single resource
    - $import: configs/datasources/all-repos.yaml  # Array of resources
  
  assistants:
    - $import: configs/assistants/ba-team.yaml
```

Supports inline resources, individual files, array files, and any combination. See [Configuration Organization](#-configuration-organization) for details.

### Name-Based Resource Management

Resources are identified by their `name` field. Renaming a resource in `codemie.yaml` results in deleting the old resource and creating a new one.

**Why names instead of IDs?**
1. **Platform generates UUIDs** - You don't know the ID until after creation, making it impossible to write config before deployment
2. **Git-friendly** - Human-readable names enable meaningful diffs in pull requests: "Added Customer Support Bot" vs "Added resource a3f2b8c9-..."
3. **Team collaboration** - Names are self-documenting; team members understand what changed without looking up UUIDs
4. **Config portability** - Same config can be deployed to different environments without ID conflicts

**Why delete+create on rename?**
- Without UUIDs in config, there's no way to track that "Old Name" became "New Name"
- Alternative would require manual migration steps, defeating IaC purpose
- State file (`state.json`) maps names→UUIDs for updates, but rename breaks this mapping

**About slugs:**
- `slug` is **optional** for all assistants
- Platform auto-generates slug from name if not provided
- **Recommendation:** Don't specify slug unless you have specific requirements
- Sub-assistants use **names** (not slugs)
- Workflows reference assistants by **name**

### Checksum-Based Change Detection

Changes to prompts and configuration are detected via SHA256 checksums, ensuring only modified resources are updated.

**Why checksums instead of timestamps or full comparison?**
1. **Idempotency** - Same config produces same checksums, enabling safe re-runs without unintended changes
2. **Efficiency** - Avoid costly API calls to fetch resources for comparison when nothing changed
3. **Precision** - Separate checksums for prompt content and resource config allow granular change detection
4. **Git integration** - Checksums stored in `state.json` provide audit trail of what was actually deployed

**How it works:**
- Prompt checksum: SHA256 of prompt file content
- Config checksum: SHA256 of resource configuration (excluding prompt path, including all other fields)
- On deployment: Compare stored checksums with current checksums
- Only update if either checksum differs

**One-time checksum change for assistants with MCP servers**

After upgrading to the release that normalizes MCP configuration, MCP server configuration is normalized before it is hashed: keys with no value (`null`) and an empty top-level `mcp_connect_url` no longer contribute to the hash, and the remaining keys are hashed in a fixed order at every depth, so the order the platform or your YAML uses for MCP fields never affects the checksum. Every assistant that has `mcp_servers` therefore gets a new `configChecksum` once - and only once.

The first `npm run preview` (or `codemie preview`) and `npm run deploy` after the upgrade list each such assistant under `⚠️  UPDATE:` as `- assistant:<name>` followed by `Prompt or configuration changed`, with no per-field diff. This is expected and is not a configuration error - nothing in your `codemie.yaml` changed. `deploy` writes the new `configChecksum` back to `.codemie/state.json`, and the second run reports the same assistants as unchanged.

### Orphaned Resource Cleanup

Resources removed from `codemie.yaml` are NOT automatically deleted by default. To remove them, you must explicitly use the `--prune` flag.

**How orphaned resources are detected:**
1. Load `state.json` - contains all resources created by IaC with their names and UUIDs
2. Load `codemie.yaml` - contains desired state (what should exist)
3. Compare: For each resource in `state.json`, check if it exists in `codemie.yaml`
4. If resource is in state but NOT in config → mark as orphaned
5. If `--prune` is used: Delete orphaned resources from platform using their UUID
6. Remove from `state.json`

**Safety mechanisms:**
- **Opt-in cleanup** - `npm run deploy` never deletes resources unless you pass `--prune`.
- **Only IaC-created resources** - Resources NOT in `state.json` are never deleted (manually created resources are safe)
- **Per-resource-type** - Checks assistants, datasources, workflows separately
- **Logged deletion** - Each deletion is logged with resource name and UUID for audit

**Why automatic cleanup?**
- **GitOps principle** - Config is source of truth; platform state should match config
- **No manual cleanup** - Prevents orphaned resources accumulating over time
- **Safe refactoring** - Rename/restructure resources without leaving behind old versions

### Workflow Assistant Resolution

Workflows reference assistants by `assistant_name`, which are resolved to platform UUIDs during deployment from `state.json` or `imported.assistants`.

**Why name-based references in workflows?**
1. **Readability** - `assistant_name: "Code Reviewer"` vs `assistant_id: "a3f2b8c9-..."`
2. **Maintainability** - Update assistant name in one place (codemie.yaml), workflows auto-resolve
3. **Versionability** - Git diffs show meaningful changes: "Changed to Data Analyzer" vs changed UUID
4. **Cross-environment** - Same workflow YAML works in dev/prod with different assistant UUIDs

**Resolution order:**
1. Check `state.json` - IaC-created assistants (have name→UUID mapping)
2. Check `imported.assistants` - Pre-existing platform assistants referenced by config
3. If not found → deployment fails with clear error message

This happens during `npm run deploy`, before sending workflow YAML to API.

### Integration Aliasing with `$ref`

Avoid duplication by referencing integrations:

```yaml
imported:
  integrations:
    - alias: jira_connection
      id: 00000000-0000-0000-0000-000000000001
      credential_type: Jira

resources:
  # For datasources: use .id suffix to get UUID string
  datasources:
    - name: my-jira-kb
      type: knowledge_base_jira
      setting_id: $ref:imported.integrations.jira_connection.id  # → "00000000..."
      jql: project = MY
  
  # For toolkits: reference full object (no .id suffix)
  assistants:
    - name: My Assistant
      toolkits:
        - toolkit: Project Management
          tools:
            - name: generic_jira_tool
              settings:
                $ref: imported.integrations.jira_connection  # → full object
```

**Why `$ref` instead of repeating integration IDs?**
1. **Single source of truth** - Integration ID defined once, used everywhere
2. **Easier updates** - Change integration ID in one place, applies to all references
3. **Reduced errors** - Copy-paste mistakes eliminated
4. **Semantic clarity** - `$ref:imported.integrations.jira_connection.id` explains what it references

**How `$ref` works:**
- **For datasources**: Path MUST end with `.id` to get the UUID string
  - `$ref:imported.integrations.name.id` → resolves to UUID string
- **For toolkits**: Path references the full object (no `.id` suffix)
  - `$ref:imported.integrations.name` → resolves to full integration object
- During config load, `ConfigLoader` resolves all `$ref` references
- Validation ensures referenced path exists before deployment

## State Management

The `.codemie/state.json` file tracks IaC-created resources:

```json
{
  "version": "1",
  "project": "my-project",
  "lastSync": "2025-01-15T10:30:00Z",
  "resources": {
    "assistants": {
      "My Assistant": {
        "id": "uuid-here",
        "promptChecksum": "sha256-hash",
        "configChecksum": "sha256-hash"
      }
    },
    "datasources": { ... },
    "workflows": { ... }
  }
}
```

**Why commit state.json to Git?**
1. **CI/CD requirement** - Pipeline needs to know what's deployed to calculate changes
2. **Team visibility** - Everyone sees current production state
3. **Audit trail** - Git history shows who deployed what and when
4. **No external backend** - Simpler than S3/Consul/etc.; Git is the backend

**Why no state locking?**
- GitLab CI/CD `resource_group: production` ensures sequential execution
- Only one pipeline runs at a time → no concurrent modifications → no race conditions
- State conflicts impossible with proper CI/CD setup

## 📝 Configuration Guide

### Importing Existing Resources from Platform

When you want to reference resources that already exist on the Codemie platform (created manually or by another team), you need to import them into your IaC configuration.

#### Why Import Resources?

**For Integrations:**
- Integrations are created in Codemie UI
- IaC only references them - doesn't create or manage them
- Required for datasources and toolkits to authenticate

**For Datasources:**
- Reuse datasources created by other teams
- Avoid duplicate indexing of the same data
- Share knowledge bases across multiple assistants

**For Assistants:**
- Reference existing assistants in workflows
- Use assistants as sub-assistants without managing them
- Collaborate across teams without duplicating resources

#### How to Import Resources

**Step 1: Find the resource in Codemie UI**

For **Integrations**:
1. Go to Codemie UI → Integrations
2. Find your integration (e.g., "Git Server Connection")
3. Copy the UUID from the URL or integration details
4. Note the integration type (Git, Jira, Confluence, etc.)

For **Datasources**:
1. Go to Codemie UI → Data Sources
2. Find your datasource
3. Copy the UUID from the URL (e.g., `00000000-0000-0000-0000-000000000002`)
4. Note the datasource name and type

For **Assistants**:
1. Go to Codemie UI → Assistants
2. Find your assistant
3. Copy the UUID from the URL (e.g., `00000000-0000-0000-0000-000000000003`)
4. Note the exact assistant name

**Step 2: Add to `imported` section in codemie.yaml**

```yaml
imported:
  # Integrations (created in Codemie UI, referenced by datasources/toolkits)
  integrations:
    - alias: git_server_connection
      id: 00000000-0000-0000-0000-000000000004  # From Codemie UI
      credential_type: Git
    
    - alias: jira_connection
      id: 00000000-0000-0000-0000-000000000001
      credential_type: Jira
    
    - alias: confluence_connection
      id: 00000000-0000-0000-0000-000000000005
      credential_type: Confluence
  
  # Datasources (existing datasources to reuse)
  datasources:
    - id: 00000000-0000-0000-0000-000000000002  # From Codemie UI
      name: Confluence-6May2025  # Exact name from platform
      type: knowledge_base_confluence
    
    - id: 00000000-0000-0000-0000-000000000006
      name: Jira-Production-KB
      type: knowledge_base_jira
  
  # Assistants (existing assistants to reference in workflows/sub-assistants)
  assistants:
    - id: 00000000-0000-0000-0000-000000000003  # From Codemie UI
      name: Front-End Code Reviewer  # Exact name from platform
    
    - id: 00000000-0000-0000-0000-000000000007
      name: Checklist Generator Assistant
```

**Step 3: Use imported resources in your configuration**

```yaml
resources:
  datasources:
    # Use imported integration
    - name: my-repo
      type: code
      link: https://git.example.com/repo
      branch: master
      setting_id: $ref:imported.integrations.git_server_connection.id  # Reference
  
  assistants:
    # Use imported datasource
    - name: My Assistant
      prompt: ./system_prompts/assistant.prompt.md
      model: gpt-4o
      context:
        - context_type: knowledge_base
          name: Confluence-6May2025  # References imported datasource
      
      # Use imported integration in toolkit
      toolkits:
        - toolkit: Project Management
          tools:
            - name: generic_jira_tool
              label: Generic Jira
              settings_config: false
              settings:
                $ref: imported.integrations.jira_connection  # Reference
      
      # Use imported assistant as sub-assistant
      sub_assistants:
        - Front-End Code Reviewer  # References imported assistant
  
  workflows:
    - name: My Workflow
      definition: ./workflows/workflow.yaml
      mode: Sequential
```

**Important Notes:**

- **Integration IDs**: Find in Codemie UI → Integrations (usually in URL or settings)
- **Datasource IDs**: Find in Codemie UI → Data Sources → Select datasource → Check URL
- **Assistant IDs**: Find in Codemie UI → Assistants → Select assistant → Check URL
- **Exact names**: Must match platform names exactly (case-sensitive)
- **Type validation**: IaC validates that types match platform resources
- **Access permissions**: Service account must have access to imported resources

**Why use `imported` instead of creating via IaC?**

| Resource Type | When to Import | When to Create via IaC |
|---------------|----------------|------------------------|
| **Integrations** | Always (created in UI only) | Not yet supported |
| **Datasources** | Shared across teams, large/expensive to index | Team-specific datasources |
| **Assistants** | Managed by other teams, stable production assistants | Your team's assistants |

### Nested Assistants (Sub-Assistants)

You can link assistants together using `sub_assistants` (name-based):

```yaml
resources:
  assistants:
    # Sub-assistant (must be defined first)
    - name: Sub Assistant Helper
      prompt: ./system_prompts/sub.prompt.md
      description: "Helper assistant"
      model: gpt-4o
    
    # Main assistant with nested sub-assistant
    - name: Main Assistant
      prompt: ./system_prompts/main.prompt.md
      description: "Main assistant with helper"
      model: gpt-4o
      sub_assistants:
        - "Sub Assistant Helper"  # Reference by NAME
```

**How it works:**
- Define sub-assistants **before** the main assistant in the YAML
- Use `sub_assistants` to reference them by **name** (name-based approach)
- During deployment, names are automatically resolved to IDs from `state.json`
- Sub-assistants must exist (be deployed first) for resolution to work

**⚠️ Important restrictions:**
- **No cyclic dependencies:** A → B → C → A is not allowed
- **No nested sub-assistants:** If an assistant has `sub_assistants`, it cannot be used as a sub-assistant by another assistant
- Example of **invalid** configuration:
  ```yaml
  # ❌ Invalid: Middle has sub-assistants AND is used as sub-assistant
  assistants:
    - name: Helper
      model: gpt-4o
    
    - name: Middle
      model: gpt-4o
      sub_assistants: ["Helper"]  # Middle has sub-assistants
    
    - name: Main
      model: gpt-4o
      sub_assistants: ["Middle"]  # ❌ Middle cannot be sub-assistant!
  ```

**📋 Deployment Order:**

IaC automatically handles deployment order to resolve dependencies:

1. **Datasources first** - All datasources are created before assistants
2. **Sub-assistants before main** - Assistants are deployed in definition order
3. **Assistants before workflows** - Workflows are deployed last

**💡 Best Practice:** Define resources in the order they're referenced (datasources → sub-assistants → main assistants → workflows) for clarity.

### Toolkits for Assistants

Toolkits provide additional capabilities to assistants, such as Git operations, Project Management (Jira/Confluence), and OpenAPI integration.

> **🔧 For detailed examples**, see `examples/toolkit-examples.yaml` with all available toolkits and their configurations.

**Available Toolkits:**
1. **Git** - Git operations (PR changes, diffs)
2. **Project Management** - Jira and Confluence integration
3. **OpenAPI** - OpenAPI specification tools

**Available MCP Integrations:**
1. **Figma MCP** - Figma design tool integration
2. **Atlassian MCP** - Alternative Jira/Confluence integration (more advanced than toolkit)
3. **Custom MCP** - Any MCP-compatible server

#### Integration Aliases & Tool Definitions

To avoid repeating integration and tool settings across multiple assistants, you can define them once and reference using aliases:

**Two-Level System:**

```yaml
# Level 1: Define integrations (created in Codemie UI)
imported:
  integrations:
    - alias: jira_main
      id: "00000000-0000-0000-0000-000000000001"
      credential_type: Jira
    
    - alias: confluence_main
      id: "00000000-0000-0000-0000-000000000005"
      credential_type: Confluence

# Level 2: Define tools (referencing integrations)
tool_definitions:
  jira_tool:
    name: generic_jira_tool
    label: Generic Jira
    settings_config: false
    settings:
      $ref: imported.integrations.jira_main  # References integration
  
  confluence_tool:
    name: generic_confluence_tool
    label: Generic Confluence
    settings_config: false
    settings:
      $ref: imported.integrations.confluence_main

# Level 3: Use tools in assistants
resources:
  assistants:
    - name: BA Assistant
      model: gpt-4o
      toolkits:
        - toolkit: Project Management
          tools:
            - $ref: tool_definitions.jira_tool
            - $ref: tool_definitions.confluence_tool
```

**Usage Options:**

```yaml
# Option 1: Use tool definitions (RECOMMENDED - cleanest & most explicit)
tools:
  - $ref: tool_definitions.jira_tool
  - $ref: tool_definitions.confluence_tool

# Option 2: Reference integration directly (middle ground)
tools:
  - name: generic_jira_tool
    settings:
      $ref: imported.integrations.jira_main

# Option 3: Inline everything (not recommended, verbose)
tools:
  - name: generic_jira_tool
    settings:
      id: "00000000-0000-0000-0000-000000000001"
      credential_type: Jira
      # ... many more fields
```

**Benefits:**
- ✅ **DRY Principle**: Define once, use everywhere
- ✅ **Easy Updates**: Change integration/tool in one place
- ✅ **Ultra Clean Config**: From 15+ lines to 1 line per tool
- ✅ **Type Safety**: Integration/tool not found? Error at load time
- ✅ **Reusability**: Share tools across multiple assistants

**Note:** Integrations are created and managed in Codemie UI. The IaC config only references them by ID.

**Basic Toolkit Structure:**
```yaml
resources:
  assistants:
    - name: My Assistant
      model: gpt-4o
      toolkits:
        - toolkit: Git  # Toolkit name
          label: ""
          settings_config: true
          is_external: false
          tools:
            - name: get_pr_changes
              label: "Get PR Changes"
              settings_config: false
```

**MCP (Model Context Protocol) Servers:**

In addition to toolkits, assistants can use MCP servers for external integrations. MCP servers use the same integration aliasing pattern as toolkits:

```yaml
imported:
  integrations:
    - alias: playwright_mcp
      id: "00000000-0000-0000-0000-000000000008"
      credential_type: MCP

resources:
  assistants:
    - name: Browser Automation Assistant
      prompt: ./system_prompts/browser-automation.prompt.md
      description: "Assistant with browser automation via Playwright MCP"
      model: gpt-4o
      mcp_servers:
        - name: Playwright MCP Server
          description: "Playwright browser automation"
          enabled: true
          config:
            url: https://your-mcp-server.example.com/playwright/
            headers:
              X-Api-Key: $API_KEY
          settings:
            $ref: imported.integrations.playwright_mcp
```

**MCP Integration Aliasing:**
- MCP integrations are defined once in `imported.integrations`
- MCP servers reference them via `settings: { $ref: imported.integrations.alias }`
- Same DRY pattern as toolkits - define once, use everywhere

> **🔧 For detailed MCP examples**, see the MCP section in `examples/toolkit-examples.yaml`

### Workflows

Workflows orchestrate multiple assistants to handle complex, multi-step tasks.

#### Workflow Configuration in codemie.yaml

```yaml
resources:
  workflows:
    - name: My Workflow  # No ID needed (name-based management)
      description: Workflow description
      definition: ./workflows/my-workflow.yaml  # Path to workflow definition file
      mode: Sequential  # Sequential or Autonomous
      shared: true  # Share with project members
```

**Required fields:**
- `name` - Unique workflow name (used as identifier)
- `description` - Workflow description
- `definition` - Path to workflow definition file
- `mode` - Execution mode: `Sequential` or `Autonomous`
- `shared` - Whether to share with project (typically `true`)

#### Workflow YAML Structure

Create a workflow definition file (e.g., `workflows/my-workflow.yaml`):

```yaml
assistants:
  # Reference assistants by NAME (name-based approach)
  - id: analyzer  # Local ID for this workflow
    assistant_name: Data Analysis Assistant  # References assistant from codemie.yaml
  
  - id: reviewer  # Local ID
    assistant_name: Code Reviewer  # Another assistant reference
  
  # Inline assistant (defined directly in workflow)
  - id: parser
    model: gpt-4o-mini
    name: Data Parser
    system_prompt: |
      You are a data parser. Extract structured data from text.

states:
  - id: first_step
    assistant_id: analyzer  # Uses local ID from assistants section
    task: |
      Analyze the following input: {{ user_input }}
    output_schema: |
      {
        "analysis": "string",
        "confidence": "number",
        "recommendations": "array"
      }
    next:
      state_id: second_step
  
  - id: second_step
    assistant_id: reviewer
    task: |
      Review the analysis: {{ analysis }}
      Provide feedback on: {{ recommendations }}
    output_schema: |
      {
        "feedback": "string",
        "approved": "boolean"
      }
    next:
      state_id: end
```

**How assistant resolution works:**
1. **External assistants** (with `assistant_name`):
   - IaC looks up in `state.json` (for IaC-managed assistants)
   - Falls back to `imported.assistants` (for platform-managed assistants)
   - Resolves name → UUID during deployment
   - Workflow YAML stays unchanged (portable!)

2. **Inline assistants** (with `model` and `system_prompt`):
   - Defined directly in workflow
   - No resolution needed
   - Good for simple, workflow-specific assistants

**Change detection:**
- **Workflow YAML checksum** (`workflowYamlChecksum`) - Detects changes to workflow logic
- **Metadata checksum** (`configChecksum`) - Detects changes to name, description, mode

> **📚 For detailed workflow patterns**, see `examples/workflow-examples.yaml`

### Linking Datasources to Assistants

You can link datasources to assistants using the `context` field:

```yaml
resources:
  datasources:
    - name: my-repo
      type: code
      description: "My repository"
      link: https://git.example.com/repo
      branch: master
      setting_id: $ref:imported.integrations.git_connection.id
  
  assistants:
    - name: My Assistant
      prompt: ./system_prompts/assistant.prompt.md
      description: "Assistant with datasources"
      model: gpt-4o
      context:
        - context_type: code
          name: my-repo  # Reference datasource by name
```

**How it works:**
- Use `context` array to reference datasources by their `name` field
- Specify `context_type` matching datasource type (`code`, `knowledge_base`, etc.)
- During deployment, datasource names are resolved to platform IDs
- Datasources must be defined in config (resources or imported) for resolution to work

**Example with imported datasources:**

```yaml
imported:
  datasources:
    - id: 00000000-0000-0000-0000-000000000006
      name: Existing Jira KB
      type: knowledge_base_jira

resources:
  datasources:
    - name: my-code-repo
      type: code
      description: "My repository"
      link: https://git.example.com/repo
      branch: master
      setting_id: $ref:imported.integrations.git_connection.id
  
  assistants:
    - name: My Assistant
      prompt: ./system_prompts/assistant.prompt.md
      model: gpt-4o
      context:
        - context_type: code
          name: my-code-repo      # From resources (IaC-managed)
        - context_type: knowledge_base
          name: Existing Jira KB  # From imported (platform-managed)
```

**💡 Use imported datasources when:**
- Datasource is shared across multiple teams
- You don't want to manage datasource lifecycle via IaC
- Datasource already exists and is maintained elsewhere

### Datasource Defaults with `$ref`

To avoid repetition, define reusable datasource configurations in `datasource_defaults` and reference them using `$ref`:

```yaml
datasource_defaults:
  code:
    type: code
    index_type: code
    embeddings_model: ada-002
    shared_with_project: true
    branch: master
    force_reindex: false
  
  production_code:
    type: code
    index_type: summary
    embeddings_model: text-embedding-3-large
    shared_with_project: true
    branch: main
    force_reindex: false
  
  jira:
    type: knowledge_base_jira
    embeddings_model: ada-002
    shared_with_project: true
    force_reindex: false

resources:
  datasources:
    # Explicit $ref - inherits ALL fields from code
    - $ref: datasource_defaults.code
      name: my-repo
      description: My Git repository
      link: https://git.example.com/repo
      setting_id: $ref:imported.integrations.git_conn.id
      # type, index_type, embeddings_model, branch, etc. from $ref!
    
    # Override specific fields
    - $ref: datasource_defaults.code
      name: special-repo
      description: Special repository
      link: https://git.example.com/repo2
      setting_id: $ref:imported.integrations.git_conn.id
      branch: develop  # ← Overrides "master" from defaults
      embeddings_model: text-embedding-3-large  # ← Override
    
    # Different defaults template
    - $ref: datasource_defaults.production_code
      name: prod-repo
      description: Production repository
      link: https://git.example.com/prod
      setting_id: $ref:imported.integrations.git_conn.id
      # Uses production_code settings (summary index, large embeddings)
    
    # Jira datasource
    - $ref: datasource_defaults.jira
      name: my-jira
      description: Jira knowledge base
      setting_id: $ref:imported.integrations.jira_conn.id
      jql: project = MY
```

**How `$ref` defaults work:**
- **Explicit reference**: `$ref: datasource_defaults.name` at the start of datasource
- **Merge strategy**: `{ ...defaults, ...datasource }` - datasource fields override defaults
- **Multiple templates**: Create different default sets for different use cases
- **Minimal config**: Only specify fields unique to each datasource (name, link, description)

**Why `$ref` instead of type-based defaults?**
1. **Explicit** - Clear where values come from
2. **Flexible** - Multiple default sets for same type (e.g., code vs production_code)
3. **Reusable** - Same `$ref` mechanism as integrations and tools
4. **DRY** - Avoid repeating same fields across 30+ datasources

**Required fields** (for CODE datasources):
- `name` - Unique datasource name
- `type` - Datasource type (determines which defaults to use)
- `description` - Description (typically repository info)
- `link` - Git repository URL
- `branch` - Git branch to index

**Common fields** (typically in defaults):
- `index_type` - Indexing type: `code`, `summary`, or `chunk-summary`
- `embeddings_model` - Model for embeddings (e.g., `ada-002`)
- `summarization_model` - LLM model for summarization (e.g., `gpt-4o`)
- `shared_with_project` - Share with project (default: `true`)
- `setting_id` - Integration reference (use `$ref:imported.integrations.name.id`)
- `force_reindex` - Force full reindex on deploy (default: `false`)

**Force Reindex:**
Set `force_reindex: true` to trigger a full reindex of the datasource on the next deployment, even if no configuration changes were detected. This is useful for:
- Updating the index with new commits from the repository
- Recovering from failed indexing
- Applying new embeddings model settings

After deployment, set it back to `false` to avoid unnecessary reindexing.

**Note:** Datasource creation starts background indexing. Check Codemie UI for indexing status.

> **📚 For detailed datasource examples**, see `examples/datasource-examples.yaml` with all available fields, descriptions, and common patterns.

### Reusing Prompts

Multiple assistants can share the same prompt file:

```yaml
assistants:
  - name: Production Bot
    prompt: system_prompts/shared.prompt.md
    model: gpt-4o
  
  - name: Development Bot (Copy)
    prompt: system_prompts/shared.prompt.md  # Same file
    model: gpt-4o-mini
```

**Use cases:**
- ✅ Creating test/staging copies of production assistants
- ✅ A/B testing with different models but same prompt
- ✅ Team-specific variants with shared core logic
- ✅ Backup/rollback scenarios

## 🔄 Common Workflows

### Adding a New Assistant

1. **Create prompt file:**
   ```bash
   touch system_prompts/my-new-assistant.prompt.md
   ```

2. **Add to `codemie.yaml`:**
   ```yaml
   resources:
     assistants:
       - name: My New Assistant  # Used as identifier (NO ID!)
         prompt: ./system_prompts/my-new-assistant.prompt.md
         description: "Description here"
         model: gpt-4o
         temperature: 0.7
         shared: true
         toolkits: []
         context: []
   ```

3. **Deploy:**
   ```bash
   npm run validate  # Check slug conflicts (if slug provided)
   npm run preview          # Preview changes
   npm run deploy        # Create assistant
   ```
   
   **✨ After deploy:**
   - `codemie.yaml` **remains unchanged** (no ID added)
   - `.codemie/state.json` is updated with name→ID mapping

### Updating an Assistant

1. **Edit the prompt file** or settings in `codemie.yaml`
2. **Run preview** to see changes:
   ```bash
   npm run preview
   ```
3. **Deploy:**
   ```bash
   npm run deploy
   ```

### Adding a New Workflow

1. **Create workflow YAML file:**
   ```bash
   touch workflows/my-workflow.yaml
   ```

2. **Define workflow** in `workflows/my-workflow.yaml`:
   ```yaml
   assistants:
     # Reference assistants by NAME (from codemie.yaml)
     - id: step1
       assistant_name: My Assistant
     - id: step2
       assistant_name: Another Assistant
   
   states:
     - id: first_step
       assistant_id: step1
       task: "Analyze: {{ user_input }}"
       output_schema: '{ "result": "string" }'
       next:
         state_id: second_step
     - id: second_step
       assistant_id: step2
       task: "Process: {{ result }}"
       output_schema: '{ "final": "string" }'
       next:
         state_id: end
   ```

3. **Add to `codemie.yaml`:**
   ```yaml
   resources:
     workflows:
       - name: My Workflow  # No ID yet
         description: "Workflow description"
         definition: ./workflows/my-workflow.yaml
         mode: Sequential
         shared: true
   ```

4. **Deploy:**
   ```bash
   npm run preview          # Preview changes
   npm run deploy        # Create workflow
   ```
   
   **✨ After deploy:**
   - `codemie.yaml` **remains unchanged** (no ID added)
   - `.codemie/state.json` is updated with name→ID mapping

## Scenarios

This section covers 18 real-world scenarios you'll encounter when managing resources with IaC.

### 📑 Quick Reference Table

| Scenario | What It Covers | Risk Level | Auto-Recovery |
|----------|---------------|------------|---------------|
| [1. Create New Assistant](#scenario-1-create-new-assistant) | Initial resource creation | ✅ Safe | N/A |
| [2. Update Assistant Prompt](#scenario-2-update-assistant-prompt) | Modify prompt content | ✅ Safe | N/A |
| [3. Update Assistant Config](#scenario-3-update-assistant-config) | Modify settings/toolkits | ✅ Safe | N/A |
| [4. Rename Assistant](#scenario-4-rename-assistant) | Delete old + create new | ⚠️ **Breaking** | ❌ No |
| [5. Delete Assistant](#scenario-5-delete-assistant) | Automatic cleanup | ⚠️ Destructive | ❌ No |
| [6. Sub-Assistants](#scenario-6-assistant-references-another-sub-assistants) | Dependency management | ✅ Safe | N/A |
| [7. Workflow References](#scenario-7-workflow-references-assistant) | Name-based resolution | ✅ Safe | N/A |
| [8. Imported Assistant](#scenario-8-workflow-references-imported-assistant) | External references | ✅ Safe | N/A |
| [9. Datasource Reference](#scenario-9-datasource-referenced-by-assistant) | Context linking | ✅ Safe | N/A |
| [10. Integration Reuse](#scenario-10-integration-used-by-multiple-resources) | `$ref` mechanism | ✅ Safe | N/A |
| [11. Manual Change](#scenario-11-manual-platform-change-detected) | Drift detection | ⚠️ Overwrites | ✅ Auto-reverts |
| [12. State Deleted](#scenario-12-statejson-deletedcorrupted) | Recovery options | 🔴 **Critical** | ❌ Manual fix |
| [13. Parallel Workflow](#scenario-13-parallel-workflow-in-gitlab-prevented) | CI/CD protection | ✅ Safe | N/A |
| [14. Field Transformation](#scenario-14-config-field-name-transformation) | SDK compatibility | ✅ Safe | N/A |
| [15. Missing Prompt](#scenario-15-prompt-file-missing) | Validation error | ✅ Safe | ❌ Manual fix |
| [16. Circular Dependency](#scenario-16-circular-dependency) | Validation error | ✅ Safe | ❌ Manual fix |
| [17. Nested Sub-Assistants](#scenario-17-nested-sub-assistants-not-allowed) | Platform limitation | ✅ Safe | ❌ Manual fix |
| [18. Missing Env Var](#scenario-18-environment-variable-missing) | Configuration error | ⚠️ Deploy fails | ❌ Manual fix |

### Scenario 1: Create New Assistant

**Config (codemie.yaml):**
```yaml
resources:
  assistants:
    - name: Code Reviewer
      prompt: system_prompts/code-reviewer.prompt.md
      model: gpt-4o
      description: Reviews code for best practices
```

**What happens:**
1. `npm run validate` - Checks prompt file exists
2. `npm run preview` - Shows "Create: 1 assistant"
3. `npm run deploy`:
   - Creates assistant via SDK
   - Gets UUID back from platform
   - Calculates checksums for prompt and config
   - Saves to state.json: `"Code Reviewer": { id: "uuid", promptChecksum: "...", configChecksum: "..." }`

### Scenario 2: Update Assistant Prompt

**Change:** Modify `system_prompts/code-reviewer.prompt.md`

**What happens:**
1. `npm run preview` - Detects prompt checksum changed
2. `npm run deploy`:
   - Recalculates prompt checksum
   - Compares with stored checksum → different
   - Calls `assistants.update(uuid, { ...config, system_prompt: newContent })`
   - Updates promptChecksum in state.json

### Scenario 3: Update Assistant Config

**Change:** Add toolkit to assistant in `codemie.yaml`

**What happens:**
1. `npm run preview` - Detects config checksum changed
2. `npm run deploy`:
   - Recalculates config checksum (based on all fields except prompt path)
   - Compares with stored checksum → different
   - Calls `assistants.update(uuid, newConfig)`
   - Updates configChecksum in state.json

### Scenario 4: Rename Assistant

**Change:** `name: Code Reviewer` → `name: Senior Code Reviewer`

**What happens:**
1. `npm run preview` - Shows "Delete: Code Reviewer, Create: Senior Code Reviewer"
2. `npm run deploy`:
   - Looks up "Senior Code Reviewer" in state.json → not found → treats as new resource
   - Creates "Senior Code Reviewer" with new UUID
   - Detects "Code Reviewer" is in state but not in config → orphaned
   - If `--prune` is NOT set:
     - Reports orphan but does NOT delete "Code Reviewer"
     - State now has both (but "Code Reviewer" is still tracked as orphan)
   - If `--prune` IS set:
     - Deletes "Code Reviewer" from platform
     - State now has only "Senior Code Reviewer"

**Note:** All references to old name break (e.g., in workflows). Update references before renaming.

### Scenario 5: Delete Assistant

**Change:** Remove assistant from `codemie.yaml`

**What happens:**
1. `npm run preview` - Shows "Delete: 1 assistant"
2. `npm run deploy`:
   - Detects assistant in state.json but not in config
   - If `--prune` IS set:
     - Deletes from platform using stored UUID
     - Removes from state.json
   - If `--prune` is NOT set:
     - Warns about orphaned resource
     - Assistant remains on platform and in state.json

### Scenario 6: Assistant References Another (Sub-Assistants)

**Config:**
```yaml
resources:
  assistants:
    - name: Data Validator
      prompt: system_prompts/validator.prompt.md
      model: gpt-4o-mini
    
    - name: Data Processor
      prompt: system_prompts/processor.prompt.md
      model: gpt-4o
      sub_assistants:
        - Data Validator  # Name reference, not UUID
```

**What happens:**
1. `npm run validate` - Checks "Data Validator" exists in config
2. `npm run deploy`:
   - Deploys assistants in order (Data Validator first, then Data Processor)
   - When deploying Data Processor:
     - Looks up "Data Validator" in state.json → gets UUID
     - Adds UUID to `assistant_ids` array for API call
   - Both assistants now in state.json

**Dependency order:** IaC automatically processes assistants in dependency order (sub-assistants before parents).

### Scenario 7: Workflow References Assistant

**Workflow YAML (workflows/my-workflow.yaml):**
```yaml
assistants:
  - id: reviewer
    assistant_name: Code Reviewer  # Name, not UUID

states:
  - id: review
    assistant_id: reviewer
    task: Review the code
    is_final: true
```

**Config (codemie.yaml):**
```yaml
resources:
  workflows:
    - name: Code Review Workflow
      definition: workflows/my-workflow.yaml
      mode: Sequential
```

**What happens:**
1. `npm run deploy`:
   - Loads workflow YAML
   - Finds `assistant_name: Code Reviewer`
   - Looks up in state.json → gets UUID
   - Replaces with `assistant_id: uuid`
   - Sends modified YAML to API
   - Stores workflow in state.json

### Scenario 8: Workflow References Imported Assistant

**Config:**
```yaml
imported:
  assistants:
    - id: external-assistant-uuid
      name: External Tool

resources:
  workflows:
    - name: My Workflow
      definition: workflows/workflow.yaml
```

**Workflow YAML:**
```yaml
assistants:
  - id: step1
    assistant_name: External Tool  # References imported assistant
```

**What happens:**
1. `npm run deploy`:
   - Looks up "External Tool" in state.json → not found
   - Looks up in `imported.assistants` → found with UUID
   - Uses that UUID for workflow
   - Deploys workflow successfully

### Scenario 9: Datasource Referenced by Assistant

**Config:**
```yaml
resources:
  datasources:
    - name: my-repo
      type: code
      link: https://git.example.com/repo
      setting_id: $ref:imported.integrations.git_connection.id
  
  assistants:
    - name: Code Assistant
      prompt: system_prompts/assistant.prompt.md
      model: gpt-4o
      context:
        - context_type: code
          name: my-repo  # Datasource name reference
```

**What happens:**
1. `npm run deploy`:
   - Deploys datasource first (dependency order)
   - Deploys assistant with context pointing to datasource name
   - Platform resolves datasource name to UUID internally

### Scenario 10: Integration Used by Multiple Resources

**Config:**
```yaml
imported:
  integrations:
    - alias: jira_conn
      id: jira-uuid
      credential_type: Jira

resources:
  datasources:
    - name: jira-data
      type: knowledge_base_jira
      jql: project = MY
      setting_id: $ref:imported.integrations.jira_conn  # Reference 1
  
  assistants:
    - name: Jira Bot
      toolkits:
        - toolkit: jira
          settings: $ref:imported.integrations.jira_conn  # Reference 2
```

**What happens:**
- During config load, both `$ref` are resolved to same integration object
- Changes to `jira_conn` automatically apply to all references
- No ID duplication in config

### Scenario 11: Manual Platform Change Detected

**Situation:** Someone manually edits assistant on platform (e.g., changes temperature)

**What happens:**
1. `npm run preview` - Compares config checksums with state
   - Prompt unchanged → prompt checksum matches
   - Config unchanged → config checksum matches
   - Shows "Unchanged: 0, Update: 0"
2. Manual change NOT detected (by design)
3. Next `npm run deploy` with ANY config change:
   - IaC pushes config version
   - Manual change overwritten

**Why?** Config is source of truth. IaC doesn't detect drift, only manages config→platform flow.

### Scenario 12: State.json Deleted/Corrupted

**What happens:**
1. `npm run preview` - Cannot find resources in state → treats all as new
   - Shows "Create: 10 assistants" (even though they exist)
2. `npm run deploy` - Attempts to create all resources
   - Platform rejects duplicates (if names conflict)
   - Or creates new resources with same names (depending on platform)

**Recovery:**
1. Restore state.json from Git history: `git checkout HEAD~1 -- .codemie/state.json`
2. Or manually reconstruct state by fetching UUIDs from platform and building state.json

### Scenario 13: Parallel Workflow in GitLab (Prevented)

**Setup:**
```yaml
deploy:
  resource_group: production  # KEY: Ensures sequential execution
```

**What happens:**
1. Developer A merges PR → triggers pipeline A
2. Developer B merges PR 10 seconds later → triggers pipeline B
3. GitLab sees `resource_group: production`:
   - Pipeline B waits for pipeline A to complete
   - No concurrent access to state.json
   - No race conditions

### Scenario 14: Config Field Name Transformation

**Config (what you write):**
```yaml
datasources:
  - name: my-repo
    type: code
    link: https://git.example.com/repo  # Config uses 'link'
    setting_id: $ref:...  # Config uses 'setting_id'
```

**What IaC does internally:**
- Reads `link` and `setting_id` from config
- API call unchanged (uses same fields)
- Backward compatibility: Also accepts `repository_url` → auto-converts to `link`

**Why?** Config field names match SDK/API expectations for consistency.

### Scenario 15: Prompt File Missing

**Config:**
```yaml
assistants:
  - name: My Bot
    prompt: system_prompts/missing.prompt.md  # File doesn't exist
```

**What happens:**
1. `npm run validate` - Checks file existence → fails
   ```
   Error: Prompt file not found: system_prompts/missing.prompt.md (referenced by assistant: My Bot)
   ```
2. Deployment blocked until file created

### Scenario 16: Circular Dependency

**Config:**
```yaml
assistants:
  - name: Assistant A
    sub_assistants: [Assistant B]
  - name: Assistant B
    sub_assistants: [Assistant A]  # Circular!
```

**What happens:**
1. `npm run validate` - DFS cycle detection → fails
   ```
   Error: Cyclic dependency detected: Assistant A → Assistant B → Assistant A
   ```
2. Deployment blocked until cycle removed

### Scenario 17: Nested Sub-Assistants (Not Allowed)

**Config:**
```yaml
assistants:
  - name: Helper
    sub_assistants: [Specialist]  # Helper has sub-assistant
  - name: Main
    sub_assistants: [Helper]  # Main uses Helper (which has sub-assistant)
```

**What happens:**
1. `npm run validate` - Detects nested sub-assistants → fails
   ```
   Error: Assistant "Helper" has sub-assistants but is itself used as a sub-assistant by: Main.
   Nested sub-assistants are not allowed.
   ```
2. Flatten hierarchy: Main should directly reference both Helper and Specialist

### Scenario 18: Environment Variable Missing

**Config:**
```yaml
environment:
  codemie_api_url: ${CODEMIE_API_URL}
```

**What happens if `CODEMIE_API_URL` not set:**
1. `npm run validate` - Env var substitution → empty string
2. Connection fails with unclear error
3. **Best practice:** Check required env vars at script start

## 🗄️ Backup & Restore

### Creating Backups

The backup tool creates a complete snapshot of ALL resources in your Codemie instance:

```bash
npm run backup
```

**What gets backed up:**
- ✅ **All Assistants** - Including prompts, toolkits, context, MCP servers, sub-assistants
- ✅ **All Datasources** - CODE, Confluence, Jira, Google Docs with full configuration
- ✅ **All Workflows** - YAML definitions, mode, and metadata
- ✅ **All Integrations** - Project integrations (IDs and configuration)
- ✅ **Complete State** - Full `state.json` with checksums for all resources

**Transaction Safety:**
- Atomic backup process with rollback on failure
- Resume capability - if backup is interrupted, rerunning continues from last checkpoint
- Temporary directory used during backup (`.temp-*`) - moved to final location only on success
- Progress tracking with `transaction.json` checkpoint file

**Output structure:**
```
backups/
└── 2025-10-22T14-30-45/     # Timestamp-based directory
    ├── backup.json          # Complete backup with all data
    ├── state.json           # State file (ready for IaC)
    ├── codemie.yaml         # Reconstructed IaC config
    ├── system_prompts/      # Individual prompt files
    │   ├── assistant-1.prompt.md
    │   └── assistant-2.prompt.md
    ├── workflows/           # Individual workflow files
    │   ├── workflow-1.yaml
    │   └── workflow-2.yaml
    └── openapi_specs/       # OpenAPI specifications (if any)
        ├── sumo-logic-api.yaml
        ├── gitlab-api.yaml
        └── coda-api.yaml
```

### Backup Contents

**1. backup.json** - Complete resource data
- Full details of all assistants, datasources, workflows, and integrations
- Used for selective restore or manual recovery

**2. state.json** - IaC state file
- Resource name → UUID mappings
- Checksums for change detection
- Ready to use with `npm run deploy`

**3. codemie.yaml** - Reconstructed IaC configuration
- Converts backup into IaC format
- References individual prompt/workflow files
- Includes all integrations in `imported` section
- MCP servers use integration aliasing (`settings: { $ref: imported.integrations.alias }`)

**4. system_prompts/** - Individual prompt files
- Each assistant's prompt as separate `.prompt.md` file

**5. workflows/** - Individual workflow definitions
- Each workflow as separate `.yaml` file

**6. openapi_specs/** - OpenAPI specifications (if any)
- Extracted from integrations and assistant toolkits
- Stored as separate files (YAML or JSON)
- File references used in codemie.yaml instead of embedding full specs

### Restore Options

#### Option 1: Full Restore via IaC (Recommended)

Best for disaster recovery or environment migration:

```bash
# 1. Copy backup to workspace
cp -r backups/2025-10-22T14-30-45/* /path/to/iac-workspace/

# 2. Review and adjust codemie.yaml
# - Update project name if needed
# - Update integration IDs for target environment
# - Remove resources you don't want to restore

# 3. Copy state file
cp state.json .codemie/state.json

# 4. Preview changes
npm run preview

# 5. Deploy
npm run deploy
```

**Important:**
- Integration IDs are environment-specific (create integrations first in target environment)
- Update `imported.integrations` section with new IDs
- Review datasource `setting_id` fields (must match target environment integrations)

#### Option 2: Selective Restore

Restore specific resources using `backup.json`:

```typescript
import { CodeMieClient } from 'codemie-sdk';
import * as fs from 'fs';

const backup = JSON.parse(fs.readFileSync('backup.json', 'utf8'));

// Restore specific assistant
const assistant = backup.resources.assistants.find(a => a.name === 'Code Reviewer');
await client.assistants.create({
  name: assistant.name,
  description: assistant.description,
  system_prompt: assistant.system_prompt,
  llm_model_type: assistant.llm_model_type,
  // ... other fields
});
```

#### Option 3: Manual Restore via UI

Use backup as reference to manually recreate resources:

1. Open `backup.json` in editor
2. For each resource:
   - Copy configuration fields
   - Create resource in Codemie UI
   - Paste prompt/workflow content
   - Configure toolkits/integrations

### Backup Best Practices

**Regular Backups**
```bash
# Daily backup (add to cron/CI)
0 2 * * * cd /path/to/iac && npm run backup

# Pre-deployment backup
npm run backup && npm run deploy
```

**Backup Retention**
```bash
# Keep last 30 days
find backups/ -type d -mtime +30 -exec rm -rf {} +
```

**Version Control**
- ✅ **Commit state.json** - Team visibility, CI/CD integration
- ❌ **Don't commit backups/** - Large files, sensitive data
- ✅ **Add to .gitignore**: `backups/`

**Sensitive Data**
- **SDK automatically masks credentials** - Integration credentials appear as `"**********"` in backups
- **Store backups securely** - Use encrypted storage and access control (backups contain prompts, configurations, and may contain other sensitive data)

### Backup vs State.json

| Feature | backup.json | state.json |
|---------|------------|------------|
| **Content** | Full resource data | IDs + checksums only |
| **Size** | Large (prompts, configs) | Small (metadata) |
| **Use Case** | Disaster recovery, migration | Normal IaC operations |
| **Git** | ❌ Don't commit | ✅ Commit |
| **Portability** | ✅ Standalone | ❌ Requires codemie.yaml |

### Troubleshooting

**Issue: Backup interrupted**
- Just run `npm run backup` again - it will resume from last checkpoint
- Transaction file (`transaction.json`) tracks progress
- Temporary directory (`.temp-*`) will be cleaned up automatically

**Issue: Backup failed completely**
- Check `.temp-*` directory exists - if yes, partial backup was attempted
- Error message will indicate which resource failed
- Temporary directory will be automatically cleaned up (rollback)
- Fix the issue and rerun backup

**Issue: Want to force fresh backup (skip resume)**
- Delete `transaction.json` from temporary directory before rerunning
- Or delete entire `.temp-*` directory to start from scratch

**Issue: Backup fails with "Not Found" error**
- Check API credentials in `.env`
- Verify service account has access to all resources
- Some resources may have been deleted on platform

**Issue: Integration IDs don't match after restore**
- Integrations are environment-specific
- Create integrations in target environment first
- Update `imported.integrations` with new IDs

**Issue: Large backup file size**
- Normal for many assistants with large prompts
- Consider selective backup if needed
- Backup tool fetches full resource details

**Issue: Code datasource missing repository link**
- Some code datasources may show warning during backup
- SDK sometimes doesn't return repository URL
- Manually add `link: https://github.com/...` in restored codemie.yaml

**Issue: Workflow assistant IDs not resolved to names**
- If workflow YAML contains `assistant_id: ast-xxx` instead of assistant name
- This happens when assistant doesn't exist in backup (e.g., deleted or from another project)
- Manually replace with correct assistant name in workflow YAML file

## Advanced Topics

### Deployment Order

Resources are deployed in dependency order:

1. **Datasources** - No dependencies, can be created first
2. **Sub-Assistants** - May reference datasources via `context`
3. **Main Assistants** - May reference sub-assistants and datasources
4. **Workflows** - Reference assistants

**Implementation:** Sequential processing in `src/deploy.ts`. Dependencies validated at validation time.

### Reusing Prompts

Multiple assistants can share the same prompt file:

```yaml
assistants:
  - name: Production Bot
    prompt: system_prompts/shared.prompt.md
    model: gpt-4o
  
  - name: Development Bot (Copy)
    prompt: system_prompts/shared.prompt.md  # Same file
    model: gpt-4o-mini
```

**Use case:** Testing variations (different models, temperatures) with same prompt.

### Finding Assistants for Import

To reference existing platform assistants in workflows:

**API Endpoints:**
- **List Assistants**: `GET /v1/assistants?per_page=100&project=project-name`
- **Get Assistant by ID**: `GET /v1/assistants/id/{id}` (⚠️ 404 if assistant doesn't exist!)

**Example: Finding Assistants by Name**

```typescript
import axios from 'axios';

async function findAssistants(token: string, keywords: string[]) {
  const url = `${CODEMIE_API_URL}/v1/assistants`;
  const response = await axios.get(url, {
    headers: { 'Authorization': `Bearer ${token}` },
    params: { per_page: 100, project: 'my-project' }
  });
  
  const assistants = response.data.assistants || response.data.data || response.data;
  
  // Filter by keywords
  return assistants.filter((a: any) => {
    const name = (a.name || '').toLowerCase();
    return keywords.some(k => name.includes(k.toLowerCase()));
  });
}

// Usage
const matches = await findAssistants(token, ['test', 'checklist', 'jira']);
matches.forEach((a: any) => {
  console.log(`• ${a.name} (ID: ${a.id}, Slug: ${a.slug || 'N/A'})`);
});
```

**Adding to imported.assistants:**

```yaml
# After finding the assistant IDs
imported:
  assistants:
    - id: 00000000-0000-0000-0000-000000000007  # From API
      name: Checklist Generator Assistant          # Exact name from API
    - id: 00000000-0000-0000-0000-000000000009
      name: Jira Test Management Assistant
```

**⚠️ Important:**
- **Assistant must exist on platform** - IaC will fail with 404 if ID is invalid
- **Use exact names** - Workflow resolution is case-sensitive
- **Verify access** - Service account must have permission to use the assistant
- **Check regularly** - Imported assistants can be deleted by their owners

### Working with Codemie API Directly

If you need to fetch assistant or datasource data directly from the API:

**API Endpoints:**
- **Get Assistant by ID**: `GET /v1/assistants/id/{id}`
- **List Datasources**: `GET /v1/index?filters={"project":["project-name"]}`

**Important Field Mappings:**

When reading datasources from API:
- API returns `repo_name` → Use as `name` in config
- API returns `index_type` → Use as `type` in config
- API returns `link` → Use as `link` in config (Git repository URL)
- API returns `setting_id` → Use as `setting_id` in config (integration ID)

When deploying datasources from config:
- Config `link` → API `link` (no mapping needed)
- Config `setting_id` → API `setting_id` (no mapping needed)
- For Jira: Config `jql` → API `jql` (flat structure)
- For Confluence: Config `cql` → API `cql` (flat structure)

**Example: Fetching Assistant Data**

```typescript
// Get token
const tokenUrl = `${CODEMIE_AUTH_URL}/realms/${CODEMIE_REALM}/protocol/openid-connect/token`;
const params = new URLSearchParams({
  grant_type: 'client_credentials',
  client_id: CODEMIE_CLIENT_ID,
  client_secret: CODEMIE_CLIENT_SECRET,
});
const tokenResponse = await axios.post(tokenUrl, params);
const token = tokenResponse.data.access_token;

// Get assistant
const assistantUrl = `${CODEMIE_API_URL}/v1/assistants/id/${assistantId}`;
const response = await axios.get(assistantUrl, {
  headers: { 'Authorization': `Bearer ${token}` },
});
```

### Mass Datasource Creation

When creating many datasources (30+), consider:

1. **Generate from API data** - Use scripts to fetch existing datasources and generate config
2. **Use consistent naming** - Add suffix like `-copy` to avoid conflicts
3. **Validate repository URLs** - Ensure all Git URLs are accessible
4. **Monitor deployment** - Large datasource deployments can take 10+ minutes

### Using Integration References

Integrations can be referenced in:
- Datasource `setting_id`
- Toolkit `settings`
- Tool `settings` (within toolkit)

**Pattern:**
```yaml
imported:
  integrations:
    - alias: my_integration
      id: uuid
      credential_type: Jira

# Reference in datasource
resources:
  datasources:
    - setting_id: $ref:imported.integrations.my_integration.id

# Reference in assistant toolkit
  assistants:
    - toolkits:
        - toolkit: jira
          settings: $ref:imported.integrations.my_integration
```

### Workflow Deployment Errors

**Error:** "Workflow assistant reference must have 'assistant_name'"

**Cause:** Workflow YAML has assistant without `assistant_name` field

**Fix:** Add `assistant_name` to reference existing assistant, or define inline assistant with `model` + `system_prompt` (which doesn't require `assistant_name`)

---

**Error:** "Assistant 'X' not found in state or imported"

**Cause:** Referenced assistant doesn't exist yet

**Fix:**
1. Deploy assistant first, OR
2. Add to `imported.assistants` if it already exists on platform

## Backup & Migration Notes

### Field Compatibility

When creating backups or migrating between environments, the system automatically handles field name conversions between the platform API and IaC configuration format:

**Common conversions:**
- API `llm_model_type` ↔ Config `model`
- API `system_prompt` ↔ Config `prompt` (file path)
- API `yaml_config` ↔ Config `definition` (file path)

**Datasource field conversions:**
- API nested structure (e.g., `code.indexType`) ↔ Config flat structure (`index_type`)
- Some fields use camelCase in API but snake_case in config for consistency

**What this means for you:**
- ✅ Backups preserve all data correctly
- ✅ Migration between environments works seamlessly
- ✅ You don't need to manually convert field names

## Architecture

### SDK Integration Patterns

#### Pattern 1: API Field Transformations

Config field names are transformed to match SDK/API:

| Config Field          | API Field        | Notes                    |
|-----------------------|------------------|--------------------------|
| `model`               | `llm_model_type` | LLM model name           |
| `link`                | `link`           | Git datasource URL       |
| `setting_id`          | `setting_id`     | Integration reference    |
| `jql` (top-level)     | `jql`            | Jira query               |
| `cql` (top-level)     | `cql`            | Confluence query         |

**Note:** Datasource config uses flat structure. Nested `jira.jql` is legacy (auto-converted).

#### Pattern 2: Workflow Assistant Resolution

1. Parse workflow YAML
2. For each `assistant_name`:
   - Lookup in `state.json` (IaC-created)
   - Fallback to `imported.assistants` (platform-existing)
3. Replace with `assistant_id` UUID
4. Send to API

### Dependency Validation

**Cycle Detection:** DFS algorithm traverses sub-assistant graph, detects cycles

**Nested Sub-Assistant Detection:** Builds set of all assistants used as sub-assistants, checks if any have their own sub-assistants

### Orphaned Resource Detection

1. Load state.json resources: `{ assistants: { "A": {...}, "B": {...} } }`
2. Load config resources: `[ { name: "A" }, { name: "C" } ]`
3. Compare: B is in state but not in config → orphaned
4. Delete B from platform, remove from state


## Troubleshooting

### "Environment variable not set" or "Connection failed"

**Cause:** Missing or incorrect environment variables

**Fix:**
1. Check that `.env` file exists in project root
2. Verify all required variables are set:
   ```bash
   cat .env  # View your .env file
   ```
3. Ensure variable names match exactly (case-sensitive):
   - `CODEMIE_API_URL`
   - `CODEMIE_AUTH_URL`
   - `CODEMIE_REALM`
   - `CODEMIE_CLIENT_ID`
   - `CODEMIE_CLIENT_SECRET`
4. No quotes needed around values in `.env`
5. Restart your terminal/shell after creating `.env`

### "Validation Error: Field required"

**Cause:** API expects field not provided in config

**Fix:** Check `examples/*.yaml` for required fields per resource type

### "Assistant created but not found by name"

**Cause:** Multiple assistants with same name, or creation failed silently

**Fix:**
1. Check platform for duplicates
2. Use unique names
3. If SDK issue persists, contact support

### "Datasource name cannot be changed"

**Platform limitation:** Datasource names are immutable after creation

**Workaround:**
1. Delete old datasource: Remove from config, deploy
2. Create new with desired name

### "State.json out of sync"

**Symptoms:** Preview shows unexpected changes, or creates/deletes wrong resources

**Diagnosis:**
```bash
# Check what's in state
cat .codemie/state.json | jq '.resources'

# Check what's in config
npm run validate
```

**Fix:** If state is wrong, restore from Git or manually reconstruct

### "Checksum mismatch but no changes"

**Cause:** Line ending differences (CRLF vs LF), file encoding

**Fix:**
1. Normalize line endings: `git config core.autocrlf input`
2. Re-save prompt files with consistent encoding (UTF-8)
3. Redeploy to update checksums

### "Workflow Configuration error"

**Cause:** Invalid workflow YAML structure or missing assistant references

**Common Issues:**

**1. Referenced assistant doesn't exist (404)**
```
Error: Failed to deploy workflow: Assistant not found
```

**Solution:**
- Verify assistant exists on platform
- Add to `imported.assistants` if it's platform-managed
- Ensure assistant is deployed first if it's IaC-managed

```yaml
# Add to codemie.yaml
imported:
  assistants:
    - id: 00000000-0000-0000-0000-000000000003
      name: Exact Assistant Name  # Must match platform exactly
```

**2. Invalid retry_policy fields**
```
Error: Workflow Configuration error
```

**Solution:**
Use correct field names in workflow YAML:
```yaml
# ❌ Wrong
retry_policy:
  initial_interval_seconds: 1
  max_interval_seconds: 10

# ✅ Correct
retry_policy:
  initial_interval: 1
  max_interval: 10
```

**3. Mixed assistant reference types**
```
Error: Workflow assistant must have either assistant_name or model
```

**Solution:**
Don't mix `assistant_name` with `model`/`system_prompt`:
```yaml
assistants:
  # ❌ Wrong - mixing external reference with inline definition
  - id: step1
    assistant_name: My Assistant
    model: gpt-4o  # Remove this!
  
  # ✅ Correct - external reference
  - id: step1
    assistant_name: My Assistant
  
  # ✅ Correct - inline definition
  - id: step2
    model: gpt-4o-mini
    name: Parser
    system_prompt: "You are a parser..."
```

### "Assistant 'X' not found in state or imported"

**Cause:** Workflow references assistant that doesn't exist in IaC configuration

**Solution:**

**Option 1: Import the assistant**
```yaml
# codemie.yaml
imported:
  assistants:
    - id: uuid-from-platform  # Get from Codemie UI → Assistants → Copy ID
      name: Exact Assistant Name  # Case-sensitive!
```

**Option 2: Deploy assistant first**
```yaml
# codemie.yaml
resources:
  assistants:
    - name: My Assistant  # Must match workflow reference exactly
      prompt: ./system_prompts/assistant.prompt.md
      model: gpt-4o
```

**Verification:**
```bash
# Check configuration
npm run validate

# Verify assistant name matches
grep -A 2 "assistant_name:" workflows/*.yaml
grep "name:" codemie.yaml
```

## CI/CD Integration

Example GitLab CI/CD pipeline:

```yaml
stages:
  - validate
  - preview
  - deploy

# Basic validation (feature branches, MRs) - fast, no API connection
validate:basic:
  stage: validate
  script:
    - npm install
    - npm run validate:basic
  rules:
    - if: '$CI_COMMIT_REF_NAME == "master"'
      when: never
    - when: always

# Full validation (master branch) - includes API connectivity check
validate:full:
  stage: validate
  script:
    - npm install
    - npm run validate
  rules:
    - if: '$CI_COMMIT_REF_NAME == "master"'
      when: always
    - when: never

preview:
  stage: preview
  script:
    - npm install
    - npm run preview
  rules:
    - if: '$CI_COMMIT_REF_NAME == "master"'
      changes:
        - codemie.yaml          # Main IaC configuration
        - system_prompts/**/*   # Assistant prompts
        - workflows/**/*        # Workflow definitions
      when: always

deploy:
  stage: deploy
  resource_group: production  # Sequential execution
  script:
    - npm install
    - npm run deploy -- --prune
  after_script:
    - |
      if [ -n "$(git status --porcelain .codemie/state.json)" ]; then
        git config user.name "GitLab CI"
        git config user.email "ci@gitlab.com"
        git add .codemie/state.json
        git commit -m "chore: Update IaC state [skip ci]"
        git push https://gitlab-ci-token:${RUNNER_CLONE_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git HEAD:${CI_COMMIT_REF_NAME}
      fi
  rules:
    - if: '$CI_COMMIT_REF_NAME == "master"'
      changes:
        - codemie.yaml          # Main IaC configuration
        - system_prompts/**/*   # Assistant prompts
        - workflows/**/*        # Workflow definitions
      when: manual
```

**Key points:**
- **Two-tier validation:** 
  - `validate:basic` runs for feature branches (fast, no credentials needed)
  - `validate:full` runs for master after merge (full API checks)
- `resource_group: production` ensures sequential deploys (no state conflicts)
- `after_script` commits updated state.json back to repo
- `[skip ci]` prevents infinite pipeline loop
- `changes:` triggers deploy only for resource configuration files (not for IaC tool code in `src/`)

## Team Collaboration

### Git Workflow for IaC Changes

**1. Create Feature Branch**
```bash
git checkout -b feature/update-assistant-prompt
```

**2. Make Changes**
- Edit prompts in `system_prompts/`
- Update configuration in `codemie.yaml`
- Add new workflows in `workflows/`

**3. Test Locally**
```bash
npm run validate:basic  # Quick syntax check (no API connection)
npm run validate        # Full validation with API checks (optional)
npm run preview            # Preview changes
```

**4. Create Pull Request**

**What happens in CI (for feature branches):**
- ✅ **Validate stage** - Basic validation (YAML syntax, file existence, dependencies) - no API connection required
- ✅ **Preview stage** - Shows deployment preview in MR comments

**5. Review Process**
- Team reviews prompt changes
- Verify deployment preview looks correct
- Check that no unintended resources will be deleted
- Approve MR

**6. Merge to Main**

**What happens after merge to master:**
- ✅ Full validation runs (with API connectivity check)
- ✅ GitLab CI automatically deploys changes
- ✅ State.json is updated and committed back
- ✅ All changes are live on Codemie platform

### Best Practices for Team Collaboration

**1. Commit state.json to Git**
- Essential for team to see current deployment state
- Enables accurate deployment previews
- Provides audit trail

**2. Use descriptive branch names**
```bash
# Good
feature/add-code-review-assistant
fix/update-jira-datasource-query
chore/update-all-assistant-models

# Not helpful
feature/changes
fix/update
```

**3. Small, focused changes**
- One assistant per MR
- Related changes together (assistant + datasource)
- Easier to review and rollback

**4. Review deployment preview**
- Always check `preview` output before merging
- Watch for unexpected deletions
- Verify resource counts

**5. Sequential deployments**
- GitLab `resource_group: production` ensures one deploy at a time
- No state conflicts
- No race conditions

**6. Document breaking changes**
- Renaming assistants breaks references
- Workflow changes may affect users
- Note in MR description

### Handling State Conflicts

**Scenario:** Two team members work on different features simultaneously

**Branch A:** Adds Assistant 1
**Branch B:** Adds Assistant 2

**What happens:**
1. Branch A merges first → state.json updated with Assistant 1
2. Branch B tries to merge → **Git conflict in state.json**
3. Manual resolution needed:
   ```json
   {
     "assistants": {
       "Assistant 1": { "id": "uuid-1", ... },
       "Assistant 2": { "id": "uuid-2", ... }  // Keep both!
     }
   }
   ```
4. After resolving, run `npm run deploy` to verify

**Prevention:**
- Keep feature branches short-lived
- Sync with main frequently
- Use `resource_group` in CI/CD (enforces sequential execution)

## Development

### Architecture & Code Organization

This project follows clean separation between business logic and CLI execution:

**Core Logic (`src/`)** - All main functionality is implemented in testable modules:
- `deploy.ts` - Deployment logic (creates/updates resources)
- `backup.ts` - Backup logic (downloads all resources)
- `destroy.ts` - Destroy logic (deletes all managed resources)
- `preview.ts` - Preview logic (shows what will change)
- `validate.ts` - Validation logic (checks configuration correctness)

Each module exports a `main()` function containing the full business logic. These functions are pure and testable - they don't execute automatically on import.

**CLI Entry Point (`src/cli/`)** - Unified router for all commands:
- `index.ts` - Routes commands to appropriate handlers with type-safe command registry

These files are the only ones that call `process.exit()` and contain shebangs.

**Library Code (`src/lib/`)** - Reusable utility modules with high test coverage (>89%):
- Configuration loading, state management, API clients
- Resource converters, validators, dependency resolution
- Retry logic, rate limiting, transaction management

**Testing Strategy:**
- All library code in `src/lib/` has extensive unit test coverage
- Core logic modules export their functions for testing
- Tests can import and test individual functions without triggering CLI execution
- CLI entry points are thin and don't need unit tests
- Coverage metrics (89%+) reflect actual code quality

**Benefits:**
- ✅ Testability: All business logic can be imported and tested without side effects
- ✅ Reusability: Core functions can be imported by other Node.js projects
- ✅ Maintainability: Clear separation between CLI concerns and business logic
- ✅ Linting: ESLint rule "no-process-exit" only applies to library code, not CLI wrappers

```bash
# Build TypeScript
npm run build

# Type checking
npm run type-check

# Clean build artifacts
npm run clean

# Run tests
npm test

# Run tests with coverage
npm test -- --coverage
```

## License

Copyright © 2025 CodeMie Team
