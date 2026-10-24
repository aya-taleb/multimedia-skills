# Job spec: youtube-audit

Written before reading any other YouTube audit skill.

## The job

A founder's channel is not working and they want to know why and what to fix first. They can
export numbers from YouTube Studio. They need a short, honest diagnosis that ranks the fixes,
based on their own numbers, not on generic advice.

## Inputs

- A YouTube Studio export (CSV) or pasted numbers: per video views, impressions, click rate,
  average view duration, average percentage viewed, subscribers gained, upload date, length.
- The business file (who they want to reach, what the channel is for).
- Optional: their titles and thumbnails described, their upload schedule.

## Output

- A read of where the funnel breaks: not shown (impressions), not clicked (click rate),
  not watched (retention), not converting (subs, clicks to the business). Compared to the
  channel's own median, since outside benchmarks vary.
- Top 3 fixes, each tied to numbers in the export, with one concrete next action.
- What the data cannot tell (small samples, missing columns).
- A small stdlib script that summarizes the CSV, so the math is repeatable.
- Written to `media/youtube/audit-<date>.md`.

## What good looks like

- Every claim cites a number from the export.
- Says when the sample is too small to judge.
- Links fixes to the business goal, not just views.

## Must not

- Invent industry benchmarks or numbers not in the export.
- Log in to YouTube or scrape the channel.
