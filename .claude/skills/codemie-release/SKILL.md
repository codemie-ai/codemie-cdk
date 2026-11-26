---
name: codemie-release
description: Release a package of codemie-cdk to PyPI and npm. Use when the user says "release", "publish a version", "cut a release" or "make an rc". Checks the repo, picks the next version from the registry, runs a dry run, writes release notes and creates the GitHub Release that starts the publish workflow.
---

# CodeMie release for codemie-cdk

A release starts when a GitHub Release is published. The workflow builds, checks and publishes the package. The tag is the version. The manifest holds only the base line `MAJOR.MINOR.0` and is never changed by a release. Read `docs/RELEASING.md` for the full rules.

**Never publish the GitHub Release without an explicit "yes" from the user.** It publishes the package to a public registry. This cannot be undone.

## Packages

| Package | Registry | Tag prefix | Directory | Manifest | Workflow |
|---------|----------|------------|-----------|----------|----------|
| `codemie-cdk-python` | PyPI | `cdk-python-v` | `iac/codemie-iac-python` | `pyproject.toml` | `publish-python.yml` |
| `@codemieai/cdk` | npm | `cdk-v` | `iac/codemie-iac-nodejs` | `package.json` | `publish.yml` |

## 1. Pre-flight

Stop and tell the user if a check fails.

```bash
git branch --show-current          # must be main
git status --porcelain             # must be empty
git fetch origin && git rev-list --left-right --count HEAD...origin/main   # must be "0 0"
gh run list --branch main --limit 3 --json conclusion,workflowName,headSha # CI on HEAD must be success
gh auth status
```

Ask which package to release if the user did not say.

## 2. Choose the version

1. Read the base line from the manifest.
   ```bash
   grep -m1 '^version' iac/codemie-iac-python/pyproject.toml                   # Python
   node -p "require('./iac/codemie-iac-nodejs/package.json').version"          # Node.js
   ```
2. Read the latest published version.
   ```bash
   curl -s https://pypi.org/pypi/codemie-cdk-python/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"
   npm view @codemieai/cdk version
   npm view @codemieai/cdk dist-tags      # rc versions live under the rc tag
   ```
3. Propose the next version:
   - Same `MAJOR.MINOR` as the base line: latest + 1 patch.
   - Registry on an older line than the base line: `MAJOR.MINOR.0` of the base line.
   - Release candidate: `-rcN` on the next version, with N one higher than the last rc of that version.
4. A new minor or major line needs the base raised in the manifest first, and merged. Stop and say so.
5. Show: package, base line, latest on the registry, proposed tag. Ask the user to confirm or give another version.

The tag is `<prefix>X.Y.Z` or `<prefix>X.Y.Z-rcN`. The workflow fails closed if the version is not higher than the registry.

## 3. Dry run

Run the local dry run. It needs no credentials and publishes nothing. Python needs `poetry`, Node.js needs `node` and `npm`.

```bash
scripts/release/dry_run.sh python cdk-python-vX.Y.Z
scripts/release/dry_run.sh node cdk-vX.Y.Z
```

If the dry run fails, stop. Report the failing step. Do not continue.

## 4. Release notes

Find the previous tag of this package. For a stable release skip `-rc` tags. For an rc use the previous tag of any kind.

```bash
PREV=$(git tag -l '<prefix>*' --sort=-v:refname | grep -v -- '-rc' | head -1)   # stable
git log --pretty='%s' ${PREV:+$PREV..HEAD} -- iac/codemie-iac-python      # or iac/codemie-iac-nodejs
```

Only list commits that touch the package. Group them by the commit prefix: `feat`, `fix`, `perf`, `refactor`, `docs`, `chore`. Put breaking changes first (`BREAKING CHANGE:` in a commit body). Keep PR numbers. Do not put internal URLs, ticket keys or customer names in the notes.

```markdown
## What's changed

### Features
- Description (#PR)

### Bug fixes
- Description (#PR)

**Full changelog**: https://github.com/codemie-ai/codemie-cdk/compare/<PREV>...<TAG>
```

Show the notes to the user.

## 5. Publish the Release

After the user says "yes" to the tag and the notes:

```bash
gh release create <TAG> --target main --title "<TAG>" --notes "<NOTES>" [--prerelease for an rc]
```

Do not save a draft: a draft does not start the workflow. Skip this step if `gh release view <TAG>` shows the release already.

## 6. After the release

```bash
gh run list --workflow publish-python.yml (Python) or publish.yml (Node.js) --limit 3
gh run watch            # pick the run of the new tag
```

`publish` may wait for approval if the `release` environment has reviewers. Tell the user. When the run is green, check the registry:

```bash
pip index versions codemie-cdk-python | head -1
npm view @codemieai/cdk version
```

Report the tag, the run URL, the registry link and the install command.

## If something fails

- `verify` fails: read the log, fix on `main`, then use a **new** tag. Never re-use or move a tag of a published version.
- Tag is wrong and nothing is published yet: `gh release delete <TAG> --cleanup-tag --yes`, after the user agrees.
- A published version cannot be changed. Release a higher patch version instead.
