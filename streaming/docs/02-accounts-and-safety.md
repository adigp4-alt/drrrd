# 2. Accounts, and not getting burned

The account setup takes twenty minutes. The safety part of this page is the bit
people skip and then regret, so it comes first.

## Protect yourself before you go live

**Turn on two-factor authentication.** Twitch *requires* it before it will let
you stream. Do it on the streaming account, the email behind it, and Discord.
A streaming account with a following is a target, and account recovery is slow.

**Know what your screen is showing.** Before you ever hit Start Streaming:

- Turn on Focus Assist / Do Not Disturb. Desktop notifications preview message
  content on screen — this is the classic way people leak things.
- Never capture your whole desktop when you can capture a single game window.
  The generated Gameplay scene uses game/window capture for exactly this reason.
- Watch out for anything that renders your real name: launcher profiles, email
  clients, browser autofill, the Windows login screen, delivery notifications.

**Don't show your location.** Not the view out your window, not your gym, not
your local anything. This is the single most common way viewers work out where a
streamer lives, and it is easier to avoid up front than to undo later.

**Pick a handle you don't mind keeping.** Same name on every platform if you can
get it. Changing it later costs you every link anyone ever shared.

**Use a separate email** for streaming. It keeps business mail out of your
personal inbox and means a leak of one doesn't expose the other.

## Which platform

| | Twitch | YouTube Live | Kick |
| --- | --- | --- | --- |
| Discovery for new streamers | Hard, but people are there to browse live | Easiest — the algorithm actually recommends you | Small, less competition |
| VODs and clips | Fine, VODs expire on the free tier | Best in the business, streams become permanent videos | Fine |
| Monetisation threshold | Slow and low at first | Slow, requires channel thresholds | Most generous split |
| Community norms | Live-first, chat-heavy | Video-first audience | Live-first |

**Realistic recommendation:** start on Twitch if you want live chat culture and
plan to stream on a schedule; start on YouTube if you also want to post the
highlights as videos, because that's where the recommendation engine will find
you. Don't multi-stream on day one — it splits an already small chat in half and
some platforms restrict it in their terms anyway.

## Getting your stream key

1. Create the account and enable 2FA.
2. Find the key: Twitch → Creator Dashboard → Settings → Stream. YouTube → Go
   Live → Stream. Kick → Creator Dashboard → Stream Settings.
3. Paste it into OBS: Settings → Stream → Service, then Stream Key.

**The key is a password.** Anyone who has it can broadcast as you. It never
appears in this repo's generated files by design. If you ever show it on stream
even for a second, reset it — every platform has a reset button next to it.

## Set the channel up before your first stream

Fifteen minutes here makes you look like you've done this before:

- **Profile picture and banner.** Anything consistent beats the default egg.
- **A one-line bio** saying what you play and when you stream.
- **Panels** (Twitch) or channel description: who you are, your schedule, your
  Discord/socials.
- **A schedule you can actually keep.** Two fixed days a week beats "whenever I
  feel like it" — it is the difference between viewers who return and viewers
  who happened to be passing.
- **Enable clips**, and let VODs be saved. Clips are how other people find you.

## Moderation, before you need it

You will get your first troll sooner than your first ten viewers.

- Turn on the platform's built-in chat filter (Twitch: AutoMod, level 2+).
- Require verified email to chat. It removes most drive-by abuse instantly.
- Set followers-only chat if you get raided by anyone unpleasant.
- Learn the `/ban` and `/timeout` commands *now*, not while it is happening.
- Give a trusted friend moderator status before you need one.

None of this makes you unfriendly. It means you get to think about your game
instead of your chat.

## Music, and the thing that gets channels struck

Do not play copyrighted music on stream. Not Spotify, not YouTube, not the
"chill beats" playlist. Game soundtracks are usually fine (check the publisher's
streaming policy — most large publishers publish one), but a licensed pop track
in the background can mute your entire VOD or strike your channel.

Use a royalty-free source made for this: Pretzel, StreamBeats, Epidemic Sound,
or the game's own soundtrack. Free, and it never costs you a VOD.
