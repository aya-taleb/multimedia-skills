# How find-model scores a shortlist

Replicate's compare-models skill said to compare cost, speed, quality and features, but gave
no way to weigh them. This is the method we use. It is plain on purpose, so the user can see
each number and change a weight.

## Step 1: must-haves first

List the user's must-haves. For each finalist, check the schema (not the description):

- "vertical video" means an `aspect_ratio` or `resolution` enum that includes `9:16` or a
  portrait size.
- "with audio" means an input like `generate_audio`, or a model whose price tiers include
  `with_audio`.
- "uses my product photo" means an image input (`image`, `input_image`, `reference_images`,
  `first_frame_image`).
- "text in the image" has no schema field. Check the model page examples for readable text,
  and say it is unconfirmed.

A finalist missing a must-have is out. Do not score it.

## Step 2: the five parts

| part | max | rule |
| --- | --- | --- |
| Fit | 40 | 40, minus 5 for each nice-to-have the schema lacks |
| Cost | 25 | 25 x (cheapest price / this price), for the user's settings |
| Speed | 15 | official and a fast or turbo tier: 15. Official: 10. Community: 5 |
| Fresh | 10 | latest version under 6 months old: 10. 6 to 12 months: 5. Older: 0 |
| Proof | 10 | official: +5. Page examples close to the job: +5 |

Round each part to a whole number.

Cost uses the price for the user's own settings and volume. Example: the user needs 6 clips of
5 seconds at 720p. Model A is $0.025 a second at 720p, so $0.75 for the job. Model B is $0.10 a
second, so $3.00. A gets 25. B gets 25 x 0.75 / 3.00 = 6.

When a model is billed by GPU time, use the typical run cost from its page, doubled for cold
boots, and mark it "estimate".

## Step 3: show it

```
| model | price for your job | fit | cost | speed | fresh | proof | total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| owner/model-a | $0.75 (6 x 5s, 720p) | 40 | 25 | 15 | 10 | 5 | 95 |
```

Under the table, list what the score cannot see: real output quality, real wait time, and
any price the page did not show.

## Step 4: when to suggest a test

If the top two are within 10 points, offer a small paid test through generate-images or
generate-video: the same prompt on both, priced up front, after a yes. Judge the results on
the user's own must-haves, not on taste alone.

## Speed, in more detail

- Official models are always warm. Community models can cold boot, which can add minutes.
- `predict_time` in a finished run's metrics is the real number. It only exists after a paid
  run, so it never feeds this score directly.
