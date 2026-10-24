# Provider facts the tools rely on

Every fact here was read from the provider's own docs on **2026-10-24**, unless a line says
otherwise. When this file and the live docs disagree, the live docs win. Update the date,
`scripts/prices.json` and this file together.

Prices for every provider except Replicate live in `scripts/prices.json`, one entry per model,
each with its source link and checked date. `generate.py` warns when a date is more than 60
days old. Replicate prices are read live from each model page (see `replicate-api.md`).

## The same rules for every provider

| rule | how the tool keeps it |
| --- | --- |
| price first | `price` and the first `run` call are dry runs. Both work with no key and no network for table providers |
| explicit yes | only `run ... --yes` spends |
| one cap | one ledger file for all five providers, default $2 a session |
| keys | read from environment variables only. Never printed, never written. Error text from a provider is scrubbed of the key before it is shown |
| save at once | images and clips are written to disk the moment the run ends, with a `.json` record |
| 429 | "slow down" 429s wait (Retry-After if sent, else 5, 10, 20 s) and try again, up to 3 times. A wait over 120 s stops instead. "Out of credit or quota" 429s stop at once |
| create errors | a dropped connection, a timeout or a 5xx while creating a run is never retried, and the charge stays on the ledger as "unknown". Runway 502 and 503 are the one exception (see Runway) |
| refusals | a content-policy block is reported as refused (exit 6). The estimate stays on the ledger, because some providers bill blocked runs. The skill never retries the same input |

## Replicate

Unchanged. See `replicate-api.md` (checked 2026-10-23). Key: `REPLICATE_API_TOKEN`.
`replicate_run.py` still works on its own; `generate.py` calls it for Replicate models.

## Cloudflare Workers AI (images)

- Keys: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. The token needs Workers AI Read
  and Edit. Dashboard path: Workers AI > Use REST API > Create a Workers AI API Token.
  Source: https://developers.cloudflare.com/workers-ai/get-started/rest-api/
- Run: `POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}` with
  `Authorization: Bearer <token>`. The answer is synchronous. JSON responses are wrapped as
  `{"result": {...}, "success": true, "errors": [], "messages": []}`.
  Source: https://developers.cloudflare.com/api/resources/ai/methods/run/
