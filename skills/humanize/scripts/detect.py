#!/usr/bin/env python3
"""Score a draft for the signs that make writing read machine-made.

This is a set of local pattern checks. It does not call any AI detector, and no
check can prove who wrote a text. A high score means none of these tells were
found, nothing more.

Usage:
  python3 detect.py draft.txt
  python3 detect.py - < draft.txt
  python3 detect.py draft.txt --json
  python3 detect.py draft.txt --context founder/context.md
  python3 detect.py draft.txt --extra-banned "disrupt, hustle"
  python3 detect.py draft.txt --min-score 80     # exit code 2 if below
  python3 detect.py rewrite.txt --compare draft.txt   # also list facts dropped or added

By default it also reads "Words to avoid" from the active business file
(founder-context): ./founder/context.md first, then
~/.founder/businesses/<slug>.md where <slug> is in ~/.founder/active.
FOUNDER_HOME, if set, replaces ~/.founder. Use --no-context to skip that.

Standard library only.
"""
import argparse
import json
import math
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEXICON_PATH = os.path.join(HERE, "lexicon.json")

# Characters nobody types on purpose in a post or an email.
HIDDEN = {
    "\u200b": "zero-width space",
    "\u200c": "zero-width non-joiner",
    "\u200d": "zero-width joiner",
    "\u2060": "word joiner",
    "\ufeff": "byte order mark",
    "\u00ad": "soft hyphen",
    "\u180e": "Mongolian vowel separator",
    "\u2061": "invisible function application",
    "\u2062": "invisible times",
    "\u2063": "invisible separator",
    "\u2064": "invisible plus",
}
ODD_SPACES = {
    "\u00a0": "no-break space",
    "\u202f": "narrow no-break space",
    "\u2007": "figure space",
    "\u2009": "thin space",
    "\u200a": "hair space",
    "\u2002": "en space",
    "\u2003": "em space",
    "\u3000": "wide space",
}
DIRECTION_MARKS = {
    "\u200e": "left-to-right mark",
    "\u200f": "right-to-left mark",
    "\u202a": "direction embedding",
    "\u202b": "direction embedding",
    "\u202c": "direction pop",
    "\u202d": "direction override",
    "\u202e": "direction override",
    "\u2066": "direction isolate",
    "\u2067": "direction isolate",
    "\u2068": "direction isolate",
    "\u2069": "direction isolate",
}
RTL_LETTERS = re.compile("[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]")
EMOJI = re.compile(
    "[\U0001f300-\U0001faff\u2600-\u27bf\U0001f000-\U0001f2ff\u2b50\u2b55\u2705\u274c]"
)
EM_DASH = "\u2014"
EN_DASH = "\u2013"
HBAR = "\u2015"
CURLY = "\u2018\u2019\u201c\u201d\u201a\u201e\u2032\u2033"
ELLIPSIS = "\u2026"

# Spans we never judge or change: code, links, emails, @handles, #hashtags.
PROTECTED = re.compile(
    r"```.*?```"
    r"|`[^`\n]+`"
    r"|https?://\S+"
    r"|www\.\S+"
    r"|[\w.+-]+@[\w-]+\.[\w.-]+"
    r"|(?<![\w@])@\w[\w.]*"
    r"|(?<![\w#])#\w+",
    re.S,
)

WORD = re.compile(r"[^\W_]+(?:['\u2019-][^\W_]+)*", re.U)
BULLET = re.compile(
    r"^\s*(?:[-*\u2022\u25aa\u25cf>]|\d+[.)]"
    r"|[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2705\u274c]\ufe0f?)\s+")


