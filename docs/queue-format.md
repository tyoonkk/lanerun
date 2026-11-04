# 큐 파일 형식

레인마다 하나, `experiments/queue_<lane>.yaml`. 항목(dict)의 목록(list)이어야 합니다. 목록이 아니거나
파싱이 안 되면 러너는 멈추고 `lanerun validate`가 이유를 알려줍니다.

## 사람이 적는 필드

| 필드 | 타입 | 필수 | 뜻 |
|---|---|---|---|
| `id` | 문자열 | 예 | 큐 안에서 고유. 로그 파일 이름(`logs/<id>.log`)으로도 쓰이므로 `/ \ : * ? " < > \|`는 못 씀 |
| `cmd` | 문자열 또는 목록 | 예 | 실행 명령. 문자열이면 셸처럼 나눔(Windows에서는 역슬래시 경로 유지). `python`은 러너의 인터프리터로 바뀜 |
| `est_min` | 숫자 | 아니오 | 예상 소요 분. 밤/낮 정렬과 STATE.md의 남은 시간 계산에 씀. 없으면 0 |
| `priority` | 정수 | 아니오 | 작을수록 먼저. 없으면 5 |
| `env` | 매핑 | 아니오 | 이 항목에만 줄 환경변수 |
| `lane` | 문자열 | 아니오 | 기록용. 파일 이름이 레인을 정한다 |
| `hypothesis` | 문자열 | 아니오 | 이 실험으로 확인하려는 것. 기록용 |
| `success_criterion` | 문자열 | 아니오 | 무엇이 나오면 성공인지. 기록용 |
| `status` | 문자열 | 아니오 | 없으면 `pending`. 사람이 `cancelled`, `skipped` 등으로 바꿔 두면 러너는 건드리지 않음 |

`hypothesis`와 `success_criterion`은 러너가 읽지 않습니다. 그래도 넣어 두기를 권합니다. 실험 200건이 넘어가면
"이걸 왜 돌렸지"를 큐 파일이 대신 기억해 줍니다.

## 러너가 채우는 필드

| 필드 | 뜻 |
|---|---|
| `status` | `running` → `done`(rc 0) 또는 `failed` |
| `started`, `finished` | `YYYY-MM-DD HH:MM:SS` |
| `rc` | 하위 프로세스 종료 코드. 실행 자체가 예외로 실패하면 -1 |
| `log` | 루트 기준 상대 경로, 예: `logs/A_P1_S0_s0-4.log` |
| `actual_min` | 실제 소요 분 (소수 첫째 자리) |

`lanerun reset`은 `started`, `finished`, `rc`, `actual_min`을 지우고 `status`를 `pending`으로 돌립니다.

## 예

```yaml
- id: A_P1_S0_s0-4
  lane: gpu
  cmd: python -m src.run --config configs/trackA/wm811k_S0.yaml --protocol P1 --seeds 0 1 2 3 4
  est_min: 100
  priority: 1
  hypothesis: lot 분리 분할에서 S0 기준선의 macro-F1
  success_criterion: 5시드 평균±표준편차가 P1 기준선으로 기록됨
  status: done
  started: '2026-09-04 05:33:17'
  log: logs/A_P1_S0_s0-4.log
  rc: 0
  finished: '2026-09-04 07:05:56'
  actual_min: 92.6
- id: B_tabpfn_rolling
  cmd: [python, -m, src.run_tabular, --model, tabpfn, --split, rolling]
  env: { OMP_NUM_THREADS: "4" }
  est_min: 25
  priority: 3
```
