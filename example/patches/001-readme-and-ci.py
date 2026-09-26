#!/usr/bin/env python3
"""
001: install the public README and a CI workflow.

The defect: the first public build shipped the internal README. Every noun
had been substituted, so the gate passed, but substitution fixes values, not
audience: a document written for insiders needs replacing, not rewriting.

The CI workflow is replaced because the private one ran on a self-hosted
runner: published as-is, anyone's pull request would run on the shop's box.
"""
import pathlib
import shutil

ROOT = pathlib.Path.cwd()
ASSETS = pathlib.Path(__file__).resolve().parent / "assets"

shutil.copyfile(ASSETS / "README.md", ROOT / "README.md")

wf = ROOT / ".github" / "workflows"
wf.mkdir(parents=True, exist_ok=True)
shutil.copyfile(ASSETS / "ci.yml", wf / "ci.yml")

print("  001: public README + ubuntu-latest CI installed")
