# 순차 Rev 컨트롤러

소스·클라이언트는 Rev 준비와 독립적으로 자동 설치·업데이트할 수 있다. 이 작업은 기존 설정·실행 연결·완료 기록을 보존하며 모델 환경 설치나 서비스 시작을 수행하지 않는다. 선택적 환경·연결 준비 뒤 인증된 `/ping`과 실제 `/score`를 따로 확인해야 한다. CPU와 Windows CUDA 후보도 dtype별 자원·실제 kernel 검사를 거치며 후보 진단은 추론 성공의 증거가 아니다.

이 소스는 0.4.0의 새 quick/project 경로다. 루트 호환 진입점도 이 소스를 사용한다. 기존 설치나 프로젝트 설정을 자동 변경하지 않는다. 실패 복구는 원인·부분 수정에 대한 명시적 재개 검토 뒤에만 제한적으로 진행한다.

큰 목표는 `project.py`가 `gpt-6.1-sol`에 읽기 전용 계획을 한 번 요청한 뒤 작업을 순서대로 실행한다. 작은 요청은 `run.py`가 계획 호출 없이 Rev를 사용한다. 각 구현 작업은 로컬 Rev의 실제 `/score` 계약으로 `gpt-6-luna` 또는 `gpt-6.1-sol`을 선택한다. 유료 Codex 분류·SEV 호출·추가 작업별 조율 호출은 없다. 오류·기권·시간 초과·입력 초과는 중단하며 모델 대체로 이어지지 않는다.

## 모델 설정

새 `.ai/models.yaml`은 `planning_model: gpt-6.1-sol`, `execution_model: null`을 구분한다. 호환되지 않는 구 설정은 자동 변환하거나 덮어쓰지 않고 중단한다. 실제 프로젝트의 기존 설정을 검토한 뒤 명시적으로 이전해야 한다. `templates/`는 프로젝트 사실과 검사 명령을 비워 둔 배포 예시다.

실행 선택 우선순위는 사용자 `--task-model TASK=worker|main`, 사용자 `--execution-model worker|main`(`--model` 별칭), 설정의 `execution_model`, Rev 순서다. 앞의 세 경우는 Rev client 구성·접속을 모두 건너뛴다. planner가 task의 `execution_model`을 지정하면 거부한다. 계획 모델은 구현을 고정하지 않는다. `--planning-model`은 현재 `gpt-6.1-sol`만 허용한다. 재개는 원래 모델 선택을 보존한다.

사용자가 재개 시 `--task-model TASK=worker|main`을 명시하면 아직 완료하지 않은 작업의 선택만 바꿀 수 있으며 변경 이력을 private 상태에 남긴다. 실패·중단 작업은 먼저 같은 `--reconcile TASK`가 필요하다. Rev 기권 뒤에도 이 방법으로 명시적 선택을 제공할 수 있다. 완료 작업·전역 설정·전체 목표를 자동 변경하지 않는다.

`.ai/routing.yaml`은 `selection: rev`, `backend: codex_cli`, `automatic_recovery: false`, `parallel_agents: false`를 명시한다. `.ai/rev.json`은 `rev/contracts.py`의 인증 loopback 연결 계약이다. token은 지정된 환경 변수에만 두며 파일·명령행·보고서에 쓰지 않는다. 전역 SEV·개인 skill·`.ai/sev.json`을 변경하지 않는다.

## 입력과 실행

`--context-file`은 `goal`, `facts`, `risks`, `constraints`, `uncertainty`를 모두 가진 JSON이다. `goal`은 전체 목표 문자열, 나머지는 문자열 목록이다. 해당 사항이 없으면 빈 목록을 명시한다. `templates/context.json`의 빈 목표는 의도적으로 실행할 수 없다. quick의 `--task-file`은 단일 요청 원문이며 생략하면 전체 목표를 사용한다.

```powershell
python assets/runner/run.py start --project C:/work/project --context-file context.json --task-file request.txt --write
python assets/runner/project.py start --project C:/work/project --context-file context.json --write
python assets/runner/project.py status --project C:/work/project
python assets/runner/project.py resume --project C:/work/project --write
```

이는 사용 예시이며 개발 중 실제 사용자 프로젝트에서 실행하지 않았다. `.ai/verification.yaml`의 `commands`에는 실제 요구 명령만 설정한다. 모델은 `verification=[]`로 소스 후보만 반환한다. controller가 별도 subprocess로 설정된 전체 명령을 실행하고 코드·설정 지문이 같은 증거만 완료로 인정한다. 관련성이 불확실하면 검사를 줄이지 않는다. 모든 명령이 미설정이면 완료하지 않는다. 검사가 작업 공간을 바꾸면 이전 지문의 증거로 완료하지 않는다. task 검사가 통과한 뒤 구현 완료를 기록한다. project에서는 모든 task 완료 뒤 집계 milestone 검사, 이어서 final 검사를 별도 subprocess로 실행한다. quick에서는 task 뒤 final 검사를 실행한다. scope마다 전체 설정 명령을 유지하며 앞 scope의 증거를 복사해 통과시키지 않는다. 검사 활성 시간도 전체 시간 예산에 포함한다.

