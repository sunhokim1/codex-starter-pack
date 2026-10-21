# Rev 런타임 단계 전달

현재 작업 `rev_runtime`은 0.4.0 독립 소스의 인증 로컬 런타임 구현이다. source 변경은 `assets/rev/`의 selector·loader·service·hardware·optional smoke·문서와 `tests/test_runtime.py`, 루트 discovery 연결 `tests/test_rev_runtime.py`, 번들 README·AGENTS·release manifest이다. 기존 0.3.1/.2/.3, 루트 manifest·호환 경로, `.ai/sev.json`, `.ai/verification.yaml`, 공유 설치와 개인 skill은 수정하지 않는다.

## 후속 단계 인터페이스

- `selector.select(context, models, task_override=None, client_factory=None)`는 override 우선 처리 후 Rev만 호출한다. models 계약은 planning_model과 execution_model을 분리한다. client factory는 `Client(connection, timeout)`을 제공하며 `.ready()`와 `.call('/score', body)`를 사용한다. 성공은 모델 실행 또는 검사 성공이 아니라 실행 모델 선택뿐이다. backend 실제 모델은 확인 전 null이다.
- context는 계약의 task/goal/facts/risks/constraints/uncertainty/dependencies 전체이다. controller는 전체 필수 목표·제약·위험을 보존하고 dependencies에는 직접 관련 요약·인터페이스·변경 파일·검사만 넣어야 한다. 런타임은 잘라내지 않는다. 262144 bytes 또는 공식 tokenizer row 16384 tokens를 초과하면 중단한다.
- `RevError.kind/action`은 정적이고 비밀을 반영하지 않는 복구 원인·행동이다. hardware/environment/integrity/identity/authentication/configuration/input/oversize/timeout/service/protocol/abstention/readiness/model/startup을 구분한다. 이는 마지막 단계의 code/plan capability 복구 분류를 대신하지 않는다. 오류·기권은 유료 분류나 자동 모델 대체로 이어지지 않아야 한다.
- `hardware.diagnose()`, `installation_modes(report)`, `require_hardware(report, device)`는 다운로드 없는 진단/입장 검사이다. 후보 모드는 실제 inference 성공이 아니다. 정정: CPU 및 Windows CUDA도 선택 경로이며 bf16/fp16/fp32별 모델 메모리 추정과 실제 torch capability를 검사한다. 미확인 자원은 실행 후보로 승인하지 않는다. Intel GPU를 CUDA/XPU 지원으로 간주하지 않는다. 과거 수치와 결과는 당시 관측이며 현재 정책은 assets/rev/README.md를 따른다.
- `service.ensure_started(state, python, base, adapter, environment, token_env, device)`, `status(state)`, `stop(state)`는 별도 새 runtime과 authenticated `/ping`을 사용한다. state는 connection+pid이고 token은 환경에만 있다. 동일 nonce·pid·lock·고정 모델·warm일 때만 재사용한다. state·lock 충돌과 stale state를 자동으로 덮어쓰지 않는다. `/stop`은 worker 실패 후에도 인증/identity를 검사하고 동작한다. start는 본인이 새로 만든 process만 종료하며 기존 pid를 kill하지 않는다. source CLI는 startup/ACL/auth 설정을 변경하지 않는다.
- `loader.load_verified(base_directory, adapter_directory, environment, device)`는 hardware 검사 뒤 pinned source·독립 adapter SHA256·base 전체 snapshot identity·직접/간접 dependency wheel 및 installed RECORD를 확인한다. `.pth` 자동 실행과 미검증 bytecode를 방지하기 위해 새 서비스는 `-I -S -B`로 시작하며 검사 후에만 site-packages를 import한다. 실제 호환 venv를 준비하고 review된 environment lock을 제공하는 일은 설치 단계에 남아 있다.

## 검증과 한계

공식 source를 고정 URL에서 다시 읽고 앞 단계에 보존한 모델 카드/metadata를 확인했다. 실제 adapter/base checkpoint 다운로드나 모델 import/로드/추론은 하지 않았다. 의존성 버전·wheel을 만들어내거나 설치하지 않았다. 공식 torch/transformers 외 미고정 버전과 모든 wheel/RECORD는 지원 환경에서 검토해야 하며 shipped environment template은 의도적으로 unresolved이다. `contracts/upstream.lock.json`의 unresolved 기록은 앞 단계의 미해결 근거를 보존한다. 인증 gateway와 loader source는 이번 단계에서 구현했지만 실제 설치·inference 검증 완료를 뜻하지 않는다.

실제 보조 점검은 Python 11개 파일 AST 구문 분석과 read-only hardware 진단이다. Windows 11/AMD64, 총 RAM 16847327232 bytes, 가용 RAM 약 2.7~2.8GiB가 관측되었고 CUDA/NVIDIA는 확인되지 않아 설치/로드 모드는 비어 있었다. CIM probe는 사용할 수 없었으며 read-only registry fallback으로 `Intel(R) Iris(R) Xe Graphics`를 확인했다. GPU 전용 메모리는 미확인이다. 메모리 가용량은 시점별로 변한다. 최초 진단에서 외부 PowerShell 인코딩 문제가 발생해 UTF-8 지정과 안전한 decode를 추가한 뒤 재실행했다. 이 결과는 Rev 추론 성공이나 latency/memory 성능 측정이 아니다. 보호 지문 114개 파일은 변경 0개였으며 0.4.0 소스 manifest를 갱신했다.

