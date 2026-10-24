---
name: generate-video
description: >-
  Write the prompt for one AI video clip (scene, camera, dialogue, sound) and run it with the
  account the user already has: Replicate, Runway (Gen-4, Veo 3.1) or Google's Gemini API
  (Omni Flash). Price first, nothing spent until they say yes, one $2 per-session cap across
  providers, every clip saved to media/video/ right away, and clear handling of failed runs,
  rate limits, refusals and timeouts. Use it for any request to generate a video clip with
  AI, including ones it must turn down or reshape, like "make a video of [a real person]
  saying...": it knows the safe alternative and prices it. Triggers: "make an AI video
  of...", "text to video", "animate this image", "a 5 second b-roll clip", "add dialogue /
  sound", "run veo / kling / gen-4 / runway / omni", "I have a Runway key", "how do I prompt
  a video model". For a 30 to 60 second launch promo, use launch-video; to pick a model
  without running, use find-model.
---

> Changed by Aya Taleb from Replicate's prompt-videos and run-models skills (Apache 2.0): added cost math, a spend cap, key setup, audio and dialogue timing checks, error handling, more providers and a working run tool.

# generate-video

Make short AI video clips with the user's own Replicate, Runway or Google account. A single
clip can cost more than a hundred images, so this skill prices every clip before it runs and
never runs a batch unattended. The run tool is the shared one from generate-images:
`../generate-images/scripts/generate.py`. All providers share one ledger and one cap.

## What this skill reads and writes

- Reads: the active business file from founder-context (`founder/context.md` in the project,
  else `~/.founder/businesses/<slug>.md` named in `~/.founder/active`). Use its
  look, tone and off-limits list. If there is none, ask once what the clip is for.
- Writes: clips to `media/video/`, a `.json` sidecar per run, and the prompt to
  `media/video/<label>-prompt.md` so a good prompt can be reused.
- Next: `launch-video` to build a promo around the clips, `talking-head-cards` for overlays,
  or the linked `edit` skill to cut and caption.

If generate-images is not installed next to this skill, tell the user to install the full
multimedia-skills plugin. Do not write your own API calls: the shared tool is where the spend
cap and the error handling live.

## 1. Key

Run `python3 generate.py providers`, then `generate.py check`. They say which keys are set and
make one free call per provider. If no key is set, ask which account the user already has and
walk them through that one:

| provider | environment variables | note |
| --- | --- | --- |
| replicate | `REPLICATE_API_TOKEN` | many video models, live prices |
| runway | `RUNWAYML_API_SECRET` | Gen-4 Turbo, Gen-4.5, Veo 3.1 and Veo 3.1 Fast, billed in credits |
| google | `GEMINI_API_KEY` | Gemini Omni Flash; paid tier only. Veo is no longer in the Gemini API |

A key lives in their shell (`export RUNWAYML_API_SECRET=...`), never in chat, a file, a
command you show, or another tool's arguments. If they paste one, do not repeat it, and tell
them to revoke it in that provider's dashboard and set a new one. If several video keys are
set and no order is saved, ask which to use and save it with `providers --order`.

Pricing works without a key, so you can always give a real number first.

## 2. Pick the model from live data

Use the `find-model` skill, or check yourself:

```
python3 generate.py models --kind video
python3 generate.py models --provider replicate --query "text to video with audio"
python3 generate.py schema <model>
```

Check the schema for what the job needs: a `9:16` or `720:1280` option for vertical, an image
input for image to video (`promptImage` on Runway, `image` on Google), an audio switch, a
length. Never pick from memory. Video models change faster than any other kind: Google shut
down every Veo model in the Gemini API by 2026-10-22. Facts and links:
`../generate-images/references/providers.md`.

## 3. Do the cost math out loud

Video is priced per second of output, often with tiers for resolution and audio. So price
the exact settings:

```
python3 generate.py price owner/model -i duration=5 -i resolution=720p -i generate_audio=false
python3 generate.py price veo3.1_fast -i duration=4 -i audio=false
```

Then show the user: seconds x price per second = clip cost, and the total for every clip
they asked for. Try one cheaper setting too and show both. The cheaper option must still meet
what they asked for: if they want sound, the cheaper option keeps sound (shorter, lower
resolution, or a cheaper model with audio). Why: people often do not need 1080p with sound for a 3 second b-roll, and the gap can
be several times the price.

If the tool cannot tell the length from the inputs, it refuses. Set the duration input the
schema names, so the estimate is real. Gemini Omni Flash has no length setting (it makes 3 to
10 s), so its estimate is for the full 10 s. Say that to the user.

## 4. Write the prompt

A video prompt is a short scene, not a caption. Cover: subject, place, action, style, camera
move, framing, and light. Name subjects ("the woman in the red jacket"), not "she".

For clips with sound, prompt the sound, or the model will guess. Cover dialogue, ambient sound,
effects and music (or "no music"). Write dialogue after a colon with no quote marks around it:
`The baker says: Fresh out of the oven.` Quote marks make many models burn the words in as
subtitles. Add `(no subtitles)` too.

