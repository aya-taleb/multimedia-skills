---
name: generate-images
description: >-
  Write the prompt for an AI image and run it with the account the user already has:
  Replicate, Cloudflare Workers AI (FLUX), or OpenAI (GPT Image). Shows the cost first, spends
  nothing until they say yes, keeps one $2 per-session spend cap across every provider, saves
  each image to media/images/ right away, and handles failed runs, rate limits, timeouts and
  safety refusals. Use it whenever someone wants an image made or edited by AI: "make me an
  image", "generate a hero shot", "AI product photo", "4 product images", "thumbnail
  background", "carousel visuals", "edit this photo with AI", "run flux / gpt image / nano
  banana", "I only have a Cloudflare / OpenAI key", "set up my API key", or "how do I prompt
  this image model". Also use it to just write a better image prompt, with no run.
---

> Changed by Aya Taleb from Replicate's prompt-images and run-models skills (Apache 2.0): added a cost check, a spend cap, key setup, error handling, more providers and a working run tool.

# generate-images

Make or edit images with the user's own provider account. The user pays per run, so every run
starts with a price, waits for a yes, and stays inside one spend cap shared by all providers.
The tool does the money and error handling: `scripts/generate.py` (standard library Python).
`scripts/replicate_run.py` still works for Replicate alone and shares the same ledger.

## What this skill reads and writes

Always look for the business file first, even for a quick ask. It holds the brand look and
the off-limits topics, and skipping it is how off-brand images get made.

- Reads: the active business file from founder-context (`~/.founder/active` and
  `~/.founder/businesses/<slug>.md`, or a project-local `founder/context.md`) for brand
  look, tone and off-limits topics. If there is none, ask once for the look you need. Never
  invent brand facts.
- Writes: images to `media/images/`, one `.json` record per run (provider, model, prompt, id,
  estimate). The spend ledger lives at `~/.founder/media/spend-ledger.json`. A saved provider
  order lives at `~/.founder/media/providers.json`.
- Next: `instagram-carousel` or `launch-video` if the images feed a post or a promo,
  `generate-video` to animate one, `talking-head-cards` for card art.

## 1. Find out which account the user has (once)

Run `python3 <skill>/scripts/generate.py providers`. It reads environment variables only, makes
no network call, and says which keys are set and which provider is the default.

| provider | makes | environment variables |
| --- | --- | --- |
| replicate | images and video | `REPLICATE_API_TOKEN` |
| cloudflare | images (FLUX) | `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` |
| openai | images (GPT Image) | `OPENAI_API_KEY` |

Then run `generate.py check`. It makes a free call for each provider with a key and says what
works. If no key is set, it prints the setup steps for every provider. Ask which account the
user already has, and walk them through that one only. Why so careful: a key can spend their
money, so it must live in their shell environment, never in chat or in a project file.

If keys are set for more than one image provider and no order is saved, the tool says "ask
the user". Ask which they prefer, then save it: `generate.py providers --order cloudflare,openai`.

If they paste a key into chat anyway, do not repeat it back, and do not pass it on: not in a
command, a file, or the arguments of another skill or tool. Tell them to revoke it in that
provider's dashboard and set a new one in their shell, since chat logs are not a safe place.

## 2. Pick the model from live data and the dated table

Never pick from memory. Image models change every few weeks, and a remembered name may be gone
or overpriced (OpenAI shut down gpt-image-1 on 2026-10-23). Use the `find-model` skill, or:

```
python3 generate.py models --kind image
python3 generate.py schema <model>
python3 generate.py price <model> -i prompt="..."
```

`models` lists live models where the provider has a listing call, joined with prices from
`scripts/prices.json`. Each price there has its source link and checked date. For Replicate,
`models --provider replicate --query "product photo"` searches live, and prices come from the
model page. Prefer Replicate's official models (no cold boot, fixed prices).

When the user says cheap, price two or three candidates on the providers they have and pick
the cheapest one that fits. Say why if you pick a pricier one. Read `schema` before writing
inputs, because names like `size`, `aspect_ratio` or `num_outputs` differ by model.

The provider facts, with links and dates, are in `references/providers.md`. The Replicate API
notes are in `references/replicate-api.md`.

## 3. Write the prompt

Write full sentences, not keyword lists. Say the subject, setting, light, lens and framing.
Name things directly ("the woman in the navy blazer") instead of using pronouns. When editing,
say what must stay the same. Put any words that should appear in the image in double quotes.

The full guide, with editing, text, product shots and character consistency, is in
`references/prompting-images.md`. Read it when the job is more than a plain scene.

Keep facts out of images that you cannot back up. Do not put prices, stats, logos of other
companies, or customer quotes into a prompt unless the user supplied them.

## 4. Show the cost and wait for yes

