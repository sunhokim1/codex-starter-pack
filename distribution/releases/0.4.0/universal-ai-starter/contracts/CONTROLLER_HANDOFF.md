# 순차 컨트롤러 단계 전달

이 문서는 선행 단계의 기록이다. 현재 검증 API와 controller schema=2, milestone/final 경계는 `VERIFICATION_HANDOFF.md`가 대체한다. 아래 schema=1 및 final 복사 설명은 당시 상태이며 현재 구현에 적용하지 않는다.

`controller_execution` 소스 후보를 구현했다. 새 경로는 `assets/runner/run.py`(작은 요청), `project.py`(큰 목표), `controller.py`이며 root discovery는 `tests/test_rev_controller.py`가 연결한다. 루트 호환 진입점·manifest는 후속 통합 단계까지 그대로다. 보관 릴리스와 bootstrap `.ai/sev.json`·`.ai/verification.yaml`, 실제 설치·개인 skill을 변경하지 않는다.

큰 목표는 읽기 전용 Sol 계획 한 번 뒤 각 구현 작업을 Rev로 선택한다. 작은 요청은 계획 없이 Rev로 간다. 사용자 task override → CLI global override → 설정 global override → Rev 순서이며 planning_model은 별도다. planner의 실행 모델 지정을 거부한다. 사용자 override는 Rev client 생성·접속을 건너뛴다. 유료 분류·SEV 실행·하위 에이전트·자동 복구가 새 경로에 없다. Rev의 공식 `/score` 변환과 잠정 기권 정책은 기존 `rev.selector.select`를 사용한다.

## 다음 단계 인터페이스

- `Controller.start(goal, request=None, mode='project'|'quick', execution_model=None, task_overrides=None, max_calls=20, max_seconds=3600, write=False, executable='codex')`는 새로운 `.ai/rev-workflow/` 상태만 만든다. 기존 Rev 상태나 구 `.ai/project-workflow/state.json`이 있으면 덮어쓰지 않는다.
- `Controller.resume(write=False, approve=None, reconcile=None, max_calls=None, max_seconds=None, task_overrides=None)`는 동일 project/config/runtime·작업 공간을 확인한다. uncertain 작업은 명시적인 같은 task/plan reconciliation이 필요하다. 완료 작업은 재실행할 수 없다. 사용자 task override 변경은 미완료 작업에만 허용하고 private 변경 기록을 남긴다. 전역 설정·목표는 자동 바꾸지 않는다.
- 상태 기본 계약은 version=4, 선택 확장은 `controller.schema=1`이다. `rev.contracts.validate_state`는 선택 controller 객체와 task 상세 필드를 허용하지만 실행 가능성은 `runner.controller.validate_state`가 별도로 확인한다. controller schema가 없는 기본 v4 상태도 자동 재개하지 않는다. `status(project)`는 구 상태를 읽기만 하고 원래 runtime 확인·명시적 reconcile/archive를 안내한다.
- `context.build(state, task, exclude_record=None)`는 필수 전체 goal/facts/risks/constraints/uncertainty와 완전한 현재 task를 보존한다. 직접 완료 의존 결과와 같은 task의 직전 시도만 담는다. 각 의존 결과/직전 시도는 16384 bytes, 전체 의존 결과는 65536 bytes 이하며 초과 시 자르지 않고 중단한다. 최종 Rev 계약의 byte/token 상한도 적용한다.
- 완료 결과는 `handoff{summary,interfaces}`, controller가 관측한 `changed_files`, `check_results`, private `report_path`, 전체 `evidence`다. 상세 raw CLI 이벤트·오류·검사는 private 보고서에 보관한다. stdout은 간단한 상태·결과·실제 체크 상태·실패·경로다. 알려진 비밀 입력은 문맥에서 조용히 지우지 않고 거부한다. 기존 redaction은 최선 노력이며 완전한 비밀 탐지 주장이 아니다.
- `codex.invoke(executable, model, project, prompt, timeout, schema, write, phase)`는 한 번의 관측 가능한 CLI 호출과 `usage/response/error/exit_code/stdout/stderr`를 반환한다. 실패·timeout의 이벤트도 가능한 끝까지 파싱해 사용량을 보존한다. `codex.aggregate(attempts)`는 전체 합계와 알려진 부분합·미확인 수를 구분한다. 각 attempt는 공통 사용량 계약이고 상세 records와 같은 index다. retry phase와 operation으로 명시적 계획/구현 재시도를 구분한다. CLI가 backend 모델·요청 횟수를 증명하지 않아 기본 실제 모델/요청 수는 null이다. app 대화 모델은 바뀌지 않는다.
- 모델 호출 예산은 예약 횟수이며 실제 관측 CLI 횟수와 구분한다. 활성 시간에는 선택·실행·검사가 포함되고 실패도 유지한다. 강제 중단의 불확실 호출은 예약을 돌려주지 않으며 마지막 활성 시점 이후 시간을 보수적으로 반영한다. 미관측 token은 null이다.
- `verification.run_checks(project, commands, deadline, state_sha256, scope='task')`, `validate_results(checks,commands,scope)`, `satisfied(checks,current_sha256)`, `fingerprint(workspace,configuration)`이 후속 검증 단계의 연결점이다. 지금은 관련성이 불확실하므로 전체 설정 검사를 유지한다. 모델은 verification=[]로 후보만 반환한다. 모든 설정 명령을 덮는 동일 지문의 controller subprocess 증거만 작업 완료를 허용하고 전부 unset이면 중단한다. 마지막 동일 전체 코드·설정 지문 증거를 final scope에 재사용하며 변경 뒤 캐시는 없다. relevance/milestone 등 확장 정책은 별도 검증 단계가 담당한다.
- 재시도·승격·재계획을 자동 실행하지 않는다. typed code/plan capability 복구와 bounded 자동 escalation/replan은 마지막 단계에서만 추가해야 한다. 현재 RevError kind/action은 report에 남기고 부분 수정 검토·명시적 재개만 안내한다.

## 실제 보조 점검과 남은 범위

최종 보조 점검에서 새 runner Python 12개, 계약 확장 1개, bundle/root test loader 2개(총 15개)의 AST 분석이 성공했다. source manifest 50개 파일의 SHA256이 일치했고 보호 대상 114개 파일의 SHA256 변화·읽기 실패는 없었다. 35개 controller fixture 정의를 추가했으나 실행은 controller 소유이므로 이 구현 모델이 테스트를 실행하지 않았다. fixture는 모델/Rev/검사를 mock으로 대체하며 실제 inference·유료 호출·코딩 비교가 아니다.

실제 Rev 다운로드·로드·추론·설치·사용자 프로젝트 실행은 하지 않았다. 기존 Windows/Iris Xe/메모리 제약과 미해결 environment lock은 그대로다. 지원 환경의 실제 설치, manager/skill·배포 연결, 상세 검증 정책, 최종 실패 복구는 각각 후속 단계에 남는다. 기존 공유 SEV의 사용 여부를 이 단계가 조사하거나 삭제하지 않았다. 새 distributable 설정 예시는 이전 안내용이며 현재 사용자 설정을 덮어쓰지 않는다. root regression과 최종 package 검사는 controller가 수행한다. commit/push/publish/release는 하지 않았다.