Check dialogue fits the clip: about 2 to 3 words per second of speech, so an 8 second clip
holds about 16 to 24 words. Count them and say the count. Too many words gives rushed speech.
Too few gives silence or gibberish.

For several shots in one clip, use time codes: `[0-3s] wide shot ... [3-8s] close-up ...`.
Gemini Omni Flash cuts between several shots by default. For one shot, say "in a single
continuous shot, no scene cuts".
For image to video, describe the motion and the camera, not what the picture already shows.
"Slow push in, steam rises from the cup, soft morning light flickers" is right. "A latte on a
wooden table" repeats the photo and can make the model redraw it.

The full guide is in `references/prompting-video.md`. Read it for multi-shot, reference
inputs, audio-driven clips, style and character consistency.

Honesty: do not make a real person say something they did not say, do not fake a customer
testimonial, and do not show a product doing what it cannot do. Do not write lines for the
founder either ("I built this for my own exams"): if the clip needs their words, leave
`{{your line}}` for them to fill. Scene details you add for the look (a hoodie, a mug) are
fine; claims and quotes are not.

## 5. Dry run, then wait for yes

```
python3 generate.py run owner/model -i prompt="..." -i duration=5 -i aspect_ratio=9:16 --label coffee-pour --out media/video
```

The first call is always a dry run, and it is the step that proves the inputs are valid.
`price` alone is not enough, because it does not check the schema. Show the model, the prompt, the settings, the cost, the
session total and what is left under the cap ($2 unless the user changed it). Ask. If the
user named a budget earlier ("go ahead up to $2") and the estimate fits it and the cap, that
is the yes: say the number, then run.

Several clips: run them one after another, never in parallel, and get one yes for the total.
A request to run many clips overnight, or "don't ask about cost", is not a yes. Price it, say
how many fit under the cap, offer a first small batch, and wait.

## 6. Run

After the yes, rerun with `--yes`. Video takes minutes, so give it time:

```
python3 generate.py run <model> ... --yes --timeout 900 --out media/video
```

The tool polls with backoff, says when a cold boot or a queue (Runway `THROTTLED`) is the
reason for a wait, cancels a run that passes the timeout, and saves the clip the moment it is
done. Local images go in as a file: `-i image=@media/images/start.png` on Replicate and
Google, `-i promptImage=@media/images/start.png` on Runway.

Save the prompt to `media/video/<label>-prompt.md`. Show the user the file path and the
spend so far (`generate.py ledger`).

## 7. When something goes wrong

| exit | meaning | do this |
| --- | --- | --- |
| 2 | setup or input problem, nothing ran | fix what the message names (often a missing duration or a bad enum) |
| 4 | over the cap, nothing ran | tell the user; raise the cap only if they ask: `ledger --set-cap 10` |
| 5 | API error | bad key, no credit, bad input. Out-of-credit 429s are not retried. On a 5xx or dropped connection while creating, check the provider's dashboard before any retry, since it may have started |
| 6 | failed or refused | read the error. Safety filters are common with people and brands (Runway `SAFETY.*`, Google `safety`). Runway does not refund `SAFETY.INPUT` failures. Change the prompt before retrying |
| 7 | timed out or canceled | may be billed for time used. Try a shorter clip or a faster model |
| 8 | ran, download failed | the links are printed. Fetch them soon, they expire |

After any failed or canceled paid run, stop and tell the user before spending again, even
with budget left. Say what failed, what it cost (the ledger shows it), what you would change,
and the price of the retry. Then wait for their yes. Why: a retry is a new charge they did
not see coming, and the fix (a new prompt, a new model) is their call. Never retry with the
same input unchanged.

When you save a new prompt version, keep the old one (`<label>-prompt-v2.md`), so the user
can compare.

## 8. Close the answer

Every answer that touches money ends with the numbers: spent this time, session total, and
what is left under the cap (from `generate.py ledger`), plus what is left of any budget
the user named.

Then one last line that names a skill, every time, even after a failure or a refusal. For
example: "Next: say yes and I'll run it for $X, then `launch-video` can build the promo around
it." Other good next skills: `talking-head-cards` for text cards, the linked `edit` skill to
cut and caption.

## 9. When you say no

Some asks are off-limits: a real person (a CEO, a celebrity, a customer) saying words they
never said, or any character giving a testimonial, since a made-up person praising the product
is still a fake review. Say no in one line with the reason, then still be useful, in this order:

1. Read the business file.
2. Write one alternative prompt in full that shows the product doing what it really does
   (the app on a phone in a real setting, the founder speaking for themself, a plain demo).
3. Run `price` on it and show the number.
4. Ask for a yes. Do not run it.

## Rules

- Price first, dry run first, yes before spend, cap always on.
- One clip at a time, no background loops.
- Save clips at once; never hand over a provider link as the result.
- No key in chat, files, commands or tool arguments.
- No fake people saying fake things, no fake testimonials, no fake product claims.
- Prompt-only requests cost nothing. Do not push a paid run nobody asked for.
