#!/usr/bin/env python3
"""Generate a ready-to-use OBS Studio profile and scene collection.

Run this on the machine you stream from. It looks at your hardware and your
upload speed, picks a resolution/bitrate/encoder that will actually hold up,
and writes the two things OBS cares about:

  * a *profile*          - output/video/audio settings + which service you stream to
  * a *scene collection* - the five scenes you need on night one, wired to the
                           overlays in ../overlays

Nothing is installed and no stream key is ever written to disk. By default the
files land in ./obs-kit for you to inspect; pass --install to drop them into
OBS's real config directory.

Examples
--------
    python3 make_obs_kit.py --upload-mbps 20
    python3 make_obs_kit.py --upload-mbps 20 --service twitch --install
    python3 make_obs_kit.py --upload-mbps 8 --max-fps 30 --encoder x264
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlencode

# --------------------------------------------------------------------------
# Quality tiers, best first. A tier is only offered if its bitrate fits inside
# the bandwidth we think you actually have.
# --------------------------------------------------------------------------
TIERS = [
    # width, height, fps, video kbps, label
    (1920, 1080, 60, 6000, "1080p60"),
    (1920, 1080, 30, 4500, "1080p30"),
    (1664, 936, 60, 5000, "936p60"),
    (1280, 720, 60, 4500, "720p60"),
    (1280, 720, 30, 3000, "720p30"),
    (854, 480, 30, 1500, "480p30"),
]

# Ceilings that the platform itself imposes on a brand-new account.
SERVICE_MAX_KBPS = {"twitch": 6000, "youtube": 9000, "kick": 8000}

SERVICE_NAMES = {"twitch": "Twitch", "youtube": "YouTube - RTMPS", "kick": "Kick"}

# OBS source type ids differ per platform. Keyed by our own generic names.
SOURCE_IDS = {
    "windows": {
        "game": "game_capture",
        "screen": "monitor_capture",
        "camera": "dshow_input",
        "mic": "wasapi_input_capture",
        "desktop_audio": "wasapi_output_capture",
    },
    "macos": {
        "game": "screen_capture",
        "screen": "screen_capture",
        "camera": "av_capture_input_v2",
        "mic": "coreaudio_input_capture",
        "desktop_audio": None,  # macOS needs a loopback driver; see docs/05
    },
    "linux": {
        "game": "xcomposite_input",
        "screen": "xshm_input",
        "camera": "v4l2_input",
        "mic": "pulse_input_capture",
        "desktop_audio": "pulse_output_capture",
    },
}

BROWSER_ID = "browser_source"


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------
def detect_platform() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def _run(cmd: list) -> str:
    """Run a probe command, returning '' if it is missing or fails."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout or ""


def detect_gpu(target: str) -> str:
    """Return a lowercase blob of GPU names we can pattern-match against."""
    if _run(["nvidia-smi", "-L"]).strip():
        return "nvidia"
    if target == "windows":
        blob = _run(["powershell", "-NoProfile", "-Command",
                     "(Get-CimInstance Win32_VideoController).Name"])
        return blob.lower()
    if target == "macos":
        return _run(["system_profiler", "SPDisplaysDataType"]).lower()
    blob = _run(["lspci"])
    if not blob:
        blob = _run(["sh", "-c", "lshw -C display 2>/dev/null"])
    return blob.lower()


def pick_encoder(target: str, gpu_blob: str) -> tuple:
    """Choose an OBS *simple output* encoder id, plus a one-line reason."""
    if "nvidia" in gpu_blob or "geforce" in gpu_blob or "rtx" in gpu_blob:
        return "nvenc", "NVIDIA GPU found - NVENC encodes on dedicated silicon"
    if target == "macos":
        return "apple_h264", "Apple silicon/Intel Mac - VideoToolbox is the hardware path"
    if "amd" in gpu_blob or "radeon" in gpu_blob:
        return "amd", "AMD GPU found - AMF encodes on the GPU"
    if "intel" in gpu_blob and target == "windows":
        return "qsv", "Intel graphics found - QuickSync encodes on the iGPU"
    return "x264", "No hardware encoder detected - falling back to CPU (x264)"


def detect_upload_mbps() -> float:
    """Best-effort upload probe. Returns 0.0 when we cannot measure it."""
    for exe, args in (("speedtest", ["--format=json"]), ("speedtest-cli", ["--json"])):
        if not shutil.which(exe):
            continue
        blob = _run([exe] + args)
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        # Ookla CLI reports bytes/sec, speedtest-cli reports bits/sec.
        if "upload" in data and isinstance(data["upload"], dict):
            return round(data["upload"].get("bandwidth", 0) * 8 / 1_000_000, 1)
        if isinstance(data.get("upload"), (int, float)):
            return round(data["upload"] / 1_000_000, 1)
    return 0.0


