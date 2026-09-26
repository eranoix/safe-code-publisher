#!/usr/bin/env python3
"""
history.py: builds the history of the public repository.

The history is synthetic: every private commit message and diff carries names,
addresses and ticket keys, and one escape would be enough to leak. So the
public history is a few THEMATIC commits built from the clean tree, one per
subsystem, dated now: a table of contents, not a falsified timeline.

Commits carry the identity declared in the manifest (`publisher:`), by the
forge's `noreply` address. It is configuration, not a constant, because a tool
that carries its author's handle signs someone else's work with it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML is not installed (see Requirements in README.md)", file=sys.stderr)
    sys.exit(2)


def load_publisher(manifest: Path) -> dict:
    """Who the generated history is signed as.

    `name` and `email` are required and have NO default: a default would sign a
    stranger's commits with the handle of whoever wrote the tool. `forge_owner`
    is optional; absent, no remote is configured rather than inventing one.
    """
    if not manifest.is_file():
        print(f"error: manifest not found: {manifest}\n"
              f"       commit authorship comes from its `publisher:` block.",
              file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    pub = data.get("publisher") or {}
    missing_keys = [k for k in ("name", "email") if not pub.get(k)]
    if missing_keys:
        print(f"error: {manifest}: missing "
              + ", ".join(f"publisher.{k}" for k in missing_keys)
              + "\n       without them the commits would be signed as someone else.",
              file=sys.stderr)
        sys.exit(2)
    return pub


def run(args: list[str], cwd: Path, env_extra: dict | None = None) -> None:
    import os

    env = os.environ.copy()
    env.update(env_extra or {})
    res = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise SystemExit(f"git failed: {' '.join(args)}\n{res.stderr}")


Layer = tuple[list[str], str, str]


def load_layers(manifest: Path, project: str | None) -> list[Layer]:
    """The thematic commits, from `projects.<project>.history` in the manifest.

    Each item has `paths` (globs), a `subject` and an optional `body`, in the
    order a reader should meet the system. A broader glob claims its files
    first, so the specific ones go before it. No project or no `history:`
    means one commit of the whole tree: nothing is invented.
    """
    if project is None:
        return []
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    cfg = (data.get("projects") or {}).get(project)
    if cfg is None:
        print(f"error: project '{project}' is not in {manifest}", file=sys.stderr)
        sys.exit(2)
    layers: list[Layer] = []
    for i, item in enumerate(cfg.get("history") or []):
        paths = item.get("paths") if isinstance(item, dict) else None
        if not isinstance(paths, list) or not paths or not item.get("subject"):
            print(f"error: {manifest}: projects.{project}.history[{i}] needs a "
                  f"non-empty `paths` list and a `subject`", file=sys.stderr)
            sys.exit(2)
        layers.append(([str(p) for p in paths], str(item["subject"]),
                       str(item.get("body") or "").strip()))
    return layers


def main() -> int:
    ap = argparse.ArgumentParser(description="Thematic history for the public tree.")
    ap.add_argument("tree", type=Path)
    ap.add_argument("--project", default=None,
                    help="manifest project whose `history:` lists the thematic "
                         "commits; without it the tree is one commit")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--manifest", type=Path,
                    default=Path(__file__).resolve().parent.parent / "manifest.yaml",
                    help="where the authorship (publisher:) and the commits "
                         "(projects.<p>.history) come from")
    args = ap.parse_args()

    pub = load_publisher(args.manifest)
    layers = load_layers(args.manifest, args.project)

    tree = args.tree
    if not tree.is_dir():
        print(f"error: {tree} does not exist", file=sys.stderr)
        return 2

    git_dir = tree / ".git"
    # The remote dies with the .git, which is recreated on every build, so a
    # missing `origin` looks like a credential error. Read it first and put it
    # back afterwards.
    previous_remote = None
    if git_dir.exists():
        import shutil

        res = subprocess.run(["git", "remote", "get-url", "origin"], cwd=tree,
                             capture_output=True, text=True)
        if res.returncode == 0:
            previous_remote = res.stdout.strip()
        shutil.rmtree(git_dir)

    run(["git", "init", "-q", "-b", args.branch], tree)
    run(["git", "config", "user.name", pub["name"]], tree)
    run(["git", "config", "user.email", pub["email"]], tree)

    # With no known remote, derive it from the configured owner and the directory
    # name (named after the public repository). With no owner, derive nothing:
    # an invented account name must never happen quietly.
    remote_url = previous_remote
    if not remote_url and pub.get("forge_owner"):
        remote_url = (f"https://{pub.get('forge_host', 'github.com')}"
                   f"/{pub['forge_owner']}/{tree.resolve().name}.git")
    if remote_url:
        run(["git", "remote", "add", "origin", remote_url], tree)
    else:
        print("  (no publisher.forge_owner in the manifest: `origin` left unconfigured)")

    made = 0
    for globs, subject, body in layers:
        added = False
        for g in globs:
            res = subprocess.run(["git", "add", "--", g], cwd=tree,
                                 capture_output=True, text=True)
            if res.returncode == 0:
                added = True
        if not added:
            continue
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                                cwd=tree, capture_output=True, text=True).stdout.strip()
        if not staged:
            continue
        run(["git", "commit", "-q", "-m", subject] + (["-m", body] if body else []), tree)
        made += 1
        print(f"  {made:2d}. {subject}  ({len(staged.splitlines())} files)")

    # Whatever no layer claimed: without this, a new file in the private
    # repository would vanish from the public one with nobody noticing.
    run(["git", "add", "-A"], tree)
    rest = subprocess.run(["git", "diff", "--cached", "--name-only"],
                          cwd=tree, capture_output=True, text=True).stdout.strip()
    if rest:
        subject = "chore: remaining sources" if made else "chore: public tree"
        run(["git", "commit", "-q", "-m", subject,
             "-m", "Files not claimed by an earlier thematic commit."
             if made else "The sanitized tree, as one commit."], tree)
        made += 1
        print(f"  {made:2d}. {subject}  ({len(rest.splitlines())} files)")

    total = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=tree,
                           capture_output=True, text=True).stdout.strip()
    print(f"\n  {total} commits in {tree}, branch {args.branch}")
    print(f"  author: {pub['name']} <{pub['email']}>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
