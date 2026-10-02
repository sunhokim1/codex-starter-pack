# Architecture

Not initialized.

application이 생기면 주요 subsystem의 책임, 경계, dependency와 데이터 흐름을 기록한다.
중요한 architecture 변화가 있을 때 갱신한다. navigation은 AGENTS.md가 담당한다.
운영 기반은 탐색, 모델 역할 매핑, 최소 routing/escalation, 검증, 프로젝트 정보로 한정한다.
작은 구현은 Codex의 native subagent로 배정하고 독립적인 작업만 병렬로 처리한다.
main이 조율·취합·검증하며 실제 모델은 models.yaml에서 해결한다.
선택 기능은 기본 흐름에 관여하지 않으며 별도 API 실행 하네스는 구현하지 않았다.
