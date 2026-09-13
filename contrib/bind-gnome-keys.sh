#!/usr/bin/env bash
# Bind Super+Z / Shift+Super+Z to voicetype, without disturbing shortcuts
# that are already bound.
set -euo pipefail
BIN="${1:-$HOME/.local/bin}"
SCHEMA=org.gnome.settings-daemon.plugins.media-keys
PATH_BASE=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings

existing=$(gsettings get $SCHEMA custom-keybindings)
[ "$existing" = "@as []" ] && existing="[]"

bind_one() {
  local name="$1" cmd="$2" key="$3"
  # Reuse the slot if this exact binding is already installed.
  local list slot i=0
  list=$(gsettings get $SCHEMA custom-keybindings)
  while echo "$list" | grep -q "custom$i/"; do
    local n
    n=$(gsettings get $SCHEMA.custom-keybinding:$PATH_BASE/custom$i/ name 2>/dev/null || echo "")
    if [ "$n" = "'$name'" ]; then slot=$i; break; fi
    i=$((i+1))
  done
  slot="${slot-$i}"

  gsettings set $SCHEMA.custom-keybinding:$PATH_BASE/custom$slot/ name "$name"
  gsettings set $SCHEMA.custom-keybinding:$PATH_BASE/custom$slot/ command "$cmd"
  gsettings set $SCHEMA.custom-keybinding:$PATH_BASE/custom$slot/ binding "$key"

  list=$(gsettings get $SCHEMA custom-keybindings)
  if ! echo "$list" | grep -q "custom$slot/"; then
    if [ "$list" = "@as []" ] || [ "$list" = "[]" ]; then
      gsettings set $SCHEMA custom-keybindings "['$PATH_BASE/custom$slot/']"
    else
      gsettings set $SCHEMA custom-keybindings \
        "$(echo "$list" | sed "s|]$|, '$PATH_BASE/custom$slot/']|")"
    fi
  fi
  unset slot
}

bind_one "Voice typing (toggle)"          "$BIN/voicetype-toggle" "<Super>z"
bind_one "Voice typing (terminal paste)"  "$BIN/voicetype-toggle --paste-key ctrl+shift+v" "<Shift><Super>z"

echo "Bound Super+Z and Shift+Super+Z"
echo "Note: <Super>space is GNOME's input-source switcher and is left alone."
