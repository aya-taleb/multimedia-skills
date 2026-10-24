# humanize: job spec

Written before looking at any other humanizer, so the skill is built from the job and not
from someone else's structure.

## The job

A founder has a draft they are about to post, send or publish. It may come from Claude,
from another tool, or from their own hands. They want it to read like a person wrote it,
in their own voice, and they want to know what still gives it away before anyone sees it.

## Who runs it

- The founder, directly: "clean this up", "does this sound like AI?", "score my post".
- Other skills, before they show a draft: LinkedIn and Instagram posts, DMs, cold emails,
  landing page copy, investor updates. They hand the draft over and get back a clean
  version plus a score.

## What a good result looks like

1. The mechanical tells are gone without changing meaning: hidden characters, long
   dashes, curly quotes, the ellipsis character, stray spaces.
2. Stock words and phrases are named, with a plainer word offered for each. The founder's
   own "words to avoid" from their business file count too.
3. Structural tells are named in plain words: same-length sentences, long sentences, the
   "it's not X, it's Y" move, stock openers and sign-offs, stacked one-word sentences.
4. A rewrite that fixes those tells and keeps every fact, number, name and link the
   draft had. Nothing new gets added.
5. A score from 0 to 100, with each check explained so a non-technical founder knows why
   points were lost and what to do.
6. Honesty about limits: these are local pattern checks. They do not call any detector
   service and cannot prove who wrote something.

## Rules it keeps

- Never add facts, numbers, quotes, names or results the draft did not have.
- Never post or send. Hand the text back.
- Keep the founder's voice and tone words from founder-context.
- Leave code, links and @handles alone.
- Leave text in other scripts (Arabic, Hebrew) intact, including direction marks.

## Tools

- `scripts/detect.py`: scores a draft and explains each check.
- `scripts/humanize.py`: cleans the mechanical tells, optionally swaps a few always-safe
  words, writes the clean copy and prints before and after scores.
- `scripts/lexicon.json`: the word and phrase lists, with suggested replacements. Easy for
  contributors to add to.

Standard library only. No network.
