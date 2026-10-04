# 5. Audio

Audio is the thing viewers actually judge you on, and the thing most likely to
be broken on your first stream. Budget an hour for this page. It only has to
happen once.

## The generated mic chain

The scene collection ships your mic with four filters already on it, in the
order OBS applies them:

1. **Noise Suppression (RNNoise)** — removes fan hum, air conditioning, distant
   traffic. Costs a little CPU, worth every cycle.
2. **Noise Gate** — mutes the mic entirely when you're not talking, so your
   keyboard and your breathing don't sit under the game audio. Opens at -35 dB,
   closes at -45 dB.
3. **Compressor** — makes quiet parts louder and loud parts quieter, so you're
   at a consistent level whether you're muttering or yelling at a boss.
4. **Limiter** — a hard ceiling at -3 dB so a sudden shout doesn't clip.

These are sensible starting values, not a finished mix. Tune them by ear:

- **Gate cutting off the start of your words?** Lower the open threshold
  (-35 → -40).
- **Still hearing your keyboard?** Raise it (-35 → -30).
- **Sounding squashed and lifeless?** Lower the compressor ratio (4:1 → 2.5:1).

Aim for your normal speaking voice to peak in the **-12 to -6 dB** range on the
OBS mixer, with the loudest moments never touching 0.

## Levels, in one rule

**Your voice should be clearly louder than the game.** Game audio around -25 dB,
voice around -10 dB. Almost every new streamer gets this wrong in the same
direction: the game is deafening and they're a whisper underneath it. Watch back
five minutes of your own recording with headphones on and you'll hear it
instantly.

## Windows: separating game, voice chat and music

By default OBS captures one lump of "desktop audio" — everything your PC plays,
mixed together. That's fine to start. It becomes a problem when you want to:

- turn the game down without turning Discord down
- keep Spotify out of your VOD so it doesn't get muted
- have a separate track for music when you edit highlights

**Voicemeeter Banana** solves this. The shape of it:

1. Install it, reboot (it installs virtual audio devices).
2. Set Voicemeeter's **A1** hardware out to your real headphones.
3. Set Windows' default playback device to **Voicemeeter Input**.
4. In each app that lets you choose an output device (Discord, Spotify, the
   game), point it at a *different* Voicemeeter input: game → Voicemeeter Input,
   Discord → Voicemeeter AUX Input.
5. In OBS, add an **Audio Input Capture** per virtual output you want on its own
   fader, and assign each to its own audio track in Advanced Audio Properties.

It is genuinely fiddly and it is also the standard answer. Do it on a day you
are not planning to stream.

**Simpler alternative:** use the game's own volume slider and Windows' Volume
Mixer to balance apps, and capture one desktop audio source. This is completely
fine for your first month.

## macOS: you need a loopback driver

macOS has no built-in way to capture its own audio. Without one, your stream has
your voice and no game sound — a very common and very confusing first-stream
failure.

The setup script installs **BlackHole** (free). To use it:

1. Open **Audio MIDI Setup** (in Utilities).
2. Create a **Multi-Output Device** containing both your real speakers/headphones
   *and* BlackHole 2ch. This lets you hear things while OBS captures them.
3. Set that Multi-Output Device as your system output.
4. In OBS, add an **Audio Input Capture** and select **BlackHole 2ch**.

Also grant OBS microphone permission in System Settings → Privacy & Security, or
your mic source will be silent with no error.

## Linux: PipeWire already does this

Modern distros give you per-application routing for free. Install `pavucontrol`
(or use your desktop's sound settings), start the stream, then in pavucontrol's
**Recording** tab set each OBS input to the specific application you want it to
hear. Nothing else to install.

## Test before every stream

Two ways, in order of reliability:

1. **Record 60 seconds** with the Start Recording button, play a bit of the
   game, talk over it, then listen back with headphones. This catches
   everything.
2. Watch the mixer bars in OBS. If your mic bar doesn't move when you talk, the
   wrong device is selected — the fastest fix is right-clicking the Mic source →
   Properties and picking the device explicitly rather than "Default".

The checklist in [`06-go-live-checklist.md`](06-go-live-checklist.md) has this
as a hard gate for a reason. Streaming for an hour to silence, or with your mic
muted, is a rite of passage you can skip.
