# Build notes

What is unfinished, what needs Aya, and the calls she should review. Scores and rounds are in
TESTING.md.

## Needs Aya's Replicate token (live tests not run)

No paid run was made during the build. All paid-path tests used a mocked Replicate API built
from real public model pages (schemas and prices read on 2026-10-23). Before release, with a
token and a small cap (`replicate_run.py ledger --set-cap 1`), please run:

1. `replicate_run.py check`: the token is accepted.
2. `replicate_run.py search "text to image" --limit 5`: the beta search API answers in the
   shape the tool expects (fields `models[].model`, `models[].metadata.tags`).
3. One cheap image: `replicate_run.py run black-forest-labs/flux-schnell -i prompt="a red bike"`
   (dry run, about $0.003), then the same with `--yes`. Check the file lands in
   `media/images/`, the run record is written, and the ledger shows the spend.
4. One community model (GPU-time priced) dry run, to see the estimate uses the page's typical
   run cost.
5. One image-to-video dry run with `-i image=@media/images/<file>`, then `--yes` on the
   shortest, cheapest setting, to confirm file upload and video download (about $0.10 to $0.30).
6. A deliberately bad input (an enum value the schema does not allow) to see the 422 message.

Not testable without a token or at all here: real 429 throttling, real cold boots, a real
`failed` prediction from a safety filter. The tool's handling of each is unit tested with the
network mocked.

## Unfinished or known limits

- **Prices come from the model page, not the API.** Replicate's API has no price field. The tool
  reads the pricing JSON embedded in each public model page. If Replicate changes that page,
  the tool finds no price and refuses to run until a person passes `--assume-cost`. That is the
  safe failure, but it means the price parser may need upkeep.
- **Per-run units the tool cannot see.** Video priced per second needs a duration input; some
  models express length as frames. Token-priced models (text to speech) are estimated from text
  length, about 3 characters per token, rounded up. Estimates can be off; the cap still holds.
- **The ledger is per machine, not per Claude session.** A "session" ends after 12 idle hours.
  Two different projects on one machine share the cap. Aya may want a per-project ledger
  instead; it is one env var (`MEDIA_LEDGER`).
- **transcribe was tested with a stand-in for faster-whisper** (a stub module returning a fixed
  transcript), since faster-whisper is not installed here and the model download is large. The
  real library's API (`WhisperModel(...).transcribe(path, beam_size, vad_filter,
  word_timestamps, language)`) was taken from its current README. A run on a real file with the
  real library is still needed.
- **talking-head-cards renders with ffmpeg and libass** (ASS subtitles), tested here with real
  ffmpeg. Fonts fall back to whatever the machine has; the default is DejaVu Sans. Animated cards
  via HyperFrames are described in the reference but not built as a tool.
- **launch-video's HyperFrames output was linted and rendered for real** with HyperFrames 0.8.191
  (0 errors, 0 warnings, 37 second 1080x1920 MP4). HyperFrames moves fast; the skill tells the
  agent to check `--help` before trusting a flag.
- Synced skill `humanize` is missing until the orchestrator's sync step. `validate.py` passes
  without it, as expected.

## Calls Aya should review

1. **Tool location.** REPO-MAP says the tool is `media/generate.py`. Your brief to me said
   `scripts/replicate_run.py` inside generate-images, so that is what exists. `generate-video`
   and `find-model` call it at `../generate-images/scripts/replicate_run.py`, so they need
   generate-images installed next to them (true for this plugin). If they are ever synced alone,
   that path breaks.
2. **Price lookup reads public model pages** (one HTTP GET to replicate.com per price check).
   It is a read of a public page, not scraping behind a login, and the tool sends a clear
   User-Agent. If you would rather not, the fallback is `--assume-cost` after a person reads the
   price.
3. **Local mock override.** The tool honors `REPLICATE_API_BASE` / `REPLICATE_SITE_BASE` only when
   they point at 127.0.0.1 or localhost, so tests can run without money. Any other host is
   ignored, so a token cannot be redirected elsewhere.
4. **A pre-approved budget counts as a yes** ("go ahead, up to $1") when the estimate fits it and
   the cap. The first call is still a dry run.
5. **Failed and canceled runs keep their estimate on the ledger**, since Replicate may bill for
   time used. Only "aborted" and "never created" runs are refunded on the ledger. This can make
   the ledger read higher than the real bill.
6. **find-model's scoring weights** (fit 40, cost 25, speed 15, fresh 10, proof 10) are my choice.
7. **youtube-audit flags** a video at under 70% of the channel median click rate or share watched,
   or under 40% of median impressions. My cut-offs, not YouTube's. Said so in the reference.
8. **Linked skills `virality` and `yt-viral` suggest yt-dlp** for public YouTube listings. Our
   skills never download from platforms. I added a heads-up to the README rather than dropping
   the links, since they are in REPO-MAP.
9. **Shipped versions.** For talking-head-cards, youtube-shorts and youtube-comment, the later
   edits scored lower in testing, so the round 1 text ships. The lower-scoring edits are kept in
   the run folders if you want to look.
10. **Fictional names.** Per the orchestrator, evals use only made-up businesses. An earlier
   draft used a name close to one of your ventures; it was renamed to "Curbside Lunch Club"
   before any file was final. Some intermediate run logs in `_work/` still show the old name.
11. **Small media files in evals** (a few short ffmpeg-made test clips and a PNG, under 200 KB
   each) are committed so the eval cases rerun as-is.

## Fix round after review

- User data moved out of `~/.claude` (protected by Claude Code) to `~/.founder`: business files, social folders and the media ledger. Tools honor `FOUNDER_HOME`; tests use a temp one.
- generate-images: the spend ledger is `<FOUNDER_HOME or ~/.founder>/media/spend-ledger.json`; `MEDIA_LEDGER` still wins. Tests use `FOUNDER_HOME`.
