# Memory — optional / inactive

`task-history.jsonl`은 보존하지만 기본 작업에서 읽거나 기록하지 않는다.
자동 logger, history 기반 routing/최적화, classifier training, durable memory,
task capsule, evidence log는 비활성이며 구현되어 있지 않다.
향후 명시적으로 도입할 때 기록 목적과 실행 범위를 정한다.
그 경우 모델 역할뿐 아니라 실행 당시 실제 family/version을 기록하고 비밀 정보는 제외한다.
