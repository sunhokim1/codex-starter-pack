# 검증 경계 단계 전달

이 문서는 선행 단계 기록이다. 최종 controller schema=3과 제한된 복구는 RECOVERY_HANDOFF.md가 추가하며 여기의 schema=2 설명은 해당 단계의 증거다.

`verification_gates`의 소스 후보를 구현했다. 외부 컨트롤러가 설정된 실제 검사를 실행한 뒤 통합 단계의 근거로 사용해야 한다. 이 구현 모델의 `verification=[]`와 완료 응답은 검사 성공 근거가 아니다.

## 현재 계약

- `controller.schema=2`다. schema=1의 final 증거 복사를 제거했고 자동 상태 변환을 하지 않는다. status는 구 상태를 읽기 전용으로 안내한다. 기존 완료 작업·보고서를 보존하고 원래 runtime에서 확인한 뒤 명시적으로 정리·보관해야 한다.
- task는 모델 소스 후보와 별도로 설정된 전체 검사를 controller subprocess로 실행해 통과해야 완료된다. 모델이 `verification=[]` 이외의 검사 주장을 반환하면 거부한다. 검사 프로세스가 코드·설정·환경을 바꾸거나 예산을 넘기면 성공 응답이어도 완료하지 않는다.
- project는 모든 task 완료 뒤 집계 `milestone` 검사와 `final` 검사를 별도 scope로 실행한다. quick은 task 뒤 final을 실행한다. 모든 scope가 전체 설정 명령을 유지한다. milestone 실패 시 final은 실행하지 않는다. 완료 판정은 실제 성공한 필수 검사가 최소 하나 있어야 하며 전부 unset/생략이면 완료하지 않는다. 일부 unset은 계속 unset으로 표시하고 통과로 주장하지 않는다.
- milestone/final의 실패·중단은 완료 task를 되돌리지 않는다. `resume --reconcile verification`은 보고서와 부분 수정에 대한 명시적 검토이며 검사만 다시 실행한다. 모델·선택·계획 호출을 추가하지 않는다. 완료 task 재실행은 계속 금지한다. 종료된 전체 완료 상태의 resume도 검사·구현을 반복하지 않는다. 설정·runtime 변경은 재개를 거부한다. 실패 gate의 외부 수정은 명시적 reconciliation 없이 수용하지 않는다.
- `verification.run_checks(project, commands, deadline, state_sha256, scope='task', relevance=None)`와 `validate_results(..., relevance=None)`, `satisfied(..., relevance=None)`가 연결점이다. required/irrelevant_skipped/unset을 구분한다. 정상 nonzero는 실제 exit_code를 보존한다. timeout은 failed/실행됨/종료코드 미확인과 부분 출력을 기록한다. launch failure와 시간 예산 소진은 required/미실행과 구체적 사유다. producer와 명령·scope·목록 전체를 확인해 model_report나 누락 검사를 거부한다.
- `relevance`는 controller가 모델 출력과 별개로 전달하는 명시적 사용자 검토다. 각 proof는 name/command/scope/state_sha256/reason/review_id/source=explicit_user_review를 모두 가져야 한다. 현재 proof가 불완전·오래됨·모델 출처이면 전체 명령을 실행한다. 생략 증거의 완료 판정에는 원래 proof가 필요하다. 공개 CLI에는 이를 입력하는 경로가 없으므로 기본은 전체 검사다. 사용자 설정이나 계획에서 생략 정책을 추론하지 않는다.
- `fingerprint(workspace, configuration, tooling=None)`은 환경 지문과 별도 tooling 식별을 포함할 수 있다. controller stamp는 전체 작업 공간/설정과 현재 환경 해시를 포함한다. 환경 원문은 기록하지 않는다. 확인할 수 없는 외부 입력은 캐시의 안전성을 증명할 수 없으므로 기본 CLI는 캐시를 사용하지 않는다.
- `EvidenceCache`는 인스턴스 메모리 내에서만 동작한다. embedding controller의 `tooling_identity={complete:true,sha256:...}`는 모든 도구·의존성·외부 입력·가정의 동일성을 controller가 독립적으로 확인했다는 명시적 보증이다. 이 보증은 Rev/구현 모델에게 받지 않는다. 동일 코드/설정·검사 정의·scope·도구 식별·환경에서 성공한 subprocess 증거만 깊은 복사해 재사용한다. 불확실/실패/미실행/미설정은 캐시하지 않으며 다른 scope나 프로세스로 넘기지 않는다. tooling 버전 확인이 없는 기본 실행은 매 gate에서 실제 subprocess를 요구한다.
- `controller.gate_records`, `milestone_checks`, `final_checks`, `gate_status`를 별도 보관한다. 상세 근거는 private `reports/gates-*.json`의 scopes/checks/cache_hit/error/elapsed다. stdout은 각 scope의 실제 상태·명령·실행 여부·종료 코드와 gate 오류·보고서 경로를 구분한다. 모델 raw 보고서는 계속 모델 시도 보고서에 별도 보관한다. gate 시간은 전체 활성 예산에 합산하지만 유료 CLI 호출 수를 늘리지 않는다. 중단된 gate의 시간도 기존 보수적 재개 규칙을 적용한다.

## fixture와 실제 점검

기존 `tests/test_controller.py`에 16개 fixture를 추가해 총 51개다. 기존 root `tests/test_rev_controller.py`가 같은 모듈의 모든 TestCase를 discovery하므로 새 검증 fixture도 root 검사 대상이다. 모델·네트워크·다운로드·검사 subprocess는 mock이며 비교 품질 평가가 아니다.

추가 fixture 범위는 거짓 모델 성공/누락 증거, 전부 unset, 명시적 생략·오래된/불확실한 관련성, nonzero·timeout·launch failure·미실행 예산, 작업 중 변경·예산 초과, task/project milestone/final, gate 실패/중단과 명시적 재개, 완료 모델 재호출 방지, schema=1 거부, 동일 캐시 hit 및 코드·설정·명령·scope·tooling·환경 무효화다. toolchain 미확인·실패·미실행의 캐시 거부도 포함한다.

이 단계에서 실제 수행한 보조 점검은 수정 Python과 root discovery adapter 총 5개의 AST 분석 성공, 보호 대상 114개 SHA256 일치(변경/누락 0개)다. 이는 fixture 실행이나 실제 설치·추론의 증거가 아니다. 새 source manifest도 최종 파일 집합으로 갱신하며 통합 단계는 controller의 실제 root 검사 결과와 package integrity 결과를 별도로 확인해야 한다.

설정된 전체 검사는 외부 컨트롤러 소유이므로 이 모델이 실행하지 않았다. 아직 미충족인 검증 gate는 실제 root unittest discovery의 성공 결과다. lint/typecheck/build/acceptance는 현재 미설정이며 통과가 아니다. 실패하면 실제 subprocess 출력과 원인을 보존하고 해결해야 한다. 실행하지 않은 모델 보고 검사를 acceptance로 세면 안 된다.

기존 bootstrap `.ai/sev.json`·`.ai/verification.yaml`과 보관 릴리스·공유 설치·개인 skill·사용자 프로젝트 설정을 변경하지 않았다. 새 배포 기본 검사 명령도 unset 그대로다. 실제 Rev 추론은 이 호스트의 하드웨어 제약으로 수행하지 않았다. 기존 설치의 실제 이전, manager/skill·활성 호환 진입점 전환·package 검증, 마지막 단계의 typed 자동 복구는 후속 작업이다. commit/push/publish/install은 수행하지 않았다.
