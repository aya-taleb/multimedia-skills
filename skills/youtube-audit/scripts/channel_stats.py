#!/usr/bin/env python3
"""Summarize a YouTube Studio export so an audit rests on the channel's own numbers.

Standard library only. Reads a CSV the user exported from YouTube Studio (Analytics,
Advanced mode, "Export current view"), or a hand-made CSV with similar columns.

Usage
  python3 channel_stats.py export.csv              # text summary
  python3 channel_stats.py export.csv --json       # machine-readable

It finds columns by name (case and wording vary between exports), skips the "Total" row,
compares each video with the channel's own median, and names the weakest funnel step.
It never invents a benchmark: the only outside reference is YouTube's own published CTR range,
and it is labeled as such.
"""
import argparse
import csv
import json
import re
import statistics
import sys

COLUMNS = {
    "title": ["video title", "title"],
    "video_id": ["content", "video", "video id"],
    "published": ["video publish time", "publish time", "published", "upload date", "date"],
    "duration": ["duration", "length"],
    "views": ["views"],
    "impressions": ["impressions"],
    "ctr": ["impressions click-through rate (%)", "impressions click-through rate", "click-through rate", "ctr"],
    "avd": ["average view duration", "avg view duration", "avg. view duration"],
    "apv": ["average percentage viewed (%)", "average percentage viewed", "avg percentage viewed"],
    "subs": ["subscribers gained", "subscribers", "subs gained", "net subscribers"],
    "watch_hours": ["watch time (hours)", "watch time hours", "watch time"],
}
YT_CTR_NOTE = ("YouTube says half of all channels and videos have an impressions CTR between 2% and 10% "
               "(support.google.com/youtube/answer/7628154). Use it as a loose range, not a target.")
MIN_VIDEOS = 5