# --------------------------------------------------------------------------
# Settings maths
# --------------------------------------------------------------------------
def choose_tier(upload_mbps: float, max_fps: int, service: str) -> tuple:
    """Pick the best tier that fits the bandwidth, with headroom to spare.

    Streaming at your full upload speed is how you get dropped frames the
    moment something else on the network wakes up, so we only spend 65% of it
    and also leave room for the 160 kbps audio track.

    Whatever headroom is left over after picking a tier gets spent on bitrate,
    up to 1.5x the tier's baseline and never past what the platform accepts -
    a 1080p60 stream at 9000 kbps looks visibly better than one at 6000, but
    only YouTube will take it.
    """
    budget_kbps = upload_mbps * 1000 * 0.65
    ceiling = SERVICE_MAX_KBPS.get(service, 6000)

    chosen = None
    for width, height, fps, kbps, label in TIERS:
        if fps > max_fps:
            continue
        if kbps + 160 <= budget_kbps and kbps <= ceiling:
            chosen = (width, height, fps, kbps, label)
            break

    if chosen is None:
        # Nothing fits. Take the smallest tier and squeeze into what is left.
        width, height, fps, kbps, label = TIERS[-1]
        fitted = max(800, int(min(kbps, budget_kbps - 160)))
        return width, height, min(fps, max_fps), fitted, label

    width, height, fps, kbps, label = chosen
    spend = min(ceiling, int(kbps * 1.5), int(budget_kbps - 160))
    return width, height, fps, max(kbps, spend), label


# --------------------------------------------------------------------------
# Scene collection building blocks
# --------------------------------------------------------------------------
def _new_uuid() -> str:
    return str(uuid.uuid4())


def make_filter(name: str, filter_id: str, settings: dict) -> dict:
    return {
        "prev_ver": 503382016,
        "name": name,
        "uuid": _new_uuid(),
        "id": filter_id,
        "versioned_id": filter_id,
        "settings": settings,
        "mixers": 0,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {},
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
    }


def make_source(name: str, source_id: str, settings: dict,
                filters: list = None, muted: bool = False,
                audio: bool = False) -> dict:
    """Build one OBS source. *audio* enables all six audio tracks on it."""
    return {
        "prev_ver": 503382016,
        "name": name,
        "uuid": _new_uuid(),
        "id": source_id,
        "versioned_id": source_id,
        "settings": settings,
        "mixers": 255 if audio else 0,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": muted,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {},
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
        "filters": filters or [],
    }


def make_item(source: dict, item_id: int, pos=(0.0, 0.0), bounds=None,
              scale=(1.0, 1.0), visible: bool = True) -> dict:
    """Place a source inside a scene.

    When *bounds* is given the source is fitted into that box, which is what
    you want for captures and overlays - it keeps things framed no matter what
    resolution the underlying capture turns out to be.
    """
    item = {
        "name": source["name"],
        "source_uuid": source["uuid"],
        "visible": visible,
        "locked": False,
        "rot": 0.0,
        "pos": {"x": float(pos[0]), "y": float(pos[1])},
        "scale": {"x": float(scale[0]), "y": float(scale[1])},
        "align": 5,
        "bounds_type": 2 if bounds else 0,
        "bounds_align": 0,
        "bounds": {"x": float(bounds[0]), "y": float(bounds[1])} if bounds else {"x": 0.0, "y": 0.0},
        "crop_left": 0,
        "crop_top": 0,
        "crop_right": 0,
        "crop_bottom": 0,
        "id": item_id,
        "group_item_backup": False,
        "scale_filter": "disable",
        "blend_method": "default",
        "blend_type": "normal",
        "show_transition": {"duration": 0},
        "hide_transition": {"duration": 0},
        "private_settings": {},
    }
    return item


def make_scene(name: str, items: list) -> dict:
    scene = make_source(name, "scene", {
        "id_counter": len(items),
        "custom_size": False,
        "items": items,
    })
    scene["mixers"] = 0
    return scene


