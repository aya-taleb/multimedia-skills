#!/usr/bin/env python3
"""Clean the mechanical tells out of a draft, then score it before and after.

What it changes (never the meaning):
  - removes hidden characters (zero-width spaces, byte order marks, soft hyphens)
  - turns odd spaces (no-break, thin, wide) into normal spaces
  - turns long dashes into commas or periods
  - turns curly quotes into straight ones, and the ellipsis character into three dots
  - tidies doubled spaces and trailing spaces
  - with --swap-words: swaps a few words that are always safe to swap ("utilize" -> "use")
  - with --strip-markdown: removes ** bold markers and # heading markers

What it never touches: code (`like this` or fenced), links, emails, @handles,
#hashtags, and text in right-to-left scripts keeps its direction marks.

It does not rewrite sentences. That part needs judgment: read the score report
(detect.py) and rewrite by hand or with the humanize skill.

Usage:
  python3 humanize.py draft.txt                 # clean copy to stdout, report to stderr
  python3 humanize.py draft.txt --out clean.txt # write the clean copy
  python3 humanize.py draft.txt --in-place      # overwrite (keeps draft.txt.bak)
  python3 humanize.py - < draft.txt
  python3 humanize.py draft.txt --report-only   # just print what it would change

Standard library only.
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import detect  # noqa: E402

SPACE_LIKE = "".join(detect.ODD_SPACES)


def _mask(text):
    """Swap code, links and handles for placeholders so no rule can touch them."""
    kept = []

    def hold(m):
        kept.append(m.group(0))
        return "\ue000%d\ue001" % (len(kept) - 1)

    return detect.PROTECTED.sub(hold, text), kept


def _unmask(text, kept):
    return re.sub("\ue000(\\d+)\ue001", lambda m: kept[int(m.group(1))], text)


def remove_hidden(text, counts):
    has_rtl = bool(detect.RTL_LETTERS.search(text))
    out = []
    for i, ch in enumerate(text):
        if ch in detect.HIDDEN:
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if ch == "\u200d" and (detect.EMOJI.match(prev) or prev == "\ufe0f" or detect.EMOJI.match(nxt)):
                out.append(ch)  # part of an emoji like a family or a flag
                continue
            if ch == "\u200c" and has_rtl and ("\u0600" <= prev <= "\u06ff" or "\u0600" <= nxt <= "\u06ff"):
                out.append(ch)  # used inside Persian and Arabic words on purpose
                continue
            counts["hidden characters removed"] = counts.get("hidden characters removed", 0) + 1
            continue
        if ch in detect.DIRECTION_MARKS and not has_rtl:
            counts["direction marks removed"] = counts.get("direction marks removed", 0) + 1
            continue
        if ch in detect.ODD_SPACES:
            counts["odd spaces made normal"] = counts.get("odd spaces made normal", 0) + 1
            out.append(" ")
            continue
        out.append(ch)
    return "".join(out)


def _bump(counts, key, n=1):
    if n:
        counts[key] = counts.get(key, 0) + n


def fix_dashes(chunk, counts):
    dash = "[\u2014\u2015]"
    # A dash used as a bullet at the start of a line becomes a hyphen bullet.
    chunk, n = re.subn(r"(?m)^(\s*)" + dash + r"\s*", r"\1- ", chunk)
    _bump(counts, "long dashes replaced", n)
    # A dash at the end of a line becomes a colon if a list follows, else a period.
    def eol(m):
        return ":" if m.group(2).lstrip().startswith(("-", "*", "\u2022")) or re.match(r"\s*\d+[.)]", m.group(2)) else "."
    chunk, n = re.subn(r"\s*" + dash + r"\s*(\n)(?=(.*))", lambda m: eol(m) + m.group(1), chunk)
    _bump(counts, "long dashes replaced", n)
    # Ranges like 2019\u20142021 or 9\u20145 become a hyphen.
    chunk, n = re.subn(r"(?<=\d)\s*" + dash + r"\s*(?=\d)", "-", chunk)
    _bump(counts, "long dashes replaced", n)
    # Everything else: a comma.
    chunk, n = re.subn(r"\s*" + dash + r"\s*", ", ", chunk)
    _bump(counts, "long dashes replaced", n)
    # Double hyphens used as a dash.
    chunk, n = re.subn(r"(?<=\w)\s?--\s?(?=\w)", ", ", chunk)
    _bump(counts, "double hyphens replaced", n)
    # Spaced en dash between words.
    chunk, n = re.subn(r"(?<=\S)\s\u2013\s(?=\S)", ", ", chunk)
    _bump(counts, "spaced en dashes replaced", n)
    # Tidy what the swaps can leave behind.
    chunk = re.sub(r",\s*,", ",", chunk)
    chunk = re.sub(r",\s*([.!?;:])", r"\1", chunk)
    chunk = re.sub(r"([.!?;:]),\s", r"\1 ", chunk)
    chunk = re.sub(r"(?m)^,\s*", "", chunk)
    chunk = re.sub(r"\(\s*,\s*", "(", chunk)
    chunk = re.sub(r",\s*\)", ")", chunk)
    return chunk


def fix_quotes(chunk, counts):
    table = {"\u2018": "'", "\u2019": "'", "\u201a": "'", "\u2032": "'",
             "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"'}
    n = 0
    for k, v in table.items():
        c = chunk.count(k)
        if c:
            chunk = chunk.replace(k, v)
            n += c
    _bump(counts, "curly quotes straightened", n)
    c = chunk.count("\u2026")
    if c:
        chunk = chunk.replace("\u2026", "...")
        _bump(counts, "ellipsis characters replaced", c)
    return chunk


def _match_case(src, word):
    if src.isupper() and len(src) > 1:
        return word.upper()
    if src[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def swap_words(chunk, counts, swaps):
    for src, dst in sorted(swaps.items(), key=lambda kv: -len(kv[0])):
        pat = re.compile(r"(?<![^\W_])" + re.escape(src) + r"(?![^\W_])", re.I)
        def rep(m, dst=dst, src=src):
            _bump(counts, "words swapped (%s -> %s)" % (src.rstrip(","), dst.rstrip(",")))
            return _match_case(m.group(0), dst)
        chunk = pat.sub(rep, chunk)
    return chunk


def strip_markdown(chunk, counts):
    chunk, n = re.subn(r"\*\*([^*\n]+)\*\*", r"\1", chunk)
    _bump(counts, "bold markers removed", n)
    chunk, n = re.subn(r"(?m)^#{1,6}\s+", "", chunk)
    _bump(counts, "heading markers removed", n)
    return chunk


def tidy_spaces(text, counts):
    lines = []
    for line in text.split("\n"):
        stripped = line.rstrip(" \t")
        indent = re.match(r"^[ \t]*", stripped).group(0)
        body = stripped[len(indent):]
        new_body = re.sub(r"(?<=\S) {2,}(?=\S)", " ", body)
        new_body = re.sub(r" +([,.;:!?])(?=\s|$)", r"\1", new_body)
        if new_body != body or stripped != line:
            _bump(counts, "extra spaces tidied")
        lines.append(indent + new_body)
    return "\n".join(lines)


def clean(text, swap=False, markdown=False, lexicon=None):
    """Return (clean_text, counts)."""
    lexicon = lexicon or detect.load_lexicon()
    counts = {}
    text = text.replace("\r\n", "\n")
    text = remove_hidden(text, counts)
    text, kept = _mask(text)
    text = fix_dashes(text, counts)
    text = fix_quotes(text, counts)
    if swap:
        text = swap_words(text, counts, lexicon.get("safe_swaps", {}))
    if markdown:
        text = strip_markdown(text, counts)
    text = tidy_spaces(text, counts)
    return _unmask(text, kept), counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Clean the mechanical tells out of a draft.")
    parser.add_argument("file", nargs="?", default="-", help="text file, or - for stdin")
    parser.add_argument("--out", help="write the clean copy here")
    parser.add_argument("--in-place", action="store_true", help="overwrite the file (keeps a .bak)")
    parser.add_argument("--swap-words", action="store_true", help="swap always-safe words (utilize -> use)")
    parser.add_argument("--strip-markdown", action="store_true", help="remove ** and # markers")
    parser.add_argument("--report-only", action="store_true", help="show what would change, write nothing")
    parser.add_argument("--quiet", action="store_true", help="no report")
    detect.add_common_args(parser)
    args = parser.parse_args(argv)

    try:
        text = detect.read_input(args.file)
    except OSError as exc:
        print("Could not read %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    if not text.strip():
        print("The draft is empty. Paste some text or pass a file.", file=sys.stderr)
        return 1

    extra, ctx = detect.resolve_extra(args)
    before = detect.analyze(text, extra_banned=extra, allow_markdown=args.allow_markdown)
    cleaned, counts = clean(text, swap=args.swap_words, markdown=args.strip_markdown)
    after = detect.analyze(cleaned, extra_banned=extra, allow_markdown=args.allow_markdown)

    report = []
    report.append("Before: %d/100   After cleaning: %d/100" % (before["score"], after["score"]))
    if counts:
        report.append("Changed:")
        for k, v in counts.items():
            report.append("  - %s: %d" % (k, v))
    else:
        report.append("Nothing mechanical to clean.")
    report.append("")
    report.append(detect.format_report(after, ctx))
    report.append("")
    report.append("Cleaning only fixes characters. The checks still flagged above need a rewrite.")
    report_text = "\n".join(report)

    if args.report_only:
        print(report_text)
        return 0
    if args.in_place and args.file not in (None, "-"):
        shutil.copyfile(args.file, args.file + ".bak")
        with open(args.file, "w", encoding="utf-8") as fh:
            fh.write(cleaned)
    elif args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(cleaned)
    else:
        sys.stdout.write(cleaned)
        if not cleaned.endswith("\n"):
            sys.stdout.write("\n")
    if not args.quiet:
        print(report_text, file=sys.stderr if not (args.out or args.in_place) else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
