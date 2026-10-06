# Strong models, thin harness

이 파일에서 필요한 경로를 찾고, 요구사항은 `PROJECT.md`에서 확인한다.

## 작업 원칙

- 관련 subsystem과 직접 dependency부터 읽고 필요할 때만 탐색을 넓힌다.
- 기존 구조를 존중하며 요구사항을 해결한다. 구체적인 구현 방법은 모델이 판단한다.
- 역할 선택은 `.ai/routing.yaml`, 실제 모델 매핑은 `.ai/models.yaml`을 따른다.
- 코드 변경 후 관련 검증을 수행한다. 완료 판단은 자기평가보다 검증 결과를 따른다.

## Repository map

| Major subsystem | Entry point | Tests | Docs / schema | Nested AGENTS.md |
| --- | --- | --- | --- | --- |
| Application | Not initialized. | — | — | — |
| UI / Design | Not initialized. | — | — | — |
| Data / Storage | Not initialized. | — | — | — |
| Services / Backend | Not initialized. | — | — | — |
| Tests | Not initialized. | — | — | — |
| Infrastructure | starter 배포: scripts/package_starter.py (원본 관리 저장소만) | tests/test_package_starter.py (원본만) | distribution/manifest.json, scripts/README.md | — |

해당 영역 작업 시 map이 연결한 nested AGENTS.md부터 읽는다. 개별 파일 목록은 기록하지 않는다.
새 subsystem이나 중요한 architecture boundary가 생길 때 map을 갱신하고,
주요 entry point/tests/docs/schema/nested 지침의 경로가 바뀌면 기존 링크를 바로잡는다.
작은 helper/component 추가에는 map 또는 문서 갱신을 요구하지 않는다.

## 핵심 설정

- `PROJECT.md`: 목표, 사용자, 기술 스택, 플랫폼, 제약.
- `.ai/models.yaml`: worker/main/escalation 매핑의 유일한 기준. 버전 변경도 여기서 한다.
- `.ai/routing.yaml`: 역할 선택, 기본 reasoning, 한 단계 escalation.
- `.ai/verification.yaml`: 프로젝트에 존재하는 검증 명령.

## Worker 실행

작고 명확한 구현은 worker 하나에 배정한다. 독립적인 작업 여러 개는 `.ai/routing.yaml`의
실행 기준에 따라 worker를 병렬로 배정하고 main이 결과 취합·검토와 통합 검증을 맡는다.
Codex의 하위 에이전트 도구가 있으면 실제로 사용한다. 별도 API 실행기는 필요하지 않다.
생성할 때 `.ai/models.yaml`에서 역할의 model_id를 읽어 모델 인수에 명시하고,
reasoning은 routing의 기본값을 사용한다. 이름만 worker로 붙이고 부모 모델을 상속하지 않는다.
현재 호스트 모델은 자동 변경되지 않는다. main 매핑과 다른 경우 현재 모델을 main이라고 오인하지 말고,
지원되면 매핑한 main 에이전트에 조율을 맡기거나 실제 사용 모델과 차이를 밝힌다.
각 worker에게 담당 파일·목표·필요한 context만 전달한다. 다른 worker의 변경을 되돌리지 않는다.
중첩 분할과 무한 재시도는 하지 않는다. 검증 실패는 원인을 확인하고 필요하면 한 단계 승격한다.
모델 지정/하위 에이전트 기능이 없거나 지정 모델을 사용할 수 없으면 그 한계를 알리고
현재 모델로 순차 처리한다. 실행하지 않은 worker/병렬 처리를 실행했다고 보고하지 않는다.

## 완료 조건

요구사항을 충족하고 변경에 관련된 실제 검증이 통과해야 한다.
설정된 명령 중 프로젝트에서 사용 가능한 것만 실행한다. 미설정/미실행/실패는 구분해서 보고한다.
명령이 없으면 가능한 수동 점검과 검증 한계를 밝히며 통과로 간주하지 않는다.
구조 변경은 navigation 정확성을 유지하고, 중요한 architecture 변화는 관련 문서에 반영한다.

보조 policies/agents/templates/docs는 해당 작업에 필요할 때만 읽는다.
선택 기능은 `.ai/config.yaml`에서 모두 비활성이다. native worker 배정 외에 이력 기록이나 별도 orchestration을 요구하지 않는다.