- `@cf/black-forest-labs/flux-1-schnell`: JSON body. Inputs: `prompt` (1 to 2048 chars,
  required), `steps` (up to 8, default 4). The input schema sets `additionalProperties: false`,
  so the tool sends nothing else. Output: `result.image`, base64 (JPEG in Cloudflare's examples).
  Source: https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/ and its
  `schema-input.json`.
- `@cf/black-forest-labs/flux-2-klein-4b` and `flux-2-dev`: multipart form data, even for a
  prompt alone. Fields: `prompt`, `width` and `height` (256 to 1920, defaults 1024 and 768),
  `guidance`, up to 4 images as `input_image_0` to `input_image_3`; klein also takes `seed`
  and has fixed 4 steps; dev takes `steps`. Output: base64 `image`.
  Sources: https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/
  and https://developers.cloudflare.com/changelog/post/2025-11-25-flux-2-dev-workers-ai/
- Free key check: `GET /accounts/{account_id}/ai/models/search?task=Text-to-Image` (needs
  Workers AI Read). Source: https://developers.cloudflare.com/api/resources/ai/subresources/models/methods/list/
- Errors: `3036` (429) means the daily free allocation of 10,000 neurons is used up, so the
  tool does not retry it. `3040` (429) means out of capacity, so it waits and retries. `3007`
  (408) is a timeout. `5004`, `5007` (400) are bad input or model. Source:
  https://developers.cloudflare.com/workers-ai/platform/errors/ (page updated 2026-09-17)
- Rate limit: 720 requests a minute for text to image. Source:
  https://developers.cloudflare.com/workers-ai/platform/limits/
- Prices: $0.011 per 1,000 neurons, 10,000 neurons a day free. flux-1-schnell $0.0000528 per
  512x512 tile and $0.0001056 per step; klein-4b $0.000287 per output tile and $0.000059 per
  input tile; flux-2-dev $0.00041 per output tile per step and $0.00021 per input tile per step.
  Source: https://developers.cloudflare.com/workers-ai/platform/pricing/ (page updated 2026-10-20)
- Calls I made: the page does not say whether the schnell step price is per tile, so the tool
  charges it per tile (the higher reading). Schnell's output size is not documented, so the tool
  assumes 1024x1024. Tiles are counted by rounding each side up to 512. Klein input images are
  counted as 16 tiles each, since their size is not documented. All of these can only make the
  estimate too high, never too low.
- No content-policy refusal is documented for these models.

## OpenAI Images API

- Key: `OPENAI_API_KEY`, from https://platform.openai.com/api-keys
- Run: `POST https://api.openai.com/v1/images/generations` with `Authorization: Bearer <key>`,
  JSON `{"model", "prompt", "n" (1 to 10), "size", "quality", "background", "output_format",
  "output_compression", "moderation"}`. GPT Image models always return base64 in
  `data[].b64_json`. Complex prompts can take up to 2 minutes.
  Source: https://developers.openai.com/api/reference/resources/images/methods/generate
- Models today: `gpt-image-2.5-flare` ("fast, high-quality everyday image generation"),
  `gpt-image-2.5-sunburst` ("editing precision matters most"), `gpt-image-2`, `gpt-image-1.5`,
  `gpt-image-1-mini`. **gpt-image-1 was shut down on 2026-10-23.** DALL-E 2 and 3 were retired
  on 2026-05-12. Quality for 2.5: low, medium, high, xhigh, max. For the others: low, medium, high.
  Sizes 1024x1024, 1536x1024, 1024x1536 for all; gpt-image-2 and 2.5 also take other sizes.
  Source: same reference page and https://developers.openai.com/api/docs/guides/image-generation
- Free key check: `GET /v1/models`. It proves the key works, not that the project has credit.
  Source: https://developers.openai.com/api/reference/resources/models/methods/list
- Refusals: HTTP 400 with `error.code = "moderation_blocked"` (type
  `image_generation_user_error`), sometimes with `moderation_details.moderation_stage`. OpenAI
  says not to retry these without changing the prompt. Source: the image generation guide,
  section "Handling blocked requests and other errors".
- 429s: `rate_limit_exceeded` and `slow_down` are retried after `Retry-After`. Not retried:
  `credit_balance_exhausted`, `organization_spend_limit_exceeded`, `project_spend_limit_exceeded`,
  `organization_usage_limit_exceeded` and type `insufficient_quota`. Source:
  https://developers.openai.com/api/docs/guides/error-codes and
  https://developers.openai.com/api/docs/guides/rate-limits
- Prices are per image output tokens. GPT Image 2.5: $30 per million image output tokens and
  $5 per million text input tokens (pricing page). Per image numbers for 2.5 come from the token
  formula in OpenAI's own cost calculator on the image generation guide; for example low
  1024x1024 is 196 tokens, $0.00588. gpt-image-2, 1.5 and 1-mini use the per image table on
  the same guide (gpt-image-2 medium 1024x1024 $0.053). Sources:
  https://developers.openai.com/api/docs/pricing and the image generation guide.
- Calls I made: OpenAI says token use can differ by model and quality, so 2.5 estimates add
  25%. The API default quality and size (`auto`) have no fixed price, so the tool always sends
  `quality=medium` and `size=1024x1024` unless told otherwise. Sizes outside the table need
  `--assume-cost`. Edits (`/v1/images/edits`) are not wired in. Refused runs stay on the ledger
  because the docs do not say whether a blocked request is billed.

## Runway API (video)

- Key: `RUNWAYML_API_SECRET` (the name Runway's SDKs read), from https://dev.runway.com
- Every request: `Authorization: Bearer <key>` and **`X-Runway-Version: 2024-11-06`**.
  Base URL `https://api.dev.runwayml.com`. Source: https://docs.dev.runwayml.com/ai-context.md
- Run: `POST /v1/image_to_video` or `POST /v1/text_to_video`. The body depends on `model`.
  `gen4_turbo` is image to video only: `promptImage` (required), `promptText` (up to 1000),
  `ratio` (1280:720, 720:1280, 1104:832, 832:1104, 960:960, 1584:672), `duration` 2 to 10.
  `gen4.5` does both; text to video takes only 1280:720 or 720:1280. `veo3.1` and `veo3.1_fast`
  take ratio 1280:720, 720:1280, 1080:1920, 1920:1080, duration 4, 6 or 8, `audio` (default true).
  Source: https://docs.dev.runwayml.com/api.md
- Async: the create call returns `{"id"}`. Poll `GET /v1/tasks/{id}` (no faster than every 5 s)
  until `SUCCEEDED` (with `output` URLs, which expire in 24 to 48 hours) or `FAILED` (with
  `failure` and `failureCode`). `THROTTLED` means queued behind the concurrency limit, not an
  error. `DELETE /v1/tasks/{id}` cancels. The task carries `cost.credits`, which the ledger uses.
- Images: a data URI works in any URL field, up to 5 MB encoded (about 3.3 MB of file).
  Source: https://docs.dev.runwayml.com/assets/inputs.md
- Free key check: `GET /v1/organization` returns `creditBalance` and the tier.
- Refusals: moderation shows up as a `FAILED` task with a `SAFETY.*` failure code, not as an
  HTTP error. Credits are not refunded for `SAFETY.INPUT.*`, and Runway says not to retry them.
  Source: https://docs.dev.runwayml.com/errors/task-failures.md
- HTTP errors: 400, 401, 404, 405 are not retryable; 429, 502, 503, 504 are, with backoff.
  Source: https://docs.dev.runwayml.com/errors/errors.md
- Prices: $0.01 per credit. gen4_turbo 5 credits a second; gen4.5 12; veo3.1_fast 15 with
  audio, 10 without; veo3.1 40 with audio, 20 without. Source:
  https://docs.dev.runwayml.com/guides/pricing.md (Runway says this page is the only source of
  truth for credit costs)
- Calls I made: the tool retries 502 and 503 on create (Runway says these mean it is shedding
  load) but not 504, since an overloaded server may still have taken the task. The tool
  requires `duration` so the price is always known. `gen3a_turbo` is retired.

## Google: Gemini API (video)

- **Veo is gone from the Gemini API.** Veo 3.1 Preview (`veo-3.1-generate-preview`, fast and
  lite) shut down on 2026-10-22, and the Veo 2 and 3.0 models on 2026-06-30. Google's
  replacement in the Gemini API is **Gemini Omni Flash** (`gemini-omni-1.1-flash`, stable since
  2026-08-27). Veo itself is still sold through Google's Gemini Enterprise Agent Platform, which
  this tool does not cover, and through Runway (`veo3.1`, `veo3.1_fast`).
  Sources: https://ai.google.dev/gemini-api/docs/video and https://ai.google.dev/gemini-api/docs/deprecations
- Key: `GEMINI_API_KEY` (or `GOOGLE_API_KEY`, which wins if both are set), from
  https://aistudio.google.com/api-keys. Header `x-goog-api-key: <key>`. Omni has no free tier.
  Source: https://ai.google.dev/gemini-api/docs/api-key and the pricing page.
- Run: `POST https://generativelanguage.googleapis.com/v1beta/interactions` with
  `{"model": "gemini-omni-1.1-flash", "input": "<prompt>" or [{"type": "image", "data": <base64>,
  "mime_type": ...}, {"type": "text", "text": ...}], "response_format": {"type": "video",
  "aspect_ratio": "16:9" or "9:16", "resolution": "360p" | "720p" | "1080p" | "4k"}}`.
  Output is 3 to 10 s, 24 fps, with audio; there is no length setting.
  Sources: https://ai.google.dev/gemini-api/docs/omni and
  https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash
- Long-running pattern: the tool sends `"background": true`, gets an interaction `id`, and
  polls `GET /v1beta/interactions/{id}` until `status` leaves `in_progress` (`completed`,
  `failed`, `cancelled`, `incomplete`). `POST /v1beta/interactions/{id}/cancel` stops it. The
  video is in `steps[]` of type `model_output`, as a part of type `video` with base64 `data`
  (or a `uri` on Google's own host). `usage` gives token counts, which the ledger uses.
  Sources: https://ai.google.dev/gemini-api/docs/background-execution and
  https://ai.google.dev/api/interactions-api
- Free key check: `GET /v1beta/models`. There is no free check for the paid tier.
  Source: https://ai.google.dev/api/models
- Errors: `{"error": {"code", "message"}}`. Blocked codes include `safety`, `prohibited_content`,
  `image_safety`, `content_blocked`; change the input before any retry. 429 `rate_limit_exceeded`
  and `too_many_requests` are retried; `quota_exceeded` (daily) is not. A spend-based 429
  `RESOURCE_EXHAUSTED` is retried after a wait. Sources:
  https://ai.google.dev/gemini-api/docs/api-errors and https://ai.google.dev/gemini-api/docs/rate-limits
- Price: video output $17.50 per million tokens at 5,792 tokens per second of 720p, about $0.10
  a second. Input $1.50 per million, text and thinking output $9 per million. Source:
  https://ai.google.dev/gemini-api/docs/pricing
- Calls I made: since length cannot be set, the estimate assumes the longest clip (10 s) plus
  10% for thinking and input tokens: about $1.12 at 720p. 360p uses the 720p rate. 1080p and 4K
  have no published rate, so they need `--assume-cost`. The docs say background execution
  supports "standard Gemini models"; the Omni page lists `background=false` as an option for a
  faster synchronous call, which is why the tool uses `background=true` and polls. Confirm this
  in the first live run. The docs do not show the body of a failed background interaction; the
  tool reads `error.code` when it is there. Stored interactions are kept by Google for the
  project's retention window (up to 55 days on paid tiers).
