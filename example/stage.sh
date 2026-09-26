#!/usr/bin/env bash
# Turn example/private-app into a throwaway git repository. The pipeline
# exports from a git ref, never from disk, and the fixture ships as plain files
# because a nested .git would be a submodule of the repository around it.
# Idempotent: run it again after editing anything under private-app/.
set -euo pipefail
cd "$(dirname "$0")"

DEST=".stage/private-app"
rm -rf "$DEST"
mkdir -p "$DEST"
cp -a private-app/. "$DEST/"

git -C "$DEST" init -q -b main
git -C "$DEST" add -A
git -C "$DEST" \
  -c user.name="Alex Doe" \
  -c user.email="alex@riverbend.example" \
  -c commit.gpgsign=false \
  commit -q -m "acme-cycle-rentals at the point it was exported"

echo "staged $(git -C "$DEST" ls-files | wc -l) tracked files in example/$DEST"
