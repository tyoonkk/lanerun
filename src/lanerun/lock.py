"""레인마다 러너를 하나만 돌게 하는 PID lock.

lock 파일에는 러너의 PID 가 들어 있다. 파일이 이미 있으면 그 PID 가 살아 있는지 본다.
죽었으면 넘겨받고, 살아 있거나 알 수 없으면 거절한다. "알 수 없음" 을 거절로 다루는 이유는
같은 GPU 에서 러너 두 개가 돌면 두 실험이 모두 느려지거나 메모리 부족으로 죽기 때문이다.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
from collections.abc import Callable
from types import TracebackType


class LockHeld(RuntimeError):
    """살아 있는 다른 러너가 lock 을 쥐고 있다."""


def _alive_windows(pid: int) -> bool | None:
    try:
        out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/NH"], stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return str(pid) in out.decode(errors="ignore")


def _alive_posix(pid: int) -> bool | None:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 다른 사용자의 프로세스: 살아 있다
    except OSError:
        return None
    return True


def pid_alive(pid: int) -> bool | None:
    """살아 있으면 True, 죽었으면 False, 판단할 수 없으면 None."""
    if pid <= 0:
        return False
    return _alive_windows(pid) if os.name == "nt" else _alive_posix(pid)


class LaneLock:
    """`with LaneLock(path): ...` 로 쓴다. 나갈 때 lock 파일을 지운다."""

    def __init__(self, path: pathlib.Path, *, alive: Callable[[int], bool | None] = pid_alive) -> None:
        self.path = path
        self._alive = alive
        self.held = False

    def _other_pid(self) -> int:
        try:
            return int(self.path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return -1

    def acquire(self) -> str:
        """lock 을 잡는다. 'acquired' 또는 'took_over' 를 돌려주고, 못 잡으면 LockHeld."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            other = self._other_pid()
            state = self._alive(other) if other > 0 else False
            if state is None or state:
                raise LockHeld(f"{self.path}: 러너(pid {other})가 이미 돌고 있습니다") from None
            self.path.write_text(str(os.getpid()), encoding="utf-8")
            self.held = True
            return "took_over"
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        self.held = True
        return "acquired"

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False

    def __enter__(self) -> LaneLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
