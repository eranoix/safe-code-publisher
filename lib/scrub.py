#!/usr/bin/env python3
"""
scrub.py: exports a private project into a sanitized public tree.

  1. EXPORTS from a git ref (`git archive`), not from the directory on disk,
     so an untracked file can never enter by accident.
  2. REMOVES the `exclude` paths before substitution: a document describing a
     client's internal process has to disappear, not become one about "Acme".
  3. SUBSTITUTES by the identity map, in the order of the file.
  4. APPLIES the transformations the private repository never receives.

It pushes nothing: publishing is a separate step, taken after the gate.

Usage:
    scrub.py <project> [--out DIR] [--keep] [--no-patches]
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML is not installed (see Requirements in README.md)", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent

# Known binary extensions are never substituted (that would corrupt them), so
# a binary holding a real value has to be excluded by glob; the gate reports
# any that escape.
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".docx", ".xlsx",
    ".zip", ".gz", ".tar", ".jar", ".apk", ".aar", ".so", ".a", ".dylib", ".dll",
    ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".webm", ".mp3", ".wav", ".class",
    ".keystore", ".jks", ".bin", ".dat",
}


@dataclass
class Substitution:
    pattern: re.Pattern
    replace: str
    label: str


@dataclass
class Stats:
    exported: int = 0
    excluded: int = 0
    rewritten: int = 0
    replacements: int = 0
    per_rule: dict[str, int] = field(default_factory=dict)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_substitutions(identities: dict) -> list[Substitution]:
    subs: list[Substitution] = []
    for e in identities.get("entries", []):
        # Entries at tier `review` have no stand-in: they are ambiguous terms
        # for a human to judge, not to swap blindly.
        if e.get("tier", "block") != "block" or "replace" not in e:
            continue
        raw = e["match"]
        pat = re.compile(raw) if e.get("re") else re.compile(re.escape(raw))
        subs.append(Substitution(pat, e["replace"], raw))
    return subs


def git_export(src: Path, ref: str, dest: Path) -> None:
    """Exports a ref into dest via `git archive`. Fails loudly when the ref
    does not exist: exporting the wrong branch quietly is worse than
    stopping."""
    try:
        subprocess.run(["git", "-C", str(src), "rev-parse", "--verify", f"{ref}^{{commit}}"],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError:
        raise SystemExit(f"error: ref '{ref}' does not exist in {src}")

    def no_links(member: tarfile.TarInfo, path: str):
        """Drops links: a tracked symlink points at the layout of the machine it
        was made on, and tarfile's `data` filter would refuse it anyway."""
        if member.issym() or member.islnk():
            return None
        return tarfile.data_filter(member, path)

    proc = subprocess.Popen(
        ["git", "-C", str(src), "archive", "--format=tar", ref],
        stdout=subprocess.PIPE,
    )
    assert proc.stdout is not None
    with tarfile.open(fileobj=proc.stdout, mode="r|") as tf:
        tf.extractall(dest, filter=no_links)
    if proc.wait() != 0:
        raise SystemExit(f"error: git archive failed in {src}")


def apply_excludes(tree: Path, patterns: list[str], stats: Stats) -> list[str]:
    removed: list[str] = []
    for path in sorted(tree.rglob("*"), key=lambda p: -len(p.parts)):
        if not path.exists():
            continue
        rel = str(path.relative_to(tree))
        if not any(fnmatch.fnmatch(rel, pat) or rel.startswith(pat.rstrip("*").rstrip("/") + "/")
                   for pat in patterns):
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed.append(rel)
        stats.excluded += 1
    return removed


def is_text(path: Path) -> bool:
    """Detects text by CONTENT, not by extension.

    The first version used an allowlist of extensions and left systemd unit
    files untouched, with an absolute path and a username intact. An extension
    list always forgets one; deciding by content, as the gate does, removes
    the whole class of error.
    """
    if path.suffix.lower() in BINARY_EXT:
        return False
    try:
        with path.open("rb") as fh:
            head = fh.read(8192)
    except OSError:
        return False
    if b"\0" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        # It may be a multibyte sequence cut at the buffer boundary: only
        # discard when the whole file fails to decode as well.
        try:
            path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return False
    return True


def substitute(tree: Path, subs: list[Substitution], stats: Stats) -> None:
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.is_symlink() or not is_text(path):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        text = original
        for sub in subs:
            text, n = sub.pattern.subn(sub.replace, text)
            if n:
                stats.replacements += n
                stats.per_rule[sub.label] = stats.per_rule.get(sub.label, 0) + n

        if text != original:
            path.write_text(text, encoding="utf-8")
            stats.rewritten += 1


