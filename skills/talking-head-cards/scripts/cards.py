#!/usr/bin/env python3
"""Timed graphic cards over a talking-head clip, synced to its transcript.

Approach credit: vtake-skills by leeoxiang (MIT, github.com/notedit/vtake-skills), which
designs cards from a transcript and renders them over the video. This file is our own code.

Standard library only. Rendering uses the user's local ffmpeg (needs libass). Free, offline.

Commands
  check  CARDS.json --transcript T.json [--video V]   validate timing, text and layout
  ass    CARDS.json --out cards.ass [--video V]        write the overlay as an ASS subtitle file
  render CARDS.json --video V --out OUT.mp4            burn the cards in with ffmpeg (asks nothing, costs nothing)
  frames CARDS.json --video V --out DIR                save one still per card, to look at before rendering
  probe  VIDEO                                         print size, length and fps

cards.json
{
  "style": {"font": "Inter", "accent": "#FF6B4A", "text": "#FFFFFF", "box": "#111111", "box_alpha": 0.82},
  "cards": [
    {"start": 3.1, "end": 6.0, "type": "point", "text": "Price for the last customer, not the first",
     "quote": "you price for the last customer", "position": "lower"},
    {"start": 9.4, "end": 12.5, "type": "number", "text": "3 offices", "sub": "in the first month",
     "quote": "three offices in the first month"}
  ]
}
types: point, number, term (word + short meaning), list (items, max 3), quote (verbatim).
position: lower (default), upper, left, right. "quote" is the words from the transcript the
card is based on: check fails when they are not in the transcript near the card's time.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

TYPES = ("point", "number", "term", "list", "quote")
POSITIONS = ("lower", "upper", "left", "right")
MIN_HOLD, MAX_HOLD, MIN_GAP = 1.2, 7.0, 0.15
MAX_CHARS = {"point": 60, "number": 14, "term": 28, "list": 34, "quote": 110}
DEFAULT_STYLE = {"font": "DejaVu Sans", "accent": "#FF6B4A", "text": "#FFFFFF", "box": "#111111",
                 "box_alpha": 0.82, "scale": 1.0}
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
                "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100, "thousand": 1000, "half": 50}


def out(msg=""):
    print(msg)
    sys.stdout.flush()


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- video info

def probe(video):
    if not shutil.which("ffprobe"):
        raise SystemExit("ffprobe was not found. Install ffmpeg (it includes ffprobe): "
                         "macOS `brew install ffmpeg`, Ubuntu `sudo apt install ffmpeg`, Windows from ffmpeg.org.")
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", video],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit("ffprobe could not read %s: %s" % (video, res.stderr.strip()[:300]))
    data = json.loads(res.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    num, _, den = (stream.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    return {"width": int(stream.get("width") or 1920), "height": int(stream.get("height") or 1080),
            "duration": float((data.get("format") or {}).get("duration") or 0), "fps": round(fps, 3)}


# ---------------------------------------------------------------- checks

def norm_words(text):
    text = text.lower().replace("’", "'")
    words = re.findall(r"[a-z0-9']+|[^\sa-z0-9']", text)
    return [w for w in words if re.match(r"[a-z0-9']", w)]


def transcript_window(transcript, start, end, pad=2.5):
    """Text of the segments that overlap [start - pad, end + pad]."""
    parts = []
    for seg in transcript.get("segments", []):
        if seg["end"] >= start - pad and seg["start"] <= end + pad:
            parts.append(seg.get("text", ""))
    return " ".join(parts)


def contains_phrase(haystack, phrase):
    h, p = norm_words(haystack), norm_words(phrase)
    if not p:
        return False
    for i in range(len(h) - len(p) + 1):
        if h[i:i + len(p)] == p:
            return True
    return False


def numbers_in(text):
    found = set(re.findall(r"\d+(?:[.,]\d+)?", text.replace(",", "")))
    for w in norm_words(text):
        if w in NUMBER_WORDS:
            found.add(str(NUMBER_WORDS[w]))
    return found


def card_text(card):
    bits = [card.get("text", ""), card.get("sub", "")]
    bits += card.get("items", [])
    return " ".join(b for b in bits if b)


def check(plan, transcript=None, info=None):
    """Return (errors, warnings). Errors block rendering."""
    errors, warnings = [], []
    cards = plan.get("cards")
    if not isinstance(cards, list) or not cards:
        return ["cards.json has no cards list."], []
    duration = (info or {}).get("duration") or (transcript or {}).get("meta", {}).get("duration") or 0
    prev_end = None
    for n, card in enumerate(sorted(cards, key=lambda c: c.get("start", 0)), 1):
        tag = "card %d (%s)" % (n, (card.get("text") or "")[:30])
        try:
            start, end = float(card["start"]), float(card["end"])
        except (KeyError, TypeError, ValueError):
            errors.append("%s: needs numeric start and end in seconds" % tag)
            continue
        kind = card.get("type", "point")
        if kind not in TYPES:
            errors.append("%s: type must be one of %s" % (tag, ", ".join(TYPES)))
        if card.get("position", "lower") not in POSITIONS:
            errors.append("%s: position must be one of %s" % (tag, ", ".join(POSITIONS)))
        if end - start < MIN_HOLD:
            errors.append("%s: on screen %.2fs, under the %.1fs people need to read it" % (tag, end - start, MIN_HOLD))
        if end - start > MAX_HOLD:
            warnings.append("%s: on screen %.1fs; over %.0fs it starts to feel stuck" % (tag, end - start, MAX_HOLD))
        if duration and end > duration + 0.05:
            errors.append("%s: ends at %.2fs, after the video ends (%.2fs)" % (tag, end, duration))
        if start < 0:
            errors.append("%s: starts before 0" % tag)
        if prev_end is not None and start < prev_end + MIN_GAP:
            errors.append("%s: overlaps or crowds the card before it (starts %.2fs, last ended %.2fs)" % (tag, start, prev_end))
        prev_end = end
        text = card.get("text", "")
        if not text.strip() and kind != "list":
            errors.append("%s: empty text" % tag)
        limit = MAX_CHARS.get(kind, 60)
        if len(text) > limit:
            errors.append("%s: %d characters; keep a %s card to %d so it reads in one glance" % (tag, len(text), kind, limit))
        if kind == "list":
            items = card.get("items") or []
            if not 2 <= len(items) <= 3:
                errors.append("%s: a list card needs 2 or 3 items" % tag)
            for item in items:
                if len(item) > MAX_CHARS["list"]:
                    errors.append("%s: list item too long: %r" % (tag, item))
        if transcript is not None:
            window = transcript_window(transcript, start, end)
            quote = card.get("quote", "")
            if not quote:
                errors.append("%s: add \"quote\": the words from the transcript this card is based on" % tag)
            elif not contains_phrase(window, quote):
                errors.append("%s: quote %r is not in the transcript near %.1fs to %.1fs" % (tag, quote, start, end))
            if kind == "quote" and not contains_phrase(window, text.strip("\"' ")):
                errors.append("%s: a quote card must use the speaker's exact words" % tag)
            said = numbers_in(window)
            for num in numbers_in(card_text(card)) - said:
                errors.append("%s: the number %s is on the card but the speaker did not say it here" % (tag, num))
            if quote and contains_phrase(window, quote):
                lead = first_word_time(transcript, quote, start - 2.5, end + 2.5)
                if lead is not None and abs(start - lead) > 1.5:
                    warnings.append("%s: starts %.1fs away from when the words are said (%.1fs)" % (tag, start - lead, lead))
    return errors, warnings


def first_word_time(transcript, quote, lo, hi):
    target = norm_words(quote)
    if not target:
        return None
    for seg in transcript.get("segments", []):
        if seg["end"] < lo or seg["start"] > hi:
            continue
        words = seg.get("words") or []
        tokens = [(norm_words(w.get("word", "")), w.get("start")) for w in words]
        flat = [(t, s) for ts, s in tokens for t in ts]
        for i in range(len(flat) - len(target) + 1):
            if [t for t, _ in flat[i:i + len(target)]] == target:
                return flat[i][1]
        if contains_phrase(seg.get("text", ""), quote) and not words:
            return seg["start"]
    return None


# ---------------------------------------------------------------- ASS output

def ass_color(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    if len(h) != 6 or not re.match(r"^[0-9a-fA-F]{6}$", h):
        raise SystemExit("Colors must look like #RRGGBB, got %r" % hex_color)
    r, g, b = h[0:2], h[2:4], h[4:6]
    a = int(round((1 - max(0.0, min(1.0, alpha))) * 255))
    return "&H%02X%s%s%s" % (a, b.upper(), g.upper(), r.upper())


def ass_time(t):
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def esc(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def layout(position, w, h):
    """Return (alignment, margin_l, margin_r, margin_v). Keeps out of the face and platform UI.

    Vertical video: bottom 22% and top 12% are covered by app buttons and captions, so cards
    sit above that. Wide video: lower third.
    """
    portrait = h > w
    side = int(w * 0.06)
    if position == "upper":
        return 8, side, side, int(h * (0.14 if portrait else 0.07))
    if position == "left":
        return 4, side, int(w * 0.45), 0
    if position == "right":
        return 6, int(w * 0.45), side, 0
    return 2, side, side, int(h * (0.24 if portrait else 0.09))


def build_ass(plan, info):
    w, h = info["width"], info["height"]
    st = dict(DEFAULT_STYLE)
    st.update(plan.get("style") or {})
    base = max(18, int(min(w, h) * 0.052 * float(st.get("scale", 1.0))))
    box = ass_color(st["box"], st.get("box_alpha", 0.82))
    text = ass_color(st["text"])
    accent = ass_color(st["accent"])
    font = st.get("font", DEFAULT_STYLE["font"]).replace(",", " ")
    lines = ["[Script Info]", "; Made by talking-head-cards (multimedia-skills). Edit freely.",
             "ScriptType: v4.00+", "PlayResX: %d" % w, "PlayResY: %d" % h, "WrapStyle: 0",
             "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
             "Alignment, MarginL, MarginR, MarginV, Encoding"]
    for name, size, colour, bold in (("Card", base, text, 0), ("Big", int(base * 2.2), accent, 1),
                                     ("Small", int(base * 0.75), text, 0), ("Term", int(base * 1.2), accent, 1)):
        lines.append("Style: %s,%s,%d,%s,%s,%s,%s,%d,0,0,0,100,100,0,0,3,%d,0,2,40,40,40,1"
                     % (name, font, size, colour, colour, box, box, bold, max(8, int(base * 0.45))))
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for card in sorted(plan["cards"], key=lambda c: c["start"]):
        align, ml, mr, mv = layout(card.get("position", "lower"), w, h)
        kind = card.get("type", "point")
        fade = r"{\an%d\fad(180,160)}" % align
        if kind == "number":
            body = r"{\rBig}%s" % esc(card["text"])
            if card.get("sub"):
                body += r"\N{\rSmall}%s" % esc(card["sub"])
        elif kind == "term":
            body = r"{\rTerm}%s" % esc(card["text"])
            if card.get("sub"):
                body += r"\N{\rSmall}%s" % esc(card["sub"])
        elif kind == "list":
            head = (r"{\b1}%s{\b0}\N" % esc(card["text"])) if card.get("text") else ""
            body = head + r"\N".join("%d. %s" % (i, esc(item)) for i, item in enumerate(card.get("items", []), 1))
        elif kind == "quote":
            body = r"{\i1}\"%s\"{\i0}" % esc(card["text"].strip("\"' "))
        else:
            body = esc(card["text"])
        lines.append("Dialogue: 0,%s,%s,Card,,%d,%d,%d,,%s%s" % (
            ass_time(card["start"]), ass_time(card["end"]), ml, mr, mv, fade, body))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- render

def ffmpeg_filter_path(path):
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_cmd(video, ass_path, out_path):
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video,
            "-vf", "ass='%s'" % ffmpeg_filter_path(ass_path),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", out_path]


def need_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg was not found. Install it: macOS `brew install ffmpeg`, "
                         "Ubuntu `sudo apt install ffmpeg`, Windows from ffmpeg.org. Then run this again.")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def gate(plan, args, info):
    transcript = load(args.transcript) if getattr(args, "transcript", None) else None
    errors, warnings = check(plan, transcript, info)
    for w in warnings:
        out("warning: " + w)
    if errors:
        for e in errors:
            out("error: " + e)
        out("Fix the cards above, then run again. Nothing was rendered.")
        return False
    return True


def cmd_check(args):
    plan = load(args.cards)
    info = probe(args.video) if args.video else None
    if not gate(plan, args, info):
        return 1
    out("OK: %d cards, timing and text check out." % len(plan["cards"]))
    return 0


def cmd_ass(args):
    plan = load(args.cards)
    info = probe(args.video) if args.video else {"width": args.width, "height": args.height, "duration": 0}
    if not gate(plan, args, info):
        return 1
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(build_ass(plan, info))
    out("Wrote %s (%dx%d)" % (args.out, info["width"], info["height"]))
    return 0


def cmd_render(args):
    need_ffmpeg()
    plan = load(args.cards)
    info = probe(args.video)
    if not gate(plan, args, info):
        return 1
    ass_path = os.path.splitext(args.out)[0] + ".ass"
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(build_ass(plan, info))
    if os.path.abspath(args.out) == os.path.abspath(args.video):
        out("The output would overwrite the original video. Pick another --out.")
        return 2
    res = run(render_cmd(args.video, ass_path, args.out))
    if res.returncode != 0:
        msg = res.stderr.strip()[-600:]
        out("ffmpeg failed: %s" % msg)
        if "No such filter" in msg or "ass" in msg and "not found" in msg:
            out("Your ffmpeg was built without libass. Install a full build (brew install ffmpeg, or the "
                "static builds at ffmpeg.org) and run again.")
        return 3
    out("Rendered %s with %d cards (overlay file %s)." % (args.out, len(plan["cards"]), ass_path))
    return 0


def cmd_frames(args):
    need_ffmpeg()
    plan = load(args.cards)
    info = probe(args.video)
    if not gate(plan, args, info):
        return 1
    os.makedirs(args.out, exist_ok=True)
    ass_path = os.path.join(args.out, "preview.ass")
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(build_ass(plan, info))
    for n, card in enumerate(sorted(plan["cards"], key=lambda c: c["start"]), 1):
        t = (card["start"] + card["end"]) / 2
        png = os.path.join(args.out, "card-%02d.png" % n)
        res = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % t, "-i", args.video,
                   "-vf", "setpts=PTS+%.3f/TB,ass='%s'" % (t, ffmpeg_filter_path(ass_path)),
                   "-frames:v", "1", png])
        if res.returncode != 0:
            out("Could not grab card %d: %s" % (n, res.stderr.strip()[-300:]))
            return 3
        out("Saved %s (at %.1fs)" % (png, t))
    return 0


def cmd_probe(args):
    out(json.dumps(probe(args.video)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Timed graphic cards over a talking-head clip.")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("cards")
    c.add_argument("--transcript")
    c.add_argument("--video")
    a = sub.add_parser("ass")
    a.add_argument("cards")
    a.add_argument("--out", required=True)
    a.add_argument("--transcript")
    a.add_argument("--video")
    a.add_argument("--width", type=int, default=1080)
    a.add_argument("--height", type=int, default=1920)
    r = sub.add_parser("render")
    r.add_argument("cards")
    r.add_argument("--video", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--transcript")
    f = sub.add_parser("frames")
    f.add_argument("cards")
    f.add_argument("--video", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--transcript")
    p = sub.add_parser("probe")
    p.add_argument("video")
    args = ap.parse_args(argv)
    handlers = {"check": cmd_check, "ass": cmd_ass, "render": cmd_render, "frames": cmd_frames, "probe": cmd_probe}
    if args.cmd not in handlers:
        ap.print_help()
        return 2
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
