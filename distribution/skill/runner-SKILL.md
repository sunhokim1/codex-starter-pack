# Rev 순차 실행
큰 목표는 runner/project.py start --project <project> --context-file <context.json>, 작은 요청은 runner/run.py를 사용한다. 프로젝트 .ai/rev.json의 명시적 로컬 인증 연결이 필요하다. Sol 계획과 Rev 실행 선택은 분리한다. 실행 override는 --execution-model worker|main이다. resume/status는 기존 기록을 보존하고 완료 작업을 재실행하지 않는다. 설정 변경·구 상태는 명시적 reconciliation/archive가 필요하다. 검증은 controller가 실행한다. 유료 분류·하위 에이전트·비교 평가를 하지 않는다.
