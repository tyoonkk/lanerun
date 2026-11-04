"""명령줄: lanerun init | add | run | status | reset | validate."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from lanerun import __version__
from lanerun.guards import TemperatureGuard
from lanerun.lock import LockHeld
from lanerun.queue import (
    PENDING,
    Item,
    Paths,
    QueueError,
    find_item,
    load_queue,
    save_queue,
    validate_item,
    validate_queue,
)
from lanerun.runner import Runner, RunnerConfig
from lanerun.state import render_state, write_state


def _paths(a: argparse.Namespace) -> Paths:
    return Paths.from_root(a.root, queue_dir=a.queue_dir, logs_dir=a.logs_dir, state_file=a.state_file)


def _lanes(a: argparse.Namespace) -> tuple[str, ...]:
    return tuple(x.strip() for x in a.lanes.split(",") if x.strip())


def cmd_init(a: argparse.Namespace) -> int:
    paths = _paths(a)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    for lane in _lanes(a):
        q = paths.queue_file(lane)
        if q.exists():
            print(f"있음: {q}")
            continue
        save_queue(q, [])
        print(f"만듦: {q}")
    write_state(paths, _lanes(a))
    print(f"만듦: {paths.state_file}")
    print('다음: lanerun add --lane gpu --id 첫실험 --cmd "python train.py --seed 0" --est-min 30')
    return 0


def cmd_add(a: argparse.Namespace) -> int:
    paths = _paths(a)
    q = paths.queue_file(a.lane)
    items = load_queue(q)
    if find_item(items, a.id) is not None:
        print(f"이미 있는 id 입니다: {a.id}", file=sys.stderr)
        return 2
    item: Item = {"id": a.id, "lane": a.lane, "cmd": a.cmd, "est_min": a.est_min, "priority": a.priority}
    if a.hypothesis:
        item["hypothesis"] = a.hypothesis
    if a.success:
        item["success_criterion"] = a.success
    item["status"] = PENDING
    problems = validate_item(item)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    items.append(item)
    save_queue(q, items)
    print(f"추가: {a.id} → {q}")
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    paths = _paths(a)
    guard = None if (a.no_gpu_guard or a.lane != "gpu") else TemperatureGuard(limit_c=a.gpu_temp_limit)
    cfg = RunnerConfig(
        lane=a.lane,
        paths=paths,
        lanes=_lanes(a),
        poll_s=a.poll,
        once=a.once,
        night_window=a.night,
        guard=guard,
    )
    try:
        Runner(cfg).loop()
    except LockHeld as e:
        print(str(e), file=sys.stderr)
        return 3
    except QueueError as e:
        print(str(e), file=sys.stderr)
        return 4
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    paths = _paths(a)
    text = render_state(paths, _lanes(a))
    if a.write:
        paths.state_file.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def cmd_reset(a: argparse.Namespace) -> int:
    paths = _paths(a)
    q = paths.queue_file(a.lane)
    items = load_queue(q)
    targets = [i for i in items if (a.failed and i.get("status") == "failed") or i.get("id") in a.ids]
    if not targets:
        print("되돌릴 항목이 없습니다", file=sys.stderr)
        return 2
    for i in targets:
        i["status"] = PENDING
        for k in ("started", "finished", "rc", "actual_min"):
            i.pop(k, None)
    save_queue(q, items)
    print(f"pending 으로 되돌림: {[i['id'] for i in targets]}")
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    paths = _paths(a)
    bad = 0
    for lane in _lanes(a):
        q = paths.queue_file(lane)
        try:
            problems = validate_queue(load_queue(q, attempts=1))
        except QueueError as e:
            problems = [str(e)]
        if problems:
            bad += 1
            print(f"{q}:")
            print("\n".join(f"  {p}" for p in problems))
        else:
            print(f"{q}: 정상")
    return 1 if bad else 0


def _window(spec: str) -> tuple[int, int]:
    try:
        start, end = (int(x) for x in spec.split("-"))
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"--night 는 '22-8' 형식이어야 합니다: {spec!r}") from e
    if not (0 <= start <= 23 and 0 <= end <= 23):
        raise argparse.ArgumentTypeError("--night 의 시(時)는 0~23 이어야 합니다")
    return start, end


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lanerun",
        description="GPU 한 장짜리 PC에서 실험 수백 건을 레인별 큐로 사람 없이 돌린다.",
    )
    p.add_argument("--version", action="version", version=f"lanerun {__version__}")
    p.add_argument("--root", default=".", help="프로젝트 루트 (기본: 현재 폴더)")
    p.add_argument("--queue-dir", default="experiments", help="queue_<lane>.yaml 이 있는 폴더")
    p.add_argument("--logs-dir", default="logs", help="로그와 lock 파일 폴더")
    p.add_argument("--state-file", default="STATE.md", help="상태 요약 파일")
    p.add_argument("--lanes", default="gpu,cpu", help="레인 이름들 (쉼표 구분)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="큐 파일·로그 폴더·STATE.md 를 만든다")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("add", help="항목을 큐 끝에 추가한다")
    s.add_argument("--lane", required=True)
    s.add_argument("--id", required=True, help="고유 id (로그 파일 이름으로도 쓰임)")
    s.add_argument("--cmd", required=True, help="실행 명령. 'python' 은 지금 인터프리터로 바뀜")
    s.add_argument("--est-min", type=float, default=0, help="예상 소요 분 (밤/낮 정렬에 쓰임)")
    s.add_argument("--priority", type=int, default=5, help="작을수록 먼저 (기본 5)")
    s.add_argument("--hypothesis", default="", help="이 실험으로 확인하려는 가설 (기록용)")
    s.add_argument("--success", default="", help="성공 기준 (기록용)")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("run", help="레인 하나의 러너를 시작한다 (레인당 프로세스 하나)")
    s.add_argument("--lane", default="gpu")
    s.add_argument("--once", action="store_true", help="항목 하나만 돌리고 끝낸다")
    s.add_argument("--poll", type=float, default=30.0, help="큐가 비었을 때 다시 읽는 간격(초)")
    s.add_argument("--night", type=_window, default=(22, 8), help="밤 시간대. 밤엔 긴 항목부터 (기본 22-8)")
    s.add_argument("--gpu-temp-limit", type=float, default=85.0, help="gpu 레인 온도 상한(°C)")
    s.add_argument("--no-gpu-guard", action="store_true", help="온도 가드를 끈다")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("status", help="레인별 현황을 출력한다 (STATE.md 와 같은 내용)")
    s.add_argument("--write", action="store_true", help="STATE.md 도 다시 쓴다")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("reset", help="항목을 pending 으로 되돌린다")
    s.add_argument("--lane", required=True)
    s.add_argument("ids", nargs="*", help="되돌릴 id 들")
    s.add_argument("--failed", action="store_true", help="failed 항목 전부")
    s.set_defaults(func=cmd_reset)

    s = sub.add_parser("validate", help="큐 파일의 형식 오류를 찾는다")
    s.set_defaults(func=cmd_validate)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    func = a.func
    result: int = func(a)
    return result
