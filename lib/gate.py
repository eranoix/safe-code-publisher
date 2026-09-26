#!/usr/bin/env python3
"""
gate.py: the fail-closed scan between the sanitized tree and the world.

Runs over the OUTPUT TREE, never the sources: a `.min.js` bundle is a separate
copy, and sanitizing the `.js` without rebuilding leaves the real value in the
file that is served. Binaries are read too. BLOCK (a deny-list value) and
SECRET (a generic credential shape) exit 1; REVIEW (a term with a high
false-positive rate) is only listed.

Usage:
    gate.py <tree> [--identities identities.yaml] [--quiet]
Exit:
    0 = clean (publishable)
    1 = blocking finding
    2 = usage or configuration error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import internal_refs  # noqa: E402


def _ref_patterns() -> tuple[re.Pattern, re.Pattern]:
    """The internal-reference rule, in its path form and its content form.

    A boundary on both sides, or `D-\\d+` matches inside `backup-1.json`.
    Case-insensitive in the PATH, where references appear in lower case; upper
    case only in CONTENT, where a short prefix is also a word inside package
    names.
    """
    ref = internal_refs.REF
    return (re.compile(r"(?<![A-Za-z0-9])(?:" + ref + r")(?![A-Za-z0-9])", re.I),
            re.compile(r"(?<![A-Za-z0-9])(?:" + ref + r")(?![A-Za-z0-9])"))


PATH_REF, TEXT_REF = _ref_patterns()

try:
    import yaml
except ImportError:
    print("error: PyYAML is not installed (see Requirements in README.md)", file=sys.stderr)
    sys.exit(2)


# Directories that are never scanned: `.git` holds the history objects, and in
# the public repository the history is synthetic and generated after this scan.
SKIP_DIRS = {".git", "node_modules", "vendor/github.com", ".gradle", "build/intermediates"}

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".docx", ".xlsx",
    ".zip", ".gz", ".tar", ".jar", ".apk", ".aar", ".so", ".a", ".dylib", ".dll",
    ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".webm", ".mp3", ".wav", ".class",
}

# Generic credential shapes: independent of the deny-list, so they catch the
# secret that was never catalogued.
SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----", "private key"),
    (r"\bsk-ant-[A-Za-z0-9_-]{20,}", "Anthropic key"),
    (r"\bsk-[A-Za-z0-9]{32,}", "OpenAI key"),
    (r"\bghp_[A-Za-z0-9]{36,}", "GitHub token (classic)"),
    (r"\bgithub_pat_[A-Za-z0-9_]{50,}", "GitHub token (fine-grained)"),
    (r"\bglpat-[A-Za-z0-9_-]{20,}", "GitLab token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"\bAIza[A-Za-z0-9_-]{35}\b", "Google API key"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "literal JWT"),
    (r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b", "SendGrid key"),
    (r"\b(?:r|s)k_live_[A-Za-z0-9]{20,}", "Stripe key (live)"),
]

# Internal addresses no deny-list can enumerate: an object in a self-hosted
# storage bucket is addressed by uncatalogued UUIDs. Tier BLOCK: a public tree
# has no legitimate reason to carry the address of a private object.
INTERNAL_PATTERNS: list[tuple[str, str]] = [
    (r"/storage/v1/object/(?:public/|sign/|authenticated/)?[A-Za-z0-9_.-]+/"
     r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
     "storage object addressed by UUID"),
]

# Fixtures that EXIST to prove that redaction works. Matched by path fragment
# + value, never by path alone. Your project's own come from the manifest
# (`gate.secret_fixtures`); the ones below are this repository's.
SECRET_ALLOWLIST: list[tuple[str, str]] = [
    # example/ plants these secrets on purpose; without these entries the
    # repository fails its own gate. Both are safe to publish: the AWS
    # documentation placeholder and a PEM block with an invalid body.
    # Values are SUBSTRINGS (`val in matched`) so that this file does not match
    # its own patterns; each substring can only come from that placeholder.
    ("example/README.md", "IOSFODNN7EXAMPLE"),
    ("example/README.md", "BEGIN EC PRIVATE"),
    ("example/private-app/config/default.json", "IOSFODNN7EXAMPLE"),
    ("example/private-app/config/default.json", "BEGIN EC PRIVATE"),
    ("example/private-app/deploy/ACME-138-backup-20260721/config.json",
     "BEGIN EC PRIVATE"),
    ("example/private-app/vendor/app.min.js", "IOSFODNN7EXAMPLE"),
    ("example/private-app/vendor/app.min.js", "BEGIN EC PRIVATE"),
]


# An identity may legitimately BE the content in a named tree or file. The
# mechanism is the gate's; the values come from the manifest (`gate.exceptions`).
#
#   TREE_EXCEPTIONS  output tree name -> identities released inside it
#   PATH_EXCEPTIONS  (path fragment, identity) -> released only in that file
#
# Empty until `load_exceptions` fills them, so an absent configuration can
# only make the gate stricter.
TREE_EXCEPTIONS: dict[str, set[str]] = {}
PATH_EXCEPTIONS: list[tuple[str, str]] = []


def load_exceptions(manifest: Path) -> None:
    """Fill the exception tables from the manifest, when there is one.

    An ABSENT manifest means no exception at all. A PRESENT but malformed block
    is a hard error: accepting it quietly would let someone believe in an
    exception the gate never read.
    """
    if not manifest.is_file():
        return
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    cfg = (data.get("gate") or {}).get("exceptions") or {}

    for tree, identities in (cfg.get("trees") or {}).items():
        if not isinstance(identities, list):
            print(f"error: {manifest}: gate.exceptions.trees['{tree}'] "
                  f"must be a list of identities", file=sys.stderr)
            sys.exit(2)
        TREE_EXCEPTIONS[str(tree)] = {str(i) for i in identities}

    for entry in cfg.get("paths") or []:
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("identity"):
            print(f"error: {manifest}: every item of gate.exceptions.paths "
                  f"needs `path` and `identity`", file=sys.stderr)
            sys.exit(2)
        PATH_EXCEPTIONS.append((str(entry["path"]), str(entry["identity"])))


# Files where the ISSUE KEY is the data under test (`gate.ref_fixtures`).
# Listed by name on purpose: "any test file" would also hide references in
# our own prose.
FIXTURE_FILES: set[str] = set()

# Directories directly under a `vendor/` that hold YOUR sources, not a third
# party's (`gate.first_party_vendor`). Empty: every vendor/ is third-party.
FIRST_PARTY_VENDOR: set[str] = set()


def load_project_rules(manifest: Path) -> None:
    """The project-specific parts of the gate, from the manifest's `gate:`.

    Absent, the gate is at its strictest: no fixture, no first-party vendor
    directory, no planted secret, and only the built-in reference forms. A
    PRESENT but malformed value is a hard error, as with the exceptions.
    """
    global PATH_REF, TEXT_REF
    if not manifest.is_file():
        return
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    gate = data.get("gate") or {}

    def names(key: str) -> list[str]:
        value = gate.get(key) or []
        if not isinstance(value, list):
            print(f"error: {manifest}: gate.{key} must be a list", file=sys.stderr)
            sys.exit(2)
        return [str(v) for v in value]

    FIXTURE_FILES.update(names("ref_fixtures"))
    FIRST_PARTY_VENDOR.update(names("first_party_vendor"))

    for entry in gate.get("secret_fixtures") or []:
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("value"):
            print(f"error: {manifest}: every item of gate.secret_fixtures "
                  f"needs `path` and `value`", file=sys.stderr)
            sys.exit(2)
        SECRET_ALLOWLIST.append((str(entry["path"]), str(entry["value"])))

    prefixes = names("ref_prefixes")
    bad = [p for p in prefixes if not re.fullmatch(r"[A-Z][A-Z0-9]*", p)]
    if bad:
        print(f"error: {manifest}: gate.ref_prefixes takes upper-case prefixes "
              f"without the dash (got {bad})", file=sys.stderr)
        sys.exit(2)
    if prefixes:
        internal_refs.configure(prefixes)
        PATH_REF, TEXT_REF = _ref_patterns()


def is_third_party(rel: str) -> bool:
    """Third-party code: `vendor/` other than the directories declared as your
    own (`gate.first_party_vendor`), and any minified bundle."""
    parts = rel.split("/")
    if ".min." in parts[-1]:
        return True
    if "vendor" in parts:
        i = parts.index("vendor")
        return not (parts[i + 1:i + 2] and parts[i + 1] in FIRST_PARTY_VENDOR)
    return False


@dataclass
class Finding:
    kind: str          # BLOCK | SECRET | REVIEW
    path: str
    line: int          # 0 = binary / position does not apply
    label: str
    excerpt: str


@dataclass
class Rule:
    pattern: re.Pattern
    literal: str | None
    tier: str
    label: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    bytes_scanned: int = 0

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.kind in ("BLOCK", "SECRET")]

    @property
    def review(self) -> list[Finding]:
        return [f for f in self.findings if f.kind == "REVIEW"]


def load_rules(path: Path) -> list[Rule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules: list[Rule] = []
    for e in data.get("entries", []):
        raw = e["match"]
        tier = e.get("tier", "block")
        if e.get("re"):
            rules.append(Rule(re.compile(raw), None, tier, raw))
        else:
            # Escaped literal, case-sensitive: the deny-list already lists the
            # case variants that matter, and matching case-insensitively would
            # produce false positives on ordinary words.
            rules.append(Rule(re.compile(re.escape(raw)), raw, tier, raw))
    return rules


def is_allowlisted(path: str, matched: str) -> bool:
    return any(frag in path and val in matched for frag, val in SECRET_ALLOWLIST)


def path_excepted(rel: str, label: str) -> bool:
    return any(frag in rel and label == val for frag, val in PATH_EXCEPTIONS)


def scan_text(rel: str, text: str, rules: list[Rule], rep: Report) -> None:
    lines = text.splitlines()
    for rule in rules:
        if path_excepted(rel, rule.label):
            continue
        for m in rule.pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            excerpt = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            kind = "BLOCK" if rule.tier == "block" else "REVIEW"
            rep.findings.append(Finding(kind, rel, line_no, rule.label, excerpt))

    # An internal tracking reference in the CONTENT. Checked here because a
    # transformation that removes them is optional per project and a gate is not;
    # tier BLOCK, the only tier that stops the next one from being born.
    if not is_third_party(rel) and rel not in FIXTURE_FILES:
        for m in TEXT_REF.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            excerpt = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            rep.findings.append(Finding("BLOCK", rel, line_no, "internal reference", excerpt))

    for pat, label in INTERNAL_PATTERNS:
        for m in re.finditer(pat, text):
            line_no = text.count("\n", 0, m.start()) + 1
            excerpt = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            rep.findings.append(Finding("BLOCK", rel, line_no, label, excerpt))

    for pat, label in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            if is_allowlisted(rel, m.group(0)):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            excerpt = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            rep.findings.append(Finding("SECRET", rel, line_no, label, excerpt))


def rel_parts_of(rel: str) -> tuple[str, ...]:
    return tuple(rel.split("/"))


def scan_path(rel: str, rules: list[Rule], rep: Report) -> None:
    """Scans the PATH, not only the content.

    The gate was born reading file bytes, and that is how a dated backup
    directory reached the gateway's repository: five files perfectly clean
    inside, in a directory whose NAME carried the ticket key and the date. A
    file name is as public as the file — it appears in the tree listing, in
    the URL and in code search. Line 0 because the position does not apply.
    """
    for rule in rules:
        if path_excepted(rel, rule.label):
            continue
        if rule.pattern.search(rel):
            kind = "BLOCK" if rule.tier == "block" else "REVIEW"
            rep.findings.append(Finding(kind, rel, 0, rule.label, f"(in the path) {rel}"))

    # A tracking reference leaks through the name too. The definition comes
    # from internal_refs so it cannot drift from the step that strips them.
    m = PATH_REF.search(rel)
    if m:
        rep.findings.append(
            Finding("BLOCK", rel, 0, "internal reference", f"(in the path) …{m.group(0)}…")
        )


def scan_binary(rel: str, blob: bytes, rules: list[Rule], rep: Report) -> None:
    """Binaries carry metadata as text — a `.docx` keeps the author's name, a
    `.png` keeps EXIF. Literals only: regex over arbitrary bytes is noise."""
    for rule in rules:
        if rule.literal is None or rule.tier != "block":
            continue
        if rule.literal.encode("utf-8", "ignore") in blob:
            rep.findings.append(
                Finding("BLOCK", rel, 0, rule.label, "(found inside a binary file)")
            )


def should_skip(rel_parts: tuple[str, ...]) -> bool:
    """Decides per path COMPONENT, never by substring.

    The first version tested `s in joined`, and `.git` is a substring of
    `.github`: NO CI workflow was ever scanned, nor the `.gitignore` — and a
    workflow is exactly where deploy hostnames, runner labels and secret names
    live. Found by comparing the scanned file count against `git ls-files`: 13
    against 15.
    """
    if any(part in SKIP_DIRS for part in rel_parts):
        return True
    # SKIP_DIRS entries with a slash ("vendor/github.com") describe a path, and
    # there the comparison is by sequence of components.
    joined = "/".join(rel_parts)
    return any(
        joined == s or joined.startswith(s + "/")
        for s in SKIP_DIRS if "/" in s
    )


def walk(tree: Path, rules: list[Rule]) -> Report:
    rep = Report()
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel_parts = path.relative_to(tree).parts
        if should_skip(rel_parts):
            continue
        rel = "/".join(rel_parts)

        scan_path(rel, rules, rep)

        try:
            blob = path.read_bytes()
        except OSError as exc:
            print(f"warning: could not read {rel}: {exc}", file=sys.stderr)
            continue

        rep.files_scanned += 1
        rep.bytes_scanned += len(blob)

        if path.suffix.lower() in BINARY_EXT or b"\0" in blob[:8192]:
            scan_binary(rel, blob, rules, rep)
        else:
            scan_text(rel, blob.decode("utf-8", "replace"), rules, rep)
    return rep


def render(rep: Report, tree: Path, quiet: bool) -> None:
    def group(findings: list[Finding]) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for f in findings:
            out.setdefault(f.label, []).append(f)
        return out

    if rep.blocking:
        print(f"\n\033[1;31m✗ BLOCKED: {len(rep.blocking)} finding(s) in {tree}\033[0m\n")
        for label, items in sorted(group(rep.blocking).items(), key=lambda kv: -len(kv[1])):
            print(f"  \033[1m{label}\033[0m  ({len(items)}x, {items[0].kind})")
            for f in items[:6]:
                loc = f"{f.path}:{f.line}" if f.line else f.path
                print(f"      {loc}")
                if f.excerpt:
                    print(f"        │ {f.excerpt}")
            if len(items) > 6:
                print(f"      … and {len(items) - 6} more")
            print()

    if rep.review and not quiet:
        print(f"\033[1;33m⚠ REVIEW: {len(rep.review)} finding(s) with a high false-positive rate\033[0m")
        for label, items in sorted(group(rep.review).items(), key=lambda kv: -len(kv[1])):
            sample = ", ".join(sorted({f"{f.path}:{f.line}" for f in items})[:3])
            print(f"  {label}  ({len(items)}x)  e.g. {sample}")
        print()

    if not rep.blocking:
        print(f"\033[1;32m✓ CLEAN\033[0m: {rep.files_scanned} files, "
              f"{rep.bytes_scanned / 1_048_576:.1f} MiB, no blocking findings.")
        if rep.review:
            print("  (the REVIEW items above never block on their own)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sanitization gate. Fails closed.")
    ap.add_argument("tree", type=Path, help="output tree to scan")
    ap.add_argument("--identities", type=Path,
                    default=Path(__file__).resolve().parent.parent / "identities.yaml")
    ap.add_argument("--manifest", type=Path,
                    default=Path(__file__).resolve().parent.parent / "manifest.yaml",
                    help="where the project's gate settings come from (gate:); "
                         "when absent there are no exceptions at all")
    ap.add_argument("--quiet", action="store_true", help="omit the REVIEW section")
    args = ap.parse_args()

    if not args.tree.is_dir():
        print(f"error: {args.tree} is not a directory", file=sys.stderr)
        return 2
    if not args.identities.is_file():
        print(f"error: identity map not found: {args.identities}", file=sys.stderr)
        return 2

    # The identity map inside the output tree would be the worst leak
    # available: a concentrated list of everything one set out to hide.
    for stray in args.tree.rglob("identities.yaml"):
        print(f"\033[1;31m✗ BLOCKED: the identity map is inside the output tree: "
              f"{stray}\033[0m", file=sys.stderr)
        return 1

    load_exceptions(args.manifest)
    load_project_rules(args.manifest)
    rules = load_rules(args.identities)

    allowed = TREE_EXCEPTIONS.get(args.tree.resolve().name, set())
    if allowed:
        rules = [r for r in rules if r.label not in allowed]
        print(f"  (excepted in this tree: {', '.join(sorted(allowed))}; "
              f"see gate.exceptions.trees in the manifest)")

    rep = walk(args.tree, rules)
    render(rep, args.tree, args.quiet)
    return 1 if rep.blocking else 0


if __name__ == "__main__":
    sys.exit(main())
