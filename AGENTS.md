# Strong models, thin harness

요구사항에 필요한 사실이 없을 때 `PROJECT.md`를 읽는다. 이미 읽은 지침과 설정은 변경되지 않았으면
세션 중 재사용한다. 관련 subsystem의 코드·테스트와
해당 영역의 nested `AGENTS.md`는 작업에 필요하면 읽는다. 기존 구조를 존중하고 관련 검증을 수행한다.

## Repository map

| Major subsystem | Entry point | Tests | Docs / schema | Nested AGENTS.md |
| --- | --- | --- | --- | --- |
| Application | apps/starter-manager/App.cs, apps/starter-manager/Core.cs | tests/test_starter_manager.py, apps/starter-manager/CoreSelfTest.cs | apps/starter-manager/README.md | — |
| UI / Design | apps/starter-manager/App.cs | apps/starter-manager/AppDiagnostics.cs, tests/test_starter_manager.py | apps/starter-manager/README.md | — |
| Rev runtime | distribution/releases/0.4.0/universal-ai-starter/assets/rev/service.py | tests/test_rev_runtime.py | distribution/releases/0.4.0/universal-ai-starter/assets/rev/README.md | distribution/releases/0.4.0/universal-ai-starter/AGENTS.md |
| Sequential controller | distribution/releases/0.4.0/universal-ai-starter/assets/runner/controller.py | tests/test_rev_controller.py, tests/test_rev_distribution.py | distribution/releases/0.4.0/universal-ai-starter/MIGRATION.md | distribution/releases/0.4.0/universal-ai-starter/AGENTS.md |
| Data / Storage | Not initialized. | — | — | — |
| Services / Backend | Not initialized. | — | — | — |
| Tests | Not initialized. | — | — | — |
| Infrastructure | starter 배포/Windows 설치: scripts/package_starter.py, scripts/install_from_github.ps1, distribution/releases/0.4.0/universal-ai-starter/scripts/install_rev.py | tests/test_package_starter.py, tests/test_github_installer.py, tests/test_install_sev.py (원본만) | distribution/manifest.json, scripts/README.md | — |

해당 영역 작업 시 map이 연결한 nested AGENTS.md부터 읽는다. 개별 파일 목록은 기록하지 않는다.
새 subsystem이나 중요한 architecture boundary가 생길 때 map을 갱신하고,
주요 entry point/tests/docs/schema/nested 지침의 경로가 바뀌면 기존 링크를 바로잡는다.
작은 helper/component 추가에는 map 또는 문서 갱신을 요구하지 않는다.

## README 언어

앞으로 저장소의 모든 README 파일은 제목, 본문, 설명을 자연스러운 한국어로 작성하고 수정한다. 명령어, 경로, 모델 이름, 코드, 설정 키, 공식 제품명은 정확한 원문 표기를 유지한다.

## 작업과 설정

- `.ai/models.yaml`은 worker/main/escalation의 실제 모델 매핑 기준이다. 현재 채팅 모델은 자동 전환되지 않는다.
- `.ai/routing.yaml`은 단독 모델 선택·기본 reasoning·실패 시 순차 승격 기준이다. 선택한 모델이 직접 구현과 검증을 맡는다. YAML은 현재 채팅 모델을 전환하지 않는다.
- `.ai/verification.yaml`은 프로젝트에 설정된 검증 명령이다. 미설정·미실행·실패를 구분하며, 설정되지 않은 검증은 통과로 보고하지 않는다.
- `.ai/config.yaml`의 선택 기능은 비활성이다. 별도 orchestration이나 이력 기록을 요구하지 않는다.

완료하려면 요구사항을 충족하고 관련 실제 검증이 통과해야 한다. 설정된 명령 중 사용 가능한 것만 실행하며,
명령이 없으면 수동 점검 결과와 검증 한계를 밝힌다.

