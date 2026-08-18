# 1. Will your setup handle it?

Short answer: almost certainly yes, at some quality level. The generator picks
that level for you. This page is for understanding what you're trading away, and
what is actually worth buying.

## The only hard requirement

**Upload speed.** Not download — upload. Run any speed test and look at the
smaller number.

| Upload | What you can realistically stream |
| --- | --- |
| Under 3 Mbps | 480p30. Watchable, not pretty. Fix the connection before anything else. |
| 3–6 Mbps | 720p30 comfortably, 720p60 for slower games |
| 6–10 Mbps | 720p60 or 1080p30 |
| 10 Mbps+ | 1080p60, the practical ceiling on Twitch anyway |

Two things matter more than the raw number:

- **Wired beats wireless, every time.** An ethernet cable is the cheapest
  upgrade in streaming. Wi-Fi bandwidth fluctuates, and a stream that drops to
  half speed for four seconds is a stream that buffers for everyone watching.
- **Never use your whole upload.** The generator spends 65% of it on purpose.
  The rest absorbs a cloud backup waking up or someone else in the house
  starting a video call.

## CPU and GPU

You have three ways to encode video, in order of preference:

1. **NVIDIA GPU (GTX 1050 or newer)** — NVENC. A dedicated chip on the card does
   the encoding, so it costs you almost no game performance. If you have this,
   you are done thinking about it.
2. **AMD GPU / Intel iGPU / Apple silicon** — AMF, QuickSync, VideoToolbox. Same
   idea, historically slightly worse quality per bit. Still the right choice.
3. **CPU (x264)** — the best-looking option at low bitrates and the most
   expensive. Only worth it if you have cores to spare (8+) or no hardware
   encoder at all.

`make_obs_kit.py` detects which of these you have and picks for you. Override it
with `--encoder` if you want to experiment.

**Single PC is fine.** The two-PC streaming setup is a thing people buy after
they have an audience, not before.

## RAM and storage

- **16 GB RAM** is the comfortable number. 8 GB works if you close Chrome.
- **Storage**: local recordings run roughly 1.5–3 GB per hour at these bitrates.
  Record locally anyway (the setup scripts make the folder) — it is higher
  quality than the platform's VOD, and it's the source of every clip you'll cut.

## What's actually worth buying, in order

1. **A microphone, ~$60–100.** People will forgive a bad-looking stream. They
   close the tab on a bad-sounding one, instantly and without thinking about it.
   A USB condenser or dynamic mic is a bigger upgrade than anything else here.
2. **An ethernet cable, ~$10.** See above.
3. **A cheap desk light, ~$25.** A webcam in a dark room looks worse than no
   webcam. A lamp pointed at your face from behind the monitor fixes it.
4. **A webcam, ~$50+.** Genuinely optional. Plenty of large channels are audio
   only for months. Your phone can also work as a webcam.
5. **Everything else** — capture cards, Stream Decks, second monitors, green
   screens. All nice. None of them are why anyone watches.

## Before you spend anything

Do one full test stream with what you own right now. Set the channel to
unlisted/private if the platform allows it, play for 30 minutes, then watch the
recording back. You will learn more from those 30 minutes about what your setup
needs than from any amount of shopping.
