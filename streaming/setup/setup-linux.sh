#!/usr/bin/env bash
#
# Installs a working game-streaming stack on Linux.
#
# Prefers Flatpak, because the Flatpak OBS is current on every distro and the
# packaged one often is not. Falls back to apt/dnf/pacman when Flatpak is
# missing.
#
# Tiers:
#   core         OBS, chat client, Discord - enough to go live tonight
#   recommended  core, plus clip trimming and audio tools (default)
#   all          everything, including the heavyweight video editor
#
# Usage:
#   ./setup-linux.sh
#   ./setup-linux.sh --tier all
#   ./setup-linux.sh --dry-run
#
# See setup-macos.sh: `set -u` and empty arrays do not mix on older bash.
set -o pipefail

TIER="recommended"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIER="${2:-recommended}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

case "$TIER" in
  core) MAX_RANK=0 ;;
  recommended) MAX_RANK=1 ;;
  all) MAX_RANK=2 ;;
  *) echo "--tier must be core, recommended or all" >&2; exit 1 ;;
esac

# flatpak_id|native_pkg|rank|name|why
PACKAGES=(
  "com.obsproject.Studio|obs-studio|0|OBS Studio|The broadcast software itself."
  "com.chatterino.chatterino|chatterino|0|Chatterino|A real chat client, not a browser tab."
  "com.discordapp.Discord|discord|0|Discord|Where your community lives between streams."
  "no.mifi.losslesscut|losslesscut|1|LosslessCut|Trims clips out of VODs without re-encoding."
  "org.audacityteam.Audacity|audacity|1|Audacity|Check what your mic actually sounds like."
  "com.obsproject.Studio.Plugin.OBSVkCapture|obs-vkcapture|1|OBS Vulkan capture|Captures Vulkan/OpenGL games properly, including under Proton."
  "com.blackmagicdesign.resolve|davinci-resolve|2|DaVinci Resolve|Full editor for highlight reels."
)

head() {
  printf '\n  %s\n  %s\n' "$1" "------------------------------------------------------------"
}

detect_native() {
  for mgr in apt-get dnf pacman zypper; do
    if command -v "$mgr" >/dev/null 2>&1; then echo "$mgr"; return; fi
  done
  echo ""
}

NATIVE=$(detect_native)
HAVE_FLATPAK=0
command -v flatpak >/dev/null 2>&1 && HAVE_FLATPAK=1

head "Game streaming setup for Linux"
echo "  Tier: $TIER"
echo "  Flatpak: $([ $HAVE_FLATPAK -eq 1 ] && echo yes || echo no)   Native package manager: ${NATIVE:-none found}"
[ "$DRY_RUN" -eq 1 ] && echo "  DRY RUN - nothing will be installed."

if [ $HAVE_FLATPAK -eq 0 ] && [ -z "$NATIVE" ]; then
  echo "  No flatpak and no recognised package manager. Install OBS from your distro's"
  echo "  store or from https://obsproject.com/download and skip to make_obs_kit.py."
  exit 1
fi

if [ $HAVE_FLATPAK -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  flatpak remote-add --if-not-exists --user \
    flathub https://dl.flathub.org/repo/flathub.flatpakrepo >/dev/null 2>&1 || true
fi

native_install() {
  case "$NATIVE" in
    apt-get) sudo apt-get install -y "$1" ;;
    dnf)     sudo dnf install -y "$1" ;;
    pacman)  sudo pacman -S --noconfirm "$1" ;;
    zypper)  sudo zypper install -y "$1" ;;
    *) return 1 ;;
  esac
}

installed=(); skipped=(); failed=()

for entry in "${PACKAGES[@]}"; do
  IFS='|' read -r fpid native rank name why <<< "$entry"
  [ "$rank" -gt "$MAX_RANK" ] && continue

  printf '\n  %s\n    %s\n' "$name" "$why"

  if [ $HAVE_FLATPAK -eq 1 ] && flatpak info "$fpid" >/dev/null 2>&1; then
    echo "    already installed - skipping"
    skipped+=("$name")
    continue
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    if [ $HAVE_FLATPAK -eq 1 ]; then
      echo "    would install (flatpak install --user flathub $fpid)"
    else
      echo "    would install ($NATIVE $native)"
    fi
    continue
  fi

  ok=1
  if [ $HAVE_FLATPAK -eq 1 ]; then
    flatpak install -y --user flathub "$fpid" || ok=0
  else
    native_install "$native" || ok=0
  fi

  if [ $ok -eq 1 ]; then
    installed+=("$name")
  else
    echo "    install failed - try your distro's software centre for this one"
    failed+=("$name")
  fi
done

REC_DIR="$HOME/Videos/Stream Recordings"
if [ ! -d "$REC_DIR" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\n  Would create %s\n' "$REC_DIR"
  else
    mkdir -p "$REC_DIR"
    printf '\n  Created %s\n' "$REC_DIR"
  fi
fi

head "Summary"
[ ${#installed[@]} -gt 0 ] && echo "  Installed:     ${installed[*]}"
[ ${#skipped[@]}   -gt 0 ] && echo "  Already there: ${skipped[*]}"
[ ${#failed[@]}    -gt 0 ] && echo "  Failed:        ${failed[*]}"

head "Linux specifics worth knowing"
cat <<'NOTES'
  Capture source. On Wayland use "PipeWire Screen Capture"; on X11 use "Screen
  Capture (XSHM)" or "Window Capture (Xcomposite)". The generated scene
  collection defaults to the X11 sources - if you are on Wayland, swap the
  capture source in the Gameplay scene and the rest still works.

  Games under Proton. Plain window capture often shows a black rectangle.
  Install the OBS Vulkan capture plugin (in the recommended tier above) and
  launch the game with:  OBS_VKCAPTURE=1 %command%  in Steam's launch options.

  Flatpak OBS and file access. If a browser-source overlay shows up blank,
  Flatpak is sandboxing the path. Grant it with:
    flatpak override --user --filesystem=home com.obsproject.Studio
NOTES

head "Next"
echo "  1. Launch OBS once so it creates its config folder, then close it."
echo "  2. Generate your OBS profile and scenes:"
echo "       python3 ./make_obs_kit.py --upload-mbps <your upload> --install"
echo "  3. Work through ../docs/06-go-live-checklist.md before your first stream."
echo ""