def browser_settings(html_path: Path, width: int, height: int,
                     params: dict = None) -> dict:
    """Point a browser source at one of the overlays.

    The overlays read their text and colours from the URL query string, but
    OBS's "local file" mode has nowhere to put one. So as soon as there is
    anything to pass we switch the source to URL mode with a file:// URL.
    local_file is filled in either way - OBS ignores it in URL mode, and it
    keeps the path visible to anyone reading the generated JSON.
    """
    params = {k: v for k, v in (params or {}).items() if v}
    settings = {
        "is_local_file": not params,
        "local_file": str(html_path),
        "width": width,
        "height": height,
        "reroute_audio": False,
        "restart_when_active": True,
        "shutdown": True,
        "css": "",
    }
    if params:
        settings["url"] = "%s?%s" % (html_path.as_uri(), urlencode(params))
    return settings


def build_scene_collection(name: str, target: str, overlays: Path,
                           width: int, height: int, handle: str) -> dict:
    """Assemble the five-scene starter collection."""
    ids = SOURCE_IDS[target]
    sources = []

    def add(src):
        sources.append(src)
        return src

    # --- shared sources, created once and reused across scenes -------------
    mic = add(make_source("Mic", ids["mic"], {"device_id": "default"}, filters=[
        make_filter("Noise Suppression", "noise_suppress_filter_v2", {"method": "rnnoise"}),
        make_filter("Noise Gate", "noise_gate_filter",
                    {"open_threshold": -35.0, "close_threshold": -45.0}),
        make_filter("Compressor", "compressor_filter",
                    {"ratio": 4.0, "threshold": -18.0, "output_gain": 3.0}),
        make_filter("Limiter", "limiter_filter", {"threshold": -3.0}),
    ], audio=True))

    desktop = None
    if ids["desktop_audio"]:
        desktop = add(make_source("Game Audio", ids["desktop_audio"],
                                  {"device_id": "default"}, audio=True))

    camera = add(make_source("Webcam", ids["camera"], {}))
    gameplay = add(make_source("Game Capture", ids["game"], {}))

    branding = {"handle": handle}
    starting = add(make_source("Starting Soon Overlay", BROWSER_ID, browser_settings(
        overlays / "starting-soon.html", width, height, branding)))
    brb = add(make_source("BRB Overlay", BROWSER_ID, browser_settings(
        overlays / "brb.html", width, height, branding)))
    ending = add(make_source("Ending Overlay", BROWSER_ID, browser_settings(
        overlays / "ending.html", width, height, branding)))
    lower = add(make_source("Lower Third", BROWSER_ID, browser_settings(
        overlays / "lower-third.html", width, 240, branding)))

    # Camera box in the bottom-right corner, sized to a quarter of the canvas.
    cam_w, cam_h = width // 4, height // 4
    cam_pos = (width - cam_w - 40, height - cam_h - 40)

    audio_items = [mic] + ([desktop] if desktop else [])

    def audio_layer(start_id: int) -> list:
        return [make_item(src, start_id + i) for i, src in enumerate(audio_items)]

    scenes = []

    scenes.append(make_scene("1 - Starting Soon", [
        make_item(starting, 1, bounds=(width, height)),
    ] + audio_layer(2)))

    scenes.append(make_scene("2 - Gameplay", [
        make_item(gameplay, 1, bounds=(width, height)),
        make_item(camera, 2, pos=cam_pos, bounds=(cam_w, cam_h)),
        make_item(lower, 3, pos=(0, height - 240), bounds=(width, 240)),
    ] + audio_layer(4)))

    scenes.append(make_scene("3 - Just Chatting", [
        make_item(camera, 1, bounds=(width, height)),
        make_item(lower, 2, pos=(0, height - 240), bounds=(width, 240)),
    ] + audio_layer(3)))

    scenes.append(make_scene("4 - BRB", [
        make_item(brb, 1, bounds=(width, height)),
    ] + audio_layer(2)))

    scenes.append(make_scene("5 - Ending", [
        make_item(ending, 1, bounds=(width, height)),
    ] + audio_layer(2)))

    all_sources = sources + scenes
    first = scenes[0]["name"]

    return {
        "current_scene": first,
        "current_program_scene": first,
        "scene_order": [{"name": s["name"]} for s in scenes],
        "name": name,
        "sources": all_sources,
        "groups": [],
        "quick_transitions": [
            {"name": "Cut", "duration": 300, "hotkeys": [], "id": 1, "fade_to_black": False},
            {"name": "Fade", "duration": 300, "hotkeys": [], "id": 2, "fade_to_black": False},
        ],
        "transitions": [],
        "current_transition": "Fade",
        "transition_duration": 300,
        "preview_locked": False,
        "scaling_enabled": False,
        "scaling_level": 0,
        "scaling_off_x": 0.0,
        "scaling_off_y": 0.0,
        "virtual-camera": {"type2": 3},
        "modules": {},
        "resolution": {"x": width, "y": height},
        "version": 2,
    }


