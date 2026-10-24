# Prompting video models

> Changed by Aya Taleb from Replicate's prompt-videos skill (Apache 2.0): trimmed, reworded to house style, added word-count timing and honesty notes.

These techniques work across current video models. They come from Replicate's blog posts on
prompting video (2025 and 2026). Choose the model with live search, not from this page.

## A scene, not a caption

Layer these into every prompt:

1. Subject: who or what is in the shot.
2. Place: where it happens.
3. Action: what they do.
4. Style: cinematic, animated, stop-motion, documentary.
5. Camera: how it moves.
6. Framing: wide, close-up, over the shoulder.
7. Mood and light: warm tones, blue light, golden hour, overcast.

Be specific. "A car chase" gives a random clip. "Two muscle cars weave through heavy traffic
on a rain-soaked highway at night, headlights cutting through the downpour, neon signs blurring
overhead" gives the clip you meant. Every concrete detail leaves the model less to make up.

Name subjects with a short description ("the bearded man in flannel"), not pronouns.

## Camera

- Shots: wide or establishing, medium (waist up), close-up, extreme close-up.
- Moves: static on a tripod, pan, tilt, dolly in or out, tracking alongside, crane up or down,
  handheld, drone, dolly zoom.
- Position: eye level, low angle (subject feels big), high angle (subject feels small), over
  the shoulder, first person.
- Lens: shallow depth of field, deep focus, macro, wide angle, tilt-shift.

A plain structure for 8 to 15 second clips is wide, then medium, then close-up, then a detail:

- 0 to 3s: wide shot of the place
- 3 to 7s: medium shot, the subject acts
- 7 to 12s: close-up on the key moment
- 12 to 15s: extreme close-up on a detail

## Sound and dialogue

Many models make sound with the picture. If you do not prompt it, the model guesses, and it
often guesses wrong (a laughing studio audience is a known failure). Prompt four layers:

1. Dialogue: exact words, or the intent ("the man introduces himself").
2. Ambient sound: rain on a metal awning, city traffic, birds.
3. Effects: a door slam, glass breaking.
4. Music: genre, mood, instruments, or "no music".

Timing: speech runs about 2 to 3 words a second. An 8 second clip fits about 16 to 24 words.
Count them before you run. Too many gives rushed speech; too few gives silence or gibberish.

Avoid burned-in subtitles:

- Use a colon for dialogue: `She says: Hello there`, not quotes.
- Add `(no subtitles)`. If they still appear, repeat it.

Spell hard names the way they sound ("foh-fur" for "fofr").

With two speakers, tie each line to a look: "The woman in pink says: ..." and "The man with
glasses replies: ...".

## Several shots in one clip

Some models can cut between shots inside one clip of up to about 15 seconds. Use time codes:

```
[0-4s]: Wide establishing shot, static camera, misty bamboo forest at dawn
[4-9s]: Medium shot, slow push-in, the fighter steps forward
[9-15s]: Close-up, orbit shot, the fighter strikes, slow motion
```

Give each shot a camera, an action and a light. Say the transition: hard cut, whip pan, snap
cut, or a smooth morph. Without one, the model picks.

## Reference inputs

- Image to video: the image is the first frame. Describe the motion and camera, not what the
  image already shows. Style carries over well, so a frame made with generate-images first
  gives you control of the look.
- First and last frame: give a start and an end image and the model fills the middle. Good for
  before and after shots.
- Subject references: some models keep a character or a product looking the same from a
  reference photo. Use a real photo of the real product, so the clip does not mislead buyers.
- Many models refer to inputs in the prompt with brackets, like `[Image1]` or `[Audio1]`.
- Audio-driven: some models sync lips or cuts to an audio file. Put the spoken words in the
  prompt too, and match the clip length to the audio.

## Style

- Name it: claymation, anime, stop-motion, documentary footage, 8-bit, graphic novel.
- Style changes motion too: claymation moves in jerky steps, anime moves fluidly.
- "Slightly grainy, film-like" makes clips feel less glossy and more real.
- Pull look and mood from the founder-context file when there is one.

## Same character across clips

Write one character line and paste it word for word into every prompt: "John, a man in his
40s with short brown hair, a blue jacket and glasses". Change only the action, place and camera.
A reference photo is more reliable than words alone.

## Common mistakes

1. No sound prompt, so the model invents sound.
2. Too much or too little dialogue for the length.
3. Not saying what stays the same when using a reference.
4. Rerunning the same prompt for variety. Many video models give near-identical results.
   Change the prompt instead, and remember each rerun costs money.
5. No camera direction.
6. Subtitles burned in. Use colons and "(no subtitles)".
7. A vague prompt for a busy scene.
8. Wrong aspect ratio or resolution. Check the schema; not every model does vertical.
9. Expecting the model to know current events. It does not.
10. Paying for 1080p with audio when a short silent 720p clip would do.

## Background reading (Replicate blog)

- How to make remarkable videos with Seedance 2.0 (Apr 2026): https://replicate.com/blog/seedance-2
- How to prompt Veo 3.1 (Oct 2025): https://replicate.com/blog/veo-3-1
- How to prompt Veo 3 with images (Aug 2025): https://replicate.com/blog/veo-3-image
- Open source video is back, Wan 2.2 (Jul 2025): https://replicate.com/blog/wan-22
- Compare AI video models (Jul 2025): https://replicate.com/blog/compare-ai-video-models

These posts name models that were current when written. Search live before you pick one.