전체 필수 목표·사실·위험·제약·불확실성과 현재 작업 문맥은 Rev와 구현에 동일하게 전달한다. 직접 의존 작업의 요약·인터페이스·변경 파일·검사 결과·private 보고서 경로만 포함한다. 간접 의존 결과·완료된 전체 이력은 복사하지 않는다. 각 의존 결과는 16384 UTF-8 bytes, 전체 의존 결과는 65536 bytes 이하다. 전체 요청은 Rev의 262144 bytes 및 실제 서비스 tokenizer 제한을 따른다. 필수 필드 누락이나 초과는 중단하며 위험·인터페이스를 자동 잘라내지 않는다. 명시적으로 내용을 정리하거나 계획 경계를 검토해야 한다.

명시적 재시도에는 같은 작업의 직전 실패·불확실 상태, 부분 변경 파일, 검사 결과, 인터페이스와 보고서 경로도 전달한다. 구현 모델은 기존 부분 수정을 읽고 이어서 작업해야 한다. 이 요약도 16384 bytes를 넘으면 조용히 잘라내지 않고 중단한다.

## 상태·승인·예산

새 상태는 `.ai/rev-workflow/state.json`, 상세 시도는 그 안의 `reports/`에 private 파일로 저장한다. 기존 private 쓰기·링크 거부·redaction을 재사용한다. redaction은 알려진 비밀 형식의 최선 노력이며 모든 비밀 탐지를 보장하지 않는다. 필수 입력에 알려진 비밀이 있으면 삭제된 문맥으로 실행하지 않고 사용자 정리를 요구한다. stdout은 상태·간단한 결과·실제 검사 상태·실패·보고서 경로를 표시한다.

기본 예산은 계획 포함 최대 20회 모델 호출 예약, controller 활성 시간 3600초다. `--max-calls`, `--max-seconds`로 명시적으로 바꿀 수 있다. 호출 예약과 관측한 CLI invocation은 구분한다. 선택·검사·모델 시간이 활성 시간에 포함되며 실패도 예산을 사용한다. 강제 종료 시 실행 여부가 불확실한 예약을 되돌리지 않고 마지막 활성 시점 이후 시간을 보수적으로 반영한다. 이 추정치를 CLI latency로 사용하지 않는다.

`--write` 없이 구현하지 않는다. 승인 작업은 `resume --write --approve TASK`가 필요하다. 실패·중단 뒤에는 보고서와 부분 수정을 검토하고 `resume --write --reconcile TASK`를 명시한다. 실패한 최초 계획은 `--reconcile plan`으로 재시도할 수 있다. 이는 사용자 재시도이며 자동 재계획이 아니다. 완료 작업은 승인·재조정으로도 재실행하지 않는다. 설정·연결·런타임 소스 또는 외부 작업 공간이 달라지면 재개를 거부한다. 완료 작업·보고서를 보존하고 명시적으로 보관한 뒤 별도 흐름을 시작해야 한다. CLI가 보관이나 상태 편집을 자동 수행하지 않는다.

기존 `.ai/project-workflow/state.json`이 있으면 새 start를 거부한다. 새 상태가 없을 때 status는 구 상태를 읽기 전용으로 표시한다. 기존 runtime으로 상세를 읽고 완료 작업·보고서를 보존한 뒤 명시적으로 정리·보관해야 한다. version=4라도 controller schema=3과 다르거나 상태가 불확실하면 조용히 변환하지 않는다. schema=1/2의 완료 기록도 자동 재실행하지 않는다. 기존 공유 SEV 제거·다른 프로젝트 사용 여부 판정은 수행하지 않는다.

## 관측 범위

각 planning/implementation/retry/escalation/replan 시도는 요청 모델, backend가 확인한 실제 모델, input/cached/output token, CLI 경과 시간, 관측한 CLI invocation과 backend 요청 수를 따로 기록한다. 실패 이벤트 뒤에도 가능한 사용량을 보존한다. 누락 값은 `null`이며 총계와 알려진 부분합·미확인 시도 수를 구분한다. 상세 기록의 `operation`은 계획 재시도와 구현 재시도를 구분한다.

