#!/usr/bin/env bash
# User-level install for voicetype. Safe to re-run: it will not overwrite an
# existing config or disturb keyboard shortcuts you already have.
#
# Run install-root.sh first (or after) for the parts that need root.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/voicetype"
VENV="$PREFIX/venv"
BIN="$HOME/.local/bin"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/voicetype"
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning: %s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------- checks
. "$REPO/contrib/distro-pkgs.sh"

say "Checking prerequisites"
PM=$(detect_pm)
missing=() missing_pkgs=()
for c in pw-record wl-copy wl-paste notify-send; do
  if ! command -v "$c" >/dev/null; then
    missing+=("$c")
    missing_pkgs+=("$(pkg_for "$c" "$PM")")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing commands: ${missing[*]}"
  echo "Install them with:"
  install_hint "$PM" "${missing_pkgs[@]}"
  exit 1
fi
if ! command -v ydotool >/dev/null; then
  warn "ydotool not installed -- text insertion will fail. Run: sudo ./install-root.sh"
fi
command -v nvidia-smi >/dev/null || warn "no nvidia-smi; this needs an NVIDIA GPU (set device=cpu support is not implemented)"
[ "${XDG_SESSION_TYPE:-}" = "wayland" ] || warn "not a Wayland session; the paste path targets GNOME/Wayland"

# uv fetches its own interpreter, so a system 3.12 is only needed without it.
PY=""
if ! command -v uv >/dev/null; then
  for p in python3.12 python3; do
    if command -v $p >/dev/null && $p -c 'import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)' 2>/dev/null; then
      PY=$p; break
    fi
  done
  if [ -z "$PY" ]; then
    echo "Need Python 3.12 (faster-whisper wheels) or uv."
    case "$(detect_pm)" in
      dnf)     echo "  sudo dnf install python3.12" ;;
      apt-get) echo "  sudo apt install python3.12 python3.12-venv" ;;
      pacman)  echo "  Arch ships only current Python; use uv instead" ;;
      zypper)  echo "  sudo zypper install python312" ;;
    esac
    echo "  uv (any distro): curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
fi

# ---------------------------------------------------------------- venv
say "Creating venv at $VENV"
mkdir -p "$PREFIX" "$BIN" "$CONF" "$UNITS"
if command -v uv >/dev/null; then
  [ -d "$VENV" ] || uv venv --python 3.12 "$VENV"
  VIRTUAL_ENV="$VENV" uv pip install -e "$REPO[dev]"
else
  [ -d "$VENV" ] || "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install -e "$REPO[dev]"
fi

say "Linking commands into $BIN"
for c in voicetype-daemon voicetype-toggle voicetype-record-fixture; do
  ln -sf "$VENV/bin/$c" "$BIN/$c"
done
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN is not on your PATH" ;; esac

# ---------------------------------------------------------------- config
if [ -e "$CONF/config.toml" ]; then
  say "Keeping existing $CONF/config.toml"
else
  say "Writing default config to $CONF/config.toml"
  cp "$REPO/contrib/config.toml.example" "$CONF/config.toml"
  if command -v nvidia-smi >/dev/null; then
    echo
    echo "Available GPUs (set 'gpu' in the config to pin one by UUID):"
    nvidia-smi --query-gpu=index,name,memory.total,uuid --format=csv,noheader | sed 's/^/  /'
  fi
fi

# ---------------------------------------------------------------- services
say "Installing systemd user units"
sed "s|@BIN@|$BIN|g" "$REPO/contrib/voicetype.service.in" > "$UNITS/voicetype.service"
cp "$REPO/contrib/ydotoold.service" "$UNITS/ydotoold.service"
systemctl --user daemon-reload
systemctl --user enable --now ydotoold 2>/dev/null || warn "could not start ydotoold (is ydotool installed?)"
systemctl --user enable --now voicetype

# ---------------------------------------------------------------- hotkeys
if command -v gsettings >/dev/null && [ "${XDG_CURRENT_DESKTOP:-}" = "GNOME" ]; then
  say "Binding GNOME shortcuts"
  "$REPO/contrib/bind-gnome-keys.sh" "$BIN" || warn "shortcut binding failed; bind them by hand in Settings > Keyboard"
else
  warn "not GNOME -- bind a shortcut to 'voicetype-toggle' yourself"
fi

say "Done"
cat <<EOF

  Super+Z         dictate, paste with Ctrl+V
  Shift+Super+Z   dictate, paste with Ctrl+Shift+V (terminals)

Config:  $CONF/config.toml
Logs:    journalctl --user -u voicetype -f

If text does not appear, run install-root.sh and log out and back in.
EOF