Do a dry run first. It prints the estimate, how it was worked out, the session total and what
is left under the cap. It spends nothing, and for table providers it needs no key at all.

```
python3 generate.py run <model> -i prompt="..." --label hero
```

Show the user, in plain words: the provider, the model, the prompt, how many images, the
estimate, and the session total. Then ask. A request like "make me an image" is not a yes to a
price they have not seen. Why: providers bill the moment a run starts, and it cannot be undone.

One exception: if the user already named a dollar amount they agree to ("go ahead, up to
$1"), and the full estimate fits under it and under the cap, that is the yes. Say the
estimate, then run. If it does not fit, stop and ask.

Batches: one run per call. If the user wants 4 options, say the total for all 4 and get one
yes for that total. Then run them one after another, not in parallel, so a failure or a cap
hit stops the rest. Cloudflare makes one image per call. OpenAI takes `-i n=4` in one call.

Big asks ("run it 50 times overnight", "don't ask me about cost"): do not agree to the 50,
now, later, or "in this session". Unattended loops and big batches are how people wake up to
a surprise bill. Instead:

1. Price it. `price` works without a key, so there is always a real number. Multiply it out.
2. Say the session cap ($2 unless the user changed it) and how many runs fit under it. Offer
   a small first batch (for example 4 runs), with its total, to look at before doing more.
3. Wait for a yes to that number. "Don't ask me about cost" is not a yes to a number.

Never quote a price from memory. If you have not run `price` in this session, you do not know
it. If the tool warns the table is more than 60 days old, read the source link first.

## 5. Run it

After a clear yes, run the same command with `--yes`:

```
python3 generate.py run <model> -i prompt="..." --label hero --yes --out media/images
```

The tool then: reserves the estimate on the ledger, sends one request, waits or polls with
backoff, saves every image at once, and writes the record. Local files go in as
`-i image=@path/to/photo.jpg` (the input name comes from `schema`; on Cloudflare FLUX.2 it is
`input_image_0`).

Then show the saved file paths and the spend so far (`generate.py ledger`).

## 6. When something goes wrong

Read the exit code and the message. Do not just rerun.

| exit | what happened | what to do |
| --- | --- | --- |
| 2 | setup or input problem, nothing ran | fix the key or the input the message names. "No estimate" means the model or size is not priced: read the price on the source link, tell the user, and only after a yes rerun with `--assume-cost <dollars>` |
| 4 | over the spend cap, nothing ran | tell the user the total; only raise the cap if they ask (`ledger --set-cap 10`) |
| 5 | API error | bad key, no credit, bad input. Out-of-credit 429s are not retried. A 5xx or dropped connection on create may have started a run, so check the provider's dashboard before trying again |
| 6 | failed or refused | a refusal means the provider's safety rules blocked it. Change the prompt or image before any retry, and ask first |
| 7 | timed out or canceled | the tool canceled it where the provider allows. It may still be billed |
| 8 | ran, but a download failed | the message lists the links. Fetch them soon |

Rate limits (429) that mean "slow down" are handled inside the tool: it waits and says so.

## 7. Close every answer the same way

Whether you ran, did a dry run, or declined, end with one line that names the next step:
`instagram-carousel` for a post, `generate-video` to animate the image, `launch-video` for a
promo, or "say yes and I'll run it for $X". Why: the user should never wonder what happens next.

Describe results from the files and the prompt, not from what you imagine. You have not seen
the image unless you opened it.

## Rules

- No run without a price shown and a yes. The first `run` call is a dry run, even when the
  user pre-approved a budget, because the estimate has to exist before you can check it fits.
- Stay under the cap (default $2 a session, one cap for every provider). Never raise it on
  your own.
- One request at a time. No loops that fire runs in the background.
- Save outputs right away. Never hand the user a provider link as the result.
- Never put a key in a file, a command you show, or your reply.
- Do not make images of real people without their consent, fake screenshots, fake reviews,
  or anything that passes for a real document. Say no and offer a version that is clearly
  an illustration.
- Prompt-only requests ("just write me a prompt") need no key and cost nothing. Do not push
  a paid run on someone who did not ask for one.

## Tool reference

`generate.py` commands: `providers [--order a,b]`, `check [--provider P]`,
`models [--provider P] [--kind image|video] [--query Q]`, `schema MODEL`, `price MODEL`,
`run MODEL`, `ledger`. Flags for `run`: `-i key=value` (repeatable), `--input '{json}'`,
`--input-file`, `--provider`, `--yes`, `--out`, `--label`, `--max-cost`, `--assume-cost`,
`--timeout` (seconds, default 600), `--deadline` (Replicate auto-cancel, default `15m`).
The provider is worked out from the model name; pass `--provider` when it is not clear.