현재 CLI JSON에서 신뢰할 실제 backend 모델·요청 횟수를 확인하지 못하므로 해당 값은 `null`이다. `--model`이나 thread ID를 실제 모델 확인으로 간주하지 않는다. 강제 중단 시 부모 controller가 관측하지 못한 invocation이 있을 수 있으므로 0회 관측은 backend 미호출 증거가 아니다. app 대화 모델·사용량은 측정하거나 바꾸지 않는다. 캐시·비용·성능·절감 효과를 추정하지 않는다.

`tests/test_controller.py`는 모델·Rev 응답·검사 subprocess를 mock으로 대체한 계약 fixture다. 실제 inference·설치·유료 실행·코딩 품질 비교를 검증하지 않는다. 실제 Rev smoke는 지원 하드웨어와 명시적 로컬 자원에서만 가능하며 이 Windows/Iris Xe 호스트에서는 실행하지 않는다.

## 검증 근거와 재개

`required`는 설정된 필수 검사가 아직 실행되지 않았다는 뜻이다. `passed`·`failed`는 관측한 subprocess 결과이며, nonzero 종료 코드를 보존한다. 시간 초과는 `failed`, `executed=true`, `exit_code=null`과 시간 초과 사유를 기록한다. 프로세스 시작 실패와 예산 소진은 `required`, `executed=false`와 각각의 사유를 기록한다. `unset`은 명령 미설정이며 통과가 아니다. 전부 미설정·생략인 경우 완료하지 않는다. 모델이 보고한 성공이나 검사 목록은 controller 증거를 대신하지 못한다.

CLI의 검사 관련성 판단이 불확실하므로 기본적으로 설정된 전체 검사를 실행한다. 내부 `run_checks(..., relevance=...)`는 사용자가 명시적으로 검토한 현재 명령·scope·코드/설정 지문·검토 ID·사유를 controller가 별도로 전달한 경우에만 `irrelevant_skipped`를 기록한다. 모델 출력·계획·과거 상태에서 생략 정책을 가져오지 않는다. 생략은 성공으로 표시하지 않으며, 현재 증거가 없거나 오래되었으면 완료 조건을 만족하지 못한다. 공개 CLI는 이러한 검토를 수집하지 않으므로 생략을 적용하지 않는다.

검사 캐시는 controller 인스턴스의 메모리에만 있으며 기본 CLI에서는 비활성이다. 임의 shell 명령이 사용하는 모든 도구·의존성·외부 입력을 자동 증명할 수 없기 때문이다. embedding controller가 전체 tooling 입력의 동일성을 명시적으로 보증한 경우에만 동일 scope·전체 작업 공간/설정 지문·명령 정의·tooling SHA256·환경 변수 지문의 성공 증거를 재사용한다. 환경 값은 저장하지 않고 해시만 사용한다. 알 수 없는 도구, 변경, 불확실한 관련성, 실패·미실행 증거는 재사용하지 않는다. 다른 scope나 다른 controller 프로세스로 캐시를 넘기지 않는다. 성능·비용 절감 효과는 측정하지 않았다.

milestone/final 실패·중단 시 완료된 task는 보존한다. private gate 보고서와 검사에 의한 부분 수정을 검토하고 `resume --write --reconcile verification`으로 검사만 재실행한다. 시간 예산이 소진되면 명시적 `--max-seconds` 연장도 필요하다. 완료된 task의 모델 호출을 재실행하지 않는다. 이미 전체 완료된 상태의 resume는 기존 완료 기록을 읽으며 검사도 반복하지 않는다. 설정·런타임·외부 파일이 달라지면 기존 규칙대로 재개를 거부하고 명시적 정리·보관을 요구한다. 이전 controller schema=1 상태는 자동 변환하지 않으며 보고서·완료 작업을 보존해야 한다.

stdout은 task·milestone·final의 이름·명령·상태·실행 여부·종료 코드와 gate 보고서 경로를 구분해 제공한다. 전체 출력·오류·각 scope의 실제 controller 증거와 cache 사용 여부는 `.ai/rev-workflow/reports/gates-*.json`에 보관한다. 모델 raw 출력은 모델 시도 보고서에 따로 남는다. 이 개발 단계의 fixture는 subprocess와 모델을 mock으로 대체하므로 실제 명령 실행이나 실제 Rev 추론의 증거가 아니다.

## 마지막 단계의 제한된 실패 복구

`recovery.py`는 `environment`(실행 환경), `transient`(시간 초과·중단), `code`(일반 결함·불확실한 원인 포함), `plan`(확인된 의존성·인터페이스·설계 변경)을 구분한다. 모델의 미해결 응답이나 검사 nonzero만으로 역량 한계를 확정하지 않는다. Rev 오류는 로컬 원인 복구가 필요하며 유료 모델 승격 근거가 될 수 없다. 오류 원인·필요 행동·전체 보고서는 private 시도 기록에 남는다.