# --------------------------------------------------------------------------
# Profile building
# --------------------------------------------------------------------------
def build_basic_ini(name: str, base_w: int, base_h: int,
                    out_w: int, out_h: int, fps: int,
                    vbitrate: int, encoder: str, rec_dir: Path) -> str:
    lines = [
        "[General]",
        "Name=%s" % name,
        "",
        "[Output]",
        "Mode=Simple",
        "",
        "[SimpleOutput]",
        "FilePath=%s" % rec_dir,
        "RecFormat2=mkv",
        "VBitrate=%d" % vbitrate,
        "ABitrate=160",
        "UseAdvanced=false",
        "Preset=veryfast",
        "RecQuality=Stream",
        "StreamEncoder=%s" % encoder,
        "RecEncoder=%s" % encoder,
        "StreamAudioEncoder=aac",
        "RecAudioEncoder=aac",
        "RecRB=true",
        "RecRBTime=20",
        "",
        "[Video]",
        "BaseCX=%d" % base_w,
        "BaseCY=%d" % base_h,
        "OutputCX=%d" % out_w,
        "OutputCY=%d" % out_h,
        "FPSType=0",
        "FPSCommon=%d" % fps,
        "ScaleType=bicubic",
        "ColorFormat=NV12",
        "ColorSpace=709",
        "ColorRange=Partial",
        "",
        "[Audio]",
        "SampleRate=48000",
        "ChannelSetup=Stereo",
        "",
    ]
    return "\n".join(lines)


def build_service_json(service: str) -> dict:
    """Point OBS at the right ingest. The stream key is deliberately absent."""
    return {
        "type": "rtmp_common",
        "settings": {
            "service": SERVICE_NAMES.get(service, "Twitch"),
            "server": "auto",
            "bwtest": False,
        },
    }


# --------------------------------------------------------------------------
# Install paths
# --------------------------------------------------------------------------
def obs_config_dir(target: str) -> Path:
    home = Path.home()
    if target == "windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "obs-studio"
    if target == "macos":
        return home / "Library" / "Application Support" / "obs-studio"
    flatpak = home / ".var" / "app" / "com.obsproject.Studio" / "config" / "obs-studio"
    if flatpak.exists():
        return flatpak
    return home / ".config" / "obs-studio"


def slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "Starter_Kit"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--upload-mbps", type=float, default=None,
                   help="Your measured upload speed. Omit to auto-probe, or 0 to assume 10.")
    p.add_argument("--service", choices=sorted(SERVICE_NAMES), default="twitch")
    p.add_argument("--max-fps", type=int, choices=[30, 60], default=60)
    p.add_argument("--encoder", choices=["auto", "nvenc", "amd", "qsv", "apple_h264", "x264"],
                   default="auto")
    p.add_argument("--canvas", default="1920x1080",
                   help="Your monitor/game resolution, e.g. 2560x1440.")
    p.add_argument("--name", default="Starter Kit", help="Name for the profile and collection.")
    p.add_argument("--handle", default="", help="Your channel name, printed on the overlays.")
    p.add_argument("--target-platform", choices=["auto", "windows", "macos", "linux"],
                   default="auto")
    p.add_argument("--out", default="obs-kit", help="Where to write the generated files.")
    p.add_argument("--install", action="store_true",
                   help="Copy the result into OBS's config directory (backs up any clash).")
    return p.parse_args(argv)


def resolve_canvas(text: str) -> tuple:
    match = re.match(r"^\s*(\d{3,5})\s*[xX*]\s*(\d{3,5})\s*$", text)
    if not match:
        raise SystemExit("--canvas must look like 1920x1080, got %r" % text)
    return int(match.group(1)), int(match.group(2))


