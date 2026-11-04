# lanerun

[![ci](https://github.com/tyoonkk/lanerun/actions/workflows/ci.yml/badge.svg)](https://github.com/tyoonkk/lanerun/actions/workflows/ci.yml)

GPU 한 장짜리 PC에서 실험 수백 건을 레인별 큐로 사람 없이 돌리는 CLI입니다.
의존성은 PyYAML 하나, Python 3.11 이상, Windows와 Linux에서 같은 코드로 돕니다.

```
lanerun init
lanerun add --lane gpu --id S0_seed0 --cmd "python train.py --seed 0" --est-min 90 --priority 1
lanerun run --lane gpu
lanerun status
```

## 왜 만들었나

석사논문 실험(웨이퍼 맵 결함 분류, 실험 208건, GPU 412시간)을 GTX 1660 SUPER 한 장으로 30일 안에
끝내야 했습니다. 막상 해 보니 모델보다 운영이 문제였습니다.

- 세션을 열 때마다 "지금 뭐가 돌고 있고 뭐가 끝났지"를 다시 확인하는 데 시간이 샜다.
- 밤에 GPU가 놀았다. 짧은 실험은 낮에 돌려 결과를 보고, 긴 실험은 밤에 돌리고 싶었다.
- 러너가 죽으면 `running`으로 남은 항목이 영원히 돌지 않았다.
- 큐 파일을 손으로 고치다 YAML이 깨지면, 순진한 러너는 빈 큐로 읽고 **빈 큐로 덮어썼다**.
- 러너를 실수로 두 개 띄우면 같은 GPU에서 두 실험이 같이 느려지거나 메모리 부족으로 죽었다.
- GPU가 85°C를 넘기면 그다음 실험이 눈에 띄게 느려졌다.

lanerun은 그때 쓴 209줄짜리 러너(논문 저장소의 `src/queue_runner.py`)에서 논문 전용 부분을 떼어내
범용으로 만든 것입니다. 원본은 GPU 167건·CPU 41건을 실패 0으로 돌렸고, 그 기록은 STATE.md 커밋 64개로 남아 있습니다.

## 어떻게 동작하나

- 레인(`gpu`, `cpu`, 또는 원하는 이름)마다 큐 파일 하나 `experiments/queue_<lane>.yaml`, 러너 프로세스 하나.
- 러너는 큐 파일을 **매번 다시 읽어** `pending` 항목 중 하나를 고릅니다. `priority`가 작은 것 먼저, 같으면
  밤(기본 22~08시)에는 `est_min`이 긴 것부터, 낮에는 짧은 것부터.
- 고른 항목을 `running`으로 표시하고 하위 프로세스로 돌립니다. stdout/stderr는 `logs/<id>.log`에 덧붙입니다.
- 끝나면 `done` 또는 `failed`, 종료 코드, 실제 소요 분을 항목에 기록하고 `STATE.md`를 다시 씁니다.
- `STATE.md`는 누적 로그가 아니라 **현재 상태의 스냅숏**입니다. 다음 세션이 사람이든 Claude Code·Codex 같은
  코딩 에이전트든, 이 파일 하나만 읽으면 어디까지 왔는지 알 수 있게 만들었습니다.

```
# STATE (2026-10-20 04:18)

## lane gpu: running=[] done=167 failed=0 pending=0 (~0.0 h queued)
- next: -
- recent done: ['RC3_poolstem_g2_k25_s0-9', 'RC3_poolstages_g2_k25_s0-9', ...]

## lane cpu: running=[] done=41 failed=0 pending=0 (~0.0 h queued)
- next: -
- recent done: ['B_P1time_tabpfn_s0-4', 'B_rolling_tabpfn_s0-4', ...]
```

## 설치

```
pip install git+https://github.com/tyoonkk/lanerun
# 또는 격리해서
pipx install git+https://github.com/tyoonkk/lanerun
```

## 명령

| 명령 | 하는 일 |
|---|---|
| `lanerun init` | 레인별 빈 큐 파일, `logs/`, `STATE.md`를 만든다 |
| `lanerun add --lane L --id ID --cmd "..." [--est-min N] [--priority P] [--hypothesis ...] [--success ...]` | 항목을 큐 끝에 추가한다. 같은 id가 있으면 거절 |
| `lanerun run --lane L [--once] [--poll 30] [--night 22-8] [--gpu-temp-limit 85] [--no-gpu-guard]` | 러너를 시작한다. 레인당 하나만 뜬다 |
| `lanerun status [--write]` | 레인별 현황을 출력한다 (`--write`면 STATE.md도 갱신) |
| `lanerun reset --lane L ID... ` / `--failed` | 항목을 `pending`으로 되돌린다 |
| `lanerun validate` | 큐 파일의 형식 오류(중복 id, 빈 cmd, 깨진 YAML)를 찾는다 |

공통 옵션: `--root`(기본 현재 폴더), `--queue-dir`, `--logs-dir`, `--state-file`, `--lanes gpu,cpu`.

## 큐 파일

```yaml
- id: A_P1_S0_s0-4
  lane: gpu
  cmd: python -m src.run --config configs/trackA/wm811k_S0.yaml --protocol P1 --seeds 0 1 2 3 4
  est_min: 100
  priority: 1
  hypothesis: lot 분리 분할에서 S0 기준선의 macro-F1
  success_criterion: 5시드 평균±표준편차가 기록됨
  status: pending
```

`cmd`는 문자열(셸처럼 나눔) 또는 목록이고, `python`은 러너를 돌리는 인터프리터로 바뀝니다. `env`로 항목별
환경변수를 줄 수 있습니다. 러너가 채우는 필드는 `status`, `started`, `finished`, `rc`, `log`, `actual_min`입니다.
전체 필드는 [docs/queue-format.md](docs/queue-format.md)에 있습니다.

러너가 도는 중에 큐 파일을 직접 고쳐도 됩니다. 항목 추가, 우선순위 변경, `status: cancelled` 같은 편집은
다음 선택 시점에 반영됩니다. 러너는 항목 하나의 상태를 바꿀 때마다 파일을 다시 읽고 그 항목만 고쳐 저장하므로
사람의 편집을 덮어쓰지 않습니다.

## 지키는 규칙

| 규칙 | 왜 |
|---|---|
| 큐 파일을 못 읽으면 **멈춘다**. 빈 큐로 돌려주지 않는다 | 빈 큐를 돌려주면 다음 저장에서 큐 전체가 사라진다 |
| 저장은 임시 파일 + `os.replace` | 쓰다 죽어도 원본이 남는다 |
| 레인마다 PID lock. 상대 PID가 살아 있거나 **알 수 없으면** 거절, 죽었으면 넘겨받는다 | 같은 GPU에 러너 둘은 둘 다 망친다. 모르면 안전한 쪽 |
| `running`으로 남은 항목은 lock을 잡은 뒤에만 `pending`으로 되돌린다 | lock이 없으면 그 항목이 정말 죽었는지 모른다 |
| gpu 레인은 온도가 상한을 넘으면 식을 때까지 기다린다 | 과열 상태에서 시작한 실험은 느리다. nvidia-smi가 없으면 조용히 건너뛴다 |
| 하위 프로세스의 예외도 `failed`로 기록하고 다음 항목으로 간다 | 한 항목 때문에 밤새 멈추지 않는다. 실패는 STATE.md의 `last error`와 로그에 남는다 |

## 24시간 운영

러너는 큐가 비면 `--poll` 간격으로 기다리기만 합니다. 러너 자체가 죽는 경우(재부팅, 실수로 닫음)를 대비해
주기적으로 다시 띄우는 스크립트를 둡니다.

- Windows: [`scripts/start_runners.ps1`](scripts/start_runners.ps1)은 레인별로 이미 떠 있는지 확인하고 없으면 숨김 창으로 띄웁니다.
  [`scripts/keepalive_windows.ps1`](scripts/keepalive_windows.ps1)은 이것을 5분마다 실행하는 작업 스케줄러 항목을 등록하고 절전을 끕니다.
- Linux: cron 한 줄이면 됩니다. lock 덕분에 이미 돌고 있으면 바로 종료합니다.
  ```
  */5 * * * * cd /path/to/project && lanerun run --lane gpu >> logs/runner_gpu.out 2>&1
  ```

## 설계 결정과 배운 점

[docs/design.md](docs/design.md)에 적었습니다. 요약하면: 큐 파일은 사람과 러너가 같이 고치는 문서다,
파싱 실패는 멈춤이다, 모르면 거절한다, 재개(resume)는 하위 작업의 책임이고 재개 키에는 설정 해시가 들어가야 한다.

## 한계

- 한 대의 PC용입니다. 여러 머신에 나누어 돌리는 기능은 없습니다 (그게 필요하면 Slurm이나 Ray 같은 도구가 맞습니다).
- 항목 간 의존성 그래프가 없습니다. `priority`와 실행 순서로 대신합니다.
- 자동 재시도가 없습니다. 실패는 사람이 로그를 보고 `lanerun reset`으로 되돌립니다. 일부러 그렇게 두었습니다.
- 이어서 돌리기(결과가 있는 시드 건너뛰기)는 하위 작업이 해야 합니다. lanerun은 결과 파일을 모릅니다.

## 개발

```
python -m venv .venv && .venv/Scripts/activate   # Linux: source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

CI(GitHub Actions)는 ubuntu·windows × Python 3.11·3.12에서 같은 네 가지를 돌리고, 설치된 `lanerun` 명령으로
init → add → run → status를 한 번 실제로 실행합니다.

```
src/lanerun/
  queue.py    큐 파일 읽기·쓰기, 검증, 다음 항목 선택 (파일과 시계만 안다)
  lock.py     레인 PID lock
  guards.py   실행 전 대기 조건 (GPU 온도)
  state.py    STATE.md 렌더링
  runner.py   한 레인을 돌리는 Runner (위 모듈을 조립)
  cli.py      argparse 명령
tests/        pytest. 하위 프로세스는 실제 python -c 로 돌리고, 시계·sleep·온도는 주입한다
```

## 라이선스

MIT
