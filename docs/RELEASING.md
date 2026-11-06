# Releasing

`@codemieai/cdk` is released by the GitHub Actions workflow `publish.yml`. A release starts when someone with write access publishes a GitHub Release whose tag names the version.

| Package | Registry | Workflow | Tag |
|---------|----------|----------|-----|
| `@codemieai/cdk` (`iac/codemie-iac-nodejs`) | npm | `publish.yml` | `cdk-vX.Y.Z` or `cdk-vX.Y.Z-rcN` |

`codemie-iac-python` (`iac/codemie-iac-python`) is not published. CI checks and builds it, nothing more.

A merge to `main` never releases the package. A tag with another prefix does not start the workflow.

## How to release

1. Merge the changes you want to release to `main`. Wait for CI to pass.
2. Choose the version. It must be higher than the highest version on npm and on the line in `iac/codemie-iac-nodejs/package.json` (see below).
3. Create the Release. Use **Publish release**: **Save draft** does not start a workflow.
   - UI: Releases > Draft a new release > choose a new tag such as `cdk-v0.2.1`, target `main` > Publish release.
   - CLI: `gh release create cdk-v0.2.1 --target main --generate-notes`
4. Open the run in the Actions tab. `verify` builds and checks. `publish` waits for approval if the `release` environment has reviewers.

## How versions work

The tag is the version: `cdk-v0.2.1` releases `0.2.1`. `iac/codemie-iac-nodejs/package.json` holds only the base line, `MAJOR.MINOR.0`. It is `0.2.0` today.

- The tag must be `MAJOR.MINOR.PATCH` on the same `MAJOR.MINOR` line as `package.json`. The only pre-release form is `-rcN`, for example `cdk-v0.2.1-rc1`: it is published under the npm dist-tag `rc`, so `latest` is not changed. A missing part or a leading zero fails.
- The workflow stamps the version into the build only. It does not commit a version change.
- To start a new line, raise the base in `package.json`, for example to `0.3.0`, and merge it. Then tag `cdk-v0.3.0`.
- Runs are grouped by tag, so a release is never cancelled by a newer one.

## Checks before anything is published

The `verify` job has no secrets. It fails, and nothing is published, when:

- the tagged commit is not on `main`;
- for a manual publish, the tag does not exist or does not point to the dispatched commit;
- the tag prefix, format or line does not match;
- the version is equal to or lower than the highest published version (`check_version.py` from `codemie-ai/ci-workflows`);
- lint, tests or the build fail.

The `publish` job runs the version check again right before the upload, because it can wait for approval and another release may land in between.

`check_version.py` compares the version with the live npm registry. The scoped name `@codemieai/cdk` is URL-encoded for the registry request.

- A package that is not on the registry yet (HTTP 404) has no latest version. The check passes.
- A timeout, network error, malformed registry response or a published version that cannot be parsed stops the release. The gate fails closed.

Run it locally:

```bash
curl -fsSL https://raw.githubusercontent.com/codemie-ai/ci-workflows/main/scripts/release/check_version.py \
  | python3 -I - --ecosystem npm --name @codemieai/cdk --version 0.2.1
```

Read the version from a release tag and check its format and baseline (does not contact npm):

```bash
curl -fsSL https://raw.githubusercontent.com/codemie-ai/ci-workflows/main/scripts/release/check_version.py \
  | python3 -I - --ecosystem npm --name @codemieai/cdk --tag cdk-v0.2.1 --base 0.2.0 --tag-prefix cdk-v
```

## Dry run

Start `publish.yml` with `workflow_dispatch` and give the `tag` input. Keep `dry_run` on. The workflow builds the package, runs the version gate and packs `codemieai-cdk-<version>.tgz` as an artifact. Nothing is published.

To publish from a manual run, set `dry_run` off, type `publish` in the `publish` input, and start the run from `main`. The tag must exist and point to the commit the run uses. A manual publish creates no Release, so use a Release for real releases.

## Admin prerequisites

An administrator does these steps once. This document only lists them.

- **Repository.** Create the public repository `codemie-ai/codemie-cdk`.
- **GitHub environment `release`.** Create it in Settings > Environments. Restrict deployments to the tag `cdk-v*` (and `main` for a manual publish). Add required reviewers if a second approval is wanted.
- **Who can release.** Only people with write access can create a Release. Keep that group small.
- **npm trusted publisher.** The workflow publishes with OpenID Connect, so no npm token is stored. In the npm settings of `@codemieai/cdk`, add a trusted publisher: repository `codemie-ai/codemie-cdk`, workflow `publish.yml`, environment `release`. Only the `publish` job has the `id-token: write` permission.
- **First commit.** Push the first exported snapshot to the new repository as a single commit. The export carries no history.
