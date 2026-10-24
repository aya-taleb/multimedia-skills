# multimedia-skills

Make the images, videos and YouTube content for your business, with your own files and a spend cap on anything paid.

## What do you want to do?

| I want to... | run this |
| --- | --- |
| Make or edit an image with AI on Replicate, Cloudflare or OpenAI (costs money, you approve every run) | /generate-images |
| Make a short AI video clip, with sound or dialogue, on Replicate, Runway or Google (costs money, you approve every run) | /generate-video |
| Pick the right AI model across the accounts I have and see what it costs, without running anything | /find-model |
| Use the API account I already have instead of opening a new one | /generate-images or /generate-video (they check which keys you have) |
| Get a transcript or captions (SRT, VTT) from my own recording | /transcribe |
| Put text cards over my talking-head or podcast clip as I say each point | /talking-head-cards |
| Turn my product page or brief into a 30 to 60 second launch video | /launch-video |
| Find the Shorts hiding in my long video | /youtube-shorts |
| Write a video's title, description and chapters | /youtube-seo |
| Plan the next few weeks of YouTube videos I can actually make | /youtube-plan |
| Reply to my YouTube comments in my voice | /youtube-comment |
| Find out why my channel is stuck, from my Studio export | /youtube-audit |

## Install

/plugin marketplace add aya-taleb/multimedia-skills
/plugin install multimedia-skills@multimedia-skills

Some skills here hand off to tools from Jake Schincariol's [master-skills](https://github.com/Jakeschincariol/master-skills)
(`edit`) and [chatgpt-youtube-agent-skill](https://github.com/Jakeschincariol/chatgpt-youtube-agent-skill)
(`yt-script`, `yt-package`, `yt-retention`, `yt-edit`, `yt-chapters`). They are not copied here. Get them,
pinned to a fixed commit, with:

python3 scripts/get_linked.py

Optional, not installed by the script: Jake's `virality` and `yt-viral` find what's working in your niche.
They suggest yt-dlp to read YouTube listings, which YouTube's terms don't allow, so this repo leaves them
out. If you want them, get them from his repos yourself and decide for your own setup.

## Start here

Run `/find-model` with what you want to make, for example "a 5 second vertical clip of a coffee pour".
It checks which provider keys you have, prices the options and recommends one, for free.
Then run `/generate-video` or `/generate-images` to make it. You see the cost and say yes before anything runs.
No AI account yet? Start with `/transcribe` or `/launch-video`, which run free on your own machine.

## Good to know

- **The generate skills cost money.** `generate-images` and `generate-video` run paid models with your own account. Each run shows its price first and waits for your yes. There is one $2 spend cap per session for all providers together, kept in a small ledger file, and only you can raise it. Video is the priciest: a single clip can cost more than a hundred images.
- **Bring the account you have.** Images: Replicate, Cloudflare Workers AI (FLUX) or OpenAI (GPT Image). Video: Replicate, Runway (Gen-4, Veo 3.1) or Google's Gemini API (Omni Flash). Prices for providers with no price API come from a dated table with a source link for each price, and the tool warns when a date is old.
- Your keys stay in your shell (`REPLICATE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, `OPENAI_API_KEY`, `RUNWAYML_API_SECRET`, `GEMINI_API_KEY`). The skills never put them in a file, a chat reply or a command they show you.
- Outputs are saved to `media/` the moment they finish, because provider links expire (Replicate's after an hour).
- Your own files only. Nothing here downloads from YouTube, Instagram, TikTok or any other platform, and nothing posts for you. You upload and post.
- Nothing made up: no invented stats, reviews, quotes or endorsements in images, videos, cards or copy. Missing numbers become `{{your number}}`.

## Credits

Made by Aya Taleb (github.com/aya-taleb). `generate-images`, `generate-video` and `find-model` are built on Replicate's
[skills](https://github.com/replicate/skills) (Apache 2.0), and call Cloudflare, OpenAI, Runway and Google APIs as their public docs describe.
This repo is not made by or affiliated with any of these companies. `launch-video` builds with HeyGen's
[HyperFrames](https://github.com/heygen-com/hyperframes) (Apache 2.0) when you have it. `transcribe` uses
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT). `talking-head-cards` follows the approach of
[vtake-skills](https://github.com/notedit/vtake-skills) by leeoxiang. Thanks to Jake Schincariol for the ideas behind
several skills here. See CREDITS.md. MIT.