def load_lexicon(path=LEXICON_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- founder context

def founder_home(home=None):
    """$FOUNDER_HOME if set, else ~/.founder (not ~/.claude, which Claude Code protects)."""
    env = os.environ.get("FOUNDER_HOME")
    if env:
        return os.path.expanduser(env)
    return os.path.join(home or os.path.expanduser("~"), ".founder")


def find_context_file(start=None, home=None):
    """Return the path of the active business file, or None."""
    start = start or os.getcwd()
    home = home or os.path.expanduser("~")
    local = os.path.join(start, "founder", "context.md")
    if os.path.isfile(local):
        return local
    base = founder_home(home)
    active = os.path.join(base, "active")
    if os.path.isfile(active):
        with open(active, encoding="utf-8") as fh:
            slug = fh.read().strip()
        if slug and re.match(r"^[a-z0-9][a-z0-9-]*$", slug):
            path = os.path.join(base, "businesses", slug + ".md")
            if os.path.isfile(path):
                return path
    return None


def split_words(raw):
    raw = re.sub(r"\{\{.*?\}\}", "", raw)
    parts = re.split(r"[,;\n]|\s+/\s+", raw)
    out = []
    for p in parts:
        p = p.strip().strip("\"'`*_.").strip()
        p = re.sub(r"^\s*[-*\u2022]\s*", "", p)
        if p and p.lower() not in ("none", "n/a", "-", "{{your words}}") and not p.startswith("{{"):
            out.append(p)
    return out


def read_avoid_words(path):
    """Read 'Words to avoid' from a founder-context business file.

    Accepts either a line like 'Words to avoid: hustle, guru, crush it'
    or a 'Words to avoid' heading followed by a bullet list.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    words = []
    label = re.compile(r"^\s*(?:[-*]\s*)?\**\s*words to avoid\s*\**\s*:?\s*\**\s*(.*)$", re.I)
    heading = re.compile(r"^\s*#+\s*words to avoid\s*$", re.I)
    i = 0
    while i < len(lines):
        line = lines[i]
        if heading.match(line):
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("#"):
                if lines[i].strip():
                    words.extend(split_words(lines[i]))
                i += 1
            continue
        m = label.match(line)
        if m:
            rest = m.group(1).strip()
            if rest:
                words.extend(split_words(rest))
            else:
                i += 1
                while i < len(lines) and BULLET.match(lines[i]):
                    words.extend(split_words(lines[i]))
                    i += 1
                continue
        i += 1
    seen, out = set(), []
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


# ---------------------------------------------------------------- helpers

def mask_protected(text):
    """Replace code, links and handles with spaces of the same length."""
    return PROTECTED.sub(lambda m: " " * len(m.group(0)), text)


def normalize_quotes(text):
    return (text.replace("\u2019", "'").replace("\u2018", "'")
            .replace("\u201c", '"').replace("\u201d", '"'))


def word_pattern(form):
    body = re.escape(form.lower()).replace(r"\ ", r"[\s-]+").replace(r"\-", r"[\s-]?")
    return re.compile(r"(?<![^\W_])" + body + r"(?![^\W_])", re.I | re.U)


def count_forms(text_low, forms):
    total = 0
    for f in forms:
        total += len(word_pattern(f).findall(text_low))
    return total


def sentences(text):
    """Split into sentences. Line breaks end a sentence too (posts use them a lot)."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        bullet = bool(BULLET.match(stripped))
        body = BULLET.sub("", stripped)
        for part in re.split(r"(?<=[.!?])[\"')\]]*\s+", body):
            part = part.strip()
            if part:
                n = len(WORD.findall(part))
                if n:
                    out.append({"text": part, "words": n, "bullet": bullet})
    return out


def paragraphs(text):
    blocks = re.split(r"\n\s*\n", text.strip())
    return [b for b in blocks if b.strip()]


def short(s, n=70):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 3] + "..."


# ---------------------------------------------------------------- checks

def check(cid, title, why, fix, points, cap, found):
    lost = min(points, cap)
    return {"id": cid, "title": title, "points_lost": int(round(lost)), "max": cap,
            "found": found, "why": why, "fix": fix}