SEV가 설정되지 않은 프로젝트는 고정 기본 모델 없이 구현 전에 작업 적합도와 예상 전체 시간·토큰·재작업 위험·검증 신뢰도를 짧게 판단한다.
모델 선택에 필요한 판단은 현재 확인 가능한 사용자 요청과 프로젝트 정보만으로 수행한다.
모델 선택만을 목적으로 광범위한 코드 탐색, 별도 에이전트 실행 또는 추가 분류 단계를 수행하지 않는다.
요구사항·범위가 명확하고 기존 코드 패턴으로 해결되며, 변경이 국소적/독립적이고 실패 영향이 작고
복구가 쉬우며 검증이 명확하고 재작업 위험이 낮으면 Luna(worker)를 선택한다.
해석·설계·복잡한 원인 분석, subsystem 의존성, architecture/데이터 구조 변경, 높은 실패 영향 또는
Luna 실패로 전체 비용이 늘 가능성이 크면 Sol(main)을 선택한다. 판단 근거가 부족하거나 실패 영향이 크면 Sol을 추천한다.
파일 수나 요청 길이만으로 선택하지 않으며 별도 분류 호출·점수 계산을 요구하지 않는다. 사용자가 지정한 모델을 우선한다.
Luna/Sol은 독립 실행 모델이며 worker/main은 매핑 이름이다. 조율자와 하위 구현자의 분업이나 고정 상하 관계를 뜻하지 않는다.

Sol+Luna 조율, 하위 에이전트 배정, 자동 병렬 실행은 사용하지 않는다. 선택된 모델이 설계·구현·검토·검증을 직접 수행한다.
처음부터 Sol이 적합하면 Sol로 시작한다. 확인된 미해결 문제나 관련 검증 실패의 원인을 분석하고
현재 모델로 해결하기 어려운 경우에만 Luna → Sol → Astra 순서로 한 단계 승격한다.
환경 오류·일시적 도구 실패·확신 부족만으로 승격하지 않는다.
승격할 때 목표·관련 파일·시도·검증 결과·남은 문제만 전달한다. 별도 하위 에이전트를 생성해 모델 전환을 대신하지 않는다.
모델 전환을 실행 환경에서 지원하지 않으면 현재 모델을 유지하며 실제 사용 모델·추천 모델·추천 이유를 밝히고 사용자 선택을 안내한다.
실행하지 않은 모델이나 승격을 실행했다고 보고하지 않는다.

관련된 읽기와 수정을 묶어 처리하되 도구 호출 횟수 제한을 두지 않는다. 실제 실행된 검증 증거를 확인하며,
코드 변경·실패·중요한 우려 없이 동일한 최종 상태의 검사를 반복하지 않는다. 완료 시 변경 내용·실제 검증·미해결 문제를 간결히 보고한다.

<!-- starter-sev:start -->
## Local SEV execution

When `.ai/sev.json` exists, use the installed `single-model-runner` for development
requests without requiring the user to name the skill. Read the paths from that JSON.
Pass the request and already known project facts unchanged. Use --model worker|main
for a user override; otherwise use persistent SEV. General questions stay in this chat.
The selected model owns implementation and verification; do not repeat its work.
Do not invoke the runner again inside a task it already selected. No subagents or
parallel agents. This authorized local workflow takes precedence over manual selection
guidance. On service failure stop and report; never substitute a paid classifier.
The app chat model does not change. This is instruction-based invocation, not interception.
<!-- starter-sev:end -->


## Maintained 0.4.0 source

The source of truth is distribution/releases/0.4.0/universal-ai-starter/.
Read its AGENTS.md for edits inside that bundle. Root/experiments compatibility entry points
forward into that source; do not create a second implementation. distribution/manifest.json
maps the complete bundle for scripts/package_starter.py. Preserve existing project facts.
Run root tests and the bundled regressions; distinguish mocks from actual installation.
Do not install, run paid models or modify startup entries merely to validate packaging.
See CONTINUOUS_IMPROVEMENT.md for remaining work.

관리기는 starter 소스·클라이언트를 자동 설치·업데이트하되 기존 지침·설정·실행 연결·완료 기록을 보존한다. 소스 버전·무결성과 선택적 Rev 환경 준비·인증된 실제 추론은 별개다. 자원·모델·환경 lock·서비스 부재는 소스 업데이트를 막지 않는다. CPU·Windows CUDA는 선택 device/dtype의 자원과 실제 capability로 판단하며 OS만으로 거부하지 않는다. 활성·불확실한 상태와 수정된 관리 파일은 개별 검토하며 완료 작업을 재생하지 않는다.

0.4.0 Rev 연결은 명시적으로 이전한다. 보관된 0.3.1·0.3.2·0.3.3 소스와 ZIP, private bootstrap 설정은 변경하지 않는다. 새 runtime/설치 경계 지침은 0.4.0 AGENTS.md에서 확인한다.
