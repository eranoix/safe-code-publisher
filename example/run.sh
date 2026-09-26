#!/usr/bin/env bash
# Build the example's public tree with the real lib/, using the example's own
# manifest, identity map and transformations, then gate it.
set -euo pipefail
cd "$(dirname "$0")/.."          # repository root

./example/stage.sh

python3 lib/scrub.py acme-cycle-rentals \
    --manifest   example/manifest.yaml \
    --identities example/identities.example.yaml \
    --patches    example/patches \
    --out        out/riverbend-rentals

echo "▸ gate"
python3 lib/gate.py out/riverbend-rentals --identities example/identities.example.yaml
