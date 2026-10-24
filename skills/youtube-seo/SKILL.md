---
name: youtube-seo
description: >-
  Write the words around a YouTube video that help the right people find and click it: three
  title options built on what the video really delivers, a description whose first two lines
  work in search, chapters that follow YouTube's rules, and a few tags, all in the founder's
  voice and checked against YouTube's current limits. Honest about what no tool can know,
  like search volume. Use it for "write my YouTube title and description", "optimize this
  video for search", "YouTube SEO", "add chapters / timestamps", "what tags should I use",
  "my video isn't showing up in search", or right before publishing a video.
---

# youtube-seo

Help a video get found by the people it was made for, and make sure the title promises what
the video delivers. A title that over-promises gets clicks, then short watch times, which
hurts the video more than a plain title would.

## What this skill reads and writes

- Reads: the video's transcript (from `transcribe`, or YouTube's own) or a summary from the
  user, the founder-context business file (who it is for, tone, words to avoid, links the
  founder uses), and the current title and description if they are fixing an old video.
- Writes: `media/youtube/<video-slug>-seo.md`.
- Uses: `humanize` on the description before showing it.
- Next: the user pastes it into YouTube Studio. Suggest `youtube-shorts` to cut clips, or the
  linked `yt-package` skill to pair the title with a thumbnail.

YouTube's limits and the sources for them are in `references/youtube-facts.md`. Check that
page if a limit matters, since YouTube changes them.

## 1. Know the video and the viewer

From the transcript or summary, write down in one line each:

- Who it is for (from the business file, in their words).
- The question or problem the viewer typed or had in mind.
- What the video actually delivers. Only what is in it.

If there is no transcript or summary, ask for one. Do not write metadata for a video you
know nothing about.

## 2. Find the words people use

You do not have search volume data, and nobody outside YouTube has exact numbers. So:

- Pull the viewer's own words from the business file, comments and the transcript.
- Ask the founder to type 2 or 3 candidate phrases into YouTube's search bar and note the
  suggestions, and to check YouTube Studio's Research tab if they have it. These are signs of
  demand, not numbers. Say so.
- Pick one main phrase and one or two close variants. Write for a person first.

## 3. Titles (give 3)

- Under 100 characters (the hard limit). Aim for the main words in the first 40 to 50, since
  the end can be cut off on phones. That is a habit, not a rule.
- One clear promise the video keeps. Specific beats clever: "How I price a lunch subscription
  for offices" beats "The pricing secret nobody tells you".
- Use a number only if the video has it ("3 mistakes" when it covers 3).
- No all caps, no bait the video does not pay off.

For each option, one line on who it is for and why it might work. Let the founder choose.

## 4. Description

- First two lines: the promise and the main phrase, in plain words. They show in search and
  above "more".
- Then 2 to 4 short lines on what the video covers.
- Links: only links the founder gave you or that are in the business file. Never invent one.
- Chapters, if the video has clear sections (see step 5).
- One call to action that matches the business goal.
- Under 5,000 characters. Run it through `humanize`.

## 5. Chapters

From a timestamped transcript, mark the real section changes. YouTube's rules: the first
timestamp is 00:00, at least three timestamps in ascending order, each chapter at least 10
seconds. Name each chapter by what the viewer gets, in a few words. Check the rules before
handing them over, because a chapter list that breaks one of them does not show at all.

If there are no timestamps, do not guess times. Say chapters need the transcript, or leave
them out.

## 6. Tags

Give up to about 10, mostly variants and common misspellings of the main phrase. Tell the
founder that YouTube says tags play a minimal role in discovery, so not to spend time on
them. Do not stuff tags into the description: YouTube treats that as spam.

## When you turn something down

If the user asks for a misleading title (a famous name or a result the video does not have)
or for tag stuffing, say no in one line with the reason, then do the job honestly in the same
answer: write the 3 title options and the short tag list from what you know, using
`{{placeholders}}` where you need the transcript. Do not stop at "send me the transcript and
I'll write them".

## 7. Hand back

Write everything to `media/youtube/<video-slug>-seo.md` and show it. End with one line naming
the next step. The founder pastes it into YouTube Studio; this skill never logs in or edits
videos.

## Rules

- Never invent search volumes, rankings, scores or "SEO grades".
- Titles promise only what the video delivers.
- Links and facts only from the founder, the business file or the transcript.
- Follow the business file's tone and words to avoid.
