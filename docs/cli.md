# 명령 레퍼런스

설치하면 `lanerun` 명령이 생깁니다. `python -m lanerun`도 같습니다.
처음 쓰는 순서는 README의 맨 위 네 줄(init → add → run → status)이고, 여기에는 옵션 전체와 종료 코드,
자주 겪는 상황의 처리 방법을 적었습니다. 큐 파일의 필드는 [queue-format.md](queue-format.md)에 있습니다.

## 공통 옵션

명령 이름 **앞에** 씁니다. 예: `lanerun --root D:\proj --lanes a100,cpu status`

| 옵션 | 기본값 | 뜻 |
|---|---|---|
| `--root` | `.` | 프로젝트 루트. 아래 경로들의 기준이고, 하위 프로세스도 여기서 실행된다 |
| `--queue-dir` | `experiments` | `queue_<lane>.yaml`이 있는 폴더 |
| `--logs-dir` | `logs` | 항목 로그(`<id>.log`)와 lock 파일(`runner_<lane>.lock`) 폴더 |
| `--state-file` | `STATE.md` | 상태 스냅숏 파일 |
| `--lanes` | `gpu,cpu` | 레인 이름 목록(쉼표 구분). `init`, `status`, `validate`와 STATE.md가 이 목록을 쓴다 |
| `--version` | | 버전을 출력하고 끝낸다 |

## lanerun init

레인마다 빈 큐 파일, `logs/`, `STATE.md`를 만듭니다. 이미 있는 큐 파일은 건드리지 않습니다.

## lanerun add

항목 하나를 큐 끝에 추가합니다.

| 옵션 | 기본값 | 뜻 |
|---|---|---|
| `--lane` | (필수) | 넣을 레인 |
| `--id` | (필수) | 큐 안에서 고유한 이름. 로그 파일 이름으로도 쓰인다 |
| `--cmd` | (필수) | 실행 명령. `python`은 러너를 돌리는 인터프리터로 바뀐다 |
| `--est-min` | `0` | 예상 소요 분. 밤/낮 정렬과 남은 시간 계산에 쓴다 |
| `--priority` | `5` | 작을수록 먼저 |
| `--hypothesis` | | 이 실험으로 확인하려는 것 (기록용) |
| `--success` | | 성공 기준 (기록용, 큐에는 `success_criterion`으로 저장) |

같은 id가 이미 있거나 항목이 형식에 맞지 않으면(빈 명령, 파일 이름에 못 쓰는 문자) 추가하지 않고 2로 끝납니다.

## lanerun run

레인 하나의 러너를 시작합니다. 레인마다 러너는 하나만 뜹니다.

| 옵션 | 기본값 | 뜻 |
|---|---|---|
| `--lane` | `gpu` | 돌릴 레인 |
| `--once` | | 항목 하나만 처리하고 끝낸다 (큐가 비어 있으면 STATE.md만 쓰고 끝) |
| `--poll` | `30` | 큐가 비었을 때 다시 읽는 간격(초) |
| `--night` | `22-8` | 밤 시간대(시). 밤에는 같은 priority 안에서 긴 항목부터, 낮에는 짧은 항목부터 |
| `--gpu-temp-limit` | `85` | gpu 레인 온도 상한(°C). 넘으면 5분씩 기다린다 |
| `--no-gpu-guard` | | 온도 가드를 끈다 |

하는 일은 이 순서입니다.

1. `logs/runner_<lane>.lock`을 잡습니다. 다른 러너가 살아 있거나 살아 있는지 **알 수 없으면** 3으로 끝납니다.
   lock의 주인이 죽었으면 넘겨받습니다.
2. 이전 러너가 `running`으로 남긴 항목을 `pending`으로 되돌립니다.
3. 큐 파일을 다시 읽고 다음 항목을 고른 뒤, (gpu 레인이면) 온도를 확인하고, `running`으로 표시하고 실행합니다.
4. 끝나면 `done` 또는 `failed`와 종료 코드, 소요 분을 적고 STATE.md를 다시 씁니다. 3으로 돌아갑니다.