모든 실패·부분 수정·중단은 먼저 중단한다. `automatic_recovery: false`는 무인 재실행을 금지한다는 뜻이다. 보고서와 현재 파일을 검토한 사용자의 `resume --write --reconcile TASK`만 같은 모델의 제한된 재시도를 허용한다. 최초 Rev 선택이 실패했으면 다시 Rev를 시도하거나 사용자가 `--task-model`을 명시한다. 완료 작업과 완료 task 뒤의 실패한 검증 gate는 구현을 재실행하지 않는다.

확인된 역량 한계는 별도로 검토한 JSON을 `--failure-review FILE`로 전달한다. 모델 출력에서 이 근거를 가져오지 않는다. `status`의 `last_report_path`, `recovery_workspace_sha256`를 현재 보고서·부분 수정 검토에 연결한다. 외부 파일을 수동 수정했다면 검토한 현재 파일의 지문을 사용해야 하며 오래된 검토는 거부한다. JSON 필드는 다음과 같다.

```json
{
  "source": "explicit_user_review",
  "review_id": "사용자 검토 식별자",
  "record": ".ai/rev-workflow/reports/0002-TASK.json",
  "workspace_sha256": "검토한 현재 작업 공간 SHA256",
  "category": "code",
  "confirmed_capability": true,
  "confirmed_change": null,
  "cause": "일반 코드 결함과 구별해 확인한 원인",
  "action": "허용된 다음 단계",
  "attempted_methods": "이미 시도한 방법과 원인 분석",
  "verification_results": "관련 실제 검증 결과",
  "remaining_problem": "확인된 미해결 문제"
}
```

실행 override가 있으면 자동 승격을 거부한다. 기록된 환경·일시 오류도 역량 실패로 바꿔 승격할 수 없다. 새 템플릿의 `recovery.sequence`는 `worker → main → escalation`이고 각각 `gpt-6-luna`, `gpt-6.1-sol`, `gpt-6-astra`다. 기존 사용자 설정은 바꾸지 않는다. `recovery` 설정이 없는 호환 설정은 `worker → main`만 허용한다. 각 복구는 순차 실행하며 Rev 재분류나 추가 조율 호출을 하지 않는다. 다음 모델은 전체 목표·필수 위험과 직접 의존성, 직전 시도 및 검토 근거를 받는다.

재계획은 project 모드에서 `category: plan`, `confirmed_capability: false`, `confirmed_change: dependency|interface|design`인 명시적 검토만 허용한다. 변경 없는 코드 실패에는 계획 호출을 추가하지 않는다. Sol은 읽기 전용 제안만 만든다. task ID 추가·삭제, 완료 task 정의 변경, 기존 위험·인터페이스 삭제, 승인 flag 변경을 거부한다. 사용자는 private 제안을 검토한 뒤 별도 `resume --write --accept-replan`으로 수락한다. 기존 계획은 `plan_history`에 보존하며 완료 task의 결과·검사 증거와 사용자 override를 유지한다. 수락도 목표 범위를 넓히는 권한은 아니다. 범위를 넓혀야 하면 기존 이력을 보존하고 별도 명시적 작업을 시작해야 한다.

템플릿은 전체 흐름에서 재시도 1회, 승격 2회, 재계획 1회로 제한한다. 호출 예약 전에 횟수를 저장하므로 강제 종료로 횟수가 초기화되지 않는다. 모든 단계는 같은 `--max-calls`, `--max-seconds`, `--max-tokens`를 사용한다. 템플릿의 토큰 한도는 input+output 합계 2,000,000이며 cached input은 다시 더하지 않는다. 누락 사용량은 계속 `null`이다. 유한 토큰 예산에서 호출 사용량이 불명확하면 다음 호출을 중단한다. Rev 선택 실패로 coding CLI를 시작하지 않았음이 확실한 시도는 별도로 구별한다.

토큰 한도는 관측 사용량에 대한 후속 호출 허용 기준이다. 현재 CLI는 호출 도중 backend 사용량을 확인·강제 제한할 수 없으므로 한 호출의 초과 소비를 막는다고 주장하지 않는다. 관측된 초과도 완료 처리하지 않는다. 시간 초과는 생성한 CLI process tree만 중단하며 backend 중단 여부·추가 요청·앱 대화 사용량은 알 수 없다. 예산 소진은 명시적 예산 연장이 필요하며, 횟수·모델 순서 소진이나 미확인 사용량은 원인 검토·보고서 보존·명시적 정리가 필요하다. 승인·재개·예산 경계를 자동 완화하지 않는다.
