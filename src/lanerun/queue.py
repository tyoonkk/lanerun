"""큐 파일 읽기·쓰기, 항목 검증, 다음 항목 선택.

큐 파일은 레인마다 하나(`queue_<lane>.yaml`)이고 항목 목록(YAML list)이다. 항목 필드는
docs/queue-format.md 에 있다. 이 모듈은 파일 시스템과 시계만 알고, 프로세스 실행은 모른다.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import shlex
import sys
import time
from dataclasses import dataclass
from typing import Any

import yaml

Item = dict[str, Any]

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
DEFAULT_PRIORITY = 5


class QueueError(RuntimeError):
    """큐 파일이나 항목이 쓸 수 없는 상태일 때."""


@dataclass(frozen=True)
class Paths:
    """러너가 쓰는 경로 묶음. 모두 root 아래에 둔다."""

    root: pathlib.Path
    queue_dir: pathlib.Path
    logs_dir: pathlib.Path
    state_file: pathlib.Path

    @classmethod
    def from_root(
        cls,
        root: str | os.PathLike[str],
        queue_dir: str = "experiments",
        logs_dir: str = "logs",
        state_file: str = "STATE.md",
    ) -> Paths:
        r = pathlib.Path(root).resolve()
        return cls(r, r / queue_dir, r / logs_dir, r / state_file)

    def queue_file(self, lane: str) -> pathlib.Path:
        return self.queue_dir / f"queue_{lane}.yaml"

    def log_file(self, item_id: str) -> pathlib.Path:
        return self.logs_dir / f"{item_id}.log"

    def lock_file(self, lane: str) -> pathlib.Path:
        return self.logs_dir / f"runner_{lane}.lock"


def load_queue(path: pathlib.Path, *, attempts: int = 5, delay_s: float = 1.0) -> list[Item]:
    """큐 파일을 읽는다. 파일이 없으면 빈 목록.

    파싱에 실패하면 몇 번 더 시도한 뒤 예외를 낸다. 절대 빈 목록을 돌려주지 않는다:
    빈 목록을 돌려주면 다음 save 에서 큐 전체가 빈 파일로 덮어써진다.
    """
    if not path.exists():
        return []
    last: Exception | None = None
    for i in range(attempts):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            last = e
            if i + 1 < attempts:
                time.sleep(delay_s)
            continue
        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
            raise QueueError(f"{path}: 큐 파일은 항목(dict) 목록이어야 합니다")
        return [dict(x) for x in data]
    raise QueueError(
        f"{path}: {attempts}번 읽어도 파싱되지 않습니다 ({last!r}). 빈 큐로 덮어쓰지 않고 멈춥니다."
    )


def save_queue(path: pathlib.Path, items: list[Item]) -> None:
    """임시 파일에 쓴 뒤 os.replace 로 바꿔치기한다. 쓰다 죽어도 원본은 남는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(yaml.safe_dump(items, allow_unicode=True, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def validate_item(item: Item) -> list[str]:
    """항목 하나의 문제를 사람이 읽을 문장으로 돌려준다. 비어 있으면 정상."""
    problems: list[str] = []
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        problems.append("id 가 비어 있습니다")
    elif any(ch in item_id for ch in '/\\:*?"<>|'):
        problems.append(f"id '{item_id}' 에 파일 이름으로 쓸 수 없는 문자가 있습니다")
    cmd = item.get("cmd")
    if isinstance(cmd, str):
        if not cmd.strip():
            problems.append("cmd 가 비어 있습니다")
    elif isinstance(cmd, list):
        if not cmd or not all(isinstance(c, str | int | float) for c in cmd):
            problems.append("cmd 목록은 문자열·숫자로만 이루어져야 합니다")
    else:
        problems.append("cmd 가 없습니다 (문자열 또는 목록)")
    for key in ("est_min", "priority"):
        v = item.get(key)
        if v is not None and not isinstance(v, int | float):
            problems.append(f"{key} 는 숫자여야 합니다")
    return problems


def validate_queue(items: list[Item]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for i, it in enumerate(items):
        for p in validate_item(it):
            problems.append(f"[{i}] {p}")
        item_id = it.get("id")
        if isinstance(item_id, str):
            if item_id in seen:
                problems.append(f"[{i}] id '{item_id}' 가 중복됩니다")
            seen.add(item_id)
    return problems


def is_night(now: dt.datetime | None = None, window: tuple[int, int] = (22, 8)) -> bool:
    """`window=(start, end)` 시(時) 사이면 밤. (22, 8) 은 22:00~07:59, 자정을 넘겨도 된다."""
    h = (now or dt.datetime.now()).hour
    start, end = window
    if start <= end:
        return start <= h < end
    return h >= start or h < end


def pick(items: list[Item], *, night: bool) -> Item | None:
    """다음에 돌릴 pending 항목. priority 가 작은 것 먼저, 같으면 밤엔 긴 것, 낮엔 짧은 것부터."""
    pending = [i for i in items if i.get("status", PENDING) == PENDING]
    if not pending:
        return None

    def key(i: Item) -> tuple[float, float]:
        est = float(i.get("est_min") or 0)
        return (float(i.get("priority") or DEFAULT_PRIORITY), -est if night else est)

    return min(pending, key=key)


def build_command(item: Item) -> list[str]:
    """`cmd` 를 subprocess 인자 목록으로. 문자열이면 shlex 로 나누고, 'python' 은 지금 인터프리터로 바꾼다."""
    cmd = item.get("cmd")
    if isinstance(cmd, str):
        parts = shlex.split(cmd, posix=(os.name != "nt"))
    elif isinstance(cmd, list) and cmd:
        parts = [str(c) for c in cmd]
    else:
        raise QueueError(f"{item.get('id')!r}: cmd 가 없습니다")
    return [sys.executable if p == "python" else p for p in parts]


def find_item(items: list[Item], item_id: str) -> Item | None:
    return next((i for i in items if i.get("id") == item_id), None)


def update_item(path: pathlib.Path, item_id: str, **fields: Any) -> list[Item]:
    """큐 파일을 다시 읽어 해당 항목만 고치고 저장한다 (다른 프로세스의 편집을 덮어쓰지 않기 위해)."""
    items = load_queue(path)
    target = find_item(items, item_id)
    if target is None:
        raise QueueError(f"{path}: id '{item_id}' 가 없습니다")
    target.update(fields)
    save_queue(path, items)
    return items


def summarize(items: list[Item]) -> dict[str, Any]:
    status = {
        k: [i for i in items if i.get("status", PENDING) == k] for k in (RUNNING, DONE, FAILED, PENDING)
    }
    return {
        "running": [i["id"] for i in status[RUNNING]],
        "done": len(status[DONE]),
        "failed": len(status[FAILED]),
        "pending": len(status[PENDING]),
        "queued_hours": sum(float(i.get("est_min") or 0) for i in status[PENDING]) / 60,
        "recent_done": [i["id"] for i in status[DONE][-10:]],
        "failed_items": [(i["id"], i.get("log")) for i in status[FAILED]],
    }
