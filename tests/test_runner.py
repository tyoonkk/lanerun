from __future__ import annotations

import datetime as dt
import sys
from typing import Any

import pytest

from lanerun.guards import TemperatureGuard
from lanerun.lock import LaneLock, LockHeld
from lanerun.queue import PENDING, Paths, load_queue
from lanerun.runner import Runner, RunnerConfig
from tests.conftest import put


def make_runner(paths: Paths, lane: str = "cpu", **kw: Any) -> Runner:
    cfg = RunnerConfig(lane=lane, paths=paths, once=True, **kw)
    return Runner(cfg, sleep=lambda s: None, now=lambda: dt.datetime(2026, 11, 4, 14, 0), log=lambda m: None)


def test_runs_real_subprocess_and_records_result(paths: Paths) -> None:
    put(paths, "cpu", [{"id": "hello", "cmd": "python -c \"print('hi')\"", "est_min": 1}])
    make_runner(paths).loop()
    item = load_queue(paths.queue_file("cpu"))[0]
    assert item["status"] == "done"
    assert item["rc"] == 0
    assert item["log"] == "logs/hello.log"
    assert "hi" in paths.log_file("hello").read_text(encoding="utf-8")
    assert "done=1" in paths.state_file.read_text(encoding="utf-8")
    assert not paths.lock_file("cpu").exists()


def test_failed_command_is_marked_failed_and_runner_continues(paths: Paths) -> None:
    put(
        paths,
        "cpu",
        [
            {"id": "bad", "cmd": ["python", "-c", "import sys; sys.exit(3)"], "priority": 1},
            {"id": "good", "cmd": ["python", "-c", "pass"], "priority": 2},
        ],
    )
    r = make_runner(paths)
    r.lock.acquire()
    assert r.step() is True
    assert r.step() is True
    assert r.step() is False
    r.lock.release()
    items = {i["id"]: i for i in load_queue(paths.queue_file("cpu"))}
    assert items["bad"]["status"] == "failed"
    assert items["bad"]["rc"] == 3
    assert items["good"]["status"] == "done"
    assert "failed=1" in paths.state_file.read_text(encoding="utf-8")


def test_stale_running_items_are_reset_at_startup(paths: Paths) -> None:
    put(paths, "cpu", [{"id": "orphan", "cmd": "python -c pass", "status": "running"}])
    r = make_runner(paths)
    r.lock.acquire()
    assert r.reset_stale_running() == ["orphan"]
    r.lock.release()
    assert load_queue(paths.queue_file("cpu"))[0]["status"] == PENDING


def test_second_runner_on_same_lane_is_refused(paths: Paths) -> None:
    put(paths, "cpu", [])
    first = LaneLock(paths.lock_file("cpu"), alive=lambda pid: True)
    first.acquire()
    try:
        with pytest.raises(LockHeld):
            make_runner(paths).loop()
    finally:
        first.release()


def test_guard_waits_before_running(paths: Paths) -> None:
    temps = iter([90.0, 88.0, 70.0])
    waited: list[float] = []
    guard = TemperatureGuard(limit_c=85, wait_s=300, read=lambda: next(temps, 60.0))
    put(paths, "gpu", [{"id": "g", "cmd": "python -c pass"}])
    cfg = RunnerConfig(lane="gpu", paths=paths, once=True, guard=guard)
    r = Runner(cfg, sleep=waited.append, now=lambda: dt.datetime(2026, 11, 4, 2, 0), log=lambda m: None)
    r.loop()
    assert waited == [300, 300]
    assert load_queue(paths.queue_file("gpu"))[0]["status"] == "done"


def test_item_env_is_passed_to_child(paths: Paths) -> None:
    put(
        paths,
        "cpu",
        [
            {
                "id": "env",
                "cmd": ["python", "-c", "import os; print(os.environ['LANERUN_X'])"],
                "env": {"LANERUN_X": "42"},
            }
        ],
    )
    make_runner(paths).loop()
    assert "42" in paths.log_file("env").read_text(encoding="utf-8")


def test_exception_in_launch_is_recorded_as_failure(paths: Paths) -> None:
    put(paths, "cpu", [{"id": "boom", "cmd": "python -c pass"}])

    def exploding_call(*a: Any, **k: Any) -> int:
        raise OSError("no such interpreter")

    cfg = RunnerConfig(lane="cpu", paths=paths, once=True)
    Runner(cfg, call=exploding_call, sleep=lambda s: None, log=lambda m: None).loop()
    item = load_queue(paths.queue_file("cpu"))[0]
    assert item["status"] == "failed"
    assert item["rc"] == -1
    assert "no such interpreter" in paths.state_file.read_text(encoding="utf-8")


def test_queue_edited_while_running_is_picked_up_next_step(paths: Paths) -> None:
    put(paths, "cpu", [{"id": "first", "cmd": "python -c pass", "priority": 1}])
    r = make_runner(paths)
    r.lock.acquire()
    assert r.step() is True
    # 러너가 도는 동안 사람이 항목을 추가
    items = load_queue(paths.queue_file("cpu"))
    items.append({"id": "second", "cmd": [sys.executable, "-c", "pass"]})
    put(paths, "cpu", items)
    assert r.step() is True
    r.lock.release()
    assert load_queue(paths.queue_file("cpu"))[1]["status"] == "done"
