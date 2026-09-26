#!/usr/bin/env python3
"""
099: install the LICENSE and set the `license` field of package.json.

Without a licence file a public repository is all rights reserved. It is a
transformation because a LICENSE written into the output tree by hand was
deleted by the next build. It runs last so that the copyright holder is the
already-substituted public persona.
"""
import collections
import json
import pathlib
import shutil

ROOT = pathlib.Path.cwd()
SRC = pathlib.Path(__file__).resolve().parent / "assets" / "LICENSE"

shutil.copyfile(SRC, ROOT / "LICENSE")

pkg = ROOT / "package.json"
if pkg.is_file():
    d = json.loads(pkg.read_text(encoding="utf-8"),
                   object_pairs_hook=collections.OrderedDict)
    changed = False
    if d.get("license") != "MIT":
        d["license"] = "MIT"
        changed = True
    # `private: true` is an npm publish guard, not a statement about the
    # repository, and leaving it next to an MIT licence reads as a contradiction.
    if d.pop("private", None) is not None:
        changed = True
    if changed:
        pkg.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")

print("  099: MIT licence installed")
