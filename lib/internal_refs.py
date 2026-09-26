"""
internal_refs.py: the SINGLE definition of "internal tracking reference".

The step that cleans the tree and the callers that normalize comment
dictionary keys (`strip_text`) must apply exactly the same rule: if they drift
by one character the keys stop matching, with no error, and the comment stays
in the original language.

Rules live here, data does not: per-project prose rewrites are loaded from
`i18n/prose-refs/` (see `PROSE_DIR`), and without them this module still works.
"""
import json
import pathlib
import re
from collections.abc import Iterable

# An EXPLICIT list of prefixes: a generic `[A-Z]+-\d+` would also take
# `UTF-8`, `RFC-2606` and `SHA-256`. The prefixes are your tracker's, so they
# are configuration: `gate.ref_prefixes` in the manifest, applied through
# `configure()`. With none, only the planning forms below (T-<n>-<n>, D-<n>)
# are recognised; a key can also be blocked by the identity map, as a
# `tier: block` entry with no `replace`.
PREFIXES: tuple[str, ...] = ()


def _ref(prefixes: tuple[str, ...]) -> str:
    forms = [r"T-\d+(?:-\d+)+", r"D-\d+[A-Za-z]?"]
    if prefixes:
        forms.insert(0, r"(?:" + "|".join(map(re.escape, prefixes)) + r")-\d+[a-z]?")
    return r"(?:" + "|".join(forms) + r")"


REF = _ref(PREFIXES)
# Citing several cards abbreviates from the second one on: `(ACME-02/03/05)`
# is THREE cards, and without the continuation the group stops matching.
_CONT = r"\d+[a-z]?"
SEQ = REF + r"(?:\s*[,/+;&]\s*(?:" + REF + r"|" + _CONT + r"))*"
# A group whose interior is ONLY a reference, optionally followed by the item
# INSIDE the card, which is as internal as the card itself: `(ACME-32 item 5)`,
# `(ACME-17 #2)`.
_ITEM = r"(?:\s*(?:item\s+\d+|#\d+|\([0-9a-z]{1,4}\)))?"
GROUP = re.compile(r"[ \t]*[\[(]\s*" + SEQ + _ITEM + r"\s*[\])]")
# Any occurrence at all, to decide cheaply whether a line is worth the work.
ANY = re.compile(r"(?<![A-Za-z0-9])(?:" + REF + r")(?![A-Za-z0-9])")

# Comment syntax, by style: what the line STARTS with and the regex of the
# marker, to re-anchor after the removal.
_SLASH_MARKER = r"(?://+|/\*+|\*+/?)"
_XML_MARKER = r"(?:<!--+|//+|/\*+|\*+/?)"

STYLES: dict[str, dict] = {
    "slash": {"starts": ("//", "*", "/*"), "marker": _SLASH_MARKER},
    "hash": {"starts": ("#",), "marker": r"#+"},
    # .html and .xml mix the two: `<!-- -->` in the markup and `//` inside the
    # <script>. Recognising only one would leave half the file out.
    "xml": {"starts": ("<!--", "-->", "*", "//", "/*"), "marker": _XML_MARKER},
    # Markdown: there is no marker, the whole file is human text.
    "prose": {"starts": None, "marker": r""},
    # The BLIND normalizer's style: callers of `strip_text` do not know the source
    # file, so it recognises the superset of markers of the files that have a
    # dictionary. `#` is left out: no `#` file has one, and JS private fields use it.
    "any": {"starts": ("//", "*", "/*", "<!--", "-->"), "marker": _XML_MARKER},
}
DEFAULT_STYLE = "any"


# PROSE rewrites: a reference that is the SUBJECT of a sentence cannot come out
# by rule, so each one is rewritten by hand. The table is data of the project
# being published (its needles carry the very references this module removes),
# so it lives in `i18n/prose-refs/`, one file per project, named after its
# manifest key.
PROSE_DIR = pathlib.Path(__file__).resolve().parent.parent / "i18n" / "prose-refs"

# A card used as a label in an end-of-line comment. `(?<![:/])` refuses the
# `//` of a URL scheme (`https://…`) and the third slash of `///`.
EOL_LABEL = re.compile(r"(?<![:/])(//+\s*)" + SEQ + _ITEM + r"\s*(?::|—|–|--)\s+")
EOL_START = re.compile(r"(?<![:/])//")


def _style(name: str) -> dict:
    return STYLES[name]


def is_comment_line(stripped: str, style: str = DEFAULT_STYLE) -> bool:
    starts = _style(style)["starts"]
    if starts is None:  # prose (Markdown): the whole file is human text
        return True
    return stripped.startswith(starts)


def has_ref(line: str) -> bool:
    """Is this line worth touching? Cheap, and it avoids rewriting the whole
    tree."""
    return bool(ANY.search(line))


