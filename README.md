# Universal AI Development Starter 0.3.3 — Codex 개발 작업을 위한 스타터팩

**Codex로 개발할 때 작업에 맞는 모델을 고르고, 구현부터 검증과 중단한 작업의 재개까지 돕는 프레임워크 중립 개발 도구 모음입니다.**

새 프로젝트를 시작하거나 기존 저장소에서 Codex를 쓰면서, 프로젝트 지침·모델 선택·검증 방식을 일관되게 관리하고 싶은 개인 개발자와 팀을 위한 스타터입니다. 완성된 서비스나 앱 화면을 제공하는 템플릿은 아닙니다. 만들 앱의 기능과 기술 스택은 사용자가 정하며, 특정 프레임워크를 전제로 하지 않습니다.

## 무엇을 해 주나요?

| 제공 기능 | 실제 사용 예시 |
| --- | --- |
| 프로젝트 운영 파일 준비 | `AGENTS.md`에 작업 기준을, `PROJECT.md`에 목표·기술 스택·제약을 정리합니다. 기존 프로젝트의 사실과 설정은 보존합니다. |
| 작업별 Codex CLI 모델 선택 | 로컬 SEV가 개발 요청에 맞는 `worker` 또는 `main`을 선택하고, 선택된 한 모델이 탐색·구현·검증을 맡습니다. 실제 모델 매핑은 `.ai/models.yaml`에서 관리합니다. |
| 작은 작업의 단일 실행 | “검색 결과가 없을 때 안내 문구를 추가하고 관련 검증을 해 줘.”처럼 범위가 명확한 변경을 수행합니다. |
| 큰 작업의 순차 계획·실행·재개 | “이 저장소에 할 일 관리 기능을 추가해 줘.” 같은 목표를 작업으로 나누고, 하나씩 구현·검증하며 상태를 저장합니다. 중단하면 상태를 확인하고 같은 목표를 재개할 수 있습니다. |
| 프로젝트에 맞는 검증 | `.ai/verification.yaml`에 설정한 실제 테스트·린트·빌드 명령으로 결과를 확인합니다. 설정하지 않은 검증을 통과했다고 처리하지 않습니다. |

불필요한 모델 호출과 반복 문맥을 줄여 토큰 사용을 아끼는 것이 목표입니다. 절감률이나 코딩 성공률을 보장하지는 않습니다. SEV의 모델 선택은 로컬에서 수행하며 OpenAI 토큰/API를 사용하지 않지만, 앱 대화와 실제 Codex 코딩 실행에는 인증 방식에 따른 사용량과 비용이 발생합니다. 앱 대화 모델이 자동으로 전환되는 기능은 아닙니다.

## Windows에서 빠르게 시작하기

### 준비물

- Windows와 PowerShell, 인터넷 연결, 의존성·로컬 분류 모델을 내려받을 디스크 공간이 필요합니다.
- 네이티브 Codex CLI를 미리 설치하고, 사용할 계정으로 인증해 두세요. 해당 계정에서 사용할 코딩 모델도 확인하세요. 설치기는 Codex 인증 설정을 바꾸지 않으며, 모델 이용 권한이나 무료 사용량을 제공하지 않습니다.
- Python 3.11+가 필요합니다. 아래 설치기는 사용 가능한 Python이 없으면 `winget`으로 Python 3.11 설치를 시도합니다. `winget`을 사용할 수 없다면 Python 3.11+를 먼저 설치하세요.
- 적용할 프로젝트 폴더를 준비하세요. 빈 폴더와 기존 저장소 모두 사용할 수 있습니다.

### 설치 순서

1. [Windows 설치 스크립트](scripts/install_from_github.ps1)의 출처와 내용을 확인한 뒤 PowerShell에서 다음 명령을 실행하세요. 원격 스크립트를 내려받아 즉시 실행하는 원클릭 설치 경로입니다.

   ```powershell
   irm https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/main/scripts/install_from_github.ps1 | iex
   ```

2. 폴더 선택 창이나 경로 입력 안내에서 **적용할 프로젝트 폴더**를 지정하세요. 설치기는 고정된 커밋의 0.3.3 ZIP을 내려받아 전체 파일과 해시를 검증한 뒤 프로젝트 파일과 로컬 SEV를 준비합니다. 기존 핵심 파일은 보존하며 필요한 지침을 추가합니다.
3. 설치 완료 후 Codex를 다시 시작하고 해당 프로젝트를 여세요. `PROJECT.md`에 실제 목표·스택·제약을 정리하고, `.ai/verification.yaml`에 그 프로젝트에서 실행 가능한 검증 명령을 설정하세요. 초기 검증 명령은 모두 `null`이며, 설치 완료가 앱 구현이나 검증 통과를 뜻하지는 않습니다.

설치기는 개인 스킬 폴더와 `~/.codex/sev` 아래에 도구를 준비하고, Windows 로그인 시 SEV가 시작되도록 등록합니다. 시작 등록을 원하지 않으면 아래 수동 설치의 `--no-autostart` 옵션을 사용하세요.

