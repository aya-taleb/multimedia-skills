# multimedia-skills

Make the images, videos and YouTube content for your business, with your own files and a spend cap on anything paid.

## What do you want to do?

| I want to... | run this |
| --- | --- |
| Make or edit an image with AI (costs money, you approve every run) | /generate-images |
| Make a short AI video clip, with sound or dialogue (costs money, you approve every run) | /generate-video |
| Pick the right AI model and see what it costs, without running anything | /find-model |
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
It searches Replicate live, prices the options and recommends one, for free.
Then run `/generate-video` or `/generate-images` to make it. You see the cost and say yes before anything runs.
No Replicate account yet? Start with `/transcribe` or `/launch-video`, which run free on your own machine.

## Good to know

- **The generate skills cost money.** `generate-images` and `generate-video` run paid models on Replicate with your own token. Each run shows its price first and waits for your yes. There is a $2 spend cap per session, kept in a small ledger file, and only you can raise it. Video is the priciest: a single clip can cost more than a hundred images.
- Your token stays in your shell (`REPLICATE_API_TOKEN`). The skills never put it in a file, a chat reply or a command they show you.
- Outputs are saved to `media/` the moment they finish, because Replicate deletes them after an hour.
- Your own files only. Nothing here downloads from YouTube, Instagram, TikTok or any other platform, and nothing posts for you. You upload and post.
- Nothing made up: no invented stats, reviews, quotes or endorsements in images, videos, cards or copy. Missing numbers become `{{your number}}`.

## Credits

Made by Aya Taleb (github.com/aya-taleb). `generate-images`, `generate-video` and `find-model` are built on Replicate's
[skills](https://github.com/replicate/skills) (Apache 2.0). `launch-video` builds with HeyGen's
[HyperFrames](https://github.com/heygen-com/hyperframes) (Apache 2.0) when you have it. `transcribe` uses
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT). `talking-head-cards` follows the approach of
[vtake-skills](https://github.com/notedit/vtake-skills) by leeoxiang. Thanks to Jake Schincariol for the ideas behind
several skills here. See CREDITS.md. MIT.
