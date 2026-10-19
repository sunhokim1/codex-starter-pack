# 지속 개선

## 이번 수정의 기준

0.3.1은 템플릿 오염, 미실행 검증 완료 판정, 비정상 SEV 입력 종료를 수정하고, 버전별 설치·복원·개인 기록 보호와 재현 가능한 회귀 검사/패키징을 추가한다. 원래 모델 매핑·가중치는 보존한다. 구체적인 검증과 한계는 `REPAIR_NOTES.md`를 따른다.

## 다음 backlog

1. Windows 실제 격리 설치: Python 3.11/지원 최신 버전, ACL·venv·다운로드·시작 항목·서비스 준비·실패 복원·기존 프로젝트 실행을 확인한다. 모형 테스트 통과를 실제 설치 통과로 대신하지 않는다.
2. 설치 재실행·장애 복구: 현재는 Python 예외·사용자 인터럽트에서 복원하며 강제 종료/전원 장애의 다중 파일 트랜잭션은 자동 복구하지 않는다. durable journal·명시적 recovery와 임의 종료 fault injection을 추가한다. 배포 디렉터리는 자동 삭제하지 않는다.
3. 실행 중단·재개: 자손 프로세스 전체 종료, 중단 뒤 관련 파일 변경과 완료 의존성 재검증을 구현한다. 기존 상태를 임의로 다시 실행하지 않는다.
4. 설정 계약: YAML subset과 모델 parser의 지원 키·오류 동작·schema를 정리한다. 현재 역할 매핑과 사용자 설정은 보존한다.
5. SEV 평가: 한국어/영어·부정문·긴 요청·facts의 위험을 분리된 holdout으로 확인한다. 실제 코딩 성공·시간·토큰·재작업을 비교한다. 같은 예제를 학습과 평가에 재사용하거나 분류 점수를 성공률로 표현하지 않는다.
6. 기록 운영: 마스킹 한계, 보관 기간, 이미 Git에 추적된 민감 파일·기존 로그 점검, 사용자별 동시 접근/설치 권한을 검토한다. 원문 요청이나 출력 전체를 장기 이력으로 복제하지 않는다.

## 회차 절차

사용자가 허용한 목표·시간·작업 수·비용 범위를 먼저 확인한다. 제한이 없으면 근거가 가장 강한 한 항목을 대상으로 진행한다. 기존 사용자 변경·중단 사유를 확인하고 문제·영향·변경 파일·통과 기준을 짧게 적는다.

안전한 재현 → 최소 수정 → 관련 회귀 검사 → diff/생성물 검토 → 변경 결과와 다음 작업 기록 순서로 진행한다. 미설정·미실행·실패는 통과가 아니다. 모형과 실제 실행을 구분한다. 같은 최종 상태를 의미 없이 반복 검사하지 않는다.

새 권한·명확화·예산이 필요한 단계에서는 검토 가능한 결과를 준비하고 필요한 결정만 요청한다. 이미 허용된 가역적 수정·읽기·검증에는 재승인을 요구하지 않는다. 중단 작업을 재시도하거나 controller 예산을 확대할 때는 기존 명시적 권한을 따른다. 실패 원인을 분석하고 같은 접근을 무한 반복하지 않는다.

한 회차의 기록은 날짜·문제·변경 목적·실제 검사/개수/종료 코드·미실행 이유·남은 위험·다음 한 작업으로 제한한다. 문서 분량이나 수정 파일 수를 개선의 증거로 삼지 않는다. 이 문서는 스케줄러가 아니며 백그라운드 실행을 시작하지 않는다.

## 다음 실행 요청문

```text
AGENTS.md와 CONTINUOUS_IMPROVEMENT.md를 읽고 남은 가장 높은 우선순위
한 항목을 개선해줘. 기존 사용자 변경과 프로젝트 사실을 보존하고,
재현 → 최소 수정 → 실제 검증 → 결과와 다음 작업 기록까지 수행해줘.
환경 의존 검사는 모형 결과와 구분하고, 비밀값을 노출하지 마.
현재 허용된 범위 밖의 실제 설치·유료 호출·외부 게시·배포는 실행하지 마.
검증 생략이나 보호 조건 약화로 완료 처리하지 마.
```

## 0.3.2 workflow contract

Use schema 3 typed plans and bounded dependency results. Keep per-task SEV selection.
Resume must detect workspace changes and require explicit successful reverification.
Add regression coverage before changing these contracts; compare measured character
counts separately from real token/cost/quality evidence. Never replay completed tasks.

## 0.3.3 Windows permission preflight

The new release adds the native managed sandbox probe before runtime preparation
and project/skill/startup promotion. Preserve its fail-closed behavior and the ten
feature checks. Packaging and offline regressions are separate from real Windows
installation acceptance. Keep prior release source immutable; continue the existing
installation/recovery backlog without granting permissions automatically.
