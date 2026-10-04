#!/usr/bin/env bash
#
# Installs a working game-streaming stack on macOS using Homebrew.
#
# Tiers:
#   core         OBS, chat client, Discord - enough to go live tonight
#   recommended  core, plus audio loopback and clip trimming (default)
#   all          everything, including the heavyweight video editor
#
# Usage:
#   ./setup-macos.sh                 # recommended tier
#   ./setup-macos.sh --tier all
#   ./setup-macos.sh --dry-run
#
# No `set -u` on purpose: macOS still ships bash 3.2, where expanding an empty
# array under `set -u` is an "unbound variable" error rather than an empty
# string, and the summary below does exactly that when nothing was installed.
set -o pipefail

TIER="recommended"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIER="${2:-recommended}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

case "$TIER" in
  core) MAX_RANK=0 ;;
  recommended) MAX_RANK=1 ;;
  all) MAX_RANK=2 ;;
  *) echo "--tier must be core, recommended or all" >&2; exit 1 ;;
esac

# cask|rank|name|why
PACKAGES=(
  "obs|0|OBS Studio|The broadcast software itself. Free, and what most of Twitch runs on."
  "chatterino|0|Chatterino|A real chat client. A browser tab will not survive a busy stream."
  "discord|0|Discord|Where your community lives between streams."
  "blackhole-2ch|1|BlackHole|macOS cannot capture its own audio without a loopback driver. This is that driver."
  "losslesscut|1|LosslessCut|Trims clips out of VODs without re-encoding. This is how you get shorts."
  "elgato-stream-deck|1|Elgato Stream Deck|Only needed if you own the hardware."
  "audacity|1|Audacity|Free audio editor. Use it once to hear what your mic really sounds like."
  "davinci-resolve|2|DaVinci Resolve|Full editor for highlight reels. Large - skip until you need it."
)

head() {
  printf '\n  %s\n  %s\n' "$1" "------------------------------------------------------------"
}

head "Game streaming setup for macOS"

if ! command -v brew >/dev/null 2>&1; then
  echo "  Homebrew is not installed."
  echo "  Install it from https://brew.sh, open a new terminal, then run this again."
  exit 1
fi

echo "  Tier: $TIER"
[ "$DRY_RUN" -eq 1 ] && echo "  DRY RUN - nothing will be installed."

installed=(); skipped=(); failed=()

for entry in "${PACKAGES[@]}"; do
  IFS='|' read -r cask rank name why <<< "$entry"
  [ "$rank" -gt "$MAX_RANK" ] && continue

  printf '\n  %s\n    %s\n' "$name" "$why"

  if brew list --cask "$cask" >/dev/null 2>&1; then
    echo "    already installed - skipping"
    skipped+=("$name")
    continue
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "    would install (brew install --cask $cask)"
    continue
  fi

  echo "    installing..."
  if brew install --cask "$cask"; then
    installed+=("$name")
  else
    echo "    install failed"
    failed+=("$name")
  fi
done

# Always keep a local recording. It is higher quality than the platform VOD and
# it is yours even if the upload dies mid-stream.
REC_DIR="$HOME/Movies/Stream Recordings"
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

head "Two things macOS makes you do by hand"
cat <<'NOTES'
  1. Permissions. Launch OBS once, then go to System Settings -> Privacy &
     Security and grant it Screen Recording, Camera and Microphone. OBS will
     capture a black screen until you do, and it will not tell you why.

  2. Desktop audio. macOS has no built-in way to capture system sound. If you
     installed BlackHole, open Audio MIDI Setup, create a Multi-Output Device
     containing both your speakers and BlackHole 2ch, set that as your system
     output, then add an Audio Input Capture in OBS pointed at BlackHole 2ch.
     Without this your stream has your voice but no game audio.
NOTES

head "Next"
echo "  1. Launch OBS once so it creates its config folder, then quit it."
echo "  2. Generate your OBS profile and scenes:"
echo "       python3 ./make_obs_kit.py --upload-mbps <your upload> --install"
echo "  3. Work through ../docs/06-go-live-checklist.md before your first stream."
echo ""