**권한 점검에서 멈췄다면:** 0.3.3은 새 venv를 만든 직후 네이티브 관리 Codex `:workspace` 샌드박스에서 Python의 표준 라이브러리 읽기·자식 프로세스 실행·임시 프로젝트 파일 읽기와 쓰기를 점검합니다. CLI 누락, 지원하지 않는 옵션, 접근 거부, 45초 시간 초과는 설치 실패로 처리하며 의존성·모델 준비와 서비스 시작·프로젝트 연결·스킬 승격·시작 등록으로 넘어가지 않습니다. 출력 진단을 확인하고 CLI 설치·업데이트나 해당 PC의 권한·관리 정책을 점검한 뒤 재시도하세요. 설치기가 ACL을 부여하거나 장치 정책을 우회하지는 않으며, 한 PC에서의 성공이 다른 PC의 성공을 보장하지 않습니다.

### 설치 후에는 이렇게 요청하세요

프로젝트를 연 Codex 대화에서 평소처럼 개발 목표를 설명하면 됩니다. 설치된 지침이 작은 변경에는 단일 실행을, 여러 구현 단계가 필요한 큰 목표에는 순차 프로젝트 실행을 사용하도록 안내합니다.

```text
검색 결과가 없을 때 안내 문구를 추가하고 관련 검증을 해 줘.
```

```text
이 저장소에 할 일 추가·완료·삭제 기능을 만들어 줘.
기존 기술 스택을 유지하고, 단계별로 구현한 뒤 설정된 검증을 실행해 줘.
```

큰 작업이 중단되었다면 “진행 상태와 중단 이유를 확인해 줘. 같은 목표를 이어서 진행해 줘.”라고 요청할 수 있습니다. 저장된 상태를 확인해 재개하며, 실패 재시도·승인·실행 한도 연장이 필요한 경우에는 사용자 판단을 받습니다. 완전 무인 실행이나 자동 배포를 보장하지 않습니다. 일반 질문은 앱 대화에서 처리하고, SEV 서비스가 실패하면 유료 분류기로 자동 대체하지 않고 중단 이유를 보고합니다.

## 직접 확인하며 설치하려면

신뢰할 수 있는 출처의 ZIP을 사용하고 적용 전에 출처와 무결성을 확인하세요. ZIP 안 manifest의 해시는 내부 일관성 검사이며 배포자 서명은 아닙니다. ZIP을 풀고 `universal-ai-starter` 폴더에서 아래 명령을 실행합니다. `<project>`는 실제 프로젝트 경로로 바꾸세요.

```text
python scripts/scaffold.py --target <project> --dry-run
python scripts/scaffold.py --target <project> --adopt --no-autostart
```

첫 명령은 적용할 파일을 미리 확인합니다. 둘째 명령은 기존 일반 파일을 보존하고 없는 파일을 추가한 뒤 SEV를 설치하되 로그인 시작 등록은 생략합니다. 파일만 적용하려면 `--files-only`를 사용하세요. 핵심 파일이 이미 준비된 프로젝트에 SEV만 연결하려면 다음 명령을 사용합니다.

```text
python scripts/install_sev.py --target <project> --no-autostart
```

설치 실패 시 새로 복사된 핵심 파일이나 진단용 새 배포 폴더가 남을 수 있습니다. 결과를 확인한 뒤 재시도하세요. 설치·보존·복구에 관한 자세한 내용은 [번들 안내](distribution/releases/0.3.3/universal-ai-starter/README.md)와 [프로젝트용 사용·복구 안내](distribution/releases/0.3.3/universal-ai-starter/assets/starter/README.md)를 참고하세요.

## 유지 관리자: 패키징·테스트·릴리스

유지 관리 원본은 [0.3.3 번들](distribution/releases/0.3.3/universal-ai-starter/README.md)입니다. 루트 `universal-ai-starter.zip`은 `distribution/manifest.json`에 따라 빌드되며 전체 소스와 회귀 테스트를 포함합니다. 배포된 0.3.1 및 0.3.2 소스는 변경하지 않습니다. 기존 프로젝트, 모델 매핑 및 가중치는 보존됩니다. 다음은 이 저장소의 유지 관리용 명령입니다.

```text
python scripts/package_starter.py
python scripts/package_starter.py --check
python distribution/releases/0.3.3/universal-ai-starter/scripts/package_starter.py --check
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s distribution/releases/0.3.3/universal-ai-starter/tests -p "test_*.py" -v
```

공개 설치 프로그램은 0.3.3 릴리스를 요구하며, 준비 단계에 들어가기 전에 ZIP 전체를 검증합니다. 게시하려면 검증된 ZIP 커밋을 가리키는 변경 불가 다운로드 핀이 필요합니다. 배포 절차는 [유지 관리 및 배포 안내](scripts/README.md), 제한 사항은 [릴리스 안내](docs/release-0.3.3.md)를 참고하세요. 실제 설치, 모델 추론 및 시작 동작은 별도로 검증해야 합니다. 오프라인 회귀 테스트 결과만으로 모든 Windows PC에서 접근 가능하다고 단정할 수는 없습니다.

호환성을 위한 runner/service/install/scaffold 진입점은 0.3.3 구현으로 연결됩니다. 남은 작업은 [지속적 개선](CONTINUOUS_IMPROVEMENT.md) 문서에 기록되어 있습니다.
