"""休眠守护脚本 contrib/voicetype-sleep 与两个 systemd 单元的接线。

脚本跑在挂起路径上,无法在本机反复触发真实挂起验证,所以用桩
(runuser/id/systemctl + 文件状态机)钉住调度不变量:phase 与 action
的对应关系、enabled/disabled 两种单元的停止与恢复语义(手动的 disabled
单元只有被钩子停过才恢复)、marker 生命周期、幽灵单元完全不碰。
单元文件里 `Before=nvidia-suspend` 是整个方案的核心前提(普通
system-sleep 钩子跑在显存快照之后,太晚),一旦有人改丢,保护静默
失效,故在此钉死。
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "contrib" / "voicetype-sleep"
PRE = REPO / "contrib" / "voicetype-pre-sleep.service"
POST = REPO / "contrib" / "voicetype-post-resume.service"

UNITS = "voicetype.service qwen.service ghost.service"
MARKER = "voicetype-sleep.was-active"


@pytest.fixture
def rig(tmp_path):
    calls = tmp_path / "calls"
    calls.write_text("")
    state = tmp_path / "state"
    state.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # uid 1000:真实用户;uid 1001:装了但没启用也没跑的用户;
    # snapfuse:非数字目录。
    (bindir / "id").write_text(
        '#!/bin/sh\ncase "$2" in 1000) echo alice ;; 1001) echo bob ;; '
        '*) exit 1 ;; esac\n')
    (bindir / "runuser").write_text('#!/bin/sh\nshift 3\nexec "$@"\n')
    # systemctl 桩:enabled/active 状态存在文件里,stop/start 迁移状态,
    # 于是 stop 与 start 两次脚本调用之间状态连续。
    (bindir / "systemctl").write_text(
        '#!/bin/sh\n'
        'uid=${XDG_RUNTIME_DIR##*/}\n'
        'printf "uid=%s %s\\n" "$uid" "$*" >> "$CALLS"\n'
        'unit=\n'
        'for a in "$@"; do case "$a" in *.service) unit=$a ;; esac; done\n'
        'enabled="$STATE/$uid.enabled"; active="$STATE/$uid.active"\n'
        'case "$*" in\n'
        '  *is-enabled*) grep -qx "$unit" "$enabled" 2>/dev/null && exit 0 || exit 1 ;;\n'
        '  *is-active*)  grep -qx "$unit" "$active" 2>/dev/null && exit 0 || exit 1 ;;\n'
        '  *stop*|*start*) [ -n "$FAIL" ] && exit 1 ;;\n'
        'esac\n'
        'case "$*" in\n'
        '  *stop*) grep -vx "$unit" "$active" > "$active.n" || true; mv "$active.n" "$active" ;;\n'
        '  *start*) echo "$unit" >> "$active" ;;\n'
        'esac\nexit 0\n')
    for stub in (bindir / "id", bindir / "runuser", bindir / "systemctl"):
        stub.chmod(0o755)
    run = tmp_path / "run"
    for d in ("1000", "1001", "snapfuse"):
        (run / d).mkdir(parents=True)
    env = dict(os.environ,
               PATH=f"{bindir}:/bin:/usr/bin",
               CALLS=str(calls),
               STATE=str(state),
               VOICETYPE_RUN_DIR=str(run),
               VOICETYPE_UNITS=UNITS,
               VOICETYPE_UNITS_FILE=str(tmp_path / "absent-units-file"))
    return env, calls, state, run


def seed(state, enabled, active):
    (state / "1000.enabled").write_text("".join(f"{u}\n" for u in enabled))
    (state / "1000.active").write_text("".join(f"{u}\n" for u in active))


def run(env, *args):
    return subprocess.run(
        ["sh", str(SCRIPT), *args], env=env,
        capture_output=True, text=True,
    )


def logged(calls):
    return calls.read_text().splitlines()


def calls_for(calls, unit):
    return [ln for ln in logged(calls) if unit in ln and "is-" not in ln]


class TestUsage:
    def test_missing_action_is_a_usage_error(self, rig):
        env, calls, state, _ = rig
        seed(state, [], [])
        r = run(env)
        assert r.returncode == 2
        assert "usage" in r.stderr
        assert logged(calls) == []

    def test_bogus_action_does_nothing(self, rig):
        env, calls, state, _ = rig
        seed(state, [], [])
        assert run(env, "restart").returncode == 2
        assert logged(calls) == []


class TestStopPhase:
    def test_enabled_unit_stopped_blocking(self, rig):
        env, calls, state, _ = rig
        seed(state, ["voicetype.service"], ["voicetype.service"])
        r = run(env, "stop")
        assert r.returncode == 0
        assert calls_for(calls, "voicetype.service") == [
            "uid=1000 --user stop voicetype.service"]

    def test_disabled_but_running_unit_stopped_and_marked(self, rig):
        env, calls, state, run_ = rig
        seed(state, [], ["qwen.service"])
        assert run(env, "stop").returncode == 0
        assert calls_for(calls, "qwen.service") == [
            "uid=1000 --user stop qwen.service"]
        assert (run_ / "1000" / MARKER).read_text().splitlines() == ["qwen.service"]

    def test_idle_ghost_unit_never_touched(self, rig):
        env, calls, state, run_ = rig
        seed(state, ["voicetype.service"], ["voicetype.service"])
        run(env, "stop")
        assert calls_for(calls, "ghost.service") == []
        # enabled 单元由 start 阶段无条件恢复,不占 marker;没有手动单元
        # 被停时 marker 根本不该存在。
        assert not (run_ / "1000" / MARKER).exists()

    def test_stale_marker_cleared_by_stop_phase(self, rig):
        env, calls, state, run_ = rig
        seed(state, [], [])
        (run_ / "1000" / MARKER).write_text("qwen.service\n")
        run(env, "stop")
        assert not (run_ / "1000" / MARKER).exists()

    def test_controller_failure_propagates(self, rig):
        env, calls, state, _ = rig
        seed(state, ["voicetype.service"], ["voicetype.service"])
        env["FAIL"] = "1"
        assert run(env, "stop").returncode == 1


class TestStartPhase:
    def test_enabled_unit_restarted_without_blocking(self, rig):
        env, calls, state, _ = rig
        seed(state, ["voicetype.service"], [])
        r = run(env, "start")
        assert r.returncode == 0
        assert calls_for(calls, "voicetype.service") == [
            "uid=1000 --user start --no-block voicetype.service"]

    def test_marked_disabled_unit_resurrected(self, rig):
        env, calls, state, run_ = rig
        seed(state, [], ["qwen.service"])
        run(env, "stop")
        calls.write_text("")
        r = run(env, "start")
        assert r.returncode == 0
        assert calls_for(calls, "qwen.service") == [
            "uid=1000 --user start --no-block qwen.service"]
        # marker 消费掉,下一轮挂起重新裁决。
        assert not (run_ / "1000" / MARKER).exists()

    def test_manually_stopped_disabled_unit_stays_stopped(self, rig):
        env, calls, state, _ = rig
        seed(state, [], [])          # 挂起前已被用户手动停掉
        run(env, "stop")
        calls.write_text("")
        run(env, "start")
        assert calls_for(calls, "qwen.service") == []

    def test_idle_unit_never_resurrected(self, rig):
        env, calls, state, _ = rig
        seed(state, [], [])
        run(env, "stop")
        calls.write_text("")
        run(env, "start")
        assert calls_for(calls, "ghost.service") == []

    def test_other_users_untouched(self, rig):
        env, calls, state, run_ = rig
        seed(state, [], ["voicetype.service"])
        run(env, "stop")
        calls.write_text("")
        run(env, "start")
        # 允许探测(is-*),但不允许任何实际 stop/start 动作。
        assert not [ln for ln in logged(calls)
                    if "uid=1001" in ln and "is-" not in ln]
        assert not (run_ / "1001" / MARKER).exists()


class TestUnitOrdering:
    """挂起事务里的相对位置;错了保护就静默失效,没有别的检查能兜住。"""

    def pre_text(self):
        return PRE.read_text()

    def test_pre_sleep_beats_nvidia_save(self):
        # nvidia-suspend.service 在 sleep.target 之前拍显存快照,
        # 普通 /usr/lib/systemd/system-sleep 钩子在其之后才跑。
        before = [ln for ln in self.pre_text().splitlines() if ln.startswith("Before=")]
        assert any("nvidia-suspend.service" in ln for ln in before)
        assert any("sleep.target" in ln for ln in before)

    def test_pre_sleep_is_wanted_by_sleep_target(self):
        assert "WantedBy=sleep.target" in self.pre_text()

    def test_pre_sleep_failure_cannot_block_sleep(self):
        # Wants=(非 Requires) + 有界超时:已卡死的守护进程不能拖住挂起。
        assert "TimeoutStartSec=" in self.pre_text()
        assert "Requires=" not in self.pre_text()

    def test_post_resume_runs_after_the_sleep_itself(self):
        text = POST.read_text()
        for target in ("suspend.target", "hibernate.target",
                       "hybrid-sleep.target", "suspend-then-hibernate.target"):
            after = [ln for ln in text.splitlines() if ln.startswith("After=")]
            wanted = [ln for ln in text.splitlines() if ln.startswith("WantedBy=")]
            assert any(target in ln for ln in after)
            assert any(target in ln for ln in wanted)