하위 프로세스는 `--root`에서 실행되고, stdout과 stderr는 `logs/<id>.log`에 덧붙습니다. 환경변수로
`PYTHONIOENCODING=utf-8`, `PYTHONUNBUFFERED=1`과 항목의 `env`가 더해집니다.
항목이 실패해도 러너는 멈추지 않고 종료 코드도 바뀌지 않습니다. 실패는 큐의 `rc`와 STATE.md의 `last error`에 남습니다.

온도는 `nvidia-smi`로 읽습니다. `nvidia-smi`가 없으면 가드는 조용히 건너뜁니다.

## lanerun status

레인별 현황(실행 중, 완료, 실패, 대기, 남은 예상 시간, 다음 항목)을 출력합니다. `--write`를 주면 STATE.md도 다시 씁니다.

## lanerun reset

| 옵션 | 뜻 |
|---|---|
| `--lane` (필수) | 레인 |
| `ID ...` | 되돌릴 항목 id들 |
| `--failed` | `failed` 항목 전부 |

대상 항목의 `status`를 `pending`으로 바꾸고 `started`, `finished`, `rc`, `actual_min`을 지웁니다. 되돌릴 항목이 없으면 2.

## lanerun validate

레인마다 큐 파일을 한 번 읽어(재시도 없이) 깨진 YAML, 중복 id, 빈 명령, 숫자가 아닌 `est_min`·`priority`를 찾습니다.
문제가 있으면 위치와 이유를 출력하고 1로 끝납니다.

## 종료 코드

| 코드 | 뜻 | 나오는 명령 |
|---|---|---|
| 0 | 정상 | 모두 |
| 1 | 큐 파일에서 문제를 찾음 | `validate` |
| 2 | 입력 오류: 중복 id, 형식에 맞지 않는 항목, 되돌릴 항목 없음, 잘못된 옵션 | `add`, `reset`, 모두(옵션 오류) |
| 3 | 같은 레인의 러너가 이미 돌고 있음 (또는 살아 있는지 알 수 없음) | `run` |
| 4 | 큐 파일을 읽을 수 없음. 1초 간격으로 다섯 번 시도한 뒤 멈추고, 파일은 건드리지 않음 | `validate`를 뺀 모든 명령 |

스크립트에서 쓸 때는 이렇게 묶을 수 있습니다.

```
lanerun validate && lanerun run --lane gpu --once
```

## 자주 겪는 상황

**실패한 항목을 다시 돌리고 싶다.** `logs/<id>.log`를 보고 원인을 고친 뒤 `lanerun reset --lane gpu --failed`
(또는 id를 지정). 러너가 돌고 있으면 다음 선택 때 잡힙니다. 자동 재시도는 일부러 두지 않았습니다.

**도는 중에 순서를 바꾸고 싶다.** 큐 파일의 `priority`를 고치면 됩니다. 지금 실행 중인 항목은 그대로 두고
다음 항목부터 반영됩니다. 항목을 빼려면 `status: cancelled`처럼 `pending`이 아닌 값을 적습니다.

**"이미 돌고 있습니다"(3)가 나온다.** 정말 러너가 떠 있는지 먼저 봅니다. lock 파일의 PID가 죽은 프로세스면
다음 실행이 알아서 넘겨받으므로, 이 메시지는 실제로 살아 있거나 확인할 수 없을 때만 나옵니다.
러너가 없다는 것을 직접 확인했다면 `logs/runner_<lane>.lock`을 지우고 다시 실행합니다.

**"파싱되지 않습니다"(4)가 나온다.** 큐 파일을 손으로 고치다 YAML이 깨진 경우입니다. `lanerun validate`로
위치를 확인하고 고치면 됩니다. lanerun은 이때 파일을 덮어쓰지 않으므로 항목은 그대로 남아 있습니다.
