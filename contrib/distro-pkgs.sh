# Package-name mapping across distros. Sourced by install.sh.
#
# The same binary lives in differently-named packages on each distro, so a
# "missing pw-record" message has to be translated before it is actionable.
#
# Only the Fedora path is tested on real hardware; the others are from each
# distro's package index. Corrections welcome.

detect_pm() {
  for pm in dnf apt-get pacman zypper; do
    command -v $pm >/dev/null 2>&1 && { echo $pm; return; }
  done
  echo ""
}

# pkg_for <command> <package-manager> -> package name providing that command
pkg_for() {
  local cmd="$1" pm="$2"
  case "$cmd:$pm" in
    pw-record:dnf)        echo pipewire-utils ;;
    pw-record:apt-get)    echo pipewire-bin ;;
    pw-record:pacman)     echo pipewire ;;
    pw-record:zypper)     echo pipewire-tools ;;
    pw-record:*)          echo pipewire ;;
    notify-send:apt-get)  echo libnotify-bin ;;
    notify-send:zypper)   echo libnotify-tools ;;
    notify-send:*)        echo libnotify ;;
    wl-copy:*|wl-paste:*) echo wl-clipboard ;;
    ydotool:*)            echo ydotool ;;
    *)                    echo "$cmd" ;;
  esac
}

# install_hint <package-manager> <pkg>... -> the command line to run
install_hint() {
  local pm="$1"; shift
  local pkgs; pkgs=$(printf '%s\n' "$@" | sort -u | tr '\n' ' ')
  pkgs="${pkgs% }"
  case "$pm" in
    dnf)     echo "  sudo dnf install $pkgs" ;;
    apt-get) echo "  sudo apt install $pkgs" ;;
    pacman)  echo "  sudo pacman -S $pkgs" ;;
    zypper)  echo "  sudo zypper install $pkgs" ;;
    *)       echo "  install with your package manager: $pkgs" ;;
  esac
}
