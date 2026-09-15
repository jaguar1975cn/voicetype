"""The watchdog must fire only on a wedged in-flight transcription.

Guards the invariant behind daemon._watchdog: a native CUDA hang cannot be
unwound from Python, so the daemon kills itself (systemd restarts it) once a
request has been in flight past TRANSCRIBE_TIMEOUT. A false positive would
kill healthy long transcriptions; a false negative is the original silent
deadlock.
"""

import time

from voicetype import daemon


def test_idle_daemon_is_not_stuck():
    daemon._busy_since = None
    assert not daemon._stuck(daemon.TRANSCRIBE_TIMEOUT)


def test_fresh_request_is_not_stuck():
    daemon._busy_since = time.monotonic()
    assert not daemon._stuck(daemon.TRANSCRIBE_TIMEOUT)


def test_request_past_deadline_is_stuck():
    daemon._busy_since = time.monotonic() - daemon.TRANSCRIBE_TIMEOUT - 1
    assert daemon._stuck(daemon.TRANSCRIBE_TIMEOUT)
