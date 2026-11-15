#!/bin/bash
# Build the site from data/ and publish it to the gh-pages branch, which GitHub Pages serves.
# Usage: scripts/publish.sh            (set COMMIT_TRAILER to add attribution lines to the commit)
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pytest -q
rm -rf _site
python3 -m build.build --out _site

WT="$(mktemp -d)"
trap 'git worktree remove --force "$WT" 2>/dev/null || true' EXIT
if git ls-remote --exit-code --heads origin gh-pages >/dev/null 2>&1; then
  git fetch -q --depth 1 origin "+refs/heads/gh-pages:refs/remotes/origin/gh-pages"
  git worktree add -q -B gh-pages "$WT" origin/gh-pages
else
  git worktree add -q --detach "$WT"
  git -C "$WT" checkout -q --orphan gh-pages
  git -C "$WT" rm -rfq --cached . >/dev/null 2>&1 || true
fi
find "$WT" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a _site/. "$WT"/

git -C "$WT" add -A
if git -C "$WT" diff --cached --quiet; then
  echo "Site unchanged; nothing to publish."
else
  git -C "$WT" commit -q -m "Publish site $(date -u +%F)" ${COMMIT_TRAILER:+-m "$COMMIT_TRAILER"}
  git -C "$WT" -c push.negotiate=true push -q origin gh-pages
  echo "Published: $(git -C "$WT" rev-parse --short HEAD) -> gh-pages"
fi