def build_kit(args) -> dict:
    """Do the whole job and return a summary dict (kept separate for tests)."""
    target = detect_platform() if args.target_platform == "auto" else args.target_platform
    base_w, base_h = resolve_canvas(args.canvas)

    upload = args.upload_mbps
    probed = False
    if upload is None:
        upload = detect_upload_mbps()
        probed = upload > 0
    if not upload:
        upload = 10.0

    gpu_blob = detect_gpu(target) if args.encoder == "auto" else ""
    if args.encoder == "auto":
        encoder, encoder_reason = pick_encoder(target, gpu_blob)
    else:
        encoder, encoder_reason = args.encoder, "chosen with --encoder"

    out_w, out_h, fps, vbitrate, label = choose_tier(upload, args.max_fps, args.service)

    root = Path(args.out).expanduser().resolve()
    overlays = (Path(__file__).resolve().parent.parent / "overlays").resolve()
    recordings = Path.home() / "Videos" / "Stream Recordings"

    slug = slugify(args.name)
    profile_dir = root / "basic" / "profiles" / slug
    scenes_dir = root / "basic" / "scenes"
    profile_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir.mkdir(parents=True, exist_ok=True)

    (profile_dir / "basic.ini").write_text(
        build_basic_ini(args.name, base_w, base_h, out_w, out_h, fps,
                        vbitrate, encoder, recordings), encoding="utf-8")
    (profile_dir / "service.json").write_text(
        json.dumps(build_service_json(args.service), indent=4), encoding="utf-8")

    collection = build_scene_collection(args.name, target, overlays, base_w, base_h, args.handle)
    scene_file = scenes_dir / ("%s.json" % slug)
    scene_file.write_text(json.dumps(collection, indent=4), encoding="utf-8")

    summary = {
        "target": target,
        "canvas": "%dx%d" % (base_w, base_h),
        "output": "%dx%d" % (out_w, out_h),
        "fps": fps,
        "label": label,
        "bitrate": vbitrate,
        "encoder": encoder,
        "encoder_reason": encoder_reason,
        "upload": upload,
        "upload_probed": probed,
        "service": args.service,
        "profile_dir": profile_dir,
        "scene_file": scene_file,
        "root": root,
        "overlays": overlays,
    }

    if args.install:
        summary["installed_to"] = install(root, target, slug)

    return summary


def install(root: Path, target: str, slug: str) -> Path:
    """Copy the generated profile and scene collection into OBS's config dir."""
    dest = obs_config_dir(target)
    if not dest.exists():
        raise SystemExit(
            "Could not find OBS's config directory at %s.\n"
            "Install and launch OBS once so it creates that folder, then re-run "
            "with --install." % dest)

    profile_src = root / "basic" / "profiles" / slug
    profile_dst = dest / "basic" / "profiles" / slug
    if profile_dst.exists():
        backup = profile_dst.with_name(slug + ".backup")
        shutil.rmtree(backup, ignore_errors=True)
        shutil.move(str(profile_dst), str(backup))
    shutil.copytree(profile_src, profile_dst)

    scene_src = root / "basic" / "scenes" / ("%s.json" % slug)
    scene_dst = dest / "basic" / "scenes" / ("%s.json" % slug)
    scene_dst.parent.mkdir(parents=True, exist_ok=True)
    if scene_dst.exists():
        shutil.copy2(scene_dst, scene_dst.with_suffix(".json.backup"))
    shutil.copy2(scene_src, scene_dst)
    return dest


def report(summary: dict) -> None:
    speed = "%.1f Mbps" % summary["upload"]
    if summary["upload_probed"]:
        speed += " (measured just now)"
    elif summary["upload"] == 10.0:
        speed += " (assumed - re-run with --upload-mbps for a real number)"

    print("")
    print("  OBS starter kit")
    print("  " + "-" * 52)
    print("  Platform        %s" % summary["target"])
    print("  Upload          %s" % speed)
    print("  Streaming to    %s" % summary["service"])
    print("  Canvas          %s  ->  output %s @ %d fps (%s)"
          % (summary["canvas"], summary["output"], summary["fps"], summary["label"]))
    print("  Video bitrate   %d kbps" % summary["bitrate"])
    print("  Encoder         %s  (%s)" % (summary["encoder"], summary["encoder_reason"]))
    print("")
    if summary["upload"] < 5:
        print("  Heads up: under ~5 Mbps up, a stable 720p30 is the honest ceiling.")
        print("  Wired ethernet buys you more than any setting in this file.")
        print("")
    print("  Profile         %s" % summary["profile_dir"])
    print("  Scenes          %s" % summary["scene_file"])
    print("  Overlays        %s" % summary["overlays"])
    print("")
    if "installed_to" in summary:
        print("  Installed into  %s" % summary["installed_to"])
        print("")
        print("  In OBS: Profile menu -> %s, Scene Collection menu -> %s."
              % (summary["profile_dir"].name, summary["scene_file"].stem))
        print("  Then Settings -> Stream and paste your stream key.")
    else:
        print("  Nothing was installed. Re-run with --install to copy these into OBS,")
        print("  or import them by hand (see ../docs/04-obs-settings.md).")
    print("")


def main(argv=None) -> int:
    args = parse_args(argv)
    report(build_kit(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
