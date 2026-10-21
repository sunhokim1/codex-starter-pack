# Rev 로컬 런타임

이 소스는 공식 Rev의 LoRA·pointer head와 `/score` 계약을 사용한다. MiniLM·ONNX·선형 분류기 파일·위험 키워드 분류·유료 분류 호출을 사용하지 않는다. 기존 SEV와 루트 연결 전환은 후속 통합 단계에서 진행한다. 이 단계는 공유 SEV나 개인 skill을 설치·삭제·수정하지 않는다.

## 공식 근거와 입력

[고정 공식 소스](https://github.com/robbalian/rev/blob/7090e4458075865853cdc791b81436d580a7dc73/serve_local.py)와 [고정 모델 카드](https://huggingface.co/robbalian/rev-qwen3.5-4b/blob/6c0775534ff1759649aec470fc55d41c9b698219/README.md)를 기준으로 한다. 원문은 `contracts/provenance/`에 보존되어 있다. source·adapter·base revision과 checkpoint SHA256은 `contracts/upstream.lock.json`을 따른다. upstream의 `--revision`은 base에 적용되므로 adapter를 고정하는 수단으로 사용하지 않는다. 로더는 Hub 다운로드 없이 별도로 제공한 adapter checkpoint를 직접 해시 검사한다.

`selector.select(context, models, task_override, client_factory)`는 `task`, `goal`, `facts`, `risks`, `constraints`, `uncertainty`, `dependencies` 전체를 `state`에 복사하고 `questions[{id,instructions,criteria:{worker,main}}]`를 전송한다. dependencies에는 직접 관련 요약·인터페이스·변경 파일·검사 결과를 전달하고 전체 완료 이력은 넣지 않는다. 런타임은 내용을 잘라내지 않는다. 전체 목표·필수 제약·위험을 줄이지 않고 직접 의존성 자료를 명시적으로 정리해야 한다.

UTF-8 JSON은 최대 262144 bytes이다. worker는 공식 `Scorer.encode`로 정확한 prompt와 tokenizer를 사용하고 row 16384 tokens를 초과하면 forward 전에 중단한다. 문자 수를 token 수로 추정하지 않는다. 한 요청에는 worker/main 질문 하나만 허용하여 batch 메모리를 제한한다. 응답 ID·선택지·최댓값 선택·확률 합·유한성·생성 token 0·row 메타데이터를 검사한다.

점수는 제시된 **선택지 확률**이며 코딩 성공 확률이 아니다. 비교 평가를 수행하지 않았으므로 코딩에 보정된 threshold라고 주장하지 않는다. 현재 잠정 정책은 선택된 항목 확률 0.80 이상, 두 항목 차이 0.60 이상일 때만 그 항목을 반환한다. 그 밖에는 abstention으로 중단하고 사용자가 명시적 실행 모델을 정하거나 문맥을 검토하도록 안내한다. 이 수치는 보수적 운영 정책일 뿐 품질·성공률·절감 근거가 아니다. 오류·timeout·초과 입력·기권 시 Sol이나 유료 분류로 자동 대체하지 않는다.

`planning_model=gpt-6.1-sol`은 구현 override가 아니다. `execution_model` 또는 task override가 지정되면 client 생성·환경 토큰 확인·Rev 로드·접속보다 먼저 반환한다. 반환된 `requested_model`은 CLI 요청용이고 `actual_model=None`은 backend 확인 전의 미확인 상태이다. 앱 대화 모델을 바꾸지 않는다.

## 공급망과 격리 환경

`loader.load_verified(base_directory, adapter_directory, environment, device=0)`는 다음 순서로 동작한다.

1. 실제 하드웨어를 진단하고 허용 후보인지 확인한다. 이 검사 전에는 큰 파일이나 torch를 읽지 않는다.
2. 배포에 고정된 source SHA256과 base provenance를 검사한다. Python 코드 실행은 이미 검사한 메모리의 source bytes만 사용한다. 공식 `load`, `resolve_checkpoint`, 인증 없는 `build_app`은 호출하지 않는다.
3. 검토된 격리 환경 lock의 정확한 버전·원본 wheel SHA256·설치된 RECORD SHA256과 RECORD의 각 파일 SHA256을 검사한다. 직접·간접·도구 배포물 모두 lock에 있어야 한다. 공유 SEV 또는 global Python은 거부한다. interpreter는 `-I -S -B`로 시작해야 하며 `.pth`를 실행하지 않고 검증 완료 후에만 격리 site-packages를 import 경로에 추가한다. `-S`에서 prefix가 base 환경을 가리키는 Python 3.13 이하도 명시한 venv interpreter 경로와 `pyvenv.cfg`로 식별한다. POSIX venv의 마지막 Python symlink는 허용하지만 state·snapshot·site-packages 링크는 거부한다. 무결성 검증·실제 라이브러리 import·모델 로딩·추론 성공은 각각 별도로 확인한다. `environment.lock.template.json`은 의도적으로 `resolved=false`이며 로드를 허용하지 않는다. upstream이 고정한 `torch==2.14.0`, `transformers==5.17.0`은 지켜야 한다. 나머지 버전·wheel은 대상 환경에서 별도로 해석하고 공식 배포 해시로 검증해야 한다. wheel metadata의 `torch==2.14.0`과 해당 공식 CPU wheel의 런타임 표기 `2.14.0+cpu`는 구분하며, 임의로 다른 wheel 버전을 허용하지 않는다.
4. base의 모든 로컬 파일을 고정 Hub revision의 LFS SHA256 또는 비 LFS Git blob SHA1로 검사한다. tokenizer/config/index/vocab/merges와 두 weight shard가 필수이며 원문에 없는 파일·custom code·링크는 거부한다. 비 LFS Git identity를 SHA256 검사라고 표현하지 않는다. adapter는 base와 독립된 revision의 checkpoint SHA256으로 검사하며, deserialize 직전에 같은 열린 handle을 다시 해시 검사한다.
5. 네트워크를 비활성화하고 local snapshot만 `trust_remote_code=False`, `local_files_only=True`로 로드한다. 선택한 CPU/CUDA와 dtype의 실제 torch SDPA·linear 연산 및 host/device 가용 메모리를 다시 확인한다. 검증된 checkpoint만 `torch.load(weights_only=False)`로 읽으며 LoRA와 FP32 pointer head를 병합한다. warm 성공 뒤에만 준비 상태를 올린다.

환경 lock 형식은 `schema=1`, `resolved=true`, 절대 `venv`, `distributions`이다. 각 distribution key는 소문자·하이픈을 밑줄로 정규화한 이름이고 값은 정확한 `version`, 로컬 `wheel`, `wheel_sha256`, `record_sha256`이다. 검토한 lock을 신뢰 근거로 사용하며 설치된 파일에서 해시를 즉석 생성하여 신뢰하지 않는다. pip가 생성한 해시 없는 `.pyc`는 제거하거나 사전에 검토한 RECORD/lock으로 고정해야 한다. 누락된 `.pyc`는 허용하지만 존재하는 미검증 bytecode는 거부한다. 격리 환경 준비와 lock 완성은 모델 로딩 전에 별도 수행한다. 원본 wheel의 공식 해시를 먼저 확인한 후 그 wheel의 RECORD에서 기대 해시를 가져와야 한다. `setuptools` 같은 wheel 내부의 vendored RECORD는 최상위 설치 RECORD가 아니라 그 RECORD가 해시로 검증하는 payload이다. 검증기는 최상위 RECORD 하나를 식별하고 vendored 파일도 빠짐없이 검증한다. 배포 ZIP에는 특정 기기의 resolved lock이나 모델 snapshot을 넣지 않는다. 신뢰한 runtime 디렉터리에서 다른 프로세스가 로드 중 파일을 수정하지 않아야 한다.

## 서비스와 수명주기

`service.ensure_started(state, python, base, adapter, environment, token_env='REV_AUTH_TOKEN')`는 기존 authenticated `/ping`이 pid·runtime nonce·lock fingerprint·고정 모델·warm 결과와 일치할 때만 재사용한다. 모델을 요청마다 로드하지 않는다. 새 서비스는 별도 격리 Python과 별도 state를 요구한다. 기존 SEV state/connection을 그대로 가져오지 않는다.

인증 토큰은 적어도 32자의 무작위 ASCII token으로 환경 변수에 별도로 제공해야 한다. CLI 인자·state·stdout·로그에 토큰이나 작업 문맥을 기록하지 않는다. 토큰 생성·저장·연결 이전은 설치 단계에서 명시적으로 처리하며 기존 계정·ACL·startup 항목을 변경하지 않는다. state에는 비밀 없는 connection metadata와 pid만 배타적으로 쓴다. 서비스의 토큰 환경은 자신이 시작될 때 상속한 값을 사용한다.

서비스는 `127.0.0.1`에만 bind하며 `/health`, `/ping`, `/score`, `/stop` 모두 bearer token·runtime nonce·lock fingerprint를 검사한다. 외부 주소·Origin·중복 인증 헤더·chunked 요청을 거부한다. body와 응답 크기, socket과 전체 요청 수명, tokenizer row와 worker deadline을 제한한다. `/health`는 생존 확인이며 준비 증거가 아니다. `/ping`은 고정 모델 정보·checkpoint SHA256·temperature 1.96·row 제한·warm·준비 상태·pid를 반환한다.

model worker는 별도 단일 프로세스에 한 번 로드한다. 로드 기본 600초(명시적 상한 1800초), score 기본 30초(명시적 상한 900초)이며 timeout/worker 오류 시 해당 worker를 종료하고 준비 상태를 내린다. gateway가 죽으면 worker도 종료되도록 parent 생존을 감시한다. worker가 비정상 종료되면 다음 `/ping`부터 준비 상태를 내리며 이전 warm 결과만으로 준비되었다고 보고하지 않는다. 인증된 `/stop`은 worker가 실패한 상태에서도 사용할 수 있다. state에 적힌 pid만으로 기존 프로세스를 강제 종료하지 않는다. 신규 시작 실패 때만 자신이 방금 만든 `Popen` 프로세스를 종료한다. 이미 존재하는 state나 잠금 파일은 조용히 덮어쓰지 않으며 상태를 조사하고 명시적으로 reconcile/archive해야 한다. 서비스 start/status/stop은 프로젝트 작업을 재실행하지 않는다.

명령 진입점은 다음과 같다. 실제 start는 지원 하드웨어·검토된 환경·별도 자원을 준비한 뒤에만 사용한다.

```powershell
python assets/rev/hardware.py
python assets/rev/service.py start --state <new-runtime-state> --python <isolated-python> --base <pinned-local-base> --adapter <pinned-local-adapter> --environment <reviewed-environment-lock> --device cpu --dtype fp32
python assets/rev/service.py status --state <new-runtime-state>
python assets/rev/service.py stop --state <new-runtime-state>
```

## 하드웨어와 실제 추론 한계

표준 라이브러리로 OS·machine·실제 총/가용 RAM을 읽고 Windows CIM으로 GPU 이름·보고된 memory·driver, `nvidia-smi`로 NVIDIA별 total/free dedicated memory·driver를 수집한다. probe 실패는 미확인으로 남긴다. `AdapterRAM`은 전용 CUDA VRAM의 증거로 사용하지 않는다. `nvidia-smi` 성공도 torch CUDA 지원이나 실제 추론 성공 증거가 아니다.

공식 고정 소스의 `cpu`·`cuda` 경로와 `bf16`·`fp16`·`fp32` 선택을 실제 로더·서비스에 연결한다. Windows라는 이유로 거부하지 않는다. `--device cpu --dtype fp32`를 명시할 수 있으며 `cuda`·`cuda:N` 및 기존 정수 CUDA 인덱스도 받는다. 기본값은 기존 CUDA/bf16이며 자동 fallback·양자화는 없다. Intel Iris Xe를 CUDA 또는 검증된 XPU로 간주하지 않는다. CPU의 저정밀 연산 및 Windows CUDA는 잠긴 torch의 실제 연산 확인과 모델 warmup이 필요하다. 이미 실행 중인 서비스의 모드가 다르면 명시적으로 중지·재시작해야 한다.

기본 `full-resident` 경로의 이전 22.76GiB(bf16/fp16)·39.53GiB(fp32)는 weights 두 벌과 고정 여유를 합친 미측정 보수 정책이다. 보편적 최소 RAM이나 bounded offload의 입장 기준으로 사용하지 않는다. CUDA 경로와 명시적 dtype/kernel 검사는 유지한다.

`loader.load_verified`의 별도 `memory_mode='bounded-cpu'` 경로는 검증된 safetensors header에서 정확한 language backbone tensor 크기, dense decoder/norm block과 제한된 embedding 조회의 작업 공간을 구한다. `offload_directory`, `row_token_budget`, `process_budget_bytes`, `safety_margin_bytes`를 명시할 수 있다. 기본 loader row budget은 16384이며, 아래 고정 smoke 요청은 528을 명시한다. 작업 공간 추정에는 FP32 attention/hybrid 중간값과 allocator 여유, runtime/tokenizer/kernel 여유 1GiB, FP32 pointer head, 병합 buffer를 따로 기록한다. 이 값 역시 실측 최소가 아니다. 현재 available RAM에서 최소 1GiB 이상의 system 여유를 뺀 process budget을 넘으면 할당 전에 거부한다. 외부 watchdog의 budget은 상한이며, 긴 무결성 검사 뒤 RAM이 줄면 로더는 그 상한을 줄일 수만 있다. 줄인 예산에도 같은 tensor/작업 공간 추정이 들어가야 하며 guard나 row를 완화하지 않는다. RAM/process probe 미확인도 거부한다. SSD 용량은 원본과 파생 파일의 저장 공간에만 쓰며 RAM으로 계산하지 않는다.

설치된 Transformers 5.17.0은 `low_cpu_mem_usage`를 무시한다. Accelerate의 기본 disk loader는 mmap 뒤 전체 tensor 복사를 수행하므로 이 경로의 메모리 절약 근거로 사용하지 않는다. `offload.py`는 meta 모델을 만든 뒤 wrapper를 버리고, 원본 checkpoint는 mmap으로 읽는다. LoRA는 FP32 `2*B@A`를 4MiB 행 단위로 계산하고 선택 dtype으로 cast한 뒤, 같은 dtype으로 변환한 base에 한 번 더한다. 양자화하지 않는다. 각 파생 tensor는 별도 regular file에 streaming으로 저장한다. source/base/adapter/environment/dtype/algorithm provenance와 manifest digest 및 각 tensor SHA256을 결합한다. 재사용할 때도 원본에서 기대 결과를 다시 계산하여 검증하며, mutable manifest만으로 신뢰하지 않는다. 원본 snapshot은 수정하지 않는다.

embedding은 전체 가중치를 mapping하거나 복사하지 않는다. 설치된 Qwen3.5의 기본 `nn.Embedding` 호출을 검증된 파생 파일의 행 조회로 대체하고 원래 parameter는 계속 meta로 유지한다. CPU int32/int64 `[batch,tokens]` 입력의 shape·storage·ID 범위를 파일을 열기 전에 검사한다. 로더는 single-row 계획을 전달하며, 공통 `embedding_contract`가 16-token padding을 포함한 행 길이·batch·총 ID 수·출력·단일 행 buffer·indices·무결성 buffer의 상한을 계획과 실제 실행에 함께 적용한다. 반복 ID도 행 하나씩 재조회하며 padding 행도 저장된 byte 그대로 복사한다. `max_norm`, 기본값이 아닌 `norm_type`, `scale_grad_by_freq`, `sparse`, training, embedding parameter/module alias와 사용자 forward/hook은 지원하지 않고 명시 거부한다. 2차원이 아닌 입력과 한도를 넘는 backing storage도 거부한다. dtype·tokenizer·직렬화·temperature·공식 scoring은 바꾸지 않는다.

행 조회마다 같은 열린 regular file을 256KiB 고정 buffer로 SHA256 검증한 뒤 필요한 행만 읽는다. 이 순차 무결성 검사는 전체 tensor materialization과 다르다. byte 크기·link·offset과 조회 전후 파일 identity도 확인한다. 별도 정렬·deduplication·index tensor·gather workspace는 없다. 예를 들어 BF16 `[248320,2560]`, single batch, padded 528 계획은 출력 2,703,360 + 행 buffer 5,120 + indices 4,224 + 무결성 buffer 262,144 = 2,974,848 bytes를 예약한다. scalar 객체·Tensor metadata와 native allocator/kernel 작업 여유는 기존 runtime/activation reserve에 남긴다. decoder/norm의 전체 dense mapping byte 수와 hash buffer는 별도 상한으로 유지하며, 둘 중 큰 materialization reserve를 사용한다. SSD staging 공간에는 여전히 가장 큰 원본 tensor 전체 크기를 계산한다.

forward hook은 각 decoder block과 마지막 norm에 private file mapping을 연결하고 반환 또는 예외 시 meta parameter로 되돌린다. block 범위가 직접 참조되는 convolution weight를 포함한다. hook에서 LoRA를 더하지 않으므로 재로딩에 의한 병합 소실·중복을 피한다. decoder의 tied alias 값이 다르면 거부한다. embedding 대체와 block hook은 반환된 handle로 제거할 수 있다. tiny CPU RoPE buffer와 FP32 pointer head는 실제 CPU tensor로 유지한다. 공식 tokenizer/prompt, temperature 1.96, warmup과 scoring 수식은 그대로 사용하며 Scorer의 입력 device만 meta 대신 실제 CPU로 명시한다.

`offload.py` 코드 hash가 derivation identity의 일부이므로 이 구현으로 실제 실행할 때는 새 작업 소유 derived 디렉터리를 사용한다. 기존 manifest와 identity가 다르면 파일을 쓰기 전에 거부한다. 과거 파생 파일·보고서·실패 증거를 덮어쓰지 않는다. 새 디렉터리도 검증된 원본에서 LoRA를 같은 순서로 계산하고 독립적으로 기대 hash를 재생성해야 한다. 이전 manifest를 고쳐 재사용하지 않는다.

API·상한 계산·검사 계약은 [제한된 embedding 조회 계약](../../contracts/BOUNDED_EMBEDDING.md)에 정리했다.

전체 row 한도는 16384를 유지한다. 선택 계획보다 긴 row나 다중 row는 자원 오류로 명시 거부하며 필수 문맥을 자르지 않는다. 짧은 fixture/score 성공이 16384-token 입력의 안전성을 입증하지 않는다. 로더는 병합 chunk와 block 전후에 fresh RAM·RSS/private memory를 확인한다. 실제 smoke는 이 검사와 별도로 소유한 child process의 주기적 memory/deadline watchdog으로 kernel 실행 중의 위험도 감시해야 한다. 서비스 CLI는 기본 resident 경로이며 `--memory-mode bounded-cpu --offload-directory <task-owned-directory> --row-token-budget <limit>`로 bounded 계획을 명시한다. `--process-budget-bytes`와 `--safety-margin-bytes`도 worker까지 전달한다. 일반 service 실행 자체는 외부 watchdog을 제공하지 않으므로 bounded 실제 실행에는 아래 smoke supervisor를 사용해야 한다. 기존 프로젝트 연결은 자동 변경하지 않는다.

소스·클라이언트 자동 설치/업데이트는 이 메모리 검사나 모델·environment lock·서비스를 요구하지 않는다. 선택 환경 준비와 실제 추론은 별도 단계다. 이번 작업의 격리 환경·고정 원본 준비와 작은 실제 tensor correctness 검사는 전체 모델 추론과 구분한다. RAM 수치는 매 실행 전 새로 읽으며 예전 호스트 측정치를 현재 가용량으로 재사용하지 않는다.

실제 smoke는 지원 하드웨어와 명시적 로컬 자원이 있을 때만 별도로 실행한다. 자동 검사에는 연결하지 않는다.

```powershell
<stdlib-python> -I -S -B assets/rev/smoke.py --allow-local-model-load --python <isolated-python> --base <pinned-local-base> --adapter <pinned-local-adapter> --environment <reviewed-environment-lock> --dtype bf16 --row-token-budget 528 --offload-directory <task-owned-derived-directory> --output <new-private-evidence-directory> --load-timeout 1500 --score-timeout 600 --total-timeout 2400
```

smoke는 private `request.json`을 새 child에 전달하고, 검증된 공식 tokenizer/Scorer encoder로 warmup과 실제 요청 token 수를 모델 파생 처리 전에 검사한다. 한국어 object state가 upstream JSON encoder에서 Unicode escape로 표현되면 UTF-8 byte 수보다 token 수가 크게 늘 수 있다. 현재 고정 smoke 요청은 공식 encoder로 525 tokens(528 padded), 1051 UTF-8 bytes로 확인했으며 기본 row budget 528은 이 요청에만 맞춘 값이다. 다른 요청이나 tokenizer에서는 사전 검사를 다시 해야 한다. 요청·필수 제약을 자르거나 serializer를 바꾸어 guard를 우회하지 않는다. 선택 row budget을 넘으면 정확한 token 수와 예산을 남기고 명시 거부한다.

Windows smoke supervisor는 새 child의 stdin launch gate를 열기 전에 kill-on-close Job Object에 배정한다. gateway·spawn worker·자식의 Job membership과 메모리를 0.2초마다 측정한다. Windows venv launcher PID와 실제 gateway PID가 달라도 새 Job membership·runtime nonce·authenticated ping PID를 함께 확인한다. state PID를 이용해 다른 프로세스를 종료하지 않는다. 선택 예산을 Windows Job commit hard limit으로도 설정하여 polling 사이 native allocation에도 적용한다. 이 한도는 file-backed RSS 한도와 다르므로 RSS와 system margin 감시도 유지한다. private bytes·working set/RSS·OS process peak working set/commit·OS job peak commit을 구분하고 available RAM의 최저값을 기록한다. commit은 private working set과 같은 값이 아니다. polling 사이 RSS 급증은 놓칠 수 있으므로 tensor/block 선제 bound를 대체하지 않는다. 필수 counter가 없거나 system margin·tree budget·전체 deadline을 넘으면 소유 Job만 종료한다. 매 실행은 현재 available RAM에서 최소 1GiB 이상의 system margin과 128MiB의 추가 여유를 남긴 예산을 선택하고 시작 직전에 다시 측정한다.

`--load-timeout`과 `--score-timeout`은 worker 한도 안에서 명시하며 총 smoke deadline은 최대 3300초이고 두 단계 합계에 최소 30초 여유를 요구한다. startup은 load보다 길어야 하고 최대 1860초다. HTTP client는 score deadline보다 15초 길게, gateway socket 전체 timer는 score보다 12초 길게 사용한다. body 수신은 별도 10초 제한이다. 무제한 timeout은 허용하지 않는다. 기본 smoke는 1500/600/2400초이며 controller 잔여 예산이 이보다 작으면 줄여야 한다.

새 private 출력 디렉터리에 `evidence.json`, `samples.jsonl`, 비밀 없는 `service.log`를 보관한다. ephemeral token은 supervisor/소유 child의 환경에만 두고 CLI·state·로그·증거에 저장하지 않는다. 실제 인증 POST `/ping` identity와 POST `/score`, worker의 공식 encoded token 수와 요청 byte 수·응답·선택/기권·cold load/score 시간·environment/derived artifact hash를 기록한다. 상태는 `verified`/`failed`, cleanup은 `stopped`/`failed`/`not-started`로 따로 표시한다. 출력 디렉터리를 재사용하거나 실패 시 자동 재시도하지 않는다. 안전 입장 거부도 성공 추론으로 표시하지 않는다. 입장 시도 예산은 `attempted_plan`에 기록한다. score 증거의 요청 byte 수와 token 수는 실제 요청 및 preflight 결과와 일치해야 하며, 정리 중 monitor 오류가 발생해도 최종 상태는 실패다. 기존 프로젝트 연결·공유 runtime·인증 설정은 바꾸지 않으며 smoke 서비스는 finally에서 정리한다. 실제 전체 Rev 추론 측정 전에는 성공으로 표시하지 않는다. `tests/test_runtime.py`의 기본 검사는 공식 encode와 HTTP를 포함한 오프라인 fixture이다. 실제 Torch가 사전 검증되어 import된 격리 환경에서는 작은 Qwen3.5 hybrid 모델로 FP32/BF16/FP16 streamed 병합, 반복 forward, 예외 해제와 변조 검사를 추가 실행한다. 이것은 전체 Rev 추론이나 품질 비교의 증거가 아니다. 컨트롤러가 루트 unittest discovery를 담당하며 실제 tensor focused 검사는 별도로 기록한다.

## 검증 후 연결과 현재 활성 상태

### compact embedding 이후 최신 실제 시도

2026-10-21의 새 소유 실행 결과는 **실제 전체 `/score` 미성공: 전체 추론 목표 미충족**이다. 기존 warmup 성공 및 이전 실패 기록은 과거 증거로 보존했다. 이번 fresh available RAM은 4,270,587,904 bytes이며 system margin 1,403,943,936 bytes와 별도 gateway/supervisor reserve 134,217,728 bytes를 유지했다. 시도한 process budget은 2732426240 bytes다. 결과: `{"kind": "resource", "action": "System safety margin disappeared; stop owned job, retain evidence, do not wait for RAM"}`.

실행 전 격리 Python 3.11.9 환경의 45개 wheel/RECORD/설치 파일 및 고정 base·adapter를 strict 재검증했다. compact embedding의 실제 BF16/FP16/FP32 fixture와 일치하는 구현 hash도 확인했다. 전체 embedding을 RAM에 올리는 추정을 단순히 낮춘 것이 아니라, 검증된 파생 가중치에서 입력 ID에 필요한 행만 읽는 구현이다. row528 embedding working set 2,974,848 bytes와 기존 dense block 상한을 유지한다. 새 파생 경로만 지정했으며 이전 파생 파일은 변경하지 않았다.

이번 authenticated ping은 false, actual inference는 false, cleanup은 `stopped`다. 준비 중 system available RAM이 1,371,508,736 bytes로 margin 아래에 내려가 watchdog이 종료했다. tree RSS peak 121,196,544 bytes, private 및 OS Job commit peak 각각 92,553,216 bytes는 준비 단계 측정이며 모델 warmup/score 측정이 아니다. RAM 감소 원인은 unknown이다. 실제 응답·choice·routing probabilities·load/score 시간은 미관측이다. 입장 추정은 실측 최소 RAM이 아니다. 상세 최신 증거는 작업 공간 `.ai/reports/rev-compact-smoke/REPORT.md`와 `attempt-01/evidence.json`에 있다. 이전 `.ai/reports/rev-finalize/REPORT.md`와 `.ai/reports/rev-compact-embedding/handoff.json`은 historical이다. 소유 Job 잔류 PID는 없고 서비스는 비활성이며 사용자 프로젝트 연결은 이전하지 않았다. 안전 기준 완화·앱 종료·유휴 RAM 대기·재다운로드는 하지 않았다. 짧은 score의 성공 여부로 16384-token 적합성·routing 품질·coding 성공 확률·비용 절감을 주장하지 않는다.

### 이 Windows 호스트의 과거 실제 실행 결과

2026-10-21의 격리 실행에서는 고정 Qwen3.5-4B·Rev LoRA·FP32 pointer head를 CPU/BF16 `bounded-cpu`로 로드하고 공식 warmup과 인증 `/ping`을 확인했다. **실제 `/score` 응답은 얻지 못했으며 Rev 연결은 비활성이다.** 첫 요청은 row 예산 512보다 공식 입력 525 tokens(528 padded)가 커 HTTP 400으로 거부됐다. 필수 문맥은 자르지 않았다.

해당 실행의 cold load는 273.702초였고 tree RSS peak 819,007,488 bytes, private peak 850,563,072 bytes, OS Job commit peak 1,982,230,528 bytes, system available low-water 3,832,815,616 bytes를 관측했다. 이는 warmup과 거부된 요청까지의 측정이며 성공한 score의 메모리나 지연이 아니다. 소유 Job은 종료됐고 잔류 PID는 없었다.

embedding 전체를 block으로 계산하던 이전 row 528 재시도는 available RAM 3,823,661,056 bytes에서 안전 process 예산 2,285,499,392 bytes보다 계획 추정 2.62GiB가 커 child 생성 전에 차단됐다. 이 추정은 실측 최소 RAM이 아니다. 위 제한된 행 조회 구현의 계획은 이 과거 실패와 별도로 새 자원 probe로 검사해야 한다. 실제 choice·probabilities·score latency·score peak는 미확인이다. 앱 종료, guard 완화, 필수 입력 축소로 실행을 강행하지 않았다.

격리된 45개 배포물의 resolved wheel/RECORD lock, 고정 base/adapter와 파생 파일은 작업 공간에 보존했고 배포 ZIP에는 넣지 않았다. 다시 실행하려면 새 자원 측정으로 같은 row 계획을 안전하게 수용할 수 있어야 하며, 원본·환경·파생 파일 무결성을 다시 확인해야 한다. 종료된 smoke 연결을 재사용하지 않는다. 짧은 요청의 향후 성공도 16384-token 안전성이나 속도·비용 절감을 입증하지 않는다. 실행별 상세 증거와 최종 패키지 hash는 작업 공간의 비공개 보고서에 기록한다.

smoke는 기능 검사이며 기존 `.ai/sev.json`/`.ai/rev.json`이나 사용 중인 프로젝트를 바꾸지 않는다. 종료된 smoke의 endpoint/state를 활성 서비스 연결로 재사용하지 않는다. 실제 성공 여부와 stopped 상태는 해당 실행의 private `evidence.json`으로 확인해야 한다.

지속 연결은 별도 소유 supervisor가 같은 검증 환경·고정 모델·bounded 계획·watchdog을 유지하는 동안에만 준비한다. 새 runtime nonce와 process-local token으로 authenticated `/ping`을 다시 확인하고, 비밀 없는 connection metadata만 connection 파일로 준비한다. 먼저 `scripts/install_rev.py --target <project> --plan`으로 기존 연결·설정·완료 기록을 검토한다. 명시적 이전을 별도 실행할 때만 `--runtime-root <new-isolated-deployment> --connection-file <public-metadata>`와 필요한 `--migrate`를 제공한다. 공유 SEV는 보존하며 활성/불확실 상태는 먼저 개별 reconcile해야 한다. 이 문서는 기존 프로젝트를 자동 활성화했다는 뜻이 아니다.

연결 단계는 이미 authenticated warm을 마친 bounded 서비스의 identity·derived hash·관측 peak와 현재 system margin을 검사하므로 resident-only 22.76/39.53GiB 추정만으로 거부하지 않는다. unknown probe·실패한 warm·관측 budget 초과는 연결을 거부한다. mock installer fixture는 실제 추론 증거가 아니며 source-only updater는 계속 모델·환경·서비스 준비와 독립적이다.

### smoke 준비 단계 예산 보정

smoke는 계획 추정치에 128MiB만 더한 값으로 안전 ceiling을 축소하지 않는다. 현재 available RAM에서 `max(1GiB,total/12)` system margin과 별도 128MiB supervisor 여유를 제외한 ceiling을 사용한다. 시작 직전 다시 측정해 ceiling을 줄일 수 있으며, 계획 추정치와 관측된 준비 단계 OS Job commit 1,986,588,672 bytes 중 큰 값에 128MiB 예비 여유를 더한 값이 들어가지 않으면 모델 로드 전에 거부한다. 이 관측치는 strict 검증/초기화 단계의 과거 peak이며 모델 최소 RAM이나 성공한 score peak가 아니다. `selected_plan`은 추정치, 과거 관측치, 예비 여유, 최초/시작 직전 ceiling과 실제 선택 budget을 구분한다. Windows Job hard limit, 주기 RSS/private/OS peak/system margin 감시, deadline과 finally 정리는 그대로 적용한다. 새 실제 응답 여부는 `.ai/reports/rev-response-check-20261021/attempt-02/evidence.json`으로 확인한다.

### 격리 CPU 자원 설정

`smoke.py`에 `--cpu-threads 4 --cpu-priority above-normal`을 추가하면 소유 Windows Job의 실제 ML worker에만 AboveNormal을 적용한다. `normal`도 지원하며 High/Realtime은 허용하지 않는다. smoke 기본값은 기존과 같은 2스레드·Normal이고, 서비스의 스레드 미지정은 기존 환경을 유지한다. 스레드는 1..64의 정수만 허용한다. 일반 `service.py start`는 `--cpu-threads`와 `--cpu-priority normal`을 지원하며 AboveNormal은 소유 launch gate가 있는 smoke로 한정한다. 기존 서비스와 명시한 스레드가 다르면 자동 교체하지 않는다.

OMP/MKL 환경은 gateway와 spawn worker의 ML import 전에 전달한다. worker는 자신의 Windows priority를 설정하고 `GetPriorityClass`로 확인하며, 검증된 로더가 반환한 뒤 실제 `torch.get_num_threads()`를 확인한다. 인증된 ping의 `cpu_allocation`에 요청값·관측값·worker PID를 기록한다. supervisor는 별도 Job membership·priority 측정으로 실제 worker를 재확인한다. gateway와 watchdog의 우선순위를 올리지 않으며 설정 실패·불일치 시 시작/score를 중단하고 기존 deadline·메모리 감시·finally 정리를 유지한다. 이 자원 설정은 가중치 변환 identity를 바꾸지 않는다.

동일 525 encoded/528 padded 입력의 기존 2스레드·Normal 실제 성공은 `.ai/reports/rev-response-check-20261021/attempt-03/evidence.json`에 보존했다. 당시 cold 332.221초, score 296.922초이며 main 선택 확률 약 0.674704지만 분류 정책은 abstention이다. 확률은 코딩 성공률이 아니고 자동 모델 배정도 아니다. CPU 설정 실험의 별도 증거는 `.ai/reports/rev-cpu-allocation/attempt-01/evidence.json`에 기록한다. 단일 표본과 두 설정의 동시 변경으로 스레드와 우선순위의 개별 효과, 일반 성능·비용·캐시·GPU 속도를 보장하지 않는다.

smoke는 원본 tensor catalog와 현재 RAM으로 `full-resident` 입장 조건도 검사하되 실제 일반 로더는 실행하지 않는다. BF16 언어 가중치 외 runtime·activation·pointer head·system margin이 추가로 필요하다. 계획치는 실측 최소 RAM이 아니며, 우선순위는 RAM 예약이 아니다. 부족하면 앱 종료·OS 설정 변경·guard 완화·RAM 대기 없이 일반 모드를 미실행으로 남긴다. 기존 프로젝트의 SEV/Rev 연결은 변경하지 않는다.

4스레드·AboveNormal의 첫 실제 시도는 원본에서 재계산한 tensor와 기존 파생 파일의 strict 비교 불일치로 준비가 중단됐다. `/ping`·`/score`와 실제 torch thread 관측에는 도달하지 못했으며 속도 변화율은 없다. Job 표본에서는 worker AboveNormal과 나머지 Normal을 확인했고 finally 종료·잔류 PID 없음도 확인했다. 이전 성공 manifest digest를 기준으로 426개 완료 tensor의 hash가 그대로임을 별도 확인했다. FP32 LoRA 행렬곱의 스레드별 수치 차이가 의심되지만 원인으로 입증한 것은 아니다. 파생 계산 설정과 추론 자원 설정의 분리가 다음 검토 사항이며, 불일치 우회·기존 파일 덮어쓰기·자동 재시도는 하지 않았다. 테스트 통과와 실제 추론 실패를 구분한다.


명시한 CPU 옵션은 두 단계로 적용한다. 준비 단계의 OMP/MKL은 원래의 2스레드로 고정해 환경·원본·파생 가중치 strict 검증, 로드와 공식 warmup을 수행한다. 검증된 로더가 반환한 뒤에만 이미 인증·import된 Torch의 `set_num_threads`로 요청한 추론 스레드 수를 적용한다. `cpu_allocation.preparation_threads`와 `preparation_torch_num_threads`는 준비 설정과 관측이며, `torch_num_threads`는 전환 뒤의 실제 추론 관측이다. AboveNormal은 준비·추론 내내 소유 worker에 유지한다. 환경의 OMP/MKL 기록은 준비 값이며 추론 관측을 대신하지 않는다. 종료·예외 시 Torch 스레드와 환경을 복구하고 소유 tree를 정리한다. 서비스 스레드 미지정은 기존 환경을 유지하며 기본 smoke 2/Normal도 유지한다. 이 분리는 strict 불일치를 우회하거나 수치 원인을 입증하지 않는다.

이미 거부된 일반 resident 계획을 반복하지 않을 때는 `--skip-full-resident-preflight`를 사용한다. 이는 일반 로드를 실행하거나 승인하지 않으며 bounded 계획·메모리 guard는 그대로 검사한다.