def analyze(text, extra_banned=None, lexicon=None, allow_markdown=False):
    lexicon = lexicon or load_lexicon()
    extra_banned = [w for w in (extra_banned or []) if w.strip()]
    results = []
    has_rtl = bool(RTL_LETTERS.search(text))

    # 1. Hidden characters
    found = []
    for ch, name in HIDDEN.items():
        n = text.count(ch)
        if ch == "\u200d":  # joiner inside emoji sequences is normal
            n = len(re.findall(r"(?<![\U0001f000-\U0001faff\u2600-\u27bf\ufe0f])\u200d"
                               r"|\u200d(?![\U0001f000-\U0001faff\u2600-\u27bf])", text))
        if ch == "\u200c" and has_rtl:
            n = len(re.findall("(?<![\u0600-\u06ff])\u200c|\u200c(?![\u0600-\u06ff])", text))
        if n:
            found.append("%d x %s (U+%04X)" % (n, name, ord(ch)))
    for ch, name in ODD_SPACES.items():
        n = text.count(ch)
        if n:
            found.append("%d x %s (U+%04X)" % (n, name, ord(ch)))
    if not has_rtl:
        for ch, name in DIRECTION_MARKS.items():
            n = text.count(ch)
            if n:
                found.append("%d x %s (U+%04X)" % (n, name, ord(ch)))
    results.append(check(
        "hidden", "Hidden characters",
        "Invisible characters and odd spaces get left behind when text is copied out of "
        "AI tools and some editors. Readers can't see them, but they can break line breaks "
        "and search, and some people check for them.",
        "Run humanize.py, which removes them.",
        10 if found else 0, 10, found))

    masked = mask_protected(text)
    low = normalize_quotes(masked).lower()

    # 2. Long dashes
    found = []
    em = masked.count(EM_DASH) + masked.count(HBAR)
    dbl = len(re.findall(r"(?<=\w)\s?--\s?(?=\w)", masked))
    en_words = len(re.findall(r"(?<=\S)\s" + EN_DASH + r"\s(?=\S)", masked))
    if em:
        found.append("%d long dash%s" % (em, "es" if em > 1 else ""))
    if dbl:
        found.append("%d double hyphen%s used as a dash" % (dbl, "s" if dbl > 1 else ""))
    if en_words:
        found.append("%d spaced en dash%s between words" % (en_words, "es" if en_words > 1 else ""))
    n = em + dbl + en_words
    results.append(check(
        "dashes", "Long dashes",
        "The long dash is the punctuation mark most tied to AI writing right now. "
        "Most people type a comma, a period, or 'and' instead.",
        "Swap each one for a comma or a period. humanize.py does this for you.",
        3 * n, 12, found))

    # 3. Typography
    curly = sum(masked.count(c) for c in CURLY)
    ell = masked.count(ELLIPSIS)
    found = []
    if curly:
        found.append("%d curly quote%s" % (curly, "s" if curly > 1 else ""))
    if ell:
        found.append("%d ellipsis character%s" % (ell, "s" if ell > 1 else ""))
    results.append(check(
        "typography", "Curly quotes and the ellipsis character",
        "Curly quotes and the one-character ellipsis come from word processors and AI "
        "tools. Phones type curly quotes too, so this is a weak sign, worth only a point or two.",
        "humanize.py turns them into straight quotes and three dots.",
        (1 if curly else 0) + (1 if ell else 0) + (1 if curly + ell > 6 else 0), 3, found))

    # 4. Banned words (house list + this business)
    found = []
    hits = 0
    for entry in lexicon.get("banned", []):
        c = count_forms(low, entry["forms"])
        if c:
            hits += c
            found.append("'%s' x%d, try: %s" % (entry["word"], c, " / ".join(entry["use"])))
    for entry in lexicon.get("banned_phrases", []):
        c = low.count(entry["text"])
        if c:
            hits += c
            found.append("'%s' x%d, try: %s" % (entry["text"], c, " / ".join(entry["use"])))
    for word in extra_banned:
        c = count_forms(low, [normalize_quotes(word).lower()])
        if c:
            hits += c
            found.append("'%s' x%d (from your business file)" % (word, c))
    results.append(check(
        "banned", "Words on the avoid list",
        "These are words the house style bans, plus any 'words to avoid' in your business "
        "file. They are the words readers now link with AI-written copy, or words you said "
        "don't sound like you.",
        "Use the plainer word suggested, or say the concrete thing the word was standing in for.",
        6 * hits, 30, found))

    # 5. Stock words
    found = []
    hits = 0
    for entry in lexicon.get("stock", []):
        c = count_forms(low, entry["forms"])
        if c:
            hits += c
            found.append("'%s' x%d, try: %s" % (entry["word"], c, " / ".join(entry["use"])))
    results.append(check(
        "stock_words", "Stock words",
        "These words show up far more in machine-written text than in how people talk. "
        "One is fine. A few together make the whole draft feel generated.",
        "Swap them for the plainer words suggested, or cut them.",
        3 * hits, 15, found))

    # 6. Stock phrases
    found = []
    hits = 0
    for entry in lexicon.get("phrases", []):
        c = len(re.findall(r"(?<![a-z])" + re.escape(entry["text"]) + r"(?![a-z])", low))
        if c:
            hits += c
            found.append("'%s' x%d, try: %s" % (entry["text"], c, " / ".join(entry["use"])))
    results.append(check(
        "stock_phrases", "Stock phrases",
        "Filler phrases that take up space without saying anything. They are the stock "
        "moves of AI drafts and of corporate email.",
        "Cut the phrase and start with the point.",
        4 * hits, 16, found))

    # 7. Openers and sign-offs
    lines = [l.strip() for l in masked.splitlines() if l.strip()]
    found = []
    pts = 0
    if lines:
        first = normalize_quotes(lines[0]).lower()
        first = re.sub(r"^(hi|hey|hello|dear)\b[^,\n]*,\s*", "", first)
        # Greeting on its own line: look at the next line too
        heads = [first]
        if len(lines) > 1 and re.match(r"^(hi|hey|hello|dear)\b[^.!?]{0,30},?$", normalize_quotes(lines[0]).lower()):
            heads.append(normalize_quotes(lines[1]).lower())
        for head in heads:
            for op in lexicon.get("openers", []):
                if head.startswith(op):
                    found.append("opens with '%s'" % short(head, 50))
                    pts += 6
                    break
        tail = [normalize_quotes(l).lower() for l in lines[-2:]]
        for closer in lexicon.get("closers", []):
            t = closer["text"]
            for l in tail:
                ok = (l.strip(" .!") == t.strip(" .!")) if closer["match"] == "line" else (t in l)
                if ok:
                    found.append("ends with '%s'" % short(l, 50))
                    pts += 5
                    break
    results.append(check(
        "open_close", "Stock opening or sign-off",
        "The first line decides if anyone keeps reading, and the last line is what they "
        "remember. Stock openers ('In today's world', 'I'm thrilled to announce') and "
        "stock sign-offs ('Thoughts?', 'Hope this helps') are skipped on sight.",
        "Open with the most specific thing in the draft: a number, a moment, a claim. "
        "End with a real question or the next step, in your words.",
        pts, 10, found))

    sents = sentences(masked)
    prose = [s for s in sents if not s["bullet"]]
    total_words = sum(s["words"] for s in sents)

    # 8. "Not X, it's Y" contrast move
    found = []
    contrast_in = re.compile(
        r"\b(?:not\s+(?:just|only|merely)\s+[^.;!?]{1,60}?[,;]?\s+but(?:\s+also)?\b"
        r"|(?:isn't|is not|it's not|it is not|aren't|are not|wasn't|was not|this isn't|that's not)"
        r"\s+(?:just\s+|only\s+|merely\s+|about\s+)?[^.;!?]{1,60}?[,;:]\s*(?:it's|it is|they're|we're|this is|that's|but)\b)",
        re.I)
    neg = re.compile(r"\b(?:isn't|is not|aren't|are not|wasn't|it's not|it is not|not just|not only|not about|not a|not an|doesn't|don't)\b", re.I)
    pos_start = re.compile(r"^(?:it's|it is|they're|we're|this is|that's|but|instead|rather|it was)\b", re.I)
    for s in sents:
        if contrast_in.search(normalize_quotes(s["text"])):
            found.append(short(s["text"]))
    for a, b in zip(sents, sents[1:]):
        ta, tb = normalize_quotes(a["text"]), normalize_quotes(b["text"])
        if neg.search(ta) and pos_start.match(tb) and a["words"] <= 14 and b["words"] <= 14:
            found.append(short(ta + " " + tb))
    n = len(found)
    results.append(check(
        "contrast", "The 'it's not X, it's Y' move",
        "Setting up a thing only to knock it down ('It's not a tool. It's a movement.') is "
        "one of the most copied AI patterns. Once can work. More than that reads like a template.",
        "Say what it is, directly. Keep one at most, the strongest.",
        0 if n == 0 else 3 + 4 * (n - 1), 11, found))

    # 9. Long sentences
    longs = [s for s in sents if s["words"] > 25]
    results.append(check(
        "long_sentences", "Long sentences",
        "Sentences over 25 words make people reread. On a phone they become a wall of text.",
        "Split at the 'and', 'which' or 'because'. One idea per sentence.",
        3 * len(longs), 12, ["%d words: %s" % (s["words"], short(s["text"])) for s in longs]))

    # 10. Same-length sentences
    found = []
    pts = 0
    if len(prose) >= 6:
        lens = [s["words"] for s in prose]
        mean = sum(lens) / float(len(lens))
        sd = math.sqrt(sum((x - mean) ** 2 for x in lens) / len(lens))
        cv = sd / mean if mean else 0
        if cv < 0.30:
            pts = 8
        elif cv < 0.40:
            pts = 4
        if pts:
            found.append("%d sentences, most between %d and %d words (spread %.2f, people "
                         "usually land above 0.45)" % (len(lens), int(max(1, mean - sd)), int(mean + sd + 0.5), cv))
    results.append(check(
        "rhythm", "Every sentence the same length",
        "People mix short and long sentences without trying. Machine drafts often keep every "
        "sentence close to the same length, and it reads flat, like a list being recited.",
        "Cut one sentence down to a few words. Let another run longer. Read it out loud.",
        pts, 8, found))

    # 11. Stacked fragments
    found = []
    run = []
    for s in prose + [None]:
        if s is not None and s["words"] <= 3:
            run.append(s["text"])
            continue
        if len(run) >= 3:
            found.append(" ".join(run))
        run = []
    results.append(check(
        "fragments", "Stacked one-word sentences",
        "Three or more tiny sentences in a row ('Fast. Cheap. Done.') is a stock copywriting "
        "move. It reads like a template, not a person.",
        "Join them into one sentence, or keep only the strongest one.",
        4 * len(found), 8, [short(f) for f in found]))

    # 12. Lists of three, again and again
    triple = re.compile(r"\b[^\W_]+(?:\s[^\W_]+){0,2},\s[^\W_]+(?:\s[^\W_]+){0,2},?\s(?:and|or)\s[^\W_]+", re.U)
    trips = []
    for s in sents:
        if not s["bullet"]:
            trips.extend(triple.findall(s["text"]))
    found = [short(t, 50) for t in trips] if len(trips) >= 3 else []
    results.append(check(
        "triples", "Lists of three, over and over",
        "Grouping things in threes ('faster, cheaper, and better') sounds polished once. "
        "When every other sentence does it, the draft sounds generated.",
        "Keep the best one. Turn the others into two items, or one concrete example.",
        0 if len(trips) < 3 else 2 * (len(trips) - 2), 6, found))

    # 13. Posting noise: exclamation marks, emoji bullets, hashtags
    found = []
    pts = 0
    bangs = masked.count("!")
    if bangs > 2:
        found.append("%d exclamation marks" % bangs)
        pts += min(6, 2 * (bangs - 2))
    emoji_bullets = sum(1 for l in text.splitlines() if EMOJI.match(l.strip()[:1] or " "))
    if emoji_bullets >= 2:
        found.append("%d lines start with an emoji" % emoji_bullets)
        pts += 4
    tags = len(re.findall(r"(?<![\w#])#\w+", text))
    if tags > 5:
        found.append("%d hashtags" % tags)
        pts += 2
    results.append(check(
        "noise", "Exclamation marks, emoji bullets, hashtag piles",
        "Lots of exclamation marks, a rocket or a check mark in front of every line, and a "
        "pile of hashtags are the house style of auto-generated posts.",
        "Keep one exclamation mark at most. Use plain line breaks instead of emoji bullets. "
        "Three hashtags or fewer.",
        pts, 8, found))

    # 14. Markdown in plain text
    found = []
    if not allow_markdown:
        stars = len(re.findall(r"\*\*[^*\n]+\*\*", masked))
        heads = len(re.findall(r"(?m)^#{1,6}\s", masked))
        if stars:
            found.append("%d bold marker%s (**)" % (stars, "s" if stars > 1 else ""))
        if heads:
            found.append("%d heading marker%s (#)" % (heads, "s" if heads > 1 else ""))
    results.append(check(
        "markdown", "Markdown symbols",
        "LinkedIn, Instagram, text messages and most email apps show ** and # as raw "
        "characters. They're a sure sign the text was pasted from a chat window.",
        "Remove the symbols, or pass --allow-markdown if the text goes somewhere that "
        "shows Markdown (a README, a doc).",
        2 * len(found), 4, found))

    # 15. Long paragraphs
    found = []
    for p in paragraphs(masked):
        ps = [s for s in sentences(p) if not s["bullet"]]
        if len(ps) > 4:
            found.append("%d sentences: %s" % (len(ps), short(ps[0]["text"], 50)))
    results.append(check(
        "paragraphs", "Long paragraphs",
        "A paragraph of five or more sentences looks like a wall on a phone screen, and "
        "people scroll past it.",
        "Break it after every two or three sentences.",
        2 * len(found), 6, found))

    lost = sum(r["points_lost"] for r in results)
    score = max(0, 100 - lost)
    notes = []
    if total_words < 40:
        notes.append("Short text (%d words), so the rhythm checks had little to go on." % total_words)
    return {
        "score": score,
        "verdict": verdict(score),
        "words": total_words,
        "sentences": len(sents),
        "checks": results,
        "extra_banned": extra_banned,
        "notes": notes,
        "honesty": "These are pattern checks run on your machine. They do not call any AI "
                   "detector and cannot prove who wrote a text. 100 means none of these "
                   "tells were found, nothing more.",
    }


STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further
had has have having he her here hers herself him himself his how i if in into is it its itself
just me more most my myself no nor not now of off on once only or other our ours ourselves out
over own same she should so some such than that the their theirs them themselves then there
these they this those through to too under until up very was we were what when where which
while who whom why will with you your yours yourself yourselves it's i'm we're you're they're
that's there's here's isn't aren't wasn't don't doesn't didn't won't can't i've we've you've
i'll we'll you'll let's also get got go going make made one two new way want like really
""".split())


def _facts(text):
    t = normalize_quotes(text)
    numbers = set(re.findall(r"(?<![\w.])[$\u00a3\u20ac]?\d[\d,.]*(?:%|k|m|x)?(?![\w])", t, re.I))
    numbers = {n.rstrip(".,") for n in numbers if n.rstrip(".,")}
    links = set(m.group(0).rstrip(".,)") for m in re.finditer(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+", t))
    handles = set(re.findall(r"(?<![\w@])@\w[\w.]*", t))
    # Capitalized words that are not the first word of a sentence or line.
    names = set()
    for line in t.splitlines():
        for sent in re.split(r"(?<=[.!?])\s+", line.strip()):
            words = WORD.findall(sent)
            for w in words[1:]:
                if w[:1].isupper() and w.lower() not in STOPWORDS and w != "I":
                    names.add(w)
    return {"numbers": numbers, "links": links, "handles": handles, "names": names}


def compare(original, rewrite):
    """List facts the rewrite dropped and facts or words it added."""
    a, b = _facts(mask_braces(original)), _facts(mask_braces(rewrite))
    out = {}
    for k in ("numbers", "links", "handles"):
        out["dropped_" + k] = sorted(a[k] - b[k])
        out["added_" + k] = sorted(b[k] - a[k])
    # A name can move to the start of a sentence, so check it anywhere in the other text.
    ta, tb = normalize_quotes(original), normalize_quotes(rewrite)
    has = lambda name, t: re.search(r"(?<![^\W_])" + re.escape(name) + r"(?![^\W_])", t) is not None
    out["dropped_names"] = sorted(n for n in a["names"] if not has(n, tb))
    out["added_names"] = sorted(n for n in b["names"] if not has(n, ta))
    low_a = normalize_quotes(original).lower()
    stems_a = {w[:5] for w in WORD.findall(low_a)}
    new_words = []
    for w in WORD.findall(normalize_quotes(mask_braces(rewrite)).lower()):
        if len(w) < 4 or w in STOPWORDS or w[:5] in stems_a or w in new_words:
            continue
        new_words.append(w)
    out["new_words"] = new_words
    return out


def mask_braces(text):
    return re.sub(r"\{\{.*?\}\}", " ", text)


def format_compare(c):
    out = ["Fact check against the original:"]
    labels = {"numbers": "numbers", "links": "links or emails", "handles": "@handles", "names": "names"}
    clean = True
    for k, label in labels.items():
        if c["dropped_" + k]:
            clean = False
            out.append("- Dropped %s: %s. Put them back unless the founder cut them." % (label, ", ".join(c["dropped_" + k])))
        if c["added_" + k]:
            clean = False
            out.append("- Added %s: %s. Each one is a new fact. Remove it, or check it came from the founder." % (label, ", ".join(c["added_" + k])))
    if c["new_words"]:
        out.append("- Words not in the original (%d): %s" % (len(c["new_words"]), ", ".join(c["new_words"][:25])))
        out.append("  Most will be plain swaps. Check that none of them adds a claim, a feature or a promise.")
    if clean and not c["new_words"]:
        out.append("- Same numbers, links, handles and names, and no new words.")
    elif clean:
        out.append("- Same numbers, links, handles and names.")
    return "\n".join(out)


def verdict(score):
    if score >= 90:
        return "Reads like a person."
    if score >= 75:
        return "Mostly reads like a person. A few tells to fix."
    if score >= 55:
        return "Several tells. Worth a rewrite pass before it goes out."
    return "Reads machine-made. Rewrite before anyone sees it."


def format_report(result, context_path=None):
    out = []
    out.append("Score: %d/100. %s" % (result["score"], result["verdict"]))
    out.append("%d words, %d sentences." % (result["words"], result["sentences"]))
    if context_path:
        out.append("Business file read: %s" % context_path)
    if result["extra_banned"]:
        out.append("Your extra words to avoid: %s" % ", ".join(result["extra_banned"]))
    out.append("")
    flagged = [c for c in result["checks"] if c["points_lost"] or c["found"]]
    clean = [c for c in result["checks"] if not (c["points_lost"] or c["found"])]
    if flagged:
        out.append("What lost points:")
        for c in sorted(flagged, key=lambda c: -c["points_lost"]):
            out.append("")
            out.append("- %s: -%d (of %d)" % (c["title"], c["points_lost"], c["max"]))
            out.append("  Why it matters: %s" % c["why"])
            for f in c["found"][:8]:
                out.append("  Found: %s" % f)
            if len(c["found"]) > 8:
                out.append("  ...and %d more" % (len(c["found"]) - 8))
            out.append("  Fix: %s" % c["fix"])
        out.append("")
    if clean:
        out.append("Passed: %s." % ", ".join(c["title"].lower() for c in clean))
    for n in result["notes"]:
        out.append("Note: %s" % n)
    out.append("")
    out.append(result["honesty"])
    return "\n".join(out)


def read_input(path):
    if path in (None, "-"):
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def resolve_extra(args):
    extra = []
    ctx = None
    if not args.no_context:
        ctx = args.context or find_context_file()
        if ctx:
            extra.extend(read_avoid_words(ctx))
    if args.extra_banned:
        extra.extend(split_words(args.extra_banned))
    return extra, ctx


def add_common_args(parser):
    parser.add_argument("--context", help="business file to read 'Words to avoid' from")
    parser.add_argument("--no-context", action="store_true", help="don't read a business file")
    parser.add_argument("--extra-banned", help="more words to avoid, comma separated")
    parser.add_argument("--allow-markdown", action="store_true",
                        help="don't flag ** and # (for READMEs, docs, pages that show Markdown)")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score a draft for machine-made tells.")
    parser.add_argument("file", nargs="?", default="-", help="text file, or - for stdin")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--min-score", type=int, help="exit with code 2 if the score is lower")
    parser.add_argument("--compare", metavar="ORIGINAL",
                        help="also check the draft against the original: dropped or added facts")
    add_common_args(parser)
    args = parser.parse_args(argv)
    try:
        text = read_input(args.file)
    except OSError as exc:
        print("Could not read %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    if not text.strip():
        print("The draft is empty. Paste some text or pass a file.", file=sys.stderr)
        return 1
    extra, ctx = resolve_extra(args)
    result = analyze(text, extra_banned=extra, allow_markdown=args.allow_markdown)
    cmp = None
    if args.compare:
        try:
            cmp = compare(read_input(args.compare), text)
        except OSError as exc:
            print("Could not read %s: %s" % (args.compare, exc), file=sys.stderr)
            return 1
    if args.json:
        result["context_file"] = ctx
        if cmp is not None:
            result["compare"] = cmp
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_report(result, ctx))
        if cmp is not None:
            print("")
            print(format_compare(cmp))
    if args.min_score is not None and result["score"] < args.min_score:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