def parse_time(value):
    """'4:05', '0:04:05', '245', '245.3' -> seconds."""
    value = (value or "").strip()
    if not value:
        return None
    if ":" in value:
        parts = [float(p) for p in value.split(":")]
        secs = 0.0
        for p in parts:
            secs = secs * 60 + p
        return secs
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def parse_num(value):
    value = (value or "").strip().replace(",", "").replace("%", "")
    if value in ("", "-", "\u2014"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def find_columns(header):
    low = [h.strip().lower() for h in header]
    found = {}
    for key, names in COLUMNS.items():
        for name in names:
            if name in low:
                found[key] = low.index(name)
                break
    return found


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise SystemExit("The file is empty.")
    header, body = rows[0], rows[1:]
    cols = find_columns(header)
    if "views" not in cols:
        raise SystemExit("No 'Views' column found. Columns seen: %s. Export per-video data from YouTube Studio "
                         "Analytics, Advanced mode, with Views, Impressions, Impressions click-through rate, "
                         "Average view duration and Subscribers." % ", ".join(header))
    videos = []
    for row in body:
        if not row or not any(c.strip() for c in row):
            continue
        first = row[0].strip().lower()
        if first in ("total", "totals"):
            continue
        get = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else ""
        v = {
            "title": get("title") or get("video_id") or "(untitled)",
            "published": get("published"),
            "duration_s": parse_time(get("duration")),
            "views": parse_num(get("views")),
            "impressions": parse_num(get("impressions")),
            "ctr": parse_num(get("ctr")),
            "avd_s": parse_time(get("avd")),
            "apv": parse_num(get("apv")),
            "subs": parse_num(get("subs")),
        }
        if v["apv"] is None and v["avd_s"] and v["duration_s"]:
            v["apv"] = round(100.0 * v["avd_s"] / v["duration_s"], 1)
        videos.append(v)
    return videos, sorted(cols)


def median(values):
    values = [x for x in values if x is not None]
    return statistics.median(values) if values else None


def summarize(videos, columns):
    out = {"videos": len(videos), "columns_found": columns, "medians": {}, "flags": [], "funnel": {},
           "notes": []}
    if len(videos) < MIN_VIDEOS:
        out["notes"].append("Only %d videos. Patterns from fewer than %d are weak; read them as hints."
                            % (len(videos), MIN_VIDEOS))
    for key in ("views", "impressions", "ctr", "avd_s", "apv", "subs", "duration_s"):
        out["medians"][key] = median(v[key] for v in videos)
    m = out["medians"]
    for v in videos:
        reasons = []
        if m["ctr"] and v["ctr"] is not None and v["ctr"] < 0.7 * m["ctr"]:
            reasons.append("click rate %.1f%% vs channel median %.1f%%" % (v["ctr"], m["ctr"]))
        if m["apv"] and v["apv"] is not None and v["apv"] < 0.7 * m["apv"]:
            reasons.append("viewed %.0f%% on average vs median %.0f%%" % (v["apv"], m["apv"]))
        if m["impressions"] and v["impressions"] is not None and v["impressions"] < 0.4 * m["impressions"]:
            reasons.append("impressions %d vs median %d" % (v["impressions"], m["impressions"]))
        if reasons:
            out["flags"].append({"title": v["title"], "why": reasons})
        if m["views"] and v["views"] and v["views"] >= 2 * m["views"]:
            out.setdefault("standouts", []).append({"title": v["title"], "views": v["views"],
                                                    "times_median": round(v["views"] / m["views"], 1)})
    # Where the funnel is weakest, judged against the channel itself
    if m["ctr"] is not None:
        out["funnel"]["click"] = "median click rate %.1f%%. %s" % (m["ctr"], YT_CTR_NOTE)
    if m["apv"] is not None:
        out["funnel"]["watch"] = "median share of each video watched: %.0f%%" % m["apv"]
    if m["impressions"] is not None and m["views"]:
        out["funnel"]["reach"] = "median impressions %d per video, median views %d" % (m["impressions"], m["views"])
    if m["subs"] is not None and m["views"]:
        out["funnel"]["convert"] = "median %.1f subscribers per 1,000 views" % (1000.0 * m["subs"] / m["views"])
    missing = [k for k in ("impressions", "ctr", "avd", "subs") if k not in columns]
    if missing:
        out["notes"].append("Missing columns: %s. Add them to the export for a full read." % ", ".join(missing))
    return out


def fmt_time(s):
    if s is None:
        return "?"
    s = int(round(s))
    return "%d:%02d" % (s // 60, s % 60)


def text_report(summary, videos):
    lines = ["Videos: %d" % summary["videos"]]
    m = summary["medians"]
    lines.append("Channel medians: views %s, impressions %s, click rate %s, avg view %s, viewed %s, subs %s" % (
        "%d" % m["views"] if m["views"] is not None else "?",
        "%d" % m["impressions"] if m["impressions"] is not None else "?",
        "%.1f%%" % m["ctr"] if m["ctr"] is not None else "?",
        fmt_time(m["avd_s"]),
        "%.0f%%" % m["apv"] if m["apv"] is not None else "?",
        "%g" % m["subs"] if m["subs"] is not None else "?"))
    for step, text in summary["funnel"].items():
        lines.append("- %s: %s" % (step, text))
    if summary.get("standouts"):
        lines.append("Stand-outs (2x the median views or more):")
        for s in summary["standouts"]:
            lines.append("  - %s: %d views, %.1fx median" % (s["title"], s["views"], s["times_median"]))
    if summary["flags"]:
        lines.append("Below the channel's own median:")
        for f in summary["flags"]:
            lines.append("  - %s: %s" % (f["title"], "; ".join(f["why"])))
    for n in summary["notes"]:
        lines.append("Note: " + n)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Summarize a YouTube Studio export.")
    ap.add_argument("csv")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    videos, columns = load(args.csv)
    if not videos:
        print("No video rows found.")
        return 1
    summary = summarize(videos, columns)
    if args.json:
        print(json.dumps({"summary": summary, "videos": videos}, indent=2))
    else:
        print(text_report(summary, videos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
