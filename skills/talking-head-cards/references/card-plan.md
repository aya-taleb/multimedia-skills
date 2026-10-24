# Card plan: format, example and style

## Full example

Transcript lines (from `media/transcripts/ep3.json`):

```
[00:04.2] But you price for the last customer, the one who has ten other options.
[00:09.5] We had three offices in the first month.
[00:14.5] Churn is just people leaving.
[00:21.0] So three things: talk to them weekly, fix the top complaint, and send the menu early.
```

Plan (`media/cards/ep3-cards.json`):

```json
{
  "style": {"font": "Inter", "accent": "#FF6B4A", "text": "#FFFFFF", "box": "#111111", "box_alpha": 0.82, "scale": 1.0},
  "cards": [
    {"start": 4.8, "end": 8.4, "type": "point", "text": "Price for the last customer",
     "quote": "price for the last customer"},
    {"start": 9.6, "end": 13.0, "type": "number", "text": "3 offices", "sub": "first month",
     "quote": "three offices in the first month"},
    {"start": 14.6, "end": 18.0, "type": "term", "text": "Churn", "sub": "people leaving",
     "quote": "churn is just people leaving"},
    {"start": 21.4, "end": 26.5, "type": "list", "text": "Three things",
     "items": ["Talk to them weekly", "Fix the top complaint", "Send the menu early"],
     "quote": "talk to them weekly, fix the top complaint, and send the menu early"}
  ]
}
```

## Fields

| field | needed | notes |
| --- | --- | --- |
| start, end | yes | seconds from the start of the video |
| type | yes | point, number, term, list, quote |
| text | yes | the main line (for list, an optional heading) |
| sub | no | small second line for number and term |
| items | list only | 2 or 3 short items |
| quote | yes | words from the transcript near this time; the check looks for them |
| position | no | lower (default), upper, left, right |

Style: `font` is any font installed on the machine (the default is DejaVu Sans, which most
systems have). `scale` makes all cards bigger or smaller. Colors are `#RRGGBB`.

## Brand colors

Read them from the founder-context business file if it lists any. Use one accent color for
numbers and terms, white text, and a dark box. A box behind the text keeps it readable over
any background. Do not put text straight on the video.

## How many cards

- 30 second clip: 2 to 3 cards.
- 60 second clip: 4 to 6.
- 10 minute video: pick the strongest 15 to 25 moments, not every sentence.

Skip cards during jokes, stories and feelings. Text there pulls the eye off the face at the
moment the face matters most.

## HyperFrames route (optional)

HyperFrames (Apache 2.0, github.com/heygen-com/hyperframes) renders HTML compositions to MP4,
so cards can slide, scale or type on. Its README, checked 2026-10-23, says:

- Needs Node.js 22 or newer and FFmpeg.
- `npx hyperframes init my-video --video media/raw/ep3.mp4 --non-interactive` scaffolds a
  project around a video.
- `npx hyperframes preview` opens a live preview. `npx hyperframes render -o out.mp4` renders.
- `npx hyperframes doctor` checks the setup. `npx hyperframes lint` checks the HTML.
- Elements are timed with `data-start` and `data-duration` (seconds) and animated with a
  seekable library such as GSAP.

To use it, turn each card into a timed element with the same start and end as the plan, and
keep the same honesty rules. The plan file stays the source of truth, so run `cards.py check`
on it first. Commands change between versions: run `npx hyperframes <command> --help` before
relying on a flag.
