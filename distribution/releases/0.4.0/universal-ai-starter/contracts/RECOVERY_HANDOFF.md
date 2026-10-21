# 마지막 실패 복구 단계 전달

선행 distribution_migration의 controller 검사 통과 전달을 근거로 마지막 소스 단계를 진행했다. 기존 bootstrap controller 상태는 수정하지 않았다. 전체 설정 검사는 계속 외부 controller 소유다. 소스 후보의 완료 응답과 fixture 성공은 최종 controller 검증 통과를 대신하지 않는다.

## 구현 계약

controller schema=3은 schema=1/2의 자동 재개를 거부하며 status는 읽기 전용으로 보존한다. 새 recovery 모듈은 environment/transient/code/plan 원인과 필요한 행동을 기록한다. 환경·시간 초과·기권·일반 검사 실패·불확실성은 자동 역량 판정이 아니다. 모든 부분 수정·중단은 명시적 reconcile 전까지 멈춘다. 실패한 gate는 검사만 재실행하고 완료 구현을 호출하지 않는다.

사용자 검토 근거는 현재 보고서·작업 공간 SHA256과 연결하며 model_report·오래된 검토·비밀·과대 입력을 거부한다. 확인된 code 역량 실패만 설정된 worker/main/escalation 순서로 승격한다. 환경·일시 오류 기록은 역량 실패 근거로 재분류해 승격할 수 없고 사용자 실행 override도 승격을 막는다. 같은 모델의 제한된 명시적 재시도와 승격을 구별한다. 호출 실패 사용량과 모르는 backend 모델·요청 횟수는 보존한다.

재계획은 확인된 dependency/interface/design 변경에만 Sol 읽기 전용 호출을 추가한다. 기존 task ID·완료 정의·위험·승인 경계를 지키는 제안을 저장하고 별도 --accept-replan 전에는 실행하지 않는다. 이력과 완료 증거를 보존한다. 재계획이 실패·중단되면 구 계획으로 구현을 이어가지 않는다. 범위 확대·새 작업은 별도 명시적 승인이 필요한 흐름이며 재계획 수락만으로 허용하지 않는다.

전체 retry/escalation/replan 횟수와 호출·시간·토큰 예산을 보존한다. 새 템플릿은 1/2/1회, 2,000,000 input+output token 예시이며 실제 프로젝트 설정은 덮어쓰지 않는다. cached input은 부분집합이므로 합산에서 중복하지 않는다. 미확인 호출 사용량은 null을 유지하고 유한 토큰 예산에서는 추가 실행·완료를 중단한다. coding CLI가 시작되지 않은 Rev 선택 실패는 별도로 구분한다. 토큰 예산은 사후 관측과 후속 호출 허용 기준이며 단일 backend 호출 도중의 강제 상한을 보장하지 않는다.

## 검증과 남은 경계

집중 fixture는 공식 모델 호출·Rev·검사 subprocess를 mock으로 대체한다. 오류 유형, 시간 초과, 부분 수정·강제 중단, 검사 중단, override, 횟수·호출·시간·토큰 소진, 확인된 승격·재계획과 변경 없는 경우, 승인, 실패 사용량, 완료 작업 보존, 실패한 재계획의 구 계획 재실행 금지를 다룬다. 이는 비교 품질 평가나 실제 추론이 아니다. 실제 보조 명령·종료 코드·개수, 패키지 SHA256·entry/hash 대조와 보호 fingerprint 결과는 루트 private .ai/reports/rev-failure-recovery-evidence.json에 별도 기록한다. 설정된 root unittest의 최종 subprocess 결과는 외부 controller가 기록한다.

최종 소스 변경 후 manifest/release.json/0.4.0 ZIP을 갱신하고 root·bundle 패키저 byte 일치와 entry별 source/hash를 대조한다. 기존 bootstrap 두 파일과 보관 release/source/ZIP 113개는 선행 fingerprint와 대조한다. manifest는 의도된 변경 대상이다. 이전 단계의 package SHA256은 최종 소스 증거로 재사용하지 않는다.

실제 사용자 설치·기존 연결 이전·공유 SEV 삭제·개인 skill/runtime 교체·startup/ACL/auth 변경·모델 다운로드·유료 호출·비교 평가·게시·commit/push를 실행하지 않았다. Windows 11 Intel Iris Xe/CUDA 없음/저가용 메모리에서 실제 Rev inference는 하드웨어상 미검증이다. 지원 호스트 environment lock 완성과 실제 smoke는 별도 자원·권한이 필요하다. 선택 latency/memory·성능·절감 효과를 주장하지 않는다. 기존 설치 사용과 명시적 격리 연결 이전은 MIGRATION.md를 따른다.
