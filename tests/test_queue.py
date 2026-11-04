from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest
import yaml

from lanerun.queue import (
    PENDING,
    Paths,
    QueueError,
    build_command,
    is_night,
    load_queue,
    pick,
    save_queue,
    update_item,
    validate_queue,
)
from tests.conftest import put


def test_missing_file_is_empty_queue(paths: Paths) -> None:
    assert load_queue(paths.queue_file("gpu")) == []


def test_save_is_atomic_and_roundtrips(paths: Paths) -> None:
    q = put(paths, "gpu", [{"id": "a", "cmd": "python -c pass", "status": PENDING}])
    assert load_queue(q)[0]["id"] == "a"
    assert not q.with_name(q.name + ".tmp").exists()


def test_unparseable_file_raises_instead_of_returning_empty(paths: Paths) -> None:
    q = paths.queue_file("gpu")
    q.write_text("- id: [unclosed\n", encoding="utf-8")
    with pytest.raises(QueueError, match="빈 큐로 덮어쓰지 않고"):
        load_queue(q, attempts=2, delay_s=0)
    # 원본은 그대로 남아 있어야 한다
    assert q.read_text(encoding="utf-8").startswith("- id: [unclosed")


def test_non_list_file_raises(paths: Paths) -> None:
    q = paths.queue_file("gpu")
    q.write_text(yaml.safe_dump({"id": "a"}), encoding="utf-8")
    with pytest.raises(QueueError, match="목록"):
        load_queue(q, attempts=1, delay_s=0)


def test_pick_orders_by_priority_then_length(day: dt.datetime, night: dt.datetime) -> None:
    items = [
        {"id": "long", "est_min": 120, "priority": 2},
        {"id": "short", "est_min": 10, "priority": 2},
        {"id": "urgent", "est_min": 60, "priority": 1},
        {"id": "done", "est_min": 1, "priority": 1, "status": "done"},
    ]
    assert pick(items, night=is_night(day))["id"] == "urgent"  # type: ignore[index]
    items = [i for i in items if i["id"] != "urgent"]
    assert pick(items, night=False)["id"] == "short"  # type: ignore[index]
    assert pick(items, night=True)["id"] == "long"  # type: ignore[index]
    assert pick([{"id": "x", "status": "done"}], night=False) is None
    assert is_night(night)


@pytest.mark.parametrize(
    ("hour", "window", "expected"),
    [
        (23, (22, 8), True),
        (3, (22, 8), True),
        (8, (22, 8), False),
        (14, (22, 8), False),
        (10, (9, 17), True),
        (18, (9, 17), False),
    ],
)
def test_is_night_windows(hour: int, window: tuple[int, int], expected: bool) -> None:
    assert is_night(dt.datetime(2026, 1, 1, hour), window) is expected


def test_build_command_replaces_python_and_splits_strings() -> None:
    assert build_command({"id": "a", "cmd": "python -m x --seed 0"}) == [
        sys.executable,
        "-m",
        "x",
        "--seed",
        "0",
    ]
    assert build_command({"id": "a", "cmd": ["python", "train.py", 3]}) == [sys.executable, "train.py", "3"]
    with pytest.raises(QueueError):
        build_command({"id": "a"})


def test_update_item_rereads_file_so_concurrent_edits_survive(paths: Paths) -> None:
    q = put(paths, "cpu", [{"id": "a", "cmd": "x"}])
    # 다른 프로세스(사람)가 항목을 하나 더 넣었다고 치자
    items = load_queue(q)
    items.append({"id": "b", "cmd": "y"})
    save_queue(q, items)
    update_item(q, "a", status="done", rc=0)
    after = load_queue(q)
    assert [i["id"] for i in after] == ["a", "b"]
    assert after[0]["status"] == "done"
    with pytest.raises(QueueError, match="없습니다"):
        update_item(q, "zzz", status="done")


def test_validate_queue_reports_problems() -> None:
    problems = validate_queue(
        [
            {"id": "ok", "cmd": "x"},
            {"id": "ok", "cmd": ""},
            {"cmd": ["python"], "est_min": "many"},
            {"id": "bad/id", "cmd": "x"},
        ]
    )
    assert any("중복" in p for p in problems)
    assert any("cmd 가 비어" in p for p in problems)
    assert any("est_min" in p for p in problems)
    assert any("파일 이름" in p for p in problems)
    assert validate_queue([{"id": "a", "cmd": "x", "est_min": 3, "priority": 1}]) == []


def test_paths_layout(tmp_path: pathlib.Path) -> None:
    p = Paths.from_root(tmp_path, queue_dir="q", logs_dir="l", state_file="S.md")
    assert p.queue_file("gpu") == tmp_path.resolve() / "q" / "queue_gpu.yaml"
    assert p.lock_file("gpu") == tmp_path.resolve() / "l" / "runner_gpu.lock"
    assert p.state_file == tmp_path.resolve() / "S.md"