def rename_paths(tree: Path, subs: list[Substitution]) -> list[tuple[str, str]]:
    """FILE NAMES leak too — `billing_<client>_test.go` tells the whole story
    with the content spotless. Deepest first, otherwise renaming a directory
    invalidates the paths still in the queue."""
    renamed: list[tuple[str, str]] = []
    for path in sorted(tree.rglob("*"), key=lambda p: -len(p.parts)):
        if not path.exists():
            continue
        new_name = path.name
        for sub in subs:
            new_name = sub.pattern.sub(sub.replace, new_name)
        if new_name != path.name:
            target = path.parent / new_name
            path.rename(target)
            renamed.append((path.name, new_name))
    return renamed


def apply_patches(tree: Path, pdir: Path, names: list[str], stats: Stats) -> None:
    """Applies the transformations the private repository never receives.

    `*.py` scripts run with cwd set to the output tree and are preferred: a
    diff's context lines have already been through substitution, so changing one
    stand-in would break a `*.patch` with an error that reads like a code error.
    `*.patch` files go through `git apply`, for additive changes.

    `pdir` defaults to `<root>/patches/<project>`; `--patches` overrides it.
    """
    # ABSOLUTE, always: the scripts run with cwd set to the OUTPUT TREE, so a
    # relative `--patches` path would be looked for inside the output.
    pdir = pdir.resolve()

    # A transformation that is written and not registered in the manifest
    # simply does not run — no error, no warning — and the defect it fixed
    # reappears in the published tree. The list is explicit because the ORDER
    # matters, and the price of an explicit list is this comparison.
    if pdir.is_dir():
        on_disk = {f.name for f in pdir.iterdir()
                   if f.suffix in (".py", ".patch") and f.name[0].isdigit()}
        orphan = sorted(on_disk - set(names))
        if orphan:
            print(f"  \033[31m✗ transformation exists but is not in the manifest: "
                  f"{', '.join(orphan)}\033[0m")
            sys.exit(1)

    for name in names:
        patch = pdir / name
        if not patch.is_file():
            print(f"  \033[33m⚠ transformation missing (not written yet): {name}\033[0m")
            continue

        if patch.suffix == ".py":
            res = subprocess.run([sys.executable, str(patch)],
                                 cwd=tree, capture_output=True, text=True)
            if res.stdout.strip():
                print(res.stdout.rstrip())
        else:
            res = subprocess.run(
                ["git", "apply", "-p1", "--whitespace=nowarn", str(patch)],
                cwd=tree, capture_output=True, text=True,
            )
            if res.returncode == 0:
                print(f"  ✓ {name}")

        if res.returncode != 0:
            raise SystemExit(
                f"error: transformation {name} failed on the sanitized tree.\n"
                f"       Usually the private code changed and the\n"
                f"       transformation needs updating.\n{res.stderr}"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="Export and sanitize a project.")
    ap.add_argument("project")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-patches", action="store_true")
    ap.add_argument("--manifest", type=Path, default=ROOT / "manifest.yaml")
    ap.add_argument("--identities", type=Path, default=ROOT / "identities.yaml")
    # Default None: the default path depends on the project, which is only known
    # after the parse.
    ap.add_argument("--patches", type=Path, default=None,
                    help="directory of the transformations "
                         "(default: <root>/patches/<project>)")
    args = ap.parse_args()

    manifest = load_yaml(args.manifest)
    cfg = manifest.get("projects", {}).get(args.project)
    if cfg is None:
        print(f"error: project '{args.project}' is not in the manifest. "
              f"Known: {', '.join(manifest.get('projects', {}))}", file=sys.stderr)
        return 2

    src = Path(cfg["src"])
    out = args.out or ROOT / "out" / cfg["public_repo"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    stats = Stats()
    subs = build_substitutions(load_yaml(args.identities))

    print(f"\n\033[1m{args.project}\033[0m  {src} @ {cfg['ref']}  →  {out}")

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "tree"
        staging.mkdir()
        git_export(src, cfg["ref"], staging)
        stats.exported = sum(1 for p in staging.rglob("*") if p.is_file())
        print(f"  exported        {stats.exported} tracked files")

        apply_excludes(staging, cfg.get("exclude", []), stats)
        print(f"  excluded        {stats.excluded}")

        substitute(staging, subs, stats)
        print(f"  rewritten       {stats.rewritten} files, "
              f"{stats.replacements} substitutions")

        renamed = rename_paths(staging, subs)
        if renamed:
            print(f"  renamed         {len(renamed)} paths")

        for item in staging.iterdir():
            shutil.move(str(item), str(out / item.name))

    if not args.no_patches:
        pdir = args.patches if args.patches is not None else ROOT / "patches" / args.project
        apply_patches(out, pdir, cfg.get("patches", []), stats)

    top = sorted(stats.per_rule.items(), key=lambda kv: -kv[1])[:8]
    if top:
        print("  most frequent rules:")
        for label, n in top:
            print(f"      {n:6d}  {label}")

    remaining = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"\n  output tree:  {remaining} files in {out}")
    print(f"  next step:    python3 lib/gate.py {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