오프라인 runtime fixture는 24개이며 source encode 형식, 한글/긴 문서와 permission/payment/data-change/unknown-bug 위험 보존, override, planning 분리, 공식 응답 검증, auth/외부 주소, 실제 loopback HTTP fixture, 모델 준비 상태, warm 재사용, pid/stale state, worker timeout 종료, 무결성/하드웨어 차단을 포함한다. 모델 응답은 mock이고 source encode는 fake tokenizer를 쓴다. 실제 tokenizer/model, 실제 설치, CUDA 실행을 검증하지 않는다. 설정된 unittest 및 번들/패키지 최종 검사는 컨트롤러 소유이므로 이 실행 모델은 실행하지 않았다. 선택지 확률은 coding 성공 확률이 아니며 0.80/0.60 선택 정책은 잠정 운영값이다. 비교 평가·유료 모델 호출·성능/절감 주장을 하지 않는다.

다음 단계는 controller/installer/manager와 최종 packaging 통합이다. 기존 SEV의 다른 프로젝트 사용 여부는 이 단계에서 조사하거나 삭제하지 않았다. 새 별도 runtime과 명시적 연결 이전을 제공하고, 알려진 참조만으로 전체 설치가 미사용이라고 단정하지 않아야 한다. private bootstrap 지문과 보관 파일은 그대로 보존해야 한다. 실제 hardware smoke는 `assets/rev/smoke.py`로 준비했지만 지원 자원과 명시적 로드 인자 없이는 실행할 수 없고 여기서는 미실행이다.

## 재시도 소스 수정

이전 컨트롤러 실패의 상세 로그가 private state 읽기 권한 거부로 보이지 않아 그 실패 원인을 확정하거나 해결됐다고 주장하지 않는다. 설정된 검사는 다시 실행하지 않았으며 이 후보 소스를 컨트롤러 검사에 넘긴다.

worker의 비정상 종료를 `/ping` 준비 상태에 반영하고 readiness 필드의 bool/정수 혼동 및 잘못된 CUDA device 표기를 거부하도록 수정했다. `-I -S -B` 격리를 유지하면서 Python 3.13 이하의 base prefix를 사용하는 경우에도 명시한 venv interpreter 경로와 `pyvenv.cfg`로 식별한다. POSIX venv의 마지막 Python symlink는 시작 시 허용한다. 다른 artifact/state 링크 제한은 유지한다. 크기 초과 context는 별도 `RequestTooLarge` 계약 오류를 `oversize`로 변환한다. worker 종료·준비 metadata·구버전 prefix·잘못된 venv fixture를 보강했다.

모델 다운로드·로드·실제 inference·의존성 설치·실제 서비스 설치는 실행하지 않았다. 의존성 lock 완성은 지원 환경의 설치 단계에 남는다. 기존 SEV·private bootstrap 설정·보관 릴리스는 수정하지 않는다. 루트의 `.ai/verification.yaml` git 변경은 이 작업 전부터 존재하며 되돌리지 않았다.

재시도 보조 점검: Python 12개 파일 AST 구문 분석 성공. 보호 지문 114개 중 변경 0개, 읽기 불가 0개. 오프라인 runtime fixture 정의 24개이며 실행 결과는 컨트롤러 소유이다. 새 소스 manifest를 재생성하고 각 파일 SHA256 일치를 확인했다.

## Windows 응답 종료 회귀 수정

컨트롤러가 확인한 실패는 마지막 Content-Length 바이트를 반환한 `HTTPResponse.read1()`이 파일과 최종 socket 참조를 닫은 후, 다음 반복의 `settimeout()`이 닫힌 소켓에 접근한 것이다. 본문 잔여 길이와 `isclosed()`를 먼저 검사해 완료 후 소켓을 다시 사용하지 않는다. EOF에서 선언된 길이가 남으면 JSON이 유효해도 잘린 응답으로 거부한다. 스트리밍 크기 제한과 절대 deadline을 유지하고, 마지막 읽기 뒤에도 deadline을 확인한다.

실제 `HTTPResponse`와 마지막 파일 참조 종료를 재현하는 socket fixture를 사용해 마지막 비어 있지 않은 읽기의 종료, 잘린 Content-Length, 길이 없는 EOF, 크기 제한·최종 읽기 기한을 다루는 회귀 fixture 4개를 추가했다. runtime fixture 정의는 총 28개다. 이 재시도에서 설정된 전체 검사와 fixture 실행은 컨트롤러 소유로 실행하지 않았다. 이전 실패가 해결됐다는 실행 증거는 컨트롤러 검사 결과로 판단해야 한다. 실제 Rev 다운로드·로드·추론은 실행하지 않았으며 기존 하드웨어 및 의존성 lock 한계는 그대로다. 기존 설치·연결·보관 릴리스와 private bootstrap 설정은 수정하지 않았다.
