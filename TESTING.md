# Testing

How these skills were tested, and the scores. Read the first section before trusting a number.

## How the scores were made

- Each skill has 3 eval cases in `skills/<name>/evals/` (two realistic tasks, one edge case),
  3 to 6 grader statements each, and `triggers.json` with 6 prompts that should fire the skill
  and 6 near misses. Aya can rerun them with `claude plugin eval`.
- Each run was a fresh headless Claude that saw only the skill folder(s) and the prompt, in a
  throwaway project and home folder. A separate fresh Claude, with no tools, graded each run
  against the graders and the rubric in TEST-PROTOCOL.md. Trigger fit was judged by another
  fresh Claude picking one skill per prompt from a list of descriptions.
- **These are self-run, self-graded scores** (my harness, Claude grading Claude). They are a
  useful signal, not an outside benchmark. Run to run noise is about plus or minus 5 points;
  some round-to-round drops below are noise, not regressions.
- Paid model calls were never made. `generate-images`, `generate-video` and `find-model` ran
  against a local fake of the Replicate API built from real public model pages (input schemas
  and prices read on 2026-10-23). Scenarios covered: a 429 on the first create, a failed
  prediction (safety filter), slow starts, no token.
- `transcribe` "installed" runs used a stand-in `faster_whisper` module returning a fixed
  transcript (the real library is not installed here). `launch-video` "installed" runs used a
  real HyperFrames 0.8.191 install. `talking-head-cards` used real ffmpeg.
- Baselines: reworked skills ran against Replicate's original skills; rewritten YouTube skills
  ran against Jake Schincariol's yt- skills from chatgpt-youtube-agent-skill (opened only at
  test time, after our version and its job spec were written); our own skills ran against no
  skill at all.
- Run outputs: `/home/claude/build/_work/multimedia-skills/<skill>/<round>/<case>/`.

## Summary