def strip_line(line: str, style: str = DEFAULT_STYLE) -> str | None:
    """The clean line, or None when the comment stopped saying anything at all.

    A line that is NOT a comment gets only the end-of-line rule: on a line of
    code, what looks like a comment may be the middle of a string.
    """
    raw = line.rstrip("\n")
    if not is_comment_line(raw.strip(), style):
        out = EOL_LABEL.sub(r"\1", raw)
        # The group comes out too, but only AFTER the `//`: before the marker
        # it is code, and there an `(ACME-63b)` would be an operand.
        m = EOL_START.search(out)
        if m:
            out = out[:m.start()] + GROUP.sub("", out[m.start():])
        return re.sub(r"[ \t]+$", "", out) if out != raw else raw
    st = _style(style)
    marker = st["marker"]
    out = GROUP.sub("", raw)
    if marker:
        anchor = r"^(\s*" + marker + r"\s*)"
        # A reference as a LABEL at the start of the comment (`# ACME-25: ...`):
        # what comes after the colon is already the whole sentence.
        out = re.sub(anchor + SEQ + _ITEM + r"\s*(?::|—|–|--)\s+", r"\1", out)
        # The same thing one word further along: `// FIX ACME-1: identity…` —
        # the card goes, `// FIX: …` stays, and the parenthesis between the two
        # stays as well.
        out = re.sub(
            anchor + r"(\S{1,14})\s+" + SEQ
            + r"(\s*(?:\([^()\n]{1,40}\))?\s*(?::|—|–))", r"\1\2\3", out)
        # The same label after a title and a dash, as in a script header. The prefix
        # cannot contain `:`, or the rule steps over the end of another clause.
        out = re.sub(
            anchor + r"([^\n:]{0,80}?[—–][^\n:]{0,40}?)" + SEQ + _ITEM + r"\s*(?::|—|–)\s+",
            r"\1\2", out)
        # A reference at the start leaves the punctuation orphaned: `*
        # (ACME-04). [entityId] travels with it` would become `*. [entityId]
        # travels with it`. Only when a group actually came out: in `# - item`
        # the leading punctuation is content.
        if out != raw:
            out = re.sub(anchor + r"[.,;:—-]+\s*", r"\1", out)
        # The removed group took the preceding space with it, so put one back. The
        # lookahead refuses `*` and `/`: with `(?=\S)`, `/\*+` would back off from
        # `/**` to `/*` and turn a KDoc opening into `/* *`.
        out = re.sub(r"^(\s*" + marker + r")(?=[^\s*/])", r"\1 ", out)
    # A comment at the END of a line of code is touched only in the complete label
    # form (marker, card, separator, space): elsewhere the `//` may be inside a
    # string, which a regex cannot decide.
    out = EOL_LABEL.sub(r"\1", out)
    # Internal whitespace is not normalized: many of these comments align
    # tables by hand, and GROUP already eats the space before the bracket.
    out = re.sub(r"[ \t]+$", "", out)
    # A comment left with nothing but its marker is dropped. A `*` continuation
    # stays (deleting it joins two paragraphs), and a lone `<!--` never qualifies
    # (deleting it would comment out the rest of the file).
    if out.strip() in ("//", "///", "#"):
        return None
    return out


_prose: list[tuple[str, str]] | None = None


def load_prose() -> list[tuple[str, str]]:
    """The prose rewrites declared in this checkout, or none at all.

    ABSENT IS NOT AN ERROR: without a project's table every other form of
    reference still comes out by rule. Returns the UNION of every project's
    table, because the blind normalizer (`strip_text`) does not know which
    project a key came from. Order is file order within a table, and tables in
    sorted filename order (an entry can contain another as a prefix).
    """
    global _prose
    if _prose is None:
        pairs: list[tuple[str, str]] = []
        if PROSE_DIR.is_dir():
            for table in sorted(PROSE_DIR.glob("*.json")):
                data = json.loads(table.read_text(encoding="utf-8"))
                pairs += [(old, new) for old, new in data["rewrites"]]
        _prose = pairs
    return _prose


def strip_prose(text: str) -> str:
    """Applies the prose rewrites.

    Literal substitution, not regex: `re.sub` would treat a `\\1` or a `\\g`
    inside a comment as a group reference. And it is not done line by line
    because two entries cross the block's line break.
    """
    for old, new in load_prose():
        if old in text:
            text = text.replace(old, new)
    return text


def strip_text(text: str, style: str = DEFAULT_STYLE) -> str:
    """Applies strip_line to each comment line of a block of text."""
    text = strip_prose(text)
    out = []
    for line in text.split("\n"):
        if not has_ref(line):
            out.append(line)
            continue
        new = strip_line(line, style)
        if new is None:
            continue
        out.append(new)
    return "\n".join(out)


def configure(prefixes: Iterable[str]) -> None:
    """Rebuilds every pattern above for the project's own ticket prefixes.

    Called once, before any scan or strip, by whoever read the manifest. The
    patterns are module globals so that the gate and the stripping step keep
    reading the SAME definition after it changes.
    """
    global PREFIXES, REF, SEQ, GROUP, ANY, EOL_LABEL
    PREFIXES = tuple(prefixes)
    REF = _ref(PREFIXES)
    SEQ = REF + r"(?:\s*[,/+;&]\s*(?:" + REF + r"|" + _CONT + r"))*"
    GROUP = re.compile(r"[ \t]*[\[(]\s*" + SEQ + _ITEM + r"\s*[\])]")
    ANY = re.compile(r"(?<![A-Za-z0-9])(?:" + REF + r")(?![A-Za-z0-9])")
    EOL_LABEL = re.compile(r"(?<![:/])(//+\s*)" + SEQ + _ITEM + r"\s*(?::|—|–|--)\s+")


# A PLANNING document cited in a comment or test message: the planning
# directory is not published, so the citation points at a missing file.
DOC_REF = re.compile(r"\b(?:PITFALLS|ROADMAP|ARCHITECTURE|REQUIREMENTS)\.md\b|\bPitfall \d+\b")
