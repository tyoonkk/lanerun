"""STATE.md: 다음 세션(사람이든 코딩 에이전트든)이 이 파일 하나만 읽으면 되게 하는 요약.

항목이 하나 끝날 때마다 통째로 다시 쓴다. 누적 로그가 아니라 현재 상태의 스냅숏이다.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from lanerun.queue import Paths, is_night, load_queue, pick, summarize


def render_state(
    paths: Paths,
    lanes: Sequence[str],
    *,
    now: dt.datetime | None = None,
    night_window: tuple[int, int] = (22, 8),
    last_error: str | None = None,
) -> str:
    now = now or dt.datetime.now()
    night = is_night(now, night_window)
    lines = [f"# STATE ({now:%Y-%m-%d %H:%M})", ""]
    for lane in lanes:
        items = load_queue(paths.queue_file(lane))
        s = summarize(items)
        lines.append(
            f"## lane {lane}: running={s['running']} done={s['done']} failed={s['failed']} "
            f"pending={s['pending']} (~{s['queued_hours']:.1f} h queued)"
        )
        nxt = pick(items, night=night)
        lines.append(f"- next: {nxt['id'] if nxt else '-'}")
        lines.append(f"- recent done: {s['recent_done']}")
        if s["failed_items"]:
            lines.append(f"- failed: {s['failed_items']}")
        lines.append("")
    if last_error:
        lines.append(f"last error: {last_error}")
        lines.append("")
    return "\n".join(lines)


def write_state(paths: Paths, lanes: Sequence[str], **kw: object) -> str:
    text = render_state(paths, lanes, **kw)  # type: ignore[arg-type]
    paths.state_file.write_text(text, encoding="utf-8")
    return text
