# 제한된 embedding 조회 계약

`offload.embedding_contract(shape, dtype, row_token_budget, batch_budget=1)`는 계획과 실행의 공통 계약이다. 행 길이는 16-token 단위로 올리고 batch는 1..16, 총 ID는 최대 16384로 제한한다. Rev 로더는 batch 1만 사용하며 공식 encoder·최대 16384-row 계약과 별도로 선택한 짧은 행 예산을 검사한다. 입력을 자르지 않는다.

`hardware.execution_plan` schema 2의 `embedding`을 `attach_mapped_blocks(..., embedding_plan=plan['embedding'])`에 전달한다. 계약이 재계산한 값과 다르거나 embedding alias·사용자 forward/hook·변경형 옵션이 있으면 연결 전에 실패한다. embedding 원래 parameter는 eval/meta 상태를 유지한다. dense decoder/norm mapping과 예외 시 복원은 별도로 유지한다. 반환된 handle의 `remove()`는 embedding forward 대체와 block hook을 해제한다.

출력 payload 상한은 `max_ids * hidden_size * element_size`, 행 buffer는 `hidden_size * element_size`, caller-owned indices/storage는 `max_ids * 8` bytes다. SHA256 buffer는 262144 bytes다. 입력 전체를 복사하거나 unique/sort/gather tensor를 만들지 않으며 복사·index tensor workspace는 0 bytes다. scalar Python/Tensor metadata와 kernel/allocator 비용은 기존 runtime/activation reserve에 포함한다. 계획은 위 payload들을 보수적으로 모두 합산한다. 실제 lookup은 hash buffer를 해제한 다음 출력과 단일 행 buffer를 만든다.

파일을 열기 전에 CPU strided int32/int64 2차원 입력의 batch·행·총 ID·backing storage·모든 ID 범위를 검사한다. 같은 열린 파일의 크기·link와 SHA256을 검증한 다음 각 ID의 byte offset에서 한 행만 읽는다. padding과 반복 ID도 같은 byte를 복사한다. 마지막 파일 identity 검사와 guard를 통과해야 출력을 반환한다. 전체 embedding의 mmap·materialization은 없다. 무결성 검사는 전체 파일을 순차 읽지만 고정 buffer만 사용한다. 지원하지 않는 입력/옵션은 fallback 없이 거부한다.

`largest_dense_block_bytes`는 decoder/norm의 실제 전체 parameter bytes이며, `materialization_reserve_bytes`는 dense와 hash buffer의 합 또는 compact embedding 상한 중 큰 값이다. `largest_source_tensor_bytes`는 SSD atomic staging에 사용하는 원본 tensor 전체 크기로 유지한다. 총 weights·병합·FP32 pointer head·runtime·activation·system margin·외부 Windows Job watchdog 기준을 줄이지 않는다. 계획 수용은 실제 추론 성공이나 실측 최소 RAM의 증거가 아니다.

`offload.py`의 SHA256은 derivation identity다. 코드가 바뀐 뒤에는 새 작업 소유 derived 디렉터리를 사용하고, 과거 manifest/파일/보고서는 보존한다. 기존 identity가 다르면 파생 파일을 쓰기 전에 거부한다. 같은 identity의 재사용도 독립적으로 원본에서 기대 hash를 다시 생성한다. LoRA의 FP32 `2*B@A`, 선택 dtype cast/add 순서와 단 한 번의 병합은 그대로다.

`tests/test_runtime.py`의 실제 격리 Torch fixture는 BF16/FP16/FP32 bitwise 조회, nonzero padding·반복·경계 ID·다중 batch·strided 입력·최대 ID 수, 읽기 전 거부, 관측 가능한 행 read/출력 할당 상한, 변조·예외 복구·alias/옵션 거부와 작은 Qwen3.5 streamed LoRA를 검사한다. 공식 전체 모델의 인증 `/score` 및 watchdog 증거는 별도 smoke 작업에서 새 디렉터리에 남겨야 한다. root 검사는 controller 소유다.
