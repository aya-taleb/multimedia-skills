---
name: humanize
description: Cleans and scores any draft before a person posts, sends or publishes it, so it reads like the founder wrote it and not a chatbot. Strips hidden characters, long dashes, curly quotes and stock AI phrases, flags words the founder's business file says to avoid, and gives a 0 to 100 score that explains every lost point in plain words. Use it whenever someone says "humanize this", "make it sound less like AI", "does this sound like ChatGPT", "clean up my post", "remove the em dashes", "score my draft" or "check this before I send it", and run it on every LinkedIn post, Instagram caption, DM, cold email, landing page or investor update another skill writes, before showing the draft. Local pattern checks only, no detector service.
---

# humanize

Make a draft read like a person wrote it, then show the founder why it scores what it
scores. The founder posts or sends it. This skill never does.

## When other skills call this

Any skill that writes words a human will post or send runs its draft through here before
showing it. Return three things to the caller: the clean draft, the before and after
score, and the short list of what changed. The caller shows those to the user.

## What you need

1. **The draft.** Pasted text or a file path. If there is no draft, ask for it. Do not
   write one from scratch here: that is the job of the skill that owns the format.
2. **Where it is going.** LinkedIn, Instagram, email, text, landing page, doc. It decides
   whether Markdown is allowed. If it's obvious from the draft, don't ask.
3. **The business file, if there is one.** Always look, even for a pasted draft. Check
   `founder/context.md` in the project, then `~/.founder/businesses/<slug>.md`
   where `<slug>` is in `~/.founder/active`. Read it for tone words and "Words to
   avoid" only. If there is none, carry on with the house list and tell the founder in one
   line ("No business file found, so I used the house word list."). The tools find the
   file on their own; you read it yourself for the tone words.

## Steps

### 1. Clean the mechanical tells

Save the draft to a file if it isn't one, then run:

```bash
python3 <skill-dir>/scripts/humanize.py draft.txt --out draft.clean.txt --swap-words
```

`<skill-dir>` is the folder this SKILL.md is in. Add `--strip-markdown` when the draft
goes somewhere that shows `**` and `#` as raw characters (LinkedIn, Instagram, texts,
most email). Add `--allow-markdown` when it goes somewhere that renders Markdown.

The tool removes hidden characters, turns long dashes into commas or periods, straightens
quotes and swaps a few always-safe words ("utilize" becomes "use"). It never touches <!-- allow-words -->
code, links, emails, @handles or #hashtags. It prints the before and after score.

Why a tool: these are character-level fixes. A script does them the same way every time
and misses nothing, where reading by eye skips invisible characters.

### 2. Read the score report

The report lists each check that lost points, why it matters, what was found and how to
fix it. Run the scorer on its own any time:

```bash
python3 <skill-dir>/scripts/detect.py draft.clean.txt
```

Pass `--context <file>` to point at a business file directly, `--extra-banned "a, b"` to
add words for this draft only, or `--json` when another tool will read the result.

### 3. Rewrite what the tool can't

The script fixes characters. Words and structure need judgment. For each flagged check,
fix it in the draft, using the suggested plainer word or the fix line in the report.
`references/rewrite-guide.md` has a short how-to per check.

Keep these while rewriting:

- **Every fact stays, nothing new comes in.** Same numbers, names, dates, links, claims
  and offers. Adding a statistic or a customer story to make it "pop" is making things up.
  If the draft needs proof it doesn't have, leave `{{your number}}` or `{{a real example}}`
  and tell the founder.
- **The business file sets the voice, not the content.** Don't pull its pitch, customer
  count, audience or proof into the draft, even when it's true. The founder chose what to
  say in this piece. If a line from the file would make it stronger, suggest it after the
  draft ("You could add: 6 offices already on the route") and let them decide.
- **Don't add enthusiasm or traits.** "Likes working with new tech", "does well in",
  "loves", "passionate about" are new claims about people. If the draft didn't say it,
  leave it out.
