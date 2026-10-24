# Prompting image models

> Changed by Aya Taleb from Replicate's prompt-images skill (Apache 2.0): trimmed, reworded to house style, added brand and honesty notes.

These techniques work across current image models. They come from Replicate's blog posts on
prompting (2024 to 2026). Pick the model with live search, not from this page.

## Write the scene, not tags

Full sentences beat keyword lists. Modern models read grammar and context.

- Good: "A woman standing in a Tokyo alleyway at dusk, neon signs reflecting off wet pavement"
- Weak: "woman, Tokyo, alleyway, dusk, neon, wet pavement"

Be exact about colors, materials, light, lens and where things sit. "Make it better" or
"artistic" gives random results. Name subjects directly ("the red car") instead of "it".

Long prompts are fine. Most models take thousands of tokens. The more requirements you add,
the more likely one gets missed, so put the most important ones first.

Start with a small change, check it, then build on what works.

## Photo language the models understand

- Film stock: Kodak Portra 800, Fuji Velvia 50, Ilford HP5
- Lens: 50mm wide open, 85mm f/1.4, 24mm wide angle
- Depth of field: shallow (soft background) or deep (all sharp)
- Time: golden hour, blue hour, long exposure
- Light: Rembrandt, soft diffused studio light, rim light, flat overcast light, volumetric haze
- Framing: rule of thirds, centered, symmetry; wide, medium, close-up, macro
- Angle: high, low, eye level, bird's-eye; tilt-shift for a miniature look

## Text in images

- Put the exact words in double quotes: a poster titled "BLUE NOTE SESSIONS" in bold condensed sans-serif.
- Plain readable fonts work best.
- To change text in a photo: Change 'old text' to 'new text'. Keep the length close, or the layout shifts.
- Say if the font style must stay the same.
- For posters and layouts, pick a model known for typography (check its page and examples).
- Only use words the user gave you. A made-up stat or quote in an ad image is still made up.

## Style

- Name the style: impressionist painting, 1960s pop art, Sumi-e ink wash.
- If the label fails, describe the traits: visible brush strokes, thick paint, rich color.
- Say what stays: "keep the original composition".
- Some models take style reference images. Use them when words fall short.
- Pull colors and mood from the founder-context file when there is one, so images match the brand.

## Same character across images

- Write one exact description and paste it into every prompt: "the woman with short black hair and green eyes wearing a navy blazer".
- Say what changes (place, action) and what stays (face, clothes).
- Use reference images when the model supports them. Some take several at once.
- Change one thing per step: outfit first, then scene.

## Editing

- Say what to keep: "keeping the pose and expression unchanged".
- Pick a precise verb. "Transform" invites a full rework. "Change the jacket to blue" does not.
- Be exact about scope: "Replace the background with a beach. Keep the person in the same
  position, same framing and same camera angle. Only change the surroundings."
- Removing an object: say what should fill the gap.
- New background: describe its light and time of day, and keep the subject's light matching.
- New camera angles are the hardest edit. Many models stay stuck to the first framing.
- Inpainting: mask the area, then prompt for what fills it. If the model has a prompt
  rewrite option on, describe only the edit; with it off, describe the whole scene.

## Several images at once

- Ask for "a set of four" or "a 2x2 storyboard grid" on models that support it.
- Describe each panel, and repeat the character description word for word in each.

## Product shots

- Name the materials: brushed steel, matte aluminum, kraft paper, frosted glass.
- Name the light: soft diffused studio light, crisp highlights, gentle shadows.
- For logos and icons, look for models that output real SVG files.
- For an existing product, edit a real photo of it (image input) instead of inventing one.
  A generated product that looks different from the real one misleads buyers.

## Fine-tunes and LoRAs

- Use the trained trigger word in every prompt.
- When mixing LoRAs, keep their scales near 0.9 to 1.1.

## Common mistakes

1. Keyword lists instead of sentences.
2. "Transform" when you mean a small edit.
3. Not saying what to keep when editing.
4. Negative prompts on models not trained for them. They add noise. Check the model page.
5. Guidance (CFG) too high: burnt, over-contrasty images. Lower it.
6. Expecting live knowledge. No image model knows today's news.
7. Short prompts for busy scenes.
8. Wrong aspect ratio. Use the sizes the schema allows, near 1 megapixel unless told otherwise.
9. Wrong model for the job. If a model keeps failing one kind of edit, try another one
   instead of fighting the prompt. Each try costs money, so say so before switching.
10. Expecting one perfect shot. Plan for a few rounds, and price them up front.

## Background reading (Replicate blog)

- How to prompt Seedream 5.0 (Feb 2026): https://replicate.com/blog/how-to-prompt-seedream-5
- Recraft V4 (Feb 2026): https://replicate.com/blog/recraft-v4
- Run FLUX.2 on Replicate (Nov 2025): https://replicate.com/blog/run-flux-2-on-replicate
- How to prompt Nano Banana Pro (Nov 2025): https://replicate.com/blog/how-to-prompt-nano-banana-pro
- Which image editing model should I use? (Sep 2025): https://replicate.com/blog/compare-image-editing-models
- Generate consistent characters (Jul 2025): https://replicate.com/blog/generate-consistent-characters
- Ideogram 3.0 (May 2025): https://replicate.com/blog/ideogram-v3

These posts name models that were current when written. Search live before you pick one.
