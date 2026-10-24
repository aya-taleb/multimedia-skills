#!/usr/bin/env python3
"""Transcribe a local audio or video file with timestamps, on this machine.

Uses faster-whisper (MIT, https://github.com/SYSTRAN/faster-whisper) when it is installed.
This file itself is standard library only. It never downloads media from a website.

Usage
  python3 transcribe.py doctor                       # what is installed, what to install
  python3 transcribe.py run FILE [--model small] [--language en] [--words]
                         [--formats md,srt,vtt,json] [--out media/transcripts]
  python3 transcribe.py convert TRANSCRIPT.json --formats srt,vtt   # re-export, no model

Outputs (by default in media/transcripts/<name>.*):
  <name>.json  segments with start, end, text (and words when --words)
  <name>.md    readable transcript with [mm:ss] stamps
  <name>.srt / <name>.vtt  caption files, lines split to stay readable

Exit codes: 0 ok, 2 bad input or refused, 3 faster-whisper missing, 4 transcription failed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

MEDIA_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mov", ".mkv",
             ".webm", ".m4v", ".avi", ".wma", ".mpga", ".mpeg"}
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
PLATFORM_HINTS = ("youtube.com", "youtu.be", "instagram.com", "tiktok.com", "facebook.com", "fb.watch",
                  "x.com/", "twitter.com", "vimeo.com", "linkedin.com", "twitch.tv", "snapchat.com")
MODELS = ("tiny", "base", "small", "medium", "large-v3", "turbo",
          "tiny.en", "base.en", "small.en", "medium.en", "distil-large-v3")

INSTALL_HELP = """faster-whisper is not installed, so nothing can be transcribed on this machine yet.

Install it (Python 3.9 or newer), ideally in a virtual environment:
  python3 -m venv ~/.venvs/whisper
  ~/.venvs/whisper/bin/pip install faster-whisper
Then run this tool with that Python:
  ~/.venvs/whisper/bin/python transcribe.py run <file>

Notes:
- The first run downloads the model you pick (small is about 0.5 GB, large-v3 about 3 GB).
- It runs on a normal CPU. An NVIDIA GPU is faster but needs CUDA 12 and cuDNN 9.
- ffmpeg is not required: faster-whisper decodes audio itself.
- Docs: https://github.com/SYSTRAN/faster-whisper"""


class Refused(Exception):
    pass


def out(msg=""):
    print(msg)
    sys.stdout.flush()


# ---------------------------------------------------------------- input checks

def check_source(path):
    """Only local files the user has. URLs are refused, platform links with a reason."""
    if URL_RE.match(path) or any(h in path.lower() for h in PLATFORM_HINTS):
        if any(h in path.lower() for h in PLATFORM_HINTS):
            raise Refused(
                "That is a link to a platform, not a file. This tool does not download from YouTube, "
                "Instagram, TikTok or similar sites, since that breaks their terms. If it is your own "
                "video, export it from the platform (YouTube Studio, Instagram 'Download your information', "
                "TikTok 'Save video' on your own post) or use your original file, then run this on that file.")
        raise Refused("This tool only reads files on this computer. Download your own copy first, then pass its path.")
    if not os.path.exists(path):
        raise Refused("No file at %s. Check the path." % path)
    if os.path.isdir(path):
        raise Refused("%s is a folder. Pass one audio or video file." % path)
    if os.path.splitext(path)[1].lower() not in MEDIA_EXT:
        raise Refused("%s does not look like audio or video (%s). Supported: %s"
                      % (path, os.path.splitext(path)[1] or "no extension", ", ".join(sorted(MEDIA_EXT))))
    if os.path.getsize(path) == 0:
        raise Refused("%s is empty." % path)
    return os.path.abspath(path)


# ---------------------------------------------------------------- time and text formats

def stamp(seconds, sep=",", hours=True):
    if seconds is None or seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    if hours:
        return "%02d:%02d:%02d%s%03d" % (h, m, s, sep, ms)
    return "%02d:%02d" % (h * 60 + m, s)