- **A cut beats a swap.** If a phrase says nothing ("smart signals to streamline your <!-- allow-words -->
  workflow"), cut it rather than rewording it into a new claim. A reworded phrase that
  promises something the draft didn't ("nothing to set up", "delivered to your door") is
  an invented claim.
- **When you replace a stock phrase, use words already in the draft.** "It's not just a
  to-do app, it's a new way to work" becomes a plain line built from what the draft says
  the product does, not a new description.
- **Their voice, not yours.** Use the tone words from the business file. If the founder
  writes in lowercase, uses slang, or mixes in another language, keep it.
- **Same length or shorter.** A cleaner draft is almost never longer.
- **Don't chase 100 by gutting it.** One stock word in a strong post is fine. Fix the
  tells that a reader would notice first: the opener, the sign-off, the banned words.
- **These are not optional:** no long dashes, no banned or avoid-list words, and no
  sentence over 25 words in the final draft. Split long ones, even the one with the proof.

### 4. Score again, check the facts, and hand it back

Run the scorer on the rewrite with the original next to it:

```bash
python3 <skill-dir>/scripts/detect.py draft.human.txt --compare draft.txt
```

`--compare` lists numbers, links, handles and names the rewrite dropped or added, and
the words that weren't in the original. Fix every dropped or added fact. Then read the
new-word list: each one should be a plain swap, not a new claim, feature, audience or
promise ("for the people who use our product", "nothing to set up"). Cut any that are.
This step exists because rewriting for flow is exactly when made-up details sneak in.

Then show the founder:

1. The final draft, ready to copy.
2. `Score: <before> -> <after>` (the before score is the original draft), then one line
   per check that still loses points, using the report's "why it matters" in plain words.
   If nothing loses points, name the two or three checks that cost the most at the start
   and why they mattered, so the founder learns what to watch for next time. Name
   anything you chose to keep and why. Say the result of the fact check in one line
   ("Same numbers, links and names as your draft.").
3. The list of changes, short: "removed 3 long dashes", "cut the stock opener", "swapped
   6 avoid-list words for plain ones". Give counts, not the words: don't quote the
   removed words or phrases in your reply at all. The score report already names them
   if the founder wants detail. A reply full of the words you just removed reads like the
   problem, and it trips the same checks when another tool reads your reply.
4. Any `{{placeholder}}` the founder must fill before it goes out, and any suggestion
   from the business file they might want to add. If no business file was found, say so
   here in one line.
5. One closing line that they post or send it themselves, for example "Copy it into
   LinkedIn when you're ready. I haven't posted anything."

A reply in this shape works well (fill in the real numbers and lines):

```
<the final draft>

Score: 40 -> 97. These are local pattern checks, not an AI detector.
Still loses 3 points: one 27-word sentence. Long sentences make people reread.
Changed: removed 2 long dashes, cut the stock opener and sign-off, swapped 7 avoid-list
words for plain ones, cut hashtags from 7 to 3.
Fact check: same numbers, link and names as your draft.
Fill before posting: {{role title}}.
Copy it into LinkedIn when you're ready. I haven't posted anything.
```

If the draft came from a file, write the final version next to it as
`<name>.human.<ext>` and say where. Don't overwrite their original unless asked. If it
was pasted, show it in the reply. Delete the in-between `.clean` copy when you're done,
so the founder is left with two files: their original and the final.

Your own reply follows the same rules as the draft: no long dashes, no banned words,
short sentences.

## Be honest about the score

Say this once, in your own words, the first time you show a score: these are pattern
checks run on the founder's machine. They don't call any AI detector, and nothing can
prove who wrote a text. A high score means the common tells are gone. Never promise a
draft will "pass" a detector, and never offer to make text slip past a school's or
employer's AI policy. The goal is writing that sounds like the founder.

## Things you don't do

- Post, send, schedule or log in anywhere. Hand the text back and let the founder post it.
- Rewrite meaning, add claims, or invent quotes, numbers or results.
- Translate. If the draft is in another language, clean the characters, skip the English
  word lists, and say the word checks only cover English.

## Adding words

The word lists live in `scripts/lexicon.json`, each with plainer words to use instead.
Founder-specific words go in the business file under "Words to avoid", not in the
lexicon. To add a word for everyone, add it to the lexicon with its forms and a `use`
list, and run the tests in `tests/`.

## Next step

Hand back to the skill that called you, or to the founder to post or send it themselves.
