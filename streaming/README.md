# Streamer Starter Kit

Everything you need to go from "I have a PC and a game" to "I am live", without
spending money or a weekend reading forum posts.

This folder is self-contained. It has nothing to do with the trading dashboard
in the rest of this repo — it just lives here.

## What's in the box

| Folder | What it is |
| --- | --- |
| `setup/` | One-command installers for Windows, macOS and Linux, plus a generator that writes your OBS settings for you |
| `overlays/` | Four working overlays — starting soon, be-right-back, outro, and an on-screen name bar |
| `docs/` | The short version of everything else: hardware, accounts, audio, settings, the pre-flight checklist, and what to do for the first month |

## Quickstart

**1. Install the software.** Open a terminal in `streaming/setup/` and run the
one for your machine:

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File setup-windows.ps1
```

```bash
# macOS
./setup-macos.sh

# Linux
./setup-linux.sh
```

Add `--dry-run` (or `-DryRun`) first if you want to see what it would install
before it does anything. Add `--tier core` for the bare minimum.

**2. Launch OBS once**, then close it. This is not optional — OBS creates its
config folder on first run and the next step writes into that folder.

**3. Find your upload speed.** Any speed test will do. You want the *upload*
number, in Mbps. It is usually much smaller than the download number, and it is
the single thing that decides how good your stream can look.

**4. Generate your settings:**

```bash
python3 make_obs_kit.py --upload-mbps 20 --handle yourname --install
```

That looks at your GPU and your bandwidth, picks a resolution / framerate /
bitrate / encoder combination that will actually hold, and writes a profile and
a five-scene collection straight into OBS. Drop `--install` to inspect the files
first — they land in `./obs-kit`.

Useful flags: `--service twitch|youtube|kick`, `--canvas 2560x1440`,
`--max-fps 30`, `--encoder x264`, `--name "My Kit"`.

**5. In OBS**, pick your new profile (Profile menu) and scene collection (Scene
Collection menu). Then Settings → Stream, and paste your stream key.

**6. Work through [`docs/06-go-live-checklist.md`](docs/06-go-live-checklist.md).**
It takes ten minutes and catches the things that ruin a first stream — silent
audio, a black capture, your desktop notifications on screen.

## The scenes you get

1. **Starting Soon** — countdown card. Go live on this five minutes early so
   people can arrive before anything happens.
2. **Gameplay** — game capture, webcam in the corner, name bar along the bottom.
3. **Just Chatting** — full-screen webcam for the start, the end, and breaks.
4. **BRB** — with a timer that counts how long you've been gone.
5. **Ending** — outro card. Leave it up for two minutes; that window is where
   follows and raids happen.

Every overlay is a normal HTML file you can open in a browser and edit. They take
options in the URL, so you can restyle them without touching code — see
[`docs/04-obs-settings.md`](docs/04-obs-settings.md).

## What this kit does not do

- **It cannot install anything on a machine it isn't running on.** Run the setup
  scripts on your actual gaming PC.
- **It never writes your stream key anywhere.** You paste that into OBS yourself,
  once. A key that lives in a file is a key that ends up in a screenshot.
- **It doesn't buy you a following.** The software is the easy part; `docs/07`
  is the honest version of the hard part.

## Requirements

- Python 3.8 or newer, to run the generator
- OBS Studio 28 or newer, which every installer here gives you
- Windows 10+, macOS 12+, or a Linux desktop with Flatpak
