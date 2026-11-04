"""레인 하나를 맡아 큐를 돌리는 Runner.

한 번의 step 은 이렇다: 큐를 다시 읽는다 → 다음 항목을 고른다 → 가드를 기다린다 → running 으로 표시하고
STATE.md 를 쓴다 → 하위 프로세스를 돌리고 로그를 남긴다 → done/failed 로 표시하고 STATE.md 를 다시 쓴다.
큐 파일은 매번 다시 읽으므로, 러너가 도는 중에 사람이 항목을 추가하거나 우선순위를 바꿔도
다음 step 에 반영된다.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, Any

from lanerun.guards import TemperatureGuard
from lanerun.lock import LaneLock
from lanerun.queue import (
    DONE,
    FAILED,
    PENDING,
    RUNNING,
    Item,
    Paths,
    build_command,
    is_night,
    load_queue,
    pick,
    save_queue,
    update_item,
)
from lanerun.state import write_state

CallFn = Callable[..., int]


@dataclass
class RunnerConfig:
    lane: str
    paths: Paths
    lanes: tuple[str, ...] = ("gpu", "cpu")
    poll_s: float = 30.0
    once: bool = False
    night_window: tuple[int, int] = (22, 8)
    guard: TemperatureGuard | None = None
    extra_env: dict[str, str] = field(default_factory=dict)


class Runner:
    def __init__(
        self,
        cfg: RunnerConfig,
        *,
        call: CallFn = subprocess.call,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], dt.datetime] = dt.datetime.now,
        log: Callable[[str], None] = print,
    ) -> None:
        self.cfg = cfg
        self._call = call
        self._sleep = sleep
        self._now = now
        self._log = log
        self.lock = LaneLock(cfg.paths.lock_file(cfg.lane))

    # -- 상태 --------------------------------------------------------------------------------
    @property
    def queue_file(self) -> Any:
        return self.cfg.paths.queue_file(self.cfg.lane)

    def reset_stale_running(self) -> list[str]:
        """죽은 러너가 남긴 running 항목을 pending 으로 되돌린다. lock 을 쥔 뒤에만 부른다."""
        items = load_queue(self.queue_file)
        reset = [i["id"] for i in items if i.get("status") == RUNNING]
        if reset:
            for i in items:
                if i.get("status") == RUNNING:
                    i["status"] = PENDING
            save_queue(self.queue_file, items)
        return reset

    def _write_state(self, last_error: str | None = None) -> None:
        write_state(
            self.cfg.paths,
            self.cfg.lanes,
            now=self._now(),
            night_window=self.cfg.night_window,
            last_error=last_error,
        )

    # -- 실행 --------------------------------------------------------------------------------
    def run_item(self, item: Item) -> int:
        """항목 하나를 하위 프로세스로 돌린다. stdout/stderr 는 logs/<id>.log 에 덧붙인다."""
        paths = self.cfg.paths
        paths.logs_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_command(item)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        env.update(self.cfg.extra_env)
        env.update({str(k): str(v) for k, v in (item.get("env") or {}).items()})
        f: IO[str]
        with paths.log_file(item["id"]).open("a", encoding="utf-8") as f:
            f.write(f"\n=== {self._now():%Y-%m-%d %H:%M:%S} {' '.join(cmd)}\n")
            f.flush()
            return int(self._call(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=paths.root, env=env))

    def step(self) -> bool:
        """항목 하나를 처리한다. 돌릴 게 없으면 STATE.md 만 쓰고 False."""
        items = load_queue(self.queue_file)
        item = pick(items, night=is_night(self._now(), self.cfg.night_window))
        if item is None:
            self._write_state()
            return False
        if self.cfg.guard is not None:
            self.cfg.guard.wait_until_cool(sleep=self._sleep, log=self._log)
        rel_log = self.cfg.paths.log_file(item["id"]).relative_to(self.cfg.paths.root).as_posix()
        update_item(
            self.queue_file,
            item["id"],
            status=RUNNING,
            started=f"{self._now():%Y-%m-%d %H:%M:%S}",
            log=rel_log,
        )
        self._write_state()
        self._log(f"[{self.cfg.lane}] running {item['id']}")
        t0 = time.monotonic()
        try:
            rc = self.run_item(item)
            err: str | None = None
        except Exception as e:  # 실행 자체가 실패해도 사유를 큐에 남기고 다음 항목으로 간다
            rc, err = -1, repr(e)
        minutes = round((time.monotonic() - t0) / 60, 1)
        update_item(
            self.queue_file,
            item["id"],
            status=DONE if rc == 0 else FAILED,
            rc=rc,
            finished=f"{self._now():%Y-%m-%d %H:%M:%S}",
            actual_min=minutes,
        )
        self._write_state(None if rc == 0 else (err or f"{item['id']} rc={rc} see {rel_log}"))
        self._log(f"[{self.cfg.lane}] finished {item['id']} rc={rc} in {minutes} min")
        return True

    def loop(self) -> None:
        """lock 을 잡고 큐가 빌 때까지(또는 once 면 한 항목만) 돈다."""
        how = self.lock.acquire()
        try:
            if how == "took_over":
                self._log(f"[{self.cfg.lane}] 죽은 러너의 lock 을 넘겨받음")
            reset = self.reset_stale_running()
            if reset:
                self._log(f"[{self.cfg.lane}] running 이었던 항목을 pending 으로 되돌림: {reset}")
            self._log(f"[{self.cfg.lane}] runner started pid={os.getpid()}")
            while True:
                ran = self.step()
                if self.cfg.once:
                    return
                if not ran:
                    self._sleep(self.cfg.poll_s)
        finally:
            self.lock.release()
