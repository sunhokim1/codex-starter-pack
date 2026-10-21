# Rev 순차 실행
실패·중단 뒤에는 private 보고서와 부분 수정을 검토하고 명시적으로 --reconcile TASK를 사용한다. 승격은 --failure-review의 확인된 역량 실패만 허용하며 실행 override·환경/일시 오류는 승격하지 않는다. 확인된 구조 변경만 Sol 재계획 제안을 만들고 --accept-replan의 별도 수락을 요구한다. 설정된 복구 횟수·전체 호출/시간/토큰 한도와 승인 경계를 유지한다. 입력 계약은 runner/README.md를 따른다.
큰 목표는 runner/project.py start --project <project> --context-file <context.json>, 작은 요청은 runner/run.py를 사용한다. 프로젝트 .ai/rev.json의 명시적 로컬 인증 연결이 필요하다. Sol 계획과 Rev 실행 선택은 분리한다. 실행 override는 --execution-model worker|main이다. resume/status는 기존 기록을 보존하고 완료 작업을 재실행하지 않는다. 설정 변경·구 상태는 명시적 reconciliation/archive가 필요하다. 검증은 controller가 실행한다. 유료 분류·하위 에이전트·비교 평가를 하지 않는다.

소스·클라이언트 자동 설치/업데이트와 선택적 Rev 환경 준비·실제 추론을 구분한다. Windows/CPU를 일괄 차단하지 않으며 `cpu`·`cuda:N`과 `bf16`·`fp16`·`fp32`의 자원·실제 kernel capability를 검사한다. 후보 진단은 로드·추론 성공이 아니다. Intel Iris Xe의 CUDA/XPU 지원을 주장하지 않는다. 부족하거나 미확인인 메모리는 모델 로드를 중단하되 소스 업데이트는 막지 않는다.
