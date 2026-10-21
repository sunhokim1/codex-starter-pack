# Rev 공급망·상태 계약

## 범위와 공식 근거

2026-10-20에 [공식 소스](https://github.com/robbalian/rev/commit/7090e4458075865853cdc791b81436d580a7dc73), [공식 모델 카드](https://huggingface.co/robbalian/rev-qwen3.5-4b/blob/6c0775534ff1759649aec470fc55d41c9b698219/README.md)와 Hub revision API를 확인했다. 원문·URL·SHA256은 `provenance/index.json`에 있다. 원문 파일은 실행 코드가 아니라 검토 증거이며 MIT 고지는 `provenance/LICENSE.txt`에 보존한다.

`upstream.lock.json`은 기계 판독 가능한 공급망 계약이다. `validate_lock`은 필수 필드·revision·경로·해시·의존성 상태를 검증한다. source commit은 `7090e4458075865853cdc791b81436d580a7dc73`, adapter revision은 `6c0775534ff1759649aec470fc55d41c9b698219`, base revision은 `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`이다. checkpoint SHA256 `6417fd6b8f41449730957f827b8d009ce69d5feadaddd41951a3dff8ad772b96`은 모델 카드와 Hub LFS에서 일치한다. 제공된 핀과 충돌하지 않는다. 체크포인트를 내려받아 해시한 결과는 아니다.

공식 `serve/modal_image.py`가 고정한 직접 필수 의존성은 `torch==2.14.0`, `transformers==5.17.0`이다. `accelerate`, `huggingface_hub`, `fastapi`, `uvicorn`의 정확한 버전은 공식 설치 안내에서 미고정이며 null로 기록했다. 선택 가속기는 이번 필수 의존성에 포함하지 않는다. 이는 로컬 호환성 검증이나 wheel 무결성 검증 결과가 아니다. `require_installable`은 미해결 항목이 있으면 설치를 거부한다. 추후 버전·wheel 해시·하드웨어 지원을 확정해야 한다. base LFS 해시는 기록했으나 tokenizer/config 등 비 LFS 파일의 SHA256은 아직 필요하다.

`verify_artifacts(directory, artifacts)`는 경로 탈출·SHA256 불일치를 거부하고 확인된 경로만 반환한다. 후속 runtime은 검증 후에만 source import/exec와 checkpoint 역직렬화를 수행해야 한다. upstream의 `--revision`은 base에만 적용되고 adapter 다운로드는 mutable하다. 반드시 고정 snapshot의 로컬 checkpoint를 전달해야 한다. `torch.load(weights_only=False)` 전에 확인한다. 검증과 로드 사이 디렉터리는 다른 작성자에게 노출하지 않아야 한다. 이 단계는 로더나 인증 서버를 실행하지 않는다.

## 호출·연결 인터페이스

`score_request(context, instructions, question_id)`는 context의 `task`, `goal`, `facts`, `risks`, `constraints`, `uncertainty`, `dependencies`를 복사해 state에 전부 보존한다. dependencies는 직접 관련 요약·인터페이스·변경 파일·검사 결과만 담는다. 전체 보고서는 private 파일에 보존하는 후속 controller의 책임이다. unknown 필드를 조용히 버리지 않고 거부한다. 공식 `validate_request`는 일반 JSON state와 `questions[{id,instructions,criteria:{option:description}}]`를 받는다. 실행 선택 기준은 worker/main이다. 한글을 보존하며 자동 요약·위험 키워드 분류·문맥 잘라내기를 하지 않는다.

`validate_response(request, response)`는 `answers[id]={choice,probabilities}`, `server_seconds`, `path='rows'`, `rows[{gpu_seconds,batch_rows,batch_padded_tokens,queued_seconds}]`, `generated_tokens=0`을 검증한다. 확률 키·합계·범위·최댓값 choice를 검사한다. 점수는 제시된 옵션에 대한 확률이며 코딩 성공 확률이 아니다. temperature 1.96은 upstream checkpoint 값이지 코딩 보정값이 아니다. 비교 평가를 하지 않았으므로 코딩 품질 임계값을 주장하지 않는다. 초기 보수 정책은 애매한 선택을 중단하여 명시적 모델 선택을 요구하는 것이다. 자동 유료 분류·오류 시 모델 fallback을 금지한다. 실제 선택 임계값은 runtime 단계에서 명시적으로 정하며 검증된 보정값으로 설명하지 않는다.

262144 byte 요청 상한은 로컬 전송 정책이다. 공식 16384 row token 상한과 다르다. 후속 runtime은 고정 tokenizer로 전체 row를 계수하고 초과 시 중단해야 한다. byte 수로 token 수를 추정하거나 필수 위험을 잘라내지 않는다. 오류·timeout·초과는 원인과 재시작/문맥 조정 방법을 보고하고 중단해야 한다.

`validate_connection` 필드: `contract_version=1`, `runtime_version='0.4.0'`, `runtime_id`, `endpoint`, `token_env`, `lock_sha256`. endpoint는 포트가 명시된 loopback IP HTTP만 허용한다. 비밀 원문 대신 환경 변수 이름만 저장한다. DNS localhost·외부 주소·userinfo·query는 거부한다. 실제 bearer 인증·타임아웃·프로세스 생명주기·`POST /ping` metadata 일치는 후속 runtime 책임이다. `/health`는 생존만 뜻하며 준비 상태 증명이 아니다. upstream 서버를 직접 인증 경계로 사용하면 안 된다.

## 모델·상태·재개

`validate_models` 필드: `planning_model='gpt-6.1-sol'`, `execution_model=null|'worker'|'main'`. task의 `execution_model`은 별도 nullable override다. `execution_override`는 task override, global override 순으로 반환하며 null이면 Rev가 선택한다. planning_model은 구현 override가 아니다. 명시적 override는 Rev를 전혀 호출하지 않는다. worker는 `gpt-6-luna`, main은 `gpt-6.1-sol`이다. 큰 목표만 Sol로 계획하고 작은 요청은 계획 호출 없이 Rev로 간다. CLI 요청 모델·backend 확인 actual_model·앱 대화 모델은 별개이며 앱 대화 모델이 바뀌었다고 보고하지 않는다.

새 상태 `version=4`의 필수 필드는 `project`, `configuration`(파일명→SHA256), `models`, `tasks`, `attempts`, `status`다. task는 `id`, `status`, `depends_on`, `execution_model`로 계약을 맺는다. 상태와 상세 계획/보고서 결합은 다음 controller 단계에서 확장할 때 명시적으로 version을 관리한다. dependencies는 먼저 선언된 task만 참조한다. task 상태는 pending/running/completed/failed/interrupted/approval_required다.

순차 controller 확장은 선택적 `controller` 객체와 그 안의 `schema=3`으로 구분한다. task에는 `title`, `instructions`, `approval_required`, `selection_context`, `result`를 추가할 수 있다. 기본 계약과 controller 계약은 별도 검증한다. 기본 version=4에 맞더라도 controller schema·완료 증거가 없으면 새 실행 경로는 재개하지 않는다. 이전 schema=1/2는 읽기 전용 status와 명시적 보관·조정이 필요하다. `assets/runner/README.md`에 새 설정·명시적 이전·상태 경로와 사용량 관측 한계·검토 후 복구를 설명한다.

`read_status(path)`는 구 version=3 및 알 수 없는 상태도 읽어 버전·상태·호환성만 반환하며 파일을 쓰지 않는다. 구 상태를 v4로 자동 변환하거나 model을 execution override로 복사하지 않는다. 원래 runtime으로 상태·완료 결과를 확인하고, 설정·부분 편집·의존성을 검토한 뒤 명시적으로 archive/reconcile하여 별도 새 workflow를 시작해야 한다. 이 단계는 archive 작업 자체를 자동 수행하지 않는다.

`resumable_tasks(state, project, configuration)`는 v4 스키마·프로젝트·설정 지문 일치를 요구한다. running/failed/interrupted/approval_required가 하나라도 있으면 부분 편집 가능성을 이유로 명시적 검토까지 중단한다. 완료 task는 다시 반환하지 않고 완료 의존성을 가진 pending task만 반환한다. 이 함수의 반환은 승인·예산·실행 권한을 부여하지 않는다. 후속 controller는 원자적 private 상태 저장·프로젝트 잠금·승인·예산·실제 완료 검증을 별도로 지켜야 한다.

## 사용량·검증 증거

`validate_usage`는 phase(planning/implementation/retry/escalation/replan), status(succeeded/failed/interrupted), requested_model, actual_model, elapsed_seconds, input_tokens, cached_input_tokens, output_tokens, cli_invocations, backend_requests를 요구한다. 실패한 호출도 같은 ledger에 남긴다. 관측 불가 값은 null이며 0으로 채우지 않는다. cached_input_tokens는 input_tokens의 부분집합이다. 관측한 CLI 횟수는 backend 요청 수나 앱 대화 사용량이 아니다. 비용·캐시 절감 추정은 하지 않는다.

`validate_evidence`는 name, command, scope(task/milestone/final), status(required/passed/failed/irrelevant_skipped/unset), producer(controller_subprocess/model_report), state_sha256, executed, exit_code, reason을 검사한다. unset은 command=null이고 통과가 아니다. irrelevant_skipped는 구체적 사유를 남겨야 하며 관련성이 불확실하면 required로 유지한다. state_sha256은 관련 코드·설정·검사 명령의 동일 상태를 나타내야 한다. `evidence_satisfies`는 동일 지문의 controller subprocess 통과만 인정하고 model_report는 인정하지 않는다. 전체 required 목록과 완료 판정은 controller 단계 책임이다.

`provenance/protected-fingerprints.json`에는 작업 시작 시 private bootstrap 연결·검증 설정, 기존 배포 소스/metadata/ZIP, 루트 manifest의 SHA256만 기록한다. 비밀 원문은 포함하지 않는다. 이는 기존 사용자 변경을 되돌리기 위한 기준이 아니라 이 단계에서 추가 변경하지 않았는지 확인하는 기준이다.

검증 확장은 `VERIFICATION_HANDOFF.md`를 따른다. task 성공 뒤 project 집계 milestone과 final을 별도로 검사한다. schema=1의 final 증거 복사와 자동 재개를 허용하지 않는다. 관련성 검토가 불확실하면 전체 명령을 실행하며 CLI는 검사 캐시를 기본 사용하지 않는다.
