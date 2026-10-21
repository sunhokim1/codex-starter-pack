# 0.4.0 개발 지침

이 디렉터리는 Rev 전환의 새 구현 소스이다. 보관된 0.3.1·0.3.2·0.3.3과 보관 릴리스는 변경하지 않는다. 루트 활성 경로는 이 번들을 가리킨다.

| 영역 | 진입점 | 검사 | 계약·문서 |
| --- | --- | --- | --- |
| 공급망·API·상태 | assets/rev/contracts.py | tests/test_contracts.py | contracts/upstream.lock.json, contracts/README.md |
| Rev 로컬 런타임 | assets/rev/selector.py, assets/rev/service.py, assets/rev/loader.py, assets/rev/hardware.py | tests/test_runtime.py | assets/rev/README.md |
| 검증 경계 | assets/runner/verification.py, assets/runner/controller.py | tests/test_controller.py | contracts/VERIFICATION_HANDOFF.md, assets/runner/README.md |
| 순차 실행 컨트롤러·복구 | assets/runner/run.py, assets/runner/project.py, assets/runner/controller.py, assets/runner/recovery.py | tests/test_controller.py | assets/runner/README.md, assets/runner/templates/ |
| 설치·배포 | scripts/install_rev.py, scripts/scaffold.py, scripts/package_starter.py | tests/test_distribution.py | MIGRATION.md, release.json |

Python 표준 라이브러리로 계약을 검사한다. 하위 에이전트, 비교 평가, 유료 분류, 모델 다운로드, 실제 설치를 실행하지 않는다. Python controller만 순차 진행·예산·승인·검증·재개를 담당한다. 모델 성공을 검증 성공으로 간주하지 않는다. README는 한국어로 작성한다. 프로젝트 사실·개인 설정·비밀·기존 설치를 보존한다.


소스 설치는 `.ai/starter-source/`와 `.ai/source-install.json`만 관리하고 기존 지침·설정·연결·완료 기록을 보존한다. 모델·서비스 준비와 소스 설치를 혼동하지 않는다. 실행 연결 이전에만 별도 runtime과 명시적 연결을 요구한다. 실제 프로젝트 설치·개인 skill/runtime 교체·공유 SEV 삭제·startup/ACL/auth 변경·게시를 검증 목적으로 실행하지 않는다.

소스·클라이언트 자동 설치/업데이트와 선택적 Rev 환경 준비·실제 추론을 구분한다. Windows/CPU를 일괄 차단하지 않으며 `cpu`·`cuda:N`과 `bf16`·`fp16`·`fp32`의 자원·실제 kernel capability를 검사한다. 후보 진단은 로드·추론 성공이 아니다. Intel Iris Xe의 CUDA/XPU 지원을 주장하지 않는다. 부족하거나 미확인인 메모리는 모델 로드를 중단하되 소스 업데이트는 막지 않는다.
