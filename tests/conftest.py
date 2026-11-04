from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from lanerun.queue import Paths, save_queue


@pytest.fixture
def paths(tmp_path: pathlib.Path) -> Paths:
    p = Paths.from_root(tmp_path)
    p.queue_dir.mkdir()
    p.logs_dir.mkdir()
    return p


@pytest.fixture
def day() -> dt.datetime:
    return dt.datetime(2026, 11, 4, 14, 0)


@pytest.fixture
def night() -> dt.datetime:
    return dt.datetime(2026, 11, 4, 23, 0)


def put(paths: Paths, lane: str, items: list[dict[str, object]]) -> pathlib.Path:
    q = paths.queue_file(lane)
    save_queue(q, items)
    return q
