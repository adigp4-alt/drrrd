# 3. The software, and why each piece is there

The setup scripts in `../setup/` install all of this. This page explains what
you actually got, so you know what to open and what to ignore.

## Core — you need these to go live

**OBS Studio** — the broadcast software. It composites your game, camera and
overlays into one video and sends it to Twitch/YouTube/Kick. Free, open source,
and what the large majority of streamers use.

> Why not Streamlabs Desktop? It's a friendlier fork of OBS with built-in
> alerts, and it's a reasonable choice. It's also heavier, and it pushes you
> toward its own paid ecosystem. Plain OBS plus a browser source for alerts does
> the same job with less running on the machine that is also playing your game.

**Chatterino** — a desktop chat client. Reading chat in a browser tab means
alt-tabbing out of a fullscreen game. Chatterino sits on a second monitor, or in
a corner, and is dramatically lighter than a browser.

**Discord** — where a community lives between streams. Also how you meet other
streamers, which is genuinely the fastest way to grow.

## Recommended — install these before stream three

**Voicemeeter Banana** (Windows) / **BlackHole** (macOS) — audio routing. Lets
you put game audio, voice chat and music on separate faders so you can duck one
without the others, and keep music out of your VOD. See
[`05-audio-routing.md`](05-audio-routing.md). On Linux, PipeWire already does
this and you don't need extra software.

**LosslessCut** — trims clips out of your local recordings in seconds without
re-encoding. This is how you turn a three-hour stream into shorts, which is how
people who have never heard of you find you.

**Audacity** — a free audio editor. You need it exactly once: record thirty
seconds of yourself talking, listen back, and fix whatever is wrong (too quiet,
room echo, keyboard clatter) before an audience hears it.

**Elgato Stream Deck software** — only if you own the hardware.

## Already built into OBS — don't install these separately

- **Virtual camera** — put your OBS output into Discord or Zoom. Just a button.
- **Replay buffer** — keeps the last N seconds in memory so you can save a clip
  after something happens. Enabled in the generated profile, set to 20 seconds.
  Bind it to a hotkey in Settings → Hotkeys ("Save Replay").
- **WebSocket server** — for Stream Deck and automation tools. Tools →
  WebSocket Server Settings.
- **Studio Mode** — set up a scene before cutting to it.

## Worth adding once you have a routine

**Alerts** (follows, subs, donations) — StreamElements or Streamlabs, both free
and browser-based. You create the alert on their site, copy a browser-source URL,
paste it into OBS as a new browser source. Nothing to install.

> Treat that URL like a password too — anyone with it can trigger your alerts.

**A chat bot** — Nightbot, StreamElements or Fossabot. Handles `!commands`,
timed messages ("follow for more") and basic spam filtering. Browser-based,
five minutes to set up. Don't bother until you have chatters to serve.

**Streamer.bot** (Windows) — heavy automation, chat-triggered scene changes,
sound effects on subs. Excellent, and completely unnecessary in month one.

## What to skip

- Paid overlay packs. You have four working ones in `../overlays/`.
- Anything promising followers, viewers or "growth". At best it's wasted money;
  at worst view-botting gets your channel banned.
- A capture card, unless you're streaming from a console.
- A second PC. Genuinely not needed until you're doing this for a living.

## If an installer skipped something

The scripts check each package against the catalogue and report anything it
couldn't find rather than failing the whole run — package IDs do get renamed
upstream. For anything listed as missing, search for it by hand:

```powershell
winget search "chatterino"     # Windows
```
```bash
brew search chatterino          # macOS
flatpak search chatterino       # Linux
```

None of the recommended tier blocks you from going live. If only OBS installed,
you can still stream tonight.
