from __future__ import annotations

import pathlib

import pytest

from lanerun.cli import main
from lanerun.queue import load_queue


def run(root: pathlib.Path, *args: str) -> int:
    return main(["--root", str(root), *args])


def test_init_add_validate_status_reset(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path, "init") == 0
    assert (tmp_path / "experiments" / "queue_gpu.yaml").exists()
    assert (tmp_path / "STATE.md").exists()

    assert (
        run(tmp_path, "add", "--lane", "gpu", "--id", "a", "--cmd", "python -c pass", "--est-min", "5") == 0
    )
    assert run(tmp_path, "add", "--lane", "gpu", "--id", "a", "--cmd", "python -c pass") == 2  # 중복 id
    assert run(tmp_path, "add", "--lane", "gpu", "--id", "bad/id", "--cmd", "x") == 2

    assert run(tmp_path, "validate") == 0
    assert run(tmp_path, "status") == 0
    out = capsys.readouterr().out
    assert "lane gpu" in out
    assert "next: a" in out

    assert run(tmp_path, "run", "--lane", "gpu", "--once", "--no-gpu-guard") == 0
    item = load_queue(tmp_path / "experiments" / "queue_gpu.yaml")[0]
    assert item["status"] == "done"

    assert run(tmp_path, "reset", "--lane", "gpu", "a") == 0
    item = load_queue(tmp_path / "experiments" / "queue_gpu.yaml")[0]
    assert item["status"] == "pending"
    assert "rc" not in item
    assert run(tmp_path, "reset", "--lane", "gpu", "--failed") == 2


def test_validate_reports_broken_file(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "experiments").mkdir()
    (tmp_path / "experiments" / "queue_gpu.yaml").write_text("- id: [x\n", encoding="utf-8")
    assert run(tmp_path, "validate") == 1
    assert "파싱되지 않습니다" in capsys.readouterr().out


def test_custom_lanes_and_dirs(tmp_path: pathlib.Path) -> None:
    assert run(tmp_path, "--lanes", "a100,cpu", "--queue-dir", "q", "init") == 0
    assert (tmp_path / "q" / "queue_a100.yaml").exists()
    assert not (tmp_path / "q" / "queue_gpu.yaml").exists()


def test_bad_night_window_is_rejected(tmp_path: pathlib.Path) -> None:
    run(tmp_path, "init")
    with pytest.raises(SystemExit):
        run(tmp_path, "run", "--lane", "cpu", "--once", "--night", "late")
