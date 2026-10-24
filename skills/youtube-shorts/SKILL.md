---
name: youtube-shorts
description: >-
  Find the Shorts hiding in a long video: reads its timestamped transcript, picks 3 to 8
  moments that make sense on their own, and gives exact cut times on sentence edges, the
  opening line, on-screen text, a title and a vertical reframing note for each, ranked. Can
  also cut the clips from the user's own file with ffmpeg on request. Use it for "turn my
  podcast / webinar / video into Shorts", "find clips in this video", "what should I cut for
  Reels or TikTok", "repurpose my long video", "best moments from this transcript", or after
  transcribe on a long recording. Works on the user's own files only, never downloads.
---

# youtube-shorts

A long video often holds a few moments that work alone: a clear tip, a strong opinion, a
short story with a point. This skill finds them in the transcript, so the founder does not
have to rewatch an hour of footage, and says exactly where to cut.

## What this skill reads and writes

- Reads: a timestamped transcript (`media/transcripts/<name>.json` or `.srt` from the
  `transcribe` skill, or a YouTube Studio transcript the user exported). The founder-context
  business file for audience, tone and off-limits topics. Optional: the video file.
- Writes: `media/shorts/<name>-shorts.md`, and cut clips in `media/shorts/` only if asked.
- Next: `talking-head-cards` to add cards to a clip, the linked `edit` skill for captions and
  tightening, `youtube-seo` for the long video itself.

If there is only a YouTube link, do not download it. Ask for their own file or an export, and
run `transcribe` on it.

## 1. Read the whole transcript first

Skim it end to end before picking anything. Note who the business file says the audience is
and what they care about. Clips that serve that buyer beat clips that are merely lively.

## 2. Pick moments that stand alone

A good Short candidate:

- Makes one point a stranger understands with no setup. If it needs "as I said earlier",
  it does not stand alone.
- Starts strong. The first sentence states the point, a surprise, or a problem. If the best
  line is in the middle, note a "cold open": start the clip on that line, then the rest.
- Ends on a finished thought, not a trailing "so yeah".
- Fits Shorts length: up to 3 minutes for square or vertical video (YouTube's limit since
  October 2024; see `references/youtube-facts.md`). Most good clips run
  20 to 60 seconds. Shorter is usually better. A Short over one minute with a copyright claim
  (music in the background, for example) gets blocked, so flag any music.

A worked example, with patterns that do and do not stand alone and how to note a cold open,
is in `references/picking-clips.md`.

Rank them by how clearly they stand alone and how well they serve the audience. Say why for
each. Do not predict views: nobody can, and a guess dressed as a number misleads.

## 3. Write each clip card

For each clip, in `media/shorts/<name>-shorts.md`:

- Rank, start and end time (on sentence edges, from the transcript's own timestamps), length.
- Why it stands alone, in one line.
- Opening line, exactly as spoken. Cold open note if needed.
- On-screen text for the first 2 seconds: the point in a few words, from what is said.
- Title: plain, specific, under 100 characters, no bait.
- Reframe note for vertical: where the speaker sits in a wide frame, any slide or screen that
  must stay visible, two-speaker clips that need a split.
- Anything to check: names, numbers, claims, music, off-limits topics, other people who
  appear and may need to agree to the clip.

Everything quoted is the speaker's words. Titles and on-screen text frame the clip; they do
not add claims, numbers or results the speaker did not say.

## 4. Cut the clips (only if asked)

If the user wants the files, and has the video and ffmpeg, cut each clip from their file:

```
ffmpeg -ss 00:12:04.200 -to 00:12:41.900 -i media/raw/episode.mp4 -c:v libx264 -c:a aac media/shorts/episode-clip1.mp4
```

Re-encoding (not `-c copy`) keeps the cut on the exact frame. This leaves the clip wide; the
vertical reframe is a job for an editor or the linked `edit` skill. Never overwrite the source.

## 5. Hand back

Show the ranked list (rank, time, length, opening line, title) and the file path. End with one
line naming the next step. The founder uploads the Shorts; this skill never posts.

## Rules

- Their own file or transcript only. No downloading.
- Quotes are exact. No invented claims, stats or results in titles or text.
- No view predictions.
- Respect the business file's off-limits list, and flag other people who appear in a clip.
