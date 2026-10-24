---
name: talking-head-cards
description: >-
  Add timed graphic cards over a talking-head, podcast or interview clip, each one popping up
  as the speaker says the point: key ideas, numbers, terms, short lists, pull quotes. Plans
  the cards from the transcript, checks every card against what was actually said (no
  invented numbers or quotes), keeps them clear of the face and the app buttons, and renders
  locally with ffmpeg for free. Use it for "add text pop-ups to my video", "make my talking
  head more visual", "put the key points on screen", "b-roll text cards", "lower thirds",
  "make this podcast clip look like a pro edit", "overlay graphics synced to what I say", or
  after transcribe when the user wants the clip to hold attention.
---

# talking-head-cards

Put short graphic cards on screen at the moment the speaker says the matching words. The
cards make a talking head easier to follow with the sound off, and they help people remember
the point. The plan comes from the transcript, so every card is tied to a real line.

Approach credit: vtake-skills by leeoxiang (MIT, github.com/notedit/vtake-skills), which
designs cards from a transcript and renders them over the video. Our tool and rules are our
own: `scripts/cards.py` (standard library; renders with the user's ffmpeg).

## What this skill reads and writes

- Reads: the video file (often `media/raw/`), its transcript JSON from the `transcribe` skill
  (`media/transcripts/<name>.json`), and the founder-context business file for brand colors,
  tone and off-limits topics. If the business file has no colors, ask once or use the neutral
  default.
- Writes: `media/cards/<name>-cards.json` (the plan), `<name>-cards.ass` (the overlay),
  `media/cards/<name>-preview/` (one still per card), and `media/cards/<name>-cards.mp4`.
  The original video is never overwritten.
- Next: the linked `edit` skill for cuts and captions, `youtube-shorts` to pick clips, or
  post the video yourself. This skill never uploads or posts.

## 1. Get the transcript first

If there is no transcript JSON, run the `transcribe` skill on the file first (ask the user).
Word timings make the cards land on time, so ask transcribe for them (`--words`, or SRT/VTT
output, which turns them on). Work only on files the user made or has rights to. Never pull
a video from a platform.

Run `python3 <skill>/scripts/cards.py probe <video>` to get the size and length. Vertical
(9:16) and wide (16:9) need different placement, and the tool handles both.

## 2. Plan the cards

Read the transcript and pick the moments worth a card. Fewer is better: about one card every
8 to 15 seconds, and none during a story or an emotional beat, where text gets in the way.

Five card types:

| type | use it for | keep it to |
| --- | --- | --- |
| point | the one idea of that stretch, in the speaker's words or very close | 60 characters |
| number | a figure the speaker says out loud, with a short label in `sub` | 14 characters |
| term | a word the viewer may not know, with a plain meaning in `sub` | 28 characters |
| list | 2 or 3 items the speaker lists | 34 per item |
| quote | a line worth pulling out, exactly as spoken | 110 characters |

Rules that keep the cards honest, and why:

- Every card has a `quote`: the words from the transcript it is based on. The tool checks the
  words are there, near the card's time. A card that says something the speaker did not say
  puts words in their mouth.
- Numbers only when the speaker said them. "Three offices" can become "3 offices". A number
  they did not say ("40% growth") is made up, even if it sounds right. The tool blocks it.
- Quote cards use the exact words. Trim the ends, never the middle.
- No claims about other people or companies, no customer names, nothing on the business
  file's off-limits list.

Timing: start a card at the first word of its quote, or up to half a second before. Hold it
at least 1.2 seconds and about 1 second per 4 words. Leave a short gap between cards. Cards
cannot overlap.

Placement: `lower` by default. On vertical video, the tool keeps cards above the bottom
quarter, where app buttons and captions sit, and below the top strip. Use `upper` when the
speaker's face sits low in frame. `left` or `right` suit wide shots with the speaker off
center.

Write the plan to `media/cards/<name>-cards.json`. The format is in the tool's header, and
`references/card-plan.md` has a full example and style notes.

## 3. Check, then preview

```
python3 cards.py check media/cards/demo-cards.json --transcript media/transcripts/demo.json --video media/raw/demo.mp4
python3 cards.py frames media/cards/demo-cards.json --video media/raw/demo.mp4 --out media/cards/demo-preview --transcript media/transcripts/demo.json
```

Fix every error the check prints. Then look at the preview stills yourself if you can read
images, and show the user the plan as a short table: time, type, text, the line it comes
from. Ask if they want changes before the full render. Rendering is free, so this is about
their taste, not cost.

## 4. Render

```
python3 cards.py render media/cards/demo-cards.json --video media/raw/demo.mp4 --out media/cards/demo-cards.mp4 --transcript media/transcripts/demo.json
```

The tool burns the cards in with ffmpeg, keeps the original audio, and refuses to overwrite
the source. If ffmpeg is missing or lacks libass, it says how to install a full build.

Optional, for animated cards: if the user has HyperFrames installed (`npx hyperframes
doctor` works), the same plan can drive a HyperFrames composition instead. See
`references/card-plan.md`. Do not install it without asking.

## 5. Hand back

Give the output path, the number of cards, and the plan table. Say that a person should
watch it once before posting, since timing that looks right on paper can feel early or late.
End with one line naming the next step: the linked `edit` skill for cuts and captions, or
`youtube-shorts` for clips. The user posts it themselves.

## Rules

- Cards come from the transcript. No invented words, numbers or quotes.
- Never overwrite the user's original video.
- Only the user's own footage. No downloading.
- Free and local. Nothing here needs a paid service.
- Respect the off-limits list in the business file.
