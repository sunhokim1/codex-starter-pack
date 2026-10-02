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
| Infrastructure | Not initialized. | — | — | — |

해당 영역 작업 시 map이 연결한 nested AGENTS.md부터 읽는다. 개별 파일 목록은 기록하지 않는다.
새 subsystem이나 중요한 architecture boundary가 생길 때 map을 갱신하고,
주요 entry point/tests/docs/schema/nested 지침의 경로가 바뀌면 기존 링크를 바로잡는다.
작은 helper/component 추가에는 map 또는 문서 갱신을 요구하지 않는다.

## 핵심 설정

- `PROJECT.md`: 목표, 사용자, 기술 스택, 플랫폼, 제약.
- `.ai/models.yaml`: worker/main/escalation 매핑의 유일한 기준. 버전 변경도 여기서 한다.
- `.ai/routing.yaml`: 역할 선택, 기본 reasoning, 한 단계 escalation.
- `.ai/verification.yaml`: 프로젝트에 존재하는 검증 명령.

## 완료 조건

요구사항을 충족하고 변경에 관련된 실제 검증이 통과해야 한다.
설정된 명령 중 프로젝트에서 사용 가능한 것만 실행한다. 미설정/미실행/실패는 구분해서 보고한다.
명령이 없으면 가능한 수동 점검과 검증 한계를 밝히며 통과로 간주하지 않는다.
구조 변경은 navigation 정확성을 유지하고, 중요한 architecture 변화는 관련 문서에 반영한다.

보조 policies/agents/templates/docs는 해당 작업에 필요할 때만 읽는다.
선택 기능은 `.ai/config.yaml`에서 모두 비활성이다. 기본 작업에 이력 기록이나 별도 orchestration을 요구하지 않는다.
