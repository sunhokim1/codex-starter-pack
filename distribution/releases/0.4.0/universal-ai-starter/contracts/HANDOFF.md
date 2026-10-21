# 다음 단계 전달

현재 작업은 `release_contract`이며 새 소스는 `distribution/releases/0.4.0/universal-ai-starter/`이다. 루트 manifest·호환 스크립트는 0.3.3을 유지한다. 신규 runtime 설치·연결 전환은 아직 구현하지 않았으며 이 단계의 범위 밖이다.

변경 파일은 이 번들 전체와 루트 `tests/test_rev_contracts.py`뿐이다. 번들에는 `AGENTS.md`, `README.md`, `release.json`, `assets/rev/contracts.py`, `contracts/upstream.lock.json`, 계약 안내·예제·공식 원문 증거와 `tests/test_contracts.py`가 있다. 기존 `.ai/verification.yaml`의 git 변경 표시는 작업 시작 전부터 있었으며 수정하지 않았다.

후속 구현은 `validate_lock`, `verify_artifacts`, `require_installable`, `score_request`, `validate_request`, `validate_response`, `validate_connection`, `validate_models`, `execution_override`, `validate_state`, `read_status`, `resumable_tasks`, `validate_usage`, `validate_evidence`, `evidence_satisfies` 인터페이스를 사용한다. 상세 필드는 `contracts/examples.json`과 `contracts/README.md`를 따른다. 상태는 version=4, 연결·공급망 계약은 version=1이다. 구 version=3 상태를 읽을 수 있으나 자동 재개·변환·덮어쓰기하지 않는다. 완료 task는 재개 대상에서 제외한다.

검증한 공식 핀은 source `7090e4458075865853cdc791b81436d580a7dc73`, adapter `6c0775534ff1759649aec470fc55d41c9b698219`, base `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, checkpoint SHA256 `6417fd6b8f41449730957f827b8d009ce69d5feadaddd41951a3dff8ad772b96`이다. 제공된 핀과 일치한다. `torch==2.14.0`, `transformers==5.17.0`은 upstream 선언이며 로컬 지원 확인은 아니다.

미해결 항목은 lock의 `unresolved`에 있다. 직접 의존성 네 개의 정확한 버전·wheel 무결성, base 비 LFS 파일 해시, 하드웨어 지원, 인증 gateway·검증된 로더·tokenizer row 제한·timeout 처리는 후속 단계에서 해결해야 한다. 미해결 lock은 설치 가능으로 인정하지 않는다. Windows Iris Xe/낮은 가용 메모리에서 실제 모델 smoke는 하드웨어 제약으로 미실행이다. source/API 증거 수집은 작은 공식 텍스트·메타데이터만 받았으며 모델 파일·유료 호출·비교 평가는 실행하지 않았다.

실제 보조 점검: Python 세 파일 AST 구문 분석 성공. 보호 지문 114개 파일에서 변경 0개. 기존 루트 ZIP SHA256은 제공된 `651afe5f6aafdd1bd83d788617b2e9197f0ab90c5e23c7fdc0044ded21adee21`과 일치했다. 공식 의존성 원문의 첫 경로 조회가 404여서 실제 위치 `serve/modal_image.py`에서 확인했다. 테스트·패키지 회귀 실행은 컨트롤러 소유이며 이 작업 모델은 실행하지 않았다. fixture는 비교 품질 평가나 실제 설치/추론 검증이 아니다.

컨트롤러가 루트 unittest discovery를 실행하면 신규 root loader를 통해 계약 fixture 10개가 포함된다. 기존 보관 번들 검사는 기존 root discovery 연결을 유지한다. 후속 통합 단계에서 최종 소스의 packaging·manifest 연결과 실제 required 검증을 수행해야 한다. 기존 SEV·개인 skill·다른 프로젝트 연결을 삭제하거나 덮어쓰지 않는다.