def clean_text(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def pack(words, max_chars=42, max_lines=2):
    """Group words into cues: each cue is at most max_lines lines of at most max_chars.

    Greedy line filling, so every line fits. A single word longer than a line gets its own line.
    Returns a list of (first_index, last_index, text_with_newlines).
    """
    cues_out, lines, line, first = [], [], "", 0
    for i, word in enumerate(words):
        if line and len(line) + 1 + len(word) > max_chars:
            lines.append(line)
            line = ""
            if len(lines) == max_lines:
                cues_out.append((first, i - 1, "\n".join(lines)))
                lines, first = [], i
        line = (line + " " + word).strip()
    if line:
        lines.append(line)
    if lines:
        cues_out.append((first, len(words) - 1, "\n".join(lines)))
    return cues_out


def split_cue(segment, max_chars=42, max_lines=2):
    """Split one segment into caption cues of at most max_lines x max_chars.

    Uses word timings when present; otherwise spreads time by character count.
    """
    timed = [w for w in (segment.get("words") or []) if clean_text(w.get("word"))]
    if timed:
        words = [clean_text(w["word"]) for w in timed]
        return [{"start": timed[a]["start"], "end": timed[b]["end"], "text": text}
                for a, b, text in pack(words, max_chars, max_lines)]
    words = clean_text(segment["text"]).split(" ")
    groups = pack(words, max_chars, max_lines)
    total = sum(len(t) for _, _, t in groups) or 1
    span = max(segment["end"] - segment["start"], 0.0)
    t, result = segment["start"], []
    for _, _, text in groups:
        dur = span * len(text) / total
        result.append({"start": t, "end": t + dur, "text": text})
        t += dur
    if result:
        result[-1]["end"] = segment["end"]
    return result


def cues(segments, max_chars=42):
    result = []
    for seg in segments:
        if clean_text(seg.get("text")):
            result.extend(split_cue(seg, max_chars))
    for i in range(len(result) - 1):  # no overlaps
        if result[i]["end"] > result[i + 1]["start"]:
            result[i]["end"] = result[i + 1]["start"]
    return result


def to_srt(segments, max_chars=42):
    blocks = []
    for n, c in enumerate(cues(segments, max_chars), 1):
        blocks.append("%d\n%s --> %s\n%s\n" % (n, stamp(c["start"]), stamp(c["end"]), c["text"]))
    return "\n".join(blocks)


def to_vtt(segments, max_chars=42):
    blocks = ["WEBVTT\n"]
    for c in cues(segments, max_chars):
        blocks.append("%s --> %s\n%s\n" % (stamp(c["start"], "."), stamp(c["end"], "."), c["text"]))
    return "\n".join(blocks)


def to_md(segments, meta):
    lines = ["# Transcript: %s" % meta.get("source_name", "recording"), "",
             "- Source file: %s" % meta.get("source_name", ""),
             "- Length: %s" % stamp(meta.get("duration") or 0, hours=False),
             "- Language: %s%s" % (meta.get("language") or "unknown",
                                   " (detected, %.0f%% sure)" % (100 * meta["language_probability"])
                                   if meta.get("language_probability") else ""),
             "- Model: faster-whisper %s, on this computer" % meta.get("model", "?"),
             "- Machine transcript: check names, numbers and quotes before you publish them.", ""]
    for seg in segments:
        text = clean_text(seg.get("text"))
        if text:
            lines.append("[%s] %s" % (stamp(seg["start"], hours=False), text))
    return "\n".join(lines) + "\n"


def write_outputs(segments, meta, out_dir, stem, formats):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    data = {"meta": meta, "segments": segments}
    makers = {
        "json": lambda: json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        "md": lambda: to_md(segments, meta),
        "srt": lambda: to_srt(segments),
        "vtt": lambda: to_vtt(segments),
        "txt": lambda: "\n".join(clean_text(s["text"]) for s in segments if clean_text(s.get("text"))) + "\n",
    }
    for fmt in formats:
        if fmt not in makers:
            raise Refused("Unknown format %r. Use any of: %s" % (fmt, ", ".join(sorted(makers))))
        path = os.path.join(out_dir, "%s.%s" % (stem, fmt))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(makers[fmt]())
        written.append(path)
    return written


# ---------------------------------------------------------------- the model (patched in tests)

def load_backend():
    try:
        from faster_whisper import WhisperModel  # noqa: F401
        return WhisperModel
    except ImportError:
        return None


def pick_device():
    if shutil.which("nvidia-smi"):
        try:
            subprocess.run(["nvidia-smi", "-L"], capture_output=True, check=True, timeout=10)
            return "cuda", "float16"
        except (subprocess.SubprocessError, OSError):
            pass
    return "cpu", "int8"


def transcribe(path, model_name, language, words, backend=None, device=None):
    WhisperModel = backend or load_backend()
    if WhisperModel is None:
        raise ImportError(INSTALL_HELP)
    device, compute = device or pick_device()
    model = WhisperModel(model_name, device=device, compute_type=compute)
    kwargs = {"beam_size": 5, "vad_filter": True, "word_timestamps": bool(words)}
    if language:
        kwargs["language"] = language
    seg_iter, info = model.transcribe(path, **kwargs)
    segments = []
    for seg in seg_iter:
        item = {"start": round(float(seg.start), 3), "end": round(float(seg.end), 3), "text": clean_text(seg.text)}
        if words and getattr(seg, "words", None):
            item["words"] = [{"start": round(float(w.start), 3), "end": round(float(w.end), 3), "word": w.word.strip()}
                             for w in seg.words]
        segments.append(item)
    meta = {"model": model_name, "device": device, "language": getattr(info, "language", None),
            "language_probability": round(float(getattr(info, "language_probability", 0) or 0), 3),
            "duration": round(float(getattr(info, "duration", 0) or 0), 3)}
    return segments, meta


# ---------------------------------------------------------------- commands

def cmd_doctor(_args):
    out("Python: %s" % sys.version.split()[0])
    backend = load_backend()
    out("faster-whisper: %s" % ("installed" if backend else "NOT installed"))
    out("ffmpeg: %s (optional; faster-whisper does not need it)" % ("found" if shutil.which("ffmpeg") else "not found"))
    device, compute = pick_device()
    out("Device: %s (%s)" % (device, compute))
    if not backend:
        out("")
        out(INSTALL_HELP)
        return 3
    out("Ready. Try: python3 transcribe.py run media/raw/episode.mp3 --formats md,srt")
    return 0


def cmd_run(args):
    path = check_source(args.file)
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    if args.model not in MODELS and not os.path.isdir(args.model):
        raise Refused("Unknown model %r. Pick one of: %s (or a local model folder)." % (args.model, ", ".join(MODELS)))
    if load_backend() is None:
        out(INSTALL_HELP)
        return 3
    out("Transcribing %s with the %s model on this computer. Long files take a while." % (os.path.basename(path), args.model))
    try:
        segments, meta = transcribe(path, args.model, args.language, args.words or "srt" in formats or "vtt" in formats)
    except ImportError as exc:
        out(str(exc))
        return 3
    except Exception as exc:  # the decoder or model failed; say so plainly
        out("Transcription failed: %s" % exc)
        out("Common causes: the file is damaged or has no audio track, or the disk is full during the model download.")
        return 4
    meta["source_name"] = os.path.basename(path)
    if not any(clean_text(s.get("text")) for s in segments):
        out("No speech found. The file may be silent, music only, or in a language the model missed. "
            "Try --language with the right code, or a bigger model.")
    stem = os.path.splitext(os.path.basename(path))[0]
    for p in write_outputs(segments, meta, args.out, stem, formats):
        out("Wrote %s" % p)
    return 0


def cmd_convert(args):
    with open(args.file, encoding="utf-8") as fh:
        data = json.load(fh)
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    stem = os.path.splitext(os.path.basename(args.file))[0]
    out_dir = args.out or os.path.dirname(os.path.abspath(args.file))
    for p in write_outputs(data["segments"], data.get("meta", {}), out_dir, stem, formats):
        out("Wrote %s" % p)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Transcribe a local audio or video file with timestamps.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("doctor")
    r = sub.add_parser("run")
    r.add_argument("file")
    r.add_argument("--model", default="small", help="tiny, base, small (default), medium, large-v3, turbo, or *.en")
    r.add_argument("--language", help="language code like en or ar; leave out to detect")
    r.add_argument("--words", action="store_true", help="keep word-level timestamps in the JSON")
    r.add_argument("--formats", default="md,json", help="any of md,json,srt,vtt,txt (default md,json)")
    r.add_argument("--out", default="media/transcripts")
    c = sub.add_parser("convert")
    c.add_argument("file")
    c.add_argument("--formats", default="srt,vtt")
    c.add_argument("--out")
    args = ap.parse_args(argv)
    handlers = {"doctor": cmd_doctor, "run": cmd_run, "convert": cmd_convert}
    if args.cmd not in handlers:
        ap.print_help()
        return 2
    try:
        return handlers[args.cmd](args)
    except Refused as exc:
        out(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
