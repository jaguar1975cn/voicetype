"""休眠守护脚本 contrib/voicetype-sleep 与两个 systemd 单元的接线。

脚本本身跑在挂起路径上,无法在本机反复触发真实挂起验证,所以用桩
(runuser/id/systemctl)钉住调度不变量:phase 与 action 的对应关系、
只操作已启用单元、非数字目录跳过。单元文件里 `Before=nvidia-suspend`
是整个方案的核心前提(普通 system-sleep 钩子跑在显存快照之后,太晚),
一旦有人改丢,保护静默失效,故在此钉死。
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "contrib" / "voicetype-sleep"
PRE = REPO / "contrib" / "voicetype-pre-sleep.service"
POST = REPO / "contrib" / "voicetype-post-resume.service"


@pytest.fixture
def rig(tmp_path):
    calls = tmp_path / "calls"
    calls.write_text("")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # 1000 已启用单元,1001 未启用,snapfuse 不是数字 uid。
    (bindir / "id").write_text(
        '#!/bin/sh\ncase "$2" in 1000) echo alice ;; 1001) echo bob ;; '
        '*) exit 1 ;; esac\n')
    (bindir / "runuser").write_text(
        '#!/bin/sh\nshift 3\nexec "$@"\n')
    (bindir / "systemctl").write_text(
        '#!/bin/sh\n'
        'printf "uid=${XDG_RUNTIME_DIR##*/} $*\\n" >> "$CALLS"\n'
        'case "$*" in\n'
        '  *is-enabled*) [ "${XDG_RUNTIME_DIR##*/}" = 1000 ] && exit 0 || exit 1 ;;\n'
        '  *stop*|*start*) [ -n "$FAIL" ] && exit 1 ;;\n'
        'esac\nexit 0\n')
    for stub in (bindir / "id", bindir / "runuser", bindir / "systemctl"):
        stub.chmod(0o755)
    run = tmp_path / "run"
    for d in ("1000", "1001", "snapfuse"):
        (run / d).mkdir(parents=True)
    env = dict(os.environ,
               PATH=f"{bindir}:/bin:/usr/bin",
               CALLS=str(calls),
               VOICETYPE_RUN_DIR=str(run))
    return env, calls


def run(env, *args):
    return subprocess.run(
        ["sh", str(SCRIPT), *args], env=env,
        capture_output=True, text=True,
    )


def logged(calls):
    return calls.read_text().splitlines()


class TestUsage:
    def test_missing_action_is_a_usage_error(self, rig):
        env, calls = rig
        r = run(env)
        assert r.returncode == 2
        assert "usage" in r.stderr
        assert logged(calls) == []

    def test_bogus_action_does_nothing(self, rig):
        env, calls = rig
        assert run(env, "restart").returncode == 2
        assert logged(calls) == []


class TestDispatch:
    def test_pre_sleep_stops_blocking(self, rig):
        env, calls = rig
        r = run(env, "stop")
        assert r.returncode == 0
        assert "uid=1000 --user stop voicetype.service" in logged(calls)
        # 必须阻塞等待停止完成(CUDA 上下文要赶在显存快照前消失)。
        assert not any("--user stop" in ln and "--no-block" in ln for ln in logged(calls))

    def test_post_resume_starts_without_blocking(self, rig):
        env, calls = rig
        r = run(env, "start")
        assert r.returncode == 0
        assert "uid=1000 --user start --no-block voicetype.service" in logged(calls)
        assert not any("stop" in ln for ln in logged(calls))

    def test_disabled_unit_is_not_resurrected(self, rig):
        env, calls = rig
        run(env, "start")
        assert not any(ln.startswith("uid=1001") and "start" in ln for ln in logged(calls))

    def test_non_numeric_runtime_dir_is_skipped(self, rig):
        env, calls = rig
        run(env, "stop")
        assert not any("uid=snapfuse" in ln for ln in logged(calls))

    def test_controller_failure_propagates(self, rig):
        env, calls = rig
        env["FAIL"] = "1"
        assert run(env, "stop").returncode == 1


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
