# Changelog

## 0.1.0 — 2026-11-04

처음 공개. 석사논문 저장소의 `src/queue_runner.py`(209줄)를 떼어내 범용으로 만들었다.

- 항목은 `cmd`만 있으면 된다 (원본은 논문 저장소의 `src.run` 전용).
- 레인 이름을 `--lanes`로 정할 수 있다 (원본은 `gpu`·`cpu` 고정).
- PID 확인을 Windows(`tasklist`)와 POSIX(`os.kill`)에서 모두 지원.
- `init`, `add`, `validate`, `reset`, `status` 명령 추가.
- 항목별 `env`.
- 테스트(pytest)와 CI(ubuntu·windows × Python 3.11·3.12, ruff·mypy·pytest·설치 명령 스모크).
- 동작 규칙은 원본 그대로: 큐 매번 재읽기, 파싱 실패 시 멈춤, 원자적 저장, PID lock(모르면 거절),
  running 복구, 밤/낮 정렬, GPU 온도 가드, STATE.md 스냅숏.
