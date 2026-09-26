#!/usr/bin/env python3
"""
002: remove internal board references (ACME-42) from the published sources.

The map has no stand-in for a board key on purpose, so the gate blocks it and
this file deletes it: only the reference, never the sentence around it.

It deliberately does NOT touch vendor/ or any *.min.* file: those are build
artifacts that no source-level transformation reaches, and rewriting them here
would paper over exactly the class of leak the gate exists to catch. See
example/README.md.

The final check stops the build if a reference survives in a shape this
script does not recognise.
"""
import pathlib
import re
import sys

REF = re.compile(r"(?<![A-Za-z0-9])ACME-\d+(?![A-Za-z0-9])")

# Each form, with the punctuation that only exists to carry the reference.
FORMS = [
    (re.compile(r"[ \t]*\(\s*ACME-\d+\s*\)"), ""),               # ... (ACME-42)
    (re.compile(r"[ \t]*\[\s*ACME-\d+\s*\]"), ""),               # ... [ACME-42]
    (re.compile(r"(?m)^(\s*(?://+|\*|#)\s*)ACME-\d+:\s*"), r"\1"),  # // ACME-42: why
    (re.compile(r"[ \t]*,[ \t]*ACME-\d+"), ""),                  # ..., ACME-91
]

# Removing a leading key (`// ACME-42: two people booked ...`) leaves a
# comment starting in lower case; re-capitalize it so the export does not
# look mangled to a reviewer.
LEAD = re.compile(r"(?m)^(\s*(?://+|\*|#)\s+)([a-z])")

BINARY = {".png", ".jpg", ".gif", ".pdf", ".zip", ".woff2", ".ico"}


def is_build_artifact(rel: str) -> bool:
    parts = rel.split("/")
    return "vendor" in parts or ".min." in parts[-1]


root = pathlib.Path.cwd()
changed = 0
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.suffix.lower() in BINARY:
        continue
    rel = path.relative_to(root).as_posix()
    if rel.startswith(".git/") or is_build_artifact(rel):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    if not REF.search(text):
        continue
    new = text
    for pattern, repl in FORMS:
        new = pattern.sub(repl, new)
    if new != text:
        before = text.splitlines()
        after = new.splitlines()
        fixed = [
            LEAD.sub(lambda m: m.group(1) + m.group(2).upper(), ln)
            if i < len(before) and ln != before[i] else ln
            for i, ln in enumerate(after)
        ]
        new = "\n".join(fixed) + ("\n" if new.endswith("\n") else "")
    if new != text:
        path.write_text(new, encoding="utf-8")
        changed += 1

left = []
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.suffix.lower() in BINARY:
        continue
    rel = path.relative_to(root).as_posix()
    if rel.startswith(".git/") or is_build_artifact(rel):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for m in REF.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        left.append(f"{rel}:{line}  {m.group(0)}")

if left:
    print("  002: a reference survived in a shape this step does not know:")
    for item in left[:10]:
        print(f"      {item}")
    print("      add the form above to FORMS, or rewrite the sentence by hand.")
    sys.exit(1)

print(f"  002: internal references removed from {changed} file(s)")
