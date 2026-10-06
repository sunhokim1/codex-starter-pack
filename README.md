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
설정은 Codex가 읽고 따르는 지침이다. 하위 에이전트 도구와 모델 지정 기능이 있으면
models.yaml의 실제 model_id로 worker를 생성한다. 별도 API 실행기나 현재 채팅 모델 자동 전환은 없다.

## 기본 작업 흐름

1. AGENTS.md map과 PROJECT.md에서 관련 context를 찾는다.
2. 작은 구현은 worker 하나, 독립적인 작은 구현 여러 개는 worker 최대 두 개에 병렬 배정한다.
3. main이 조율·취합·검토한다. 의존하거나 수정 파일/공유 interface가 겹치면 순차 실행한다.
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

스타터 원본 관리 저장소에서 수정한 뒤에는 `python scripts/package_starter.py`로 배포 ZIP을 만든다.
버전·파일 해시·원본 일치를 검증한 ZIP만 교체한다. 설치된 스킬 갱신과 GitHub 업로드는 별도로 실행한다.
관리 도구의 사용법은 원본 저장소의 `scripts/README.md`를 참고한다. 도구 자체는 생성 프로젝트에 포함하지 않는다.

## 선택 자료와 기능

기존 `.ai/policies/`, `.ai/agents/`, `.ai/templates/`, `docs/`, `scripts/` 구조는 유지한다.
작업에 필요한 자료만 선택해서 읽으며 별도 agent 실행이나 고정 프로세스를 요구하지 않는다.

`.ai/config.yaml`의 Hermes, Figma, custom router, classifier training, task history와
자동 최적화, durable memory, task capsule, evidence log, design pipeline은 모두 비활성이다.
이력 파일은 유지하지만 기본 작업에서 읽거나 기록할 필요가 없다.
비활성 기능을 켜는 것만으로 integration이 구현되지는 않는다.

native subagent 배정은 위 비활성 custom router와 별개다. 환경이 지원하지 않거나 지정 모델을
사용할 수 없으면 한계를 밝히고 현재 모델로 순차 처리한다. Luna 실행을 보장하는 standalone
프로그램은 아니다. 동시 수는 프로젝트 실행 기준과 호스트의 사용 가능한 슬롯 중 작은 값을 따른다.
