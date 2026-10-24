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

## Decision, Oct 24

Aya decided: `virality` and `yt-viral` are no longer linked from this repo, because they suggest
yt-dlp. The README lists them as optional with the reason. She keeps a personal copy on her own Mac.

## Multi-provider update, Oct 24

`generate-images`, `generate-video` and `find-model` now work with five providers through one
entry tool, `skills/generate-images/scripts/generate.py`. `replicate_run.py` still works on
its own and shares the same ledger. Every endpoint, header, request and response shape,
polling pattern and price came from the providers' own docs on 2026-10-24. Each is listed with
its link in `skills/generate-images/references/providers.md`; prices are in
`skills/generate-images/scripts/prices.json`, each with its source and checked date.

| provider | kind | key | models in the table |
| --- | --- | --- | --- |
| replicate | image, video | `REPLICATE_API_TOKEN` | any (live search and live page prices, as before) |
| cloudflare | image | `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` | flux-1-schnell, flux-2-klein-4b, flux-2-dev |
| openai | image | `OPENAI_API_KEY` | gpt-image-2.5-flare, gpt-image-2.5-sunburst, gpt-image-2, gpt-image-1.5, gpt-image-1-mini |
| runway | video | `RUNWAYML_API_SECRET` (header `X-Runway-Version: 2024-11-06`) | gen4_turbo, gen4.5, veo3.1_fast, veo3.1 |
| google | video | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | gemini-omni-1.1-flash |

### Things that changed under us (found while checking the docs)

- **OpenAI shut down gpt-image-1 on 2026-10-23.** The current models are GPT Image 2.5 Flare and
  Sunburst. The brief named gpt-image-1, so the table uses the 2.5 models instead.
- **Veo is no longer in the Gemini API.** Veo 3.1 Preview shut down on 2026-10-22, and the Veo 2
  and 3.0 models on 2026-06-30. Google's replacement there is Gemini Omni Flash, which uses the
  Interactions API (create in the background, then poll). The google provider runs Omni Flash. Veo 3.1 and Veo 3.1 Fast are still reachable through Runway, so they are in the
  Runway table.

### Live checks: to run with Aya

No paid call was made. No real key exists here; every provider path is unit tested with the
network mocked. Run these with real keys, in this order, from the repo root. Expected total:
about $1.25 on the ledger, most of it the one Google clip. The default $2 cap covers it.

```
G=skills/generate-images/scripts/generate.py
python3 $G ledger --new-session
python3 $G providers
python3 $G check                      # free: one call per provider with a key
python3 $G models --kind image        # free: "listed live: yes" next to each table model
python3 $G models --kind video        # free
```

| # | provider | command (dry run first, then add --yes) | expected cost |
| --- | --- | --- | --- |
| 1 | replicate | `python3 $G run black-forest-labs/flux-schnell -i prompt="a red bike on a quiet street" --label live-rep` | about $0.003 |
| 2 | cloudflare | `python3 $G run @cf/black-forest-labs/flux-1-schnell -i prompt="a red bike on a quiet street" --label live-cf` | $0.0019 on the ledger, likely $0 billed (free daily neurons) |
| 3 | cloudflare | `python3 $G run @cf/black-forest-labs/flux-2-klein-4b -i prompt="a red bike on a quiet street" -i width=512 -i height=512 --label live-cf2` | $0.0003 (checks the multipart path) |
| 4 | openai | `python3 $G run gpt-image-2.5-flare -i prompt="a red bike on a quiet street" -i quality=low --label live-oa` | $0.0074 on the ledger, about $0.006 billed |
| 5 | runway | `python3 $G run gen4_turbo -i prompt="slow push in" -i promptImage=@media/images/<the file from step 2> -i ratio=960:960 -i duration=2 --out media/video --label live-rw` | $0.10 (10 credits) |
| 6 | google | `python3 $G run gemini-omni-1.1-flash -i prompt="A single continuous shot of a red bike leaning on a brick wall. No scene cuts, no dialogue." -i resolution=360p --out media/video --timeout 900 --label live-gm` | $1.12 on the ledger, $0.30 to $1.02 billed by clip length |

After each `--yes` run, check: the file is in `media/images/` or `media/video/`, the `.json`
record is written, and `python3 $G ledger` matches the provider's dashboard. Then:

- Runway: the task's `cost.credits` should replace the estimate on the ledger.
- Google: confirm Omni accepts `"background": true` and that polling `GET /v1beta/interactions/{id}`
  returns the video. The docs show it for "standard Gemini models" and list `background=false`
  as an Omni option, but no Omni example uses it. If it fails with a 400, the fix is a
  synchronous call with a long timeout; tell me and I will change it. Also check that `usage`
  comes back, so the ledger can use the real token count.
- OpenAI: see whether `usage` comes back for 2.5 models (the docs say "gpt-image-1 only").
- Free failure checks, no spend: `OPENAI_API_KEY=sk-wrong python3 $G check --provider openai`
  (should say the key is not valid and not print it), and the same for each provider.

Not testable without real accounts: real 429s, a real refusal from each provider's safety
system, a real timeout. Each is unit tested with a mocked network.

### Calls Aya should review

1. **Upper-bound pricing where docs are unclear.** Cloudflare schnell's step price is charged
   per tile; schnell output is assumed 1024x1024; klein input images count as 16 tiles. OpenAI
   2.5 adds 25% (OpenAI says token use differs by model). Omni assumes a 10 s clip plus 10%.
   Every one of these makes the estimate high, never low.
2. **Refused and failed runs stay on the ledger** unless the provider reports the real cost
   (Runway `cost.credits`, Google `usage`). Runway says `SAFETY.INPUT` failures are not refunded;
   OpenAI and Google do not say. This can make the ledger read higher than the bill.
3. **Runway 502 and 503 on create are retried**, because Runway's error page says they mean load
   shedding. Every other 5xx on create is never retried, as before.
4. **Auto-pick.** With one provider key for the job, that provider is the default. With several
   and no saved order, the tool says "ask the user", and the skill asks once and saves the order
   to `~/.founder/media/providers.json`.
5. **Not wired in:** OpenAI image edits, Runway and Google audio models, Runway image models,
   Omni 1080p and 4K (no published rate, so they need `--assume-cost`), Omni editing and
   extension. Replicate still covers audio, upscaling and edits.
6. **generate.py is about 1,100 lines**, longer than "lean". Most of it is the four provider
   paths and their error handling; splitting it into modules is easy later if you prefer.
7. Gemini interactions are stored by Google (`store` must be on for background runs). The tool
   does not delete them after download. A delete call exists if you want it.
8. **instagram-carousel** said "--cap 5" and its eval said "$5 default cap", left over from
   before the $2 change. Fixed both in instagram-boost-skills while syncing.
