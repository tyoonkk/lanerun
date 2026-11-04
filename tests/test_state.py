from __future__ import annotations

import datetime as dt

from lanerun.queue import Paths
from lanerun.state import render_state, write_state
from tests.conftest import put


def test_render_state_summarizes_each_lane(paths: Paths) -> None:
    put(
        paths,
        "gpu",
        [
            {"id": "d1", "cmd": "x", "status": "done"},
            {"id": "f1", "cmd": "x", "status": "failed", "log": "logs/f1.log"},
            {"id": "p1", "cmd": "x", "est_min": 90},
            {"id": "p2", "cmd": "x", "est_min": 30},
        ],
    )
    put(paths, "cpu", [])
    text = render_state(paths, ("gpu", "cpu"), now=dt.datetime(2026, 11, 4, 23, 30), last_error="f1 rc=1")
    assert text.startswith("# STATE (2026-11-04 23:30)")
    assert "## lane gpu: running=[] done=1 failed=1 pending=2 (~2.0 h queued)" in text
    assert "- next: p1" in text  # 밤이라 긴 항목부터
    assert "- failed: [('f1', 'logs/f1.log')]" in text
    assert "## lane cpu: running=[] done=0 failed=0 pending=0" in text
    assert "last error: f1 rc=1" in text


def test_write_state_creates_file(paths: Paths) -> None:
    put(paths, "gpu", [])
    write_state(paths, ("gpu",), now=dt.datetime(2026, 1, 1, 9, 0))
    assert paths.state_file.read_text(encoding="utf-8").startswith("# STATE (2026-01-01 09:00)")
