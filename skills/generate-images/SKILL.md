---
name: generate-images
description: >-
  Write the prompt for an AI image and run it on Replicate with the user's own token, showing
  the cost first and spending nothing until they say yes. Keeps a $5 per-session spend cap,
  saves every image to media/images/ right away (Replicate links die after an hour), and
  handles failed runs, rate limits and cold boots. Use it whenever someone wants an image
  made or edited by AI: "make me an image", "generate a hero shot", "AI product photo",
  "thumbnail background", "carousel visuals", "edit this photo with AI", "swap the
  background", "run flux / nano banana / seedream", "how do I prompt this image model", or
  "set up my Replicate token". Also use it to just write a better image prompt, with no run.
---

> Changed by Aya Taleb from Replicate's prompt-images and run-models skills (Apache 2.0): added a cost check, a spend cap, a token setup step, error handling and a working run tool.

# generate-images

Make or edit images with Replicate models. The user pays per run, so every run starts with a
price, waits for a yes, and stays inside a spend cap. The tool does the money and error
handling for you: `scripts/replicate_run.py` (standard library Python).

## What this skill reads and writes

Always look for the business file first, even for a quick ask. It holds the brand look and
the off-limits topics, and skipping it is how off-brand images get made.

- Reads: the active business file from founder-context (`~/.founder/active` and
  `~/.founder/businesses/<slug>.md`, or a project-local `founder/context.md`) for brand
  look, tone and off-limits topics. If there is none, ask once for the look you need. Never
  invent brand facts.
- Writes: images to `media/images/`, one `.json` sidecar per run (model, prompt, prediction id,
  estimate). The spend ledger lives at `~/.founder/media/spend-ledger.json`.
- Next: `instagram-carousel` or `launch-video` if the images feed a post or a promo,
  `generate-video` to animate one, `talking-head-cards` for card art.

## 1. Set up the token (once)

Run `python3 <skill>/scripts/replicate_run.py check`. If it prints setup steps, walk the user
through them. Why so careful: the token can spend their money, so it must live in their shell
environment, never in chat or in a project file.

1. Account at replicate.com with a payment method or credit.
2. Token from replicate.com/account/api-tokens.
3. `export REPLICATE_API_TOKEN=r8_...` in their shell profile. Then run `check` again.

If they paste a token into chat anyway, do not repeat it back, and do not pass it on: not in a
command, a file, or the arguments of another skill or tool. Tell them to revoke it at
replicate.com/account/api-tokens and set a new one in their shell, since chat logs are not a
safe place for it.

## 2. Pick the model from live data

Never pick from memory. Image models change every few weeks, and a remembered name may be gone
or overpriced. Use the `find-model` skill, or at least:

```
python3 replicate_run.py search "product photo editing" --limit 8
python3 replicate_run.py schema owner/model
python3 replicate_run.py price owner/model -i num_outputs=1
```

Prefer official models (`official: True`). They have fixed per-image prices and no cold boot.
When the user says cheap, price two or three candidates and pick the cheapest one that fits
the job. Say why if you pick a pricier one.
Read the schema before writing inputs, because names like `aspect_ratio` or `num_outputs`
differ from model to model.

## 3. Write the prompt

Write full sentences, not keyword lists. Say the subject, setting, light, lens and framing.
Name things directly ("the woman in the navy blazer") instead of using pronouns. When editing,
say what must stay the same. Put any words that should appear in the image in double quotes.

The full guide, with editing, text, product shots and character consistency, is in
`references/prompting-images.md`. Read it when the job is more than a plain scene.

Keep facts out of images that you cannot back up. Do not put prices, stats, logos of other
companies, or customer quotes into a prompt unless the user supplied them.

## 4. Show the cost and wait for yes

Do a dry run first. It looks up the price on the model page and prints the estimate, the
session total and what is left under the cap. It spends nothing.

```
python3 replicate_run.py run owner/model -i prompt="..." -i aspect_ratio=4:5 --label hero
```

Show the user, in plain words: the model, the prompt, how many images, the estimate, and the
session total. Then ask. A request like "make me an image" is not a yes to a price they have
not seen. Why: Replicate bills the moment a run starts, and a mistake cannot be undone.

