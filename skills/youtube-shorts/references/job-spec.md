# Job spec: youtube-shorts

Written before reading any other YouTube Shorts skill.

## The job

A founder has a long video (a webinar, podcast, tutorial, talk) and its transcript. They want
a few Shorts from it without watching the whole thing again. They need to know which moments
stand alone, exactly where to cut, what the first second says, and what text goes on screen.

## Inputs

- A timestamped transcript (from the transcribe skill, or YouTube Studio's own export).
- Optional: the video file, the founder-context business file, how many Shorts they want.

## Output

- A ranked list of 3 to 8 clips, each with: start and end time (inside YouTube's Shorts length
  limit, checked on the day), why it stands alone, the opening line as spoken, a stronger
  cold open if the clip should start mid-sentence, on-screen text, a title, and the reframe
  note for vertical (where the speaker sits).
- Optional cut commands for ffmpeg on the user's own file, run only on request.
- Written to `media/shorts/<video>-shorts.md`.

## What good looks like

- Every clip makes sense to someone who never saw the long video.
- Cuts land on sentence edges, not mid-word.
- Nothing is added that the speaker did not say. Titles and on-screen text can frame, not invent.
- It says plainly that it cannot predict views.

## Must not

- Download from YouTube or any platform.
- Upload or post. The user does that.
- Invent numbers, quotes or results.
