# Replicate API facts the tool relies on

> Changed by Aya Taleb from Replicate's run-models and find-models skills (Apache 2.0): one docs list instead of a copy in every skill, plus the money and error facts.

Checked on 2026-10-23. When something here and the live docs disagree, the live docs win.

## Docs

- Reference index: https://replicate.com/docs/llms.txt
- OpenAPI schema (source of truth): https://api.replicate.com/openapi.json
- Per-model docs: `https://replicate.com/{owner}/{model}/llms.txt`
- Send `Accept: text/markdown` when fetching docs pages to get Markdown.

## Calls

| job | call | costs money? |
| --- | --- | --- |
| check the token | `GET /v1/account` | no |
| search models | `GET /v1/search?query=...&limit=N` (beta, needs a token) | no |
| one model + schema | `GET /v1/models/{owner}/{name}` | no |
| run an official model | `POST /v1/models/{owner}/{name}/predictions` with `{"input": {...}}` | yes |
| run any model at a version | `POST /v1/predictions` with `{"version": "owner/name:<64 hex>", "input": {...}}` | yes |
| check a run | `GET /v1/predictions/{id}` | no |
| cancel a run | `POST /v1/predictions/{id}/cancel` | stops billing |
| upload an input file | `POST /v1/files` (multipart, under 100 MB) | no |

Auth header: `Authorization: Bearer $REPLICATE_API_TOKEN`.

The input schema sits at `latest_version.openapi_schema.components.schemas.Input`. Enum inputs
often point elsewhere with `allOf: [{"$ref": "#/components/schemas/<name>"}]`. The tool
follows those refs when it checks inputs.

## Prediction states

`starting` (a long `starting` usually means a cold boot), `processing`, then one of:
`succeeded`, `failed`, `canceled` (stopped after it began, billed for time used), `aborted`
(deadline hit before it began, not billed).

- Runs time out after 30 minutes.
- `Cancel-After: 15m` header on create sets a deadline (minimum 5 seconds). The tool sends it.
- `Prefer: wait=n` (1 to 60 seconds) holds the request open. The tool polls instead, because
  a long hold that drops leaves you unsure whether you paid.

Source: https://replicate.com/docs/topics/predictions/lifecycle

## Rate limits

- Create prediction: 600 requests per minute. Other endpoints: 3000 per minute.
- Accounts with granted credit and no card: 1 request per second, 6 per minute.
- Low credit brings tighter limits.
- A 429 body looks like `{"detail":"Request was throttled. Your rate limit resets in ~30s."}`.
  The tool reads `Retry-After` if present, else the `~30s` in the text, and waits that long.

Source: https://replicate.com/docs/topics/predictions/rate-limits

## Output files

- API predictions delete their inputs, outputs and files after one hour.
- Output links on `replicate.delivery` expire after one hour.
- So the tool downloads every output as soon as the run succeeds.

Sources: https://replicate.com/docs/topics/predictions/data-retention and
https://replicate.com/docs/topics/predictions/output-files

## Prices

The API has no price field. Prices are shown on each model page under Pricing, and the page
embeds them as JSON (`billingConfig`, plus `price` and `p50price` for GPU-time models). The
tool reads that JSON:

- Official models: priced per output (per image, per second of video, per token). Some have
  tiers by option, like resolution or audio on or off. If the tool cannot tell which tier
  applies, it uses the most expensive one.
- Community models: billed by GPU seconds. The tool takes the page's typical run cost and
  doubles it to cover a cold boot. Real cost can be higher on a very slow run.
- Some models bill through another company's key (for example "You pay OpenAI directly").
  The tool says so and refuses to guess.

If the page layout changes and the tool finds no price, it refuses to run until a human reads
the price and passes `--assume-cost`. That is on purpose.

Official model notes: https://replicate.com/docs/topics/models/official-models
Billing: https://replicate.com/docs/topics/billing
