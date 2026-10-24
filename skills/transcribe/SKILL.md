---
name: transcribe
description: >-
Turn an audio or video file the user owns into a timestamped transcript, on their own
  computer with faster-whisper (free, nothing uploaded). Writes a readable transcript with
  [mm:ss] stamps, plus SRT or VTT captions and a JSON file other skills can read, and walks
  the user through the install if faster-whisper is missing. Use it for ANY request to
  transcribe, caption or get the words of a recording, including when the user pastes a
  YouTube, Instagram or TikTok link: this skill knows how to handle links safely (it never
  downloads from platforms and shows how to export your own file). Triggers: "transcribe
  this", "get the transcript of my podcast / webinar / interview / reel", "make subtitles",
  "SRT file", "what did I say at minute 12", or before talking-head-cards, chapters or clips.
---

# transcribe

Make a transcript with timestamps from a recording the user has as a file. Everything runs
locally, so private calls and unreleased videos never leave the machine. The tool is
`scripts/transcribe.py` (standard library; it calls faster-whisper when installed).

## What this skill reads and writes

- Reads: one audio or video file in the project (often `media/raw/`). The founder-context
  business file only if the user wants names spelled a certain way.
- Writes: `media/transcripts/<name>.md` (readable), `<name>.json` (segments, for other
  skills), and `<name>.srt` / `<name>.vtt` when captions are asked for.
- Next: `talking-head-cards` for graphic cards over the clip, the linked `yt-chapters` or
  `edit` skills, `youtube-shorts` to find clips, or a post-writing skill to repurpose it.

## 1. Check the source is a file they have

Ask for, or find, the file path. Then make sure of two things.

- It is a file on this computer. If the user gives a YouTube, Instagram, TikTok or other
  link, do not download it, not with yt-dlp, a browser, or anything else. Downloading breaks
  those platforms' terms, and someone else's video is not theirs to transcribe. Explain that
  in one line, then tell them how to get their own copy:
  - YouTube: YouTube Studio, Content, the video's menu, Download (their own uploads).
  - Instagram: Settings, Your activity, Download your information, or the original file.
  - TikTok: their own post, Share, Save video. Or the original from their phone.
  - Zoom, Riverside, Descript and phone recorders: the export or the original file.
- It is theirs, or they have permission. If they say it is someone else's video, say you
  can only work on recordings they made or have rights to.

When you say no to a link or someone else's video, keep it short and complete:

1. One line on why: you only work on files the user owns or exported, and downloading from
   platforms breaks their terms.
2. Do not point them to another way to get that content (YouTube's transcript panel, a
   download site, pasting it in), and do not offer to study or rework someone else's script.
3. A way forward with their own material: the export steps above for their own videos, and
   an offer to help write an original script with a named skill (the linked `yt-script`).

## 2. Check the setup

```
python3 <skill>/scripts/transcribe.py doctor
```

If faster-whisper is missing, the tool prints the install steps. Walk the user through them
and say what to expect: a one-time model download (about 0.5 GB for `small`, about 3 GB for
`large-v3`), and that it runs fine on a normal laptop CPU, just slower. Do not run `pip
install` yourself without asking, because it changes their machine. Offer to do it.

If faster-whisper is installed in a separate Python (a venv), run the tool with that Python.

## 3. Pick the settings

- Model: `small` is the default and is good for clear speech. Use `medium` or `large-v3`
  for accents, noise, or several speakers, and say it will take longer. Use `turbo` when the
  user wants it fast.
- Language: leave it out to detect. Set it (`--language ar`, `--language es`) when you know
  it, since detection can slip on short clips or mixed languages.
- Formats: `md,json` by default. Add `srt` or `vtt` for captions. `--words` keeps word timings
  in the JSON for tools that sync to single words (the SRT and VTT options turn it on).

## 4. Run it

```
python3 <skill>/scripts/transcribe.py run media/raw/episode-12.mp4 --formats md,json,srt --out media/transcripts
```

A long recording can take a while on a CPU. Tell the user before you start. If it fails,
read the message: a damaged file or one with no audio track is the usual cause. If it finds
no speech, try the right `--language` or a bigger model.

To make captions later from an existing JSON, without the model:
`transcribe.py convert media/transcripts/episode-12.json --formats srt,vtt`

## 5. Hand it back

Show the file paths and a short preview (the first few `[mm:ss]` lines from the .md). Then
say plainly: it is a machine transcript, so check names, numbers and quotes before publishing
any of them. Say this even before a run, when you explain what they will get.
Whisper often misspells names and brand words. If the business file lists the right
spellings, offer to fix them in the transcript, and only change what you are sure of.

Do not "clean up" what the speaker said into something they did not say. Fixing a misheard
word is fine. Rewriting a sentence is a different job, and it must be marked as an edit.

End with one line naming the next skill that fits, by name: `talking-head-cards` for text
cards over the clip, `youtube-shorts` to find clips, `youtube-seo` or the linked `yt-chapters`
for chapters, or a post-writing skill.

## Rules

- Files only. Never download from any platform or site, even when asked, even "just this once".
- Local only. Do not send the audio to a paid API from this skill. If the user wants a hosted
  service, say it costs money and uploads their audio, and let them choose.
- Never invent words for parts that are silent or unclear. Leave the gap.
- Say it is a machine transcript every time.
- Ask before installing anything.
