#!/usr/bin/env bash
# Root-level setup: the keystroke injector.
#
# GNOME's Mutter does not implement the Wayland virtual-keyboard protocol, so
# pasting goes through /dev/uinput via ydotool. Granting your user access to
# /dev/uinput means any process running as you can synthesise keystrokes
# system-wide. That is inherent to this class of tool; review before running.
set -euo pipefail

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
echo "Done. Log out and back in for the group change to apply, then:"
echo "  systemctl --user enable --now ydotoold"
