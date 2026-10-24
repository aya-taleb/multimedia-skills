# Reading the numbers

Plain notes for turning an export into fixes. Every rule here compares a video with the
channel's own median, because outside benchmarks vary by niche, format and audience size.

## The four steps

1. **Shown.** Impressions count times YouTube showed the thumbnail in certain places (not
   every place counts, per YouTube Help). Low impressions across all videos usually means the
   topics are not ones people look for or browse, or uploads are too far apart for YouTube to
   learn who the channel is for.
2. **Clicked.** Impressions click rate. Low on some videos and not others usually points at
   those titles and thumbnails: vague promise, too many words on the thumbnail, a topic
   framed for the founder instead of the viewer. Click rate tends to fall as impressions grow,
   so a video that reached many new people can show a lower rate for a good reason.
3. **Watched.** Average percentage viewed and average view duration. Low share watched on a
   video with a good click rate often means the title promised something the opening did not
   deliver fast enough. Check the first 30 seconds.
4. **Acted.** Subscribers per 1,000 views, and anything the business tracks (link clicks,
   sign-ups). If people watch but do not act, the video may lack one clear next step.

## How we flag a video

`channel_stats.py` flags a video when:

- click rate is under 70% of the channel's median, or
- share watched is under 70% of the median, or
- impressions are under 40% of the median.

These cut-offs are our choice, picked to catch clear outliers in small channels. They are not
YouTube rules. Say so if the user asks.

A stand-out is a video with at least 2 times the median views.

## Small samples

Under 5 videos, or videos with a few hundred views each, the medians move a lot with one new
upload. Say the findings are hints, and suggest re-running after 4 more videos.

## What a fix looks like

Each fix names: the number, the change, and one action this week. The shape, with the
numbers left for the real export:

- "Videos {{a}} and {{b}} (product updates) have a {{x}}% click rate against a {{median}}%
  median. Retitle them around the problem they solve, not the feature name. This week: rewrite
  these two titles with youtube-seo."
- "Video {{c}} keeps {{y}}% of viewers on average and is about {{topic}}, 2 times or more the
  median views. Make two more on that problem. This week: plan them with youtube-plan."