One exception: if the user already named a dollar amount they agree to ("go ahead, up to
$1"), and the full estimate fits under it and under the cap, that is the yes. Say the
estimate, then run. If it does not fit, stop and ask.

Batches: one run per call. If the user wants 4 options, say the total for all 4 and get one
yes for that total. Then run them one after another, not in parallel, so a failure or a cap
hit stops the rest.

Big asks ("run it 50 times overnight", "don't ask me about cost"): do not agree to the 50,
now, later, or "in this session". Unattended loops and big batches are how people wake up to
a surprise bill. Instead:

1. Price it. `price` works without a token, so there is always a real number:
   `replicate_run.py price owner/model -i num_outputs=1`. Multiply it out for the ask.
2. Say the session cap ($5 unless the user changed it) and how many runs fit under it. Offer
   a small first batch (for example 4 runs), with its total, to look at before doing more.
3. Wait for a yes to that number. "Don't ask me about cost" is not a yes to a number.

Never quote a price from memory. If you have not run `price` in this session, you do not know it.

## 5. Run it

After a clear yes, run the same command with `--yes`:

```
python3 replicate_run.py run owner/model -i prompt="..." -i aspect_ratio=4:5 --label hero --yes --out media/images
```

The tool then: reserves the estimate on the ledger, creates the prediction, polls with
backoff, downloads every output at once, and writes the sidecar. Local files go in with
`-i image=@path/to/photo.jpg` (small files are sent inline, big ones uploaded).

Then show the saved file paths and the actual spend so far (`replicate_run.py ledger`).

## 6. When something goes wrong

Read the exit code and the message. Do not just rerun.

| exit | what happened | what to do |
| --- | --- | --- |
| 2 | setup or input problem, nothing ran | fix the token or the input the message names |
| 4 | over the spend cap, nothing ran | tell the user the total; only raise the cap if they ask (`ledger --set-cap 10`) |
| 5 | API error | 401 bad token, 402 no credit, 422 bad input. A 5xx on create may have started a run, so check replicate.com/predictions before trying again |
| 6 | the model failed | read the error (often a safety filter or a bad input). Change the prompt or input before any retry |
| 7 | timed out or canceled | the tool canceled it to stop billing. Try a faster model or a smaller size |
| 8 | ran, but a download failed | the message lists the links. Fetch them within the hour |

Rate limits (429) and cold boots are handled inside the tool: it waits and says so. A cold
boot only happens on community models, which is one more reason to prefer official ones.

If the price cannot be found (the tool says "No estimate"), read the pricing section on the
model's page yourself, tell the user the number and its link, and only after a yes rerun with
`--assume-cost <dollars>`.

## 7. Close every answer the same way

Whether you ran, did a dry run, or declined, end with one line that names the next step:
`instagram-carousel` for a post, `generate-video` to animate the image, `launch-video` for a
promo, or "say yes and I'll run it for $X". Why: the user should never wonder what happens next.

Describe results from the files and the prompt, not from what you imagine. You have not seen
the image unless you opened it.

## Rules

- No run without a price shown and a yes. The first `run` call is a dry run, even when the
  user pre-approved a budget, because the estimate has to exist before you can check it fits.
- Stay under the cap (default $5 a session). Never raise it on your own.
- One prediction at a time. No loops that fire runs in the background.
- Save outputs right away. Never hand the user a replicate.delivery link as the result.
- Never put the token in a file, a command you show, or your reply.
- Do not make images of real people without their consent, fake screenshots, fake reviews,
  or anything that passes for a real document. Say no and offer a version that is clearly
  an illustration.
- Prompt-only requests ("just write me a prompt") need no token and cost nothing. Do not push
  a paid run on someone who did not ask for one.

## Tool reference

`replicate_run.py` commands: `check`, `search`, `schema`, `price`, `run`, `ledger`.
Flags for `run`: `-i key=value` (repeatable), `--input '{json}'`, `--input-file`, `--yes`,
`--out`, `--label`, `--max-cost`, `--assume-cost`, `--timeout` (seconds, default 600),
`--deadline` (Replicate auto-cancel, default `15m`). The API facts it relies on, with links,
are in `references/replicate-api.md`.