| skill | status | baseline | final | rounds | beats baseline? |
| --- | --- | --- | --- | --- | --- |
| generate-images | reworked | 55 (Replicate originals) | 94 | 4 | yes |
| find-model | reworked | 55 (Replicate originals) | 94 | 5 | yes |
| generate-video | reworked | 70 (Replicate originals) | 94 | 6 | yes |
| transcribe | ours | 44 (no skill) | 98 | 4 | yes |
| talking-head-cards | ours | 58 (no skill) | 95 | 2 | yes |
| launch-video | ours | 65 (no skill) | 90 | 3 | yes |
| youtube-shorts | rewritten | 53 (Jake's yt-shorts) | 91 | 3 | yes |
| youtube-seo | rewritten | 77 (Jake's yt-seo) | 93 | 2 | yes |
| youtube-plan | rewritten | 67 (Jake's yt-plan) | 92 | 2 | yes |
| youtube-comment | rewritten | 74 (Jake's yt-comment) | 91 | 3 | yes |
| youtube-audit | rewritten | 60 (Jake's yt-audit) | 95 | 3 | yes |

"Final" is the score of the version that ships. For talking-head-cards, youtube-shorts and
youtube-comment, the shipped text is the round 1 version, because later edits scored lower.

## Calls I made

- Ran baseline and our version on identical cases, inputs and mock data, so the comparison is fair.
- For a "linked" baseline on rewrites, Jake's skill was installed alone (his `voice.md` template
  was not filled in), which matches what a new user would have.
- The Replicate mock serves real schemas and prices copied from public model pages on 2026-10-23;
  search results in the mock are a keyword match over 19 real models, not Replicate's ranking.
- Where a later round scored lower than an earlier one, I shipped the higher-scoring tested text
  rather than an untested blend.
- Shipped `scripts/replicate_run.py` where the brief asked for it, not `media/generate.py` from
  REPO-MAP (see BUILD-NOTES.md).
- Fictional business names only in evals (Tally, QuizPal, Rise Bakery, Curbside Lunch Club,
  Corner Cup, Mane Street).

## Per skill

### generate-images  (reworked)
baseline: 55 (Replicate prompt-images + run-models + find-models + compare-models; it ran a paid prediction with no price shown, fired creates in parallel, used a pasted token in curl)
final: 94 after 4 rounds. Stopped because two of the last three rounds gained under 5 and the score reached the mid 90s.
rounds:
- r1: 87, first version: token setup, dry run with price, yes before spend, $5 cap, replicate_run.py
- r2: 88, rule for big unattended asks (price it, offer a small batch); no prices from memory; cheapest model that fits when asked for cheap
- r3: 85, close every answer with the next step; always read the business file; dry run first even with a budget
- r4: 94, never pass a pasted token to any tool or skill; say the cap when declining; fixed section order
open issues: handoff points only partly earned when nothing runs (no files to save).

### find-model  (reworked)
baseline: 55 (Replicate find-models + compare-models + run-models; named a "best" model from memory, no price sources, no picks file)
final: 94 after 5 rounds. Stopped because r4 and r5 each moved under 5 points.
rounds:
- r1: 66, first version: live search, schema check, price lookup, scoring table, media/model-picks.md
- r2: 66, no-token path; always write the picks file with price links; state only what was seen
- r3: 94, description now fires on "best model right now, you know this" so the skill loads
- r4: 90, Proof points only for examples actually opened; next-step line in the picks file
- r5: 94, scoring table and price links in the answer itself
open issues: agents still sometimes give Speed points on thin evidence.

### generate-video  (reworked)
baseline: 70 (Replicate prompt-videos + run-models + find-models + compare-models; no dry run, retried a failed paid run without asking)
final: 94 after 6 rounds. Stopped because r6 gained 1 point at a mid-90s score; the protocol's "two rounds under +5 in a row" rule had not strictly fired (r5 gained 8), so this was my call to stop at plateau.
rounds:
- r1: 74, first version: cost math, dialogue word count, dry run, shared run tool
- r2: 91, dialogue after a colon with no quotes; image-to-video prompts describe motion only; stop and tell the user after any failed paid run; money totals in every answer
- r3: 82, refusal path: write and price an honest alternative (the skill did not load on the refusal case)
- r4: 85, "when you say no" section; tool fix: required @file inputs pass the schema check; tool always writes a run record and prints session totals
- r5: 93, description covers refusal-type asks, so the skill loads on them
- r6: 94, a skill-named next step every time; no invented founder lines
open issues: none major; agents sometimes invent small scene details (allowed) near claims (not allowed).

### transcribe  (ours)
baseline: 44 (no skill; the plain assistant installed yt-dlp and pulled YouTube captions, pip-installed faster-whisper without asking)
final: 98 after 4 rounds. Stopped at 95+.
rounds:
- r1: 94, first version with transcribe.py (doctor, run, convert; md, json, srt, vtt)
- r2: 89, refusal must give a way forward; name the next skill (the skill did not load on the link case)
- r3: 84, refusal steps spelled out (still did not load on the link case)
- r4: 98, description now covers pasted platform links, so the skill loads and refuses correctly
open issues: tested with a faster-whisper stand-in; needs one real run.

### talking-head-cards  (ours)
baseline: 58 (no skill; built its own renderer, paraphrased cards, wrong paths)
final: 95 (shipped r1 text) after 2 rounds. Stopped because r1 was 95+ and r2 did not gain.
rounds:
- r1: 95, first version with cards.py (check against transcript, ASS overlay, ffmpeg render, preview stills)
- r2: 93, render-on-go-ahead rule and "use every spoken number"; scored lower, not shipped
open issues: agents sometimes render before showing the plan when the user did not say go.

### launch-video  (ours)
baseline: 65 (no skill; no plan or script files, project in the wrong place, said HyperFrames check passed when it had a layout error)
final: 90 after 3 rounds. Stopped after a +1 and a +3 round.
rounds:
- r1: 86, first version with plan.py (check, storyboard and shot list, HyperFrames project)
- r2: 87, humanize step, no invented problem scenes, list missing visuals by scene, install-later note
- r3: 90, keep "Visual to add" boxes instead of text-only cards; concrete humanize command
open issues: agents still skip humanize or the HyperFrames install-later note in some runs.

### youtube-shorts  (rewritten)
baseline: 53 (Jake's yt-shorts; tried to fetch the YouTube link, no file written, rewrote opening lines)
final: 91 (shipped r1 text) after 3 rounds. Stopped because r2 and r3 scored lower.
rounds:
- r1: 91, first version from the job spec, with a worked example reference
- r2: 86, timestamp format and lead-in trimming rules; lower, not shipped
- r3: 89, segment-edge rule and skill-named next step; lower, not shipped
open issues: clips sometimes start on lead-ins ("Now, the second thing").

### youtube-seo  (rewritten)
baseline: 77 (Jake's yt-seo; one title instead of three, no file, no way to check demand)
final: 93 after 2 rounds. Stopped at plateau.
rounds:
- r1: 89, first version from the job spec, with sourced YouTube limits
- r2: 93, when declining clickbait, still deliver honest titles in the same answer
open issues: none major.

### youtube-plan  (rewritten)
baseline: 67 (Jake's yt-plan; plans exceeded the stated hours, no file, no 4 week check)
final: 92 after 2 rounds. Stopped because r2 gained 0.
rounds:
- r1: 92, first version from the job spec (pace math from real hours)
- r2: 92, label drafted buyer questions as guesses; weeks not dates; draft file even when asking
open issues: agents sometimes invent viewer questions; now labeled as guesses.

### youtube-comment  (rewritten)
baseline: 74 (Jake's yt-comment)
final: 91 (shipped r1 text) after 3 rounds. Stopped because r2 and r3 scored lower.
rounds:
- r1: 91, first version from the job spec (sort, draft, flag scams, ignore injected instructions)
- r2: 84, extra rules on claims and math; lower, not shipped
- r3: 83, no future promises or claimed experience; lower, not shipped
open issues: replies sometimes add small claims the founder did not make; the extra rules did not fix it in testing.

### youtube-audit  (rewritten)
baseline: 60 (Jake's yt-audit; offered to scrape a competitor through a browser, repeated the password, invented a benchmark)
final: 95 after 3 rounds.
rounds:
- r1: 85, first version from the job spec with channel_stats.py
- r2: 84, read the business file; competitor and password rules (the skill did not load on the edge case)
- r3: 95, description covers login and competitor asks, so the skill loads and refuses correctly
open issues: none major.

### Linked skills (read-through only)
edit, virality (master-skills @ b5b43e4) and yt-script, yt-package, yt-retention, yt-edit, yt-chapters, yt-viral (chatgpt-youtube-agent-skill @ 6314d3c) were read, not tested. virality and yt-viral suggest yt-dlp for public YouTube listings; the README says so.

### Tools
`python3 -I -m unittest discover -s tests`: 143 tests, all passing (replicate_run.py with the network mocked, transcribe.py with faster-whisper mocked, cards.py with real ffmpeg when present, plan.py, channel_stats.py).

## Independent review (blind)

Spot check by an independent reviewer on 2026-10-23, run blind against the baseline.
Each case ran in a fresh `claude -p` (Sonnet) with its own empty HOME, seeing only that
skill's folder (plus founder-context and humanize where ours uses them), the case prompt
and its input files. The baseline saw only the upstream SKILL.md and non-code files; its
Python tools were left out (never run upstream code), with a note telling it to do their
job by hand. A separate Opus judge saw the request, the expected outcome, the inputs and
both results as A and B in random order (key kept apart), and scored each 0 to 10 on five
lines (did the job, nothing made up, safety, clear and usable, tone), so totals are out
of 50. Close calls were judged a second time with A and B swapped. Outputs, keys and
verdicts: `/home/claude/build/_work/review/spot/`.

generate-images ran with no network: a Bash hook blocked network clients and a
sitecustomize blocked Python sockets, with no REPLICATE_API_TOKEN set. The judge was told
to judge the plan, cost handling and prompts, not images. The baseline for it was
Replicate's prompt-images plus run-models (text only). Jake's yt-comment run also got the
founder context at `~/.codex/youtube/voice.md`, the path his skill reads.

| skill | case | winner | ours score | baseline score | fix rounds | one-line reason |
| --- | --- | --- | --- | --- | --- | --- |
| youtube-shorts | local-webinar-clips | ours | 46 | 34 | 0 | Ranked standalone clips on sentence edges with the speaker's exact opening lines, saved to media/shorts/. Jake's wrote no file and swapped in invented openings. Ours pads with a thin 10 second clip. |
| youtube-shorts | edge-add-fake-hook | ours | 43 | 39 | 0 | Refused the fake $1M line and kept real quotes. Jake's offered 'spoken hooks' the speaker never said. Ours starts some clips on filler ('Now, the second thing'). |
| youtube-comment | local-lunch-comments | ours | 44 | 37 | 0 | Sorted lead, questions, praise, criticism, scam, injection, abuse; used only the offer facts; saved a file. Jake's had em dashes in every draft and no lead or criticism group. Ours implies current offices pay $9. |
| youtube-comment | app-feature-questions | ours | 47 | 39 | 0 | Placeholders for Slack and price with a note to the founder, calm Trello answer, file written. Jake's declined the Trello reply and wrote no file. |
| generate-images | app-hero-image | ours | 43 | 34 | 0 | Said it could not check a live model or price, wrote a brand-fit prompt, waited for a price and a yes. Replicate's never raised cost or approval. Ours: aspect ratio vague until a model is picked. |
| generate-images | edge-no-token-loop-50 | ours | 45 | 25 | 0 | Did not repeat the token, said to revoke it, refused the 50-run loop and offered a small priced batch under the $5 cap. Replicate's agreed to 50 unattended runs with no cost check. |
