# 4. OBS settings, and customising the overlays

`../setup/make_obs_kit.py` writes all of this for you. Read this page if you
want to understand what it chose, change it, or set things up by hand.

## What the generator writes

Two things, in OBS's own config directory:

```
obs-studio/basic/profiles/Starter_Kit/basic.ini      video, audio, output settings
obs-studio/basic/profiles/Starter_Kit/service.json   which platform, no key
obs-studio/basic/scenes/Starter_Kit.json             the five scenes
```

Both are ordinary files. If a generated setting is wrong for you, change it in
OBS's own UI — OBS writes back to the same files.

To switch to them after generating: **Profile** menu → *Starter Kit*, and
**Scene Collection** menu → *Starter Kit*. If either menu doesn't list them,
OBS was running when you generated; restart it.

## Importing by hand instead

If you'd rather not use `--install`:

1. Run the generator without it. The files land in `./obs-kit/`.
2. In OBS: **Scene Collection → Import**, point it at
   `obs-kit/basic/scenes/Starter_Kit.json`.
3. Profiles have no import button — copy the folder
   `obs-kit/basic/profiles/Starter_Kit/` into OBS's `basic/profiles/`
   directory yourself. OBS's config lives at:
   - Windows `%APPDATA%\obs-studio`
   - macOS `~/Library/Application Support/obs-studio`
   - Linux `~/.config/obs-studio`, or
     `~/.var/app/com.obsproject.Studio/config/obs-studio` for the Flatpak

## The settings that matter, explained

**Base (canvas) vs Output (scaled) resolution.** Canvas is the size you compose
in — set it to your monitor's resolution so captures aren't letterboxed. Output
is what actually gets sent. Scaling 1440p down to 1080p is normal and good.

**Bitrate.** How many bits per second of video. More is sharper, especially in
fast motion, until you exceed what your connection or the platform allows and
everything falls apart. The generator spends 65% of your upload and caps at what
the platform accepts: Twitch realistically 6000 kbps, YouTube up to 9000.

**Keyframe interval: 2 seconds.** Every platform requires this. The generated
profile uses OBS's Simple output mode, which applies the right value for the
service automatically — you only need to set this by hand if you later switch
the profile to Advanced output mode.

**Encoder preset.** For x264, `veryfast` is the standard streaming preset — it
is what fits inside a CPU that is also running a game. Slower presets look
better and will cost you frames in the game.

**60 fps vs 30 fps.** 60 is worth it for shooters and platformers. For slower
games, 30 fps at a higher bitrate looks *better* than 60 fps at a stretched one,
because each frame gets twice the bits. Pass `--max-fps 30` to force it.

**Downscale filter: Bicubic.** Sharper than Bilinear, cheaper than Lanczos.

## Customising the overlays

The four files in `../overlays/` are plain HTML. Open any of them in a browser
to preview. Two ways to change them:

**Options in the URL** (no code). In OBS, double-click the browser source,
untick *Local file*, and put a `file://` URL with a query string in the URL box:

```
file:///path/to/overlays/starting-soon.html?minutes=15&handle=yourname&accent=%23ff5f6d
```

| Overlay | Options |
| --- | --- |
| `starting-soon.html` | `minutes`, `title`, `subtitle`, `handle`, `accent`, `accent2` |
| `brb.html` | `title`, `subtitle`, `handle`, `timer=off`, `accent`, `accent2` |
| `ending.html` | `title`, `subtitle`, `handle`, `next`, `accent`, `accent2` |
| `lower-third.html` | `handle`, `game`, `messages` (pipe-separated), `interval`, `accent`, `accent2` |

Colours must be URL-encoded — `#ff5f6d` becomes `%23ff5f6d`.

Example lower third with your own rotating lines:

```
file:///path/to/overlays/lower-third.html?handle=yourname&game=Hades&messages=!discord|!socials|Follow%20for%20more
```

**Editing the files** — the CSS is at the top of each file, uncommented and
plain. The two colours are CSS variables named `--accent` and `--accent2` in the
`:root` block; change those two lines and the whole overlay re-themes.

After any change, right-click the browser source in OBS → **Refresh**.

## Things that catch people out

**The overlay shows a black box instead of being transparent.** Only
`lower-third.html` is meant to be transparent; the other three are full-screen
cards. If the lower third is showing black, your browser source has a background
colour set in its custom CSS box — clear it.

**The overlay is blank (Flatpak Linux).** The sandbox can't read the file. Run:
`flatpak override --user --filesystem=home com.obsproject.Studio`

**The countdown doesn't restart.** The browser source is set to refresh when the
scene becomes active, so it restarts each time you switch to it. If you disabled
that, right-click → Refresh.

**Game capture shows black.** Windows: run OBS as administrator, or switch the
source to Window Capture. Linux/Proton: use the Vulkan capture plugin and add
`OBS_VKCAPTURE=1 %command%` to the game's Steam launch options. macOS: grant OBS
Screen Recording permission in System Settings.

**Dropped frames while streaming.** That's the network, not your PC. Lower the
bitrate (re-run the generator with a smaller `--upload-mbps`), and get on
ethernet. Check Stats in OBS's View menu — "Dropped frames (network)" is the
number that matters.

**Encoding overload / laggy game.** That's your PC. Switch to a hardware
encoder (`--encoder nvenc`), drop to 30 fps, or lower the output resolution.
