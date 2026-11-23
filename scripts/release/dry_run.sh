#!/usr/bin/env bash
# Local dry run of a release: reads the live registry, stamps a COPY of the package, builds it.
# Publishes nothing and needs no credentials. Usage: scripts/release/dry_run.sh python|node TAG   (TAG: cdk-python-vX.Y.Z or cdk-vX.Y.Z)
set -euo pipefail

kind="${1:-}"
tag="${2:-}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CI_WORKFLOWS_REF="${CI_WORKFLOWS_REF:-main}"
check_url="https://raw.githubusercontent.com/codemie-ai/ci-workflows/${CI_WORKFLOWS_REF}/scripts/release/check_version.py"
# Run check_version.py from ci-workflows without saving it. pipefail makes a failed download fail the call.
check() { curl -fsSL "$check_url" | python3 -I - "$@"; }

case "$kind" in
  python) pkg=iac/codemie-iac-python; eco=pypi; name=codemie-cdk-python; prefix=cdk-python-v ;;
  node) pkg=iac/codemie-iac-nodejs; eco=npm; name=@codemieai/cdk; prefix=cdk-v ;;
  *) echo "usage: $0 python|node TAG" >&2; exit 2 ;;
esac
[ -n "$tag" ] || { echo "usage: $0 python|node TAG" >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
rsync -a --exclude node_modules --exclude .venv --exclude dist --exclude __pycache__ "$root/$pkg/" "$work/"
cd "$work"

if [ "$kind" = python ]; then
  base="$(poetry version --short)"
else
  base="$(node -p "require('./package.json').version")"
fi
version="$(check --ecosystem "$eco" --name "$name" --tag "$tag" --base "$base" --tag-prefix "$prefix")"
echo "base $base, tag $tag -> release $version"

if [ "$kind" = python ]; then
  poetry version "$version" >/dev/null
  poetry install --no-interaction
  poetry run ruff check .
  poetry run ruff format --check .
  poetry run pytest tests/
else
  npm version "$version" --no-git-tag-version --allow-same-version >/dev/null
  npm install --no-audit --no-fund
  npm run lint
  npm test
  npm run build
fi

check --ecosystem "$eco" --name "$name" --version "$version"

if [ "$kind" = python ]; then
  poetry build
  ls dist
else
  mkdir -p "$work/pack"
  npm pack --pack-destination "$work/pack" >/dev/null
  ls "$work/pack"
fi
echo "dry run ok: $name $version would be released (nothing published)"
