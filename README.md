# Universal AI Development Starter

Strong models, thin harness.

웹·SaaS·게임·모바일·데스크톱·백엔드·CLI용 운영 기반이다. 기술 스택과 application은
아직 초기화되지 않았다. 모델은 구현을 판단하고, 지침은 탐색·역할 선택·검증을 정리한다.

## 핵심

| 파일 | 책임 |
| --- | --- |
| `AGENTS.md` | subsystem navigation, nested 지침, 작업·완료 기준 |
| `PROJECT.md` | 프로젝트 기본 정보와 요구사항 |
| `.ai/models.yaml` | 실제 모델 매핑의 source of truth |
| `.ai/routing.yaml` | 단독 모델 선택, 순차 승격, 기본 reasoning |
| `.ai/verification.yaml` | test/lint/typecheck/build/필요 시 acceptance 명령 |

모델 매핑은 worker = GPT-6.0 Luna, main = GPT-6.1 Sol, escalation = GPT-6.0 Astra다.
이 표기는 참고용이며 실제 model_id는 models.yaml을 따른다. 현재 채팅 모델은 자동 전환되지 않는다.

## 작업 흐름

1. 비용 우선·명확한 구현은 Luna 단독, 분석·디버깅·설계 또는 속도·실패 위험 우선은 Sol 단독으로 선택한다. 사용자 지정 모델이 우선한다.
2. 선택된 모델 하나가 필요한 탐색·설계·구현·검토를 직접 수행한다. Sol+Luna 조율, 하위 에이전트 배정과 자동 병렬 실행은 사용하지 않는다.
3. 같은 모델이 관련 검증을 수행한다. 변경·실패·중요한 우려 없이 동일한 최종 상태를 반복 검증하지 않는다.
4. 현재 모델로 해결하기 어려운 미해결 문제나 검증 실패가 있으면 Luna → Sol → Astra 순으로 한 단계 승격한다.
5. 실제 모델·변경·검증 결과·남은 문제를 보고한다. YAML은 채팅 모델을 바꾸지 않으며 전환을 지원하지 않는 환경에서는 필요한 모델을 사용자가 선택하도록 안내한다.

관련된 읽기와 수정은 적절히 묶어 처리하며 도구 호출 횟수 제한은 두지 않는다.

## 시작과 재사용

프로젝트를 선택하면 PROJECT.md에 목표·스택·플랫폼·제약을 기록한다.
선택한 스택의 검증 명령과 subsystem map을 채운다. 스택을 선택하지 않은 상태에서 framework를 설치하지 않는다.

개인 Codex 스킬을 등록한 컴퓨터에서는 새 프로젝트 폴더에서 다음처럼 호출한다.

```text
$universal-ai-starter 현재 디렉터리에 범용 AI 개발 스타터만 적용해줘.
```

배포용 `universal-ai-starter.zip`은 개인 스킬 경로 `~/.agents/skills/`에 압축을 풀어
`universal-ai-starter/SKILL.md`가 위치하도록 한다. 목록에 나타나지 않으면 Codex를 재시작한다.
스킬은 핵심 파일 7개와 충돌 시 덮어쓰지 않는 복사 스크립트를 포함한다.
각 프로젝트는 독립된 복사본이며 이후 스킬 수정이 기존 프로젝트에 자동 전파되지는 않는다.

스타터 원본 관리 저장소에서 수정한 뒤에는 `python scripts/package_starter.py`로 배포 ZIP을 만든다.
버전·파일 해시·원본 일치를 검증한 ZIP만 교체한다. 설치된 스킬 갱신과 GitHub 업로드는 별도로 실행한다.
관리 도구의 사용법은 원본 저장소에만 있는 `scripts/README.md`를 참고한다. 도구와 그 안내는 생성 프로젝트에 포함하지 않는다.

## 선택 기능과 프로젝트 문서

별도 역할·정책·유형별 체크리스트와 빈 구조 문서는 포함하지 않는다. 실제 subsystem이나 중요한
architecture 결정에 설명이 필요할 때 프로젝트 문서를 만들고 AGENTS.md map에서 연결한다.

`.ai/config.yaml`의 Hermes, Figma, custom router, classifier training, task history와
자동 최적화, durable memory, task capsule, evidence log, design pipeline은 모두 비활성이다.
비활성 기능의 이력 파일은 새 프로젝트에 포함하지 않는다. 기능을 켜도 integration이
자동으로 구현되지는 않는다. 단독 실행과 순차 승격은 지침이며 현재 채팅 모델을 자동 전환하는
프로그램이 아니다. 필요한 모델은 실제 실행 환경에서 선택한다.
