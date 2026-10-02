# Universal AI Development Starter

Strong models, thin harness.

웹·SaaS·게임·모바일·데스크톱·백엔드·CLI용 운영 기반이다. 기술 스택과 application은
아직 초기화되지 않았다. 모델의 구현 판단은 자율적으로 두고 탐색·역할 선택·검증만 간단히 정한다.

## 핵심

| 파일 | 책임 |
| --- | --- |
| `AGENTS.md` | subsystem navigation, nested 지침, 완료 기준 |
| `PROJECT.md` | 프로젝트 기본 정보 |
| `.ai/models.yaml` | 실제 모델 매핑의 source of truth |
| `.ai/routing.yaml` | 단순 역할 선택과 한 단계 escalation |
| `.ai/verification.yaml` | test/lint/typecheck/build/필요 시 acceptance 명령 |

현재 매핑은 worker = GPT-6.0 Luna, main = GPT-6.1 Sol, escalation = GPT-6.0 Astra다.
이 표는 참고 표시이며 매핑이 바뀌면 models.yaml을 따른다.
설정은 선언적이다. 모델 호출·검증 자동 실행·현재 채팅 모델 전환을 구현한 것은 아니다.

## 기본 작업 흐름

1. AGENTS.md map과 PROJECT.md에서 관련 context를 찾는다.
2. 작업에 맞는 worker/main/escalation 역할을 선택한다.
3. 필요한 파일만 읽고 모델이 구현 방법을 판단한다.
4. 관련된 실제 검증을 실행하고 실패/복잡도 증가 시 한 단계 승격한다.
5. 결과와 검증 한계를 보고하고 구조 변화가 있으면 navigation을 바로잡는다.

## 시작과 재사용

프로젝트를 선택하면 PROJECT.md에 정보를 기록하고, 필요할 때 해당 `.ai/templates/` preset을 읽는다.
선택한 스택의 검증 명령과 subsystem map을 채운다. 스택을 선택하지 않은 상태에서 framework를 설치하지 않는다.

개인 Codex 스킬을 등록한 컴퓨터에서는 새 프로젝트 폴더에서 다음처럼 호출한다.

```text
$universal-ai-starter 현재 디렉터리에 범용 AI 개발 스타터만 적용해줘.
```

배포용 `universal-ai-starter.zip`은 개인 스킬 경로 `~/.agents/skills/`에 압축을 풀어
`universal-ai-starter/SKILL.md`가 위치하도록 한다. 목록에 나타나지 않으면 Codex를 재시작한다.
스킬은 27개 템플릿 파일과 충돌 시 덮어쓰지 않는 복사 스크립트를 포함한다.
각 프로젝트는 독립된 복사본이며 이후 스킬 수정이 기존 프로젝트에 자동 전파되지는 않는다.

## 선택 자료와 기능

기존 `.ai/policies/`, `.ai/agents/`, `.ai/templates/`, `docs/`, `scripts/` 구조는 유지한다.
작업에 필요한 자료만 선택해서 읽으며 별도 agent 실행이나 고정 프로세스를 요구하지 않는다.

`.ai/config.yaml`의 Hermes, Figma, custom router, classifier training, task history와
자동 최적화, durable memory, task capsule, evidence log, design pipeline은 모두 비활성이다.
이력 파일은 유지하지만 기본 작업에서 읽거나 기록할 필요가 없다.
비활성 기능을 켜는 것만으로 integration이 구현되지는 않는다.
