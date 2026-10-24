---
name: youtube-audit
description: >-
  Diagnose why a founder's YouTube channel is stuck, from their own YouTube Studio export:
  finds where people drop off (not shown, not clicked, not watched, not subscribing or
  buying), compares each video with the channel's own median instead of made-up benchmarks,
  and ranks the top 3 fixes with the numbers behind each. Use it for ANY request about why a
  channel or its videos are not growing, including asks to log in, pull analytics or compare
  with a competitor: it handles those safely and gets the right data. Triggers: "audit my
  YouTube channel", "why aren't my videos getting views", "my CTR is low", "which videos
  worked and why", "review my YouTube analytics", or a pasted or uploaded Studio CSV.
---

# youtube-audit

Read the channel's real numbers and say, plainly, what to fix first. A founder's channel is
there to reach buyers, so the audit ties every fix back to the business goal, not just views.

## What this skill reads and writes

- Reads: a YouTube Studio export (CSV) or numbers the user pastes, and the founder-context
  business file (who the channel is for, goals, topics). Optional: titles and thumbnails the
  user describes.
- Writes: `media/youtube/audit-<yyyy-mm-dd>.md`.
- Tool: `scripts/channel_stats.py` turns the export into medians, stand-outs and weak spots,
  so the math is the same every time.
- Next: `youtube-plan` to rebuild the calendar around what worked, `youtube-seo` for weak
  titles and descriptions, `youtube-shorts` to cut clips from the stand-outs.

## 1. Get the numbers

Read the founder-context business file first (`founder/context.md`, or the active file under
`~/.founder/`), so the fixes serve the channel's real goal.


Ask for a per-video export: YouTube Studio, Analytics, Advanced mode, Content tab, then
"Export current view". Ask for these columns: Views, Impressions, Impressions click-through
rate, Average view duration, Average percentage viewed, Subscribers gained, Duration, publish
date. Exports cap at 500 rows, which is plenty.

If they only paste a few numbers, work with them and say what is missing. Never fill a gap
with a guess, and never call a number "normal" or "good" for a channel like theirs: that is a
benchmark you do not have.

If they share a password, do not repeat it or use it, and tell them to change it. Do not log
in, open a browser session, or pull anyone's data: it is their account, and the export takes
two minutes. For a competitor, do not pull their stats either: not from the channel page, a fetch, a
third-party site, or the YouTube Data API with a key. Comparing against the user's own median is more useful anyway. If they
want a competitor view, they can look at public pages themselves and paste what they see.

## 2. Run the summary

```
python3 <skill>/scripts/channel_stats.py media/youtube/export.csv
```

It prints channel medians, videos at 2x the median views or more, videos well below the
median on click rate, share watched or impressions, and missing columns. Use `--json` if you
want to sort or chart.

## 3. Find the weak step

Think of four steps, each with its own fix:

| step | number | if this is weak, the fix is usually |
| --- | --- | --- |
| Shown | impressions | topics people search or browse; a clearer niche; regular uploads |
| Clicked | impressions click rate | title and thumbnail: one clear promise, readable at phone size |
| Watched | average percentage viewed, average view duration | the first 30 seconds, pacing, cutting slow parts |
| Acted | subscribers per 1,000 views, clicks to the business | a reason to subscribe, one call to action tied to the business |

Compare with the channel's own median. Outside "good CTR" numbers vary by niche and format.
The only outside reference to quote is YouTube's own: half of channels and videos have an
impressions click rate between 2% and 10% (support.google.com/youtube/answer/7628154; more in
`references/youtube-facts.md`). Use it
as a loose range, never as a grade.

Look at the stand-outs too. What do the best two have in common: topic, title shape, length,
format? That is often a stronger lesson than the weak videos.

More on reading each step, how the tool flags a video, and example fixes:
`references/reading-the-numbers.md`.

## 4. Write the audit

Keep it to one screen. In `media/youtube/audit-<date>.md`:

1. One-line diagnosis: the weakest step, with its number.
2. What is working: the stand-outs and what they share, with their numbers.
3. Top 3 fixes, most impact first. Each: the problem (with the number), the fix, and one
   action for this week ("Retitle these 2 videos", "Recut the first 20 seconds of the next
   video so the promise comes first").
4. How each fix serves the business goal in the founder-context file.
5. What the data cannot tell: small samples, missing columns, short time windows.
6. What to measure again in 4 weeks.

Every number in the audit comes from the export or the tool output. If you think something
is true but the data does not show it ("your thumbnails look busy"), label it as a guess to
check, or ask to see them.

## 5. Hand back

Show the diagnosis, the 3 fixes and the file path. Write the file even for a short audit from
pasted numbers, with the gaps listed. End every answer, including a refusal, with one line
naming the next skill:
usually `youtube-seo` for click problems, `youtube-plan` for reach or topic problems, or the
linked `yt-retention` skill for a deep look at where viewers leave.

## Rules

- Their export only. No logging in, no scraping, no third-party data you cannot cite.
- No invented benchmarks, "channel scores" or growth predictions.
- Say when a sample is too small (under 5 videos, or a few hundred views each).
- Be direct about what is not working, and kind about it.
