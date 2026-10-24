---
name: youtube-plan
description: >-
  Build a YouTube plan a busy founder can actually keep: works out a pace from the hours they
  really have, then lays out the next 4 to 8 weeks of videos with working titles, the viewer
  question each answers, the format, the Shorts to cut from each, and how each video leads
  back to the business. No promised views. Use it for "plan my YouTube channel", "what
  videos should I make", "YouTube content calendar", "how often should I post on YouTube",
  "video ideas for my business", "I want to start a YouTube channel for my startup", or after
  youtube-audit when the plan needs to change.
---

# youtube-plan

Most founder channels stop in week three because the plan assumed time nobody had. This skill
starts from the hours, then fills the calendar with videos the founder's buyers are already
asking about.

## What this skill reads and writes

- Reads: the founder-context business file (who they serve, goals, topics, proof, tone,
  off-limits). The latest `media/youtube/audit-*.md` if `youtube-audit` ran. Any idea list
  the user has.
- Writes: `media/youtube/plan-<yyyy-mm>.md`.
- Next: the linked `yt-script` skill to script the first video, `youtube-seo` before each
  upload, `youtube-shorts` after each long video.

## 1. Ask what is real (one batch of questions)

Skip anything the business file or the user already said:

- Hours per week for YouTube, all in (planning, filming, editing, uploading).
- Format they can make: talking head, screen recording, podcast or interview, a mix.
- Who does the editing: them, a tool, an editor.
- What the channel is for: leads, trust before a sales call, hiring, a launch.
- Videos already made, and any ideas they want in.

## 2. Work out the pace, and show the math

Rough hours per finished long video, as a starting point to adjust with the founder:

| format | first videos | once practiced |
| --- | --- | --- |
| screen recording tutorial | 4 to 6 h | 2 to 3 h |
| talking head, light edit | 5 to 8 h | 3 to 4 h |
| interview or podcast | 6 to 10 h (with guest prep) | 4 to 6 h |

These are planning guesses, not measured facts. Say so, and ask how long their last video
took if they made one. Cutting 2 to 3 Shorts from a finished long video adds about an hour.

Pace = hours per week / hours per video. Round down. One good video every two weeks that keeps
going beats a weekly plan that stops. Show the sum.

## 3. Fill the calendar

Draw ideas from the business file's topics and the buyer's real questions (from sales calls,
comments, support, the audit's stand-outs). Ask for those questions if you have none. If you
draft questions yourself, label them "likely question, check with buyers", never as quotes.
Use weeks (week 1, week 3), not calendar dates, unless the user gave a start date. Do not name
product features or past events the business file does not mention.

If you must ask questions first, still write a draft plan file with your assumptions marked,
so the user has something to react to. For a
founder channel, a good mix over a month is:

- Mostly "how to" or "how I" videos that answer a question the buyer would search.
- One video with the founder's point of view or a story from building the business.
- Shorts cut from each long video.

For each video: week, working title (plain and specific), the viewer question it answers,
format, rough length, the Shorts it can yield, and the next step it points to (a product page,
email list, booking a call). Keep titles honest. Ideas that need proof the founder lacks (a
case study with numbers) go in as "needs: {{the real number}}" or wait until they have it.

## 4. Decide what to check

After 4 weeks, look at: which videos got the most views per impression and the longest watch,
which questions came up in comments, and whether any viewers took the next step. Name these in
the plan, with "run youtube-audit" as the check. Do not set view or subscriber targets you
cannot ground in their own past numbers.

## 5. Write and hand back

Write `media/youtube/plan-<yyyy-mm>.md`: the pace math, the calendar table, the 4-week check,
and a one-line "if you only do one thing" for weeks when time runs out. Show the calendar and
end with one line naming the next step, usually scripting video 1 with the linked
`yt-script` skill. Nothing gets scheduled or uploaded by this skill.

## Rules

- Start from real hours. Show the math.
- Ideas come from the founder's topics and buyers, not generic trends.
- No promised views, subscribers or revenue.
- Off-limits topics stay off the calendar.
