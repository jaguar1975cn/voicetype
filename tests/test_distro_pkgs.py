"""发行版包名映射。

这些分支无法在本机验证(只有一台 Fedora),所以至少把映射本身钉住,
避免改动时悄悄改错另一个发行版的包名。
"""
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "contrib" / "distro-pkgs.sh"

PMS = ["dnf", "apt-get", "pacman", "zypper"]


def sh(func: str, *args: str) -> str:
    r = subprocess.run(
        ["bash", "-c", f'. "{SCRIPT}"; {func} "$@"', "--", *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


class TestPkgFor:
    @pytest.mark.parametrize("pm,expected", [
        ("dnf", "pipewire-utils"),
        ("apt-get", "pipewire-bin"),
        ("pacman", "pipewire"),
        ("zypper", "pipewire-tools"),
    ])
    def test_pw_record_package_differs_per_distro(self, pm, expected):
        assert sh("pkg_for", "pw-record", pm) == expected

    @pytest.mark.parametrize("pm,expected", [
        ("dnf", "libnotify"),
        ("apt-get", "libnotify-bin"),
        ("pacman", "libnotify"),
        ("zypper", "libnotify-tools"),
    ])
    def test_notify_send_package(self, pm, expected):
        assert sh("pkg_for", "notify-send", pm) == expected

    @pytest.mark.parametrize("pm", PMS)
    def test_wl_clipboard_is_uniform(self, pm):
        assert sh("pkg_for", "wl-copy", pm) == "wl-clipboard"
        assert sh("pkg_for", "wl-paste", pm) == "wl-clipboard"

    @pytest.mark.parametrize("pm", PMS)
    def test_every_required_command_maps_to_something(self, pm):
        """安装脚本检查的每个命令都必须有包名,否则提示无法执行。"""
        for cmd in ("pw-record", "wl-copy", "wl-paste", "notify-send", "ydotool"):
            assert sh("pkg_for", cmd, pm), f"{cmd} on {pm} mapped to nothing"

    def test_unknown_pm_still_yields_a_name(self):
        """包管理器识别不出时不能返回空,否则提示里会缺项。"""
        assert sh("pkg_for", "pw-record", "") == "pipewire"


class TestInstallHint:
    @pytest.mark.parametrize("pm,expected", [
        ("dnf", "sudo dnf install wl-clipboard"),
        ("apt-get", "sudo apt install wl-clipboard"),
        ("pacman", "sudo pacman -S wl-clipboard"),
        ("zypper", "sudo zypper install wl-clipboard"),
    ])
    def test_command_line_per_distro(self, pm, expected):
        assert sh("install_hint", pm, "wl-clipboard").strip() == expected

    def test_deduplicates_packages(self):
        """wl-copy 和 wl-paste 都缺失时,wl-clipboard 不该出现两次。"""
        out = sh("install_hint", "dnf", "wl-clipboard", "wl-clipboard", "libnotify")
        assert out.split().count("wl-clipboard") == 1
        assert "libnotify" in out

    def test_unknown_pm_degrades_to_a_readable_message(self):
        out = sh("install_hint", "", "wl-clipboard")
        assert "wl-clipboard" in out
        assert "sudo" not in out

    def test_no_trailing_whitespace_in_command(self):
        assert sh("install_hint", "dnf", "a", "b") == sh("install_hint", "dnf", "a", "b").rstrip()
