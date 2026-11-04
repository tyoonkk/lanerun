from __future__ import annotations

import os
import pathlib

import pytest

from lanerun.lock import LaneLock, LockHeld, pid_alive


def test_acquire_writes_own_pid_and_release_removes(tmp_path: pathlib.Path) -> None:
    lock = LaneLock(tmp_path / "logs" / "runner_gpu.lock")
    assert lock.acquire() == "acquired"
    assert lock.path.read_text(encoding="utf-8") == str(os.getpid())
    lock.release()
    assert not lock.path.exists()


def test_live_holder_is_refused(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "runner_gpu.lock"
    path.write_text("4242", encoding="utf-8")
    with pytest.raises(LockHeld):
        LaneLock(path, alive=lambda pid: True).acquire()
    assert path.read_text(encoding="utf-8") == "4242"


def test_unknown_liveness_is_treated_as_live(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "runner_gpu.lock"
    path.write_text("4242", encoding="utf-8")
    with pytest.raises(LockHeld):
        LaneLock(path, alive=lambda pid: None).acquire()


def test_stale_lock_is_taken_over(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "runner_gpu.lock"
    path.write_text("4242", encoding="utf-8")
    lock = LaneLock(path, alive=lambda pid: False)
    assert lock.acquire() == "took_over"
    assert path.read_text(encoding="utf-8") == str(os.getpid())


def test_garbage_lock_file_is_taken_over(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "runner_gpu.lock"
    path.write_text("not a pid", encoding="utf-8")
    assert LaneLock(path, alive=lambda pid: True).acquire() == "took_over"


def test_context_manager_releases(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "runner_cpu.lock"
    with LaneLock(path):
        assert path.exists()
    assert not path.exists()


def test_pid_alive_on_self_and_nonsense() -> None:
    assert pid_alive(os.getpid()) is True
    assert pid_alive(0) is False
    assert pid_alive(-5) is False
