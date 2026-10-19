# Universal AI Starter 개발 지침

이 저장소는 범용 템플릿, 로컬 SEV 선택기, 단일 Codex 실행기와 순차 controller를 배포한다. Python 3.11+와 표준 라이브러리 기반 회귀 검사를 사용한다. 모델 추론 의존성은 `assets/sev/requirements.txt`에 있다.

## 지도

| 영역 | 파일 | 검증 |
| --- | --- | --- |
| 생성·채택 | scripts/scaffold.py, bootstrap.ps1 | tests/test_regressions.py |
| 설치·배포 | scripts/install_sev.py, package_starter.py, release.json | 같은 회귀 검사와 package --check |
| 분류·서비스 | assets/sev/ | 입력 형식·인증·서비스 생존 모형 검사; 실제 추론은 별도 |
| 단일 실행·순차 제어 | assets/runner/run.py, project.py | 완료 상태·검증 소유자·실검증·재개 경계 |
| 개인 기록 | assets/runner/runtime_safety.py | 원자적 쓰기·권한 실패·마스킹·콘솔 최소화 |
| 생성 템플릿 | assets/starter/ | 실제 파일 생성·기존 사실 보존·미초기화 검증 |

`assets/starter/AGENTS.md`는 생성 프로젝트의 템플릿이다. 해당 문서의 내용과 예시는 스타터 저장소의 실제 프로젝트 사실이 아니다.

## 보존과 변경

- 사용자 변경·원본 ZIP·기존 프로젝트의 사실·명령·모델 매핑을 보존한다. reset/clean/일괄 초기화하지 않는다.
- 새 템플릿에는 특정 앱·게임의 사실이나 존재하지 않는 명령·경로를 넣지 않는다.
- 하나의 결함과 연결된 계약을 한 변경 단위로 다룬다. quick와 controller의 검증 책임을 함께 고려한다.
- 현재 단일 모델·순차 실행·사용자 override를 유지한다. 하위 에이전트·자동 병렬 작업·유료 분류·새 프레임워크·자가학습을 임의로 도입하지 않는다.
- 공용 환경 실험은 임시 target/runtime/skills와 자동 시작 비활성으로 격리한다. 일반 회귀 검사에서 실제 설치·모델 호출·서비스 포트를 열지 않는다.
- 기존 런타임·개인 스킬을 덮어쓰지 않는다. 새 버전을 준비하고 확인한 뒤 프로젝트를 연결한다. 실패 시 복원·중단 한계를 보고한다.
- 비밀값은 환경/비밀 저장소 참조로 전달한다. 비밀 원문을 보고서·로그·예시에 넣지 않는다. 마스킹은 완전한 비밀 탐지 기능이 아니다.
- 요청·모델 출력·소켓 JSON·실행 설정은 타입·크기·경로·상태를 검사한다. planner의 승인 boolean은 사용자 권한 자체를 대체하지 않는다.
- 검증을 약화하거나 미실행 검사를 통과로 바꾸어 완료 처리하지 않는다. 모델의 결과와 검증된 최종 완료를 구분한다.

## 실제 검증

```text
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/package_starter.py --check
```

소스 변경 후 manifest가 오래되면 `python scripts/package_starter.py --output <소스 밖 ZIP 경로>`로 재생성하고 검사한다. 검사·패키징을 통과시키기 위해 무결성 검사를 끄지 않는다. 테스트 0개 실행을 통과로 보고하지 않는다. 실제 Codex·추론·Windows 설치·ACL 검증은 모형 회귀 검사와 구분해서 보고한다.

실제 파일과 검증 명령이 바뀌면 관련 문서도 갱신한다. 코드 변경·실패·새 우려가 없으면 같은 검사를 반복하지 않는다. 완료 보고는 변경, 실제 검증, 미실행 범위와 남은 위험을 간결히 설명한다.

## 지속 개선

`CONTINUOUS_IMPROVEMENT.md`의 남은 backlog를 따른다. 권한·예산 안에서 문제 재현 → 작은 수정 → 실제 검증 → 결과 기록의 회차를 진행한다. 보호 조건을 스스로 완화하거나 예산·재시도·외부 게시 권한을 확대하지 않는다. 지침 추가만으로 자동 실행이 시작된다고 보고하지 않는다.
