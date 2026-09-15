#!/usr/bin/env bash
# Root-level setup: the keystroke injector.
#
# GNOME's Mutter does not implement the Wayland virtual-keyboard protocol, so
# pasting goes through /dev/uinput via ydotool. Granting your user access to
# /dev/uinput means any process running as you can synthesise keystrokes
# system-wide. That is inherent to this class of tool; review before running.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo ./install-root.sh"; exit 1; }
USER_NAME="${SUDO_USER:?run via sudo, not as root directly}"

if command -v ydotool >/dev/null && command -v ydotoold >/dev/null; then
  echo "ydotool already installed, skipping"
elif command -v dnf >/dev/null;     then dnf install -y ydotool
elif command -v apt-get >/dev/null; then apt-get install -y ydotool
elif command -v pacman >/dev/null;  then pacman -S --needed --noconfirm ydotool
elif command -v zypper >/dev/null;  then zypper install -y ydotool
else
  echo "Install 'ydotool' with your package manager, then re-run."
  exit 1
fi

if ! command -v ydotoold >/dev/null; then
  echo
  echo "ydotool installed but ydotoold is missing. Some older distro"
  echo "packages ship only the client. Build it from source:"
  echo "  https://github.com/ReimuNotMoe/ydotool"
  exit 1
fi

# static_node is required when uinput is built into the kernel rather than
# loaded as a module -- without it the rule never fires.
cat > /etc/udev/rules.d/60-uinput-ydotool.rules <<'RULE'
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
RULE

udevadm control --reload-rules
udevadm trigger --name-match=uinput
modprobe uinput 2>/dev/null || true
# Most distros own /dev/uinput with the "input" group; create it if this one
# does not have it, since the udev rule above references it either way.
getent group input >/dev/null || groupadd -r input
usermod -aG input "$USER_NAME"

echo
ls -l /dev/uinput
echo

# ------------------------------------------------------------- sleep safety
# A CUDA context held across a suspend whose GPU state-save fails comes back
# attached to dead video memory: the daemon then blocks in an uninterruptible
# driver ioctl, cannot be killed, and pins its VRAM until reboot. These units
# stop it before the NVIDIA driver snapshots VRAM -- Before=nvidia-suspend,
# since stock system-sleep hooks fire after that save -- and start it again
# after resume. See README, "Suspend / resume".
echo
echo "Installing sleep guards"
LIBEXEC=/usr/libexec
[ -d "$LIBEXEC" ] || LIBEXEC=/usr/lib
install -d "$LIBEXEC/voicetype"
install -m 0755 "$REPO/contrib/voicetype-sleep" "$LIBEXEC/voicetype/voicetype-sleep"
for u in voicetype-pre-sleep voicetype-post-resume; do
  sed "s|@LIBEXEC@|$LIBEXEC/voicetype|g" "$REPO/contrib/$u.service" > "/etc/systemd/system/$u.service"
done
systemctl daemon-reload
systemctl enable voicetype-pre-sleep.service voicetype-post-resume.service

# The driver can only survive suspend if it can spill VRAM to disk; better to
# say so now than to have the save fail silently and wedge every GPU process
# on resume.
if command -v nvidia-smi >/dev/null 2>&1; then
  spill="$(awk -F'"' '/TemporaryFilePath/ {print $2}' /proc/driver/nvidia/params 2>/dev/null)"
  [ -n "$spill" ] && [ -d "$spill" ] || spill=/var/tmp
  vram_kb=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk '{s+=$1} END {print s+0}')
  free_kb=$(df --output=avail -k "$spill" 2>/dev/null | tail -1 | tr -d ' ')
  if [ -n "$free_kb" ] && [ "$free_kb" -lt "$vram_kb" ]; then
    echo
    echo "WARNING: NVIDIA state-save needs a spill target bigger than total VRAM."
    echo "  NVreg_TemporaryFilePath ($spill): $((free_kb / 1024 / 1024))G free"
    echo "  GPUs combined:                    $((vram_kb / 1024 / 1024))G"
    echo "With NVreg_PreserveVideoMemoryAllocations=1 the save will fail at"
    echo "suspend and GPU processes wedge on resume. Free up disk there (or"
    echo "point NVreg_TemporaryFilePath at a bigger volume) and provide"
    echo "disk-backed swap of at least the same size (zram does not count)."
  fi
fi
echo
echo "Done. Log out and back in for the group change to apply, then:"
echo "  systemctl --user enable --now ydotoold"
