"""실행 전에 기다릴지 정하는 가드. 지금은 GPU 온도 하나다.

GTX 1660 SUPER 한 장으로 30일을 돌리다 보니 85°C 를 넘기면 다음 실험이 눈에 띄게 느려졌다.
nvidia-smi 가 없거나 읽지 못하면 가드는 아무것도 하지 않는다 (CPU 머신, 다른 GPU).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field


def nvidia_smi_temperature() -> float | None:
    """GPU 0 의 온도(°C). 읽지 못하면 None."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return float(out.decode().strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


@dataclass
class TemperatureGuard:
    limit_c: float = 85.0
    wait_s: float = 300.0
    read: Callable[[], float | None] = field(default=nvidia_smi_temperature)

    def wait_until_cool(self, *, sleep: Callable[[float], None], log: Callable[[str], None]) -> int:
        """온도가 limit 아래로 내려올 때까지 기다린다. 기다린 횟수를 돌려준다."""
        waits = 0
        t = self.read()
        while t is not None and t > self.limit_c:
            log(f"GPU {t:.0f}°C > {self.limit_c:.0f}°C, {self.wait_s / 60:.0f}분 대기")
            sleep(self.wait_s)
            waits += 1
            t = self.read()
        return waits
