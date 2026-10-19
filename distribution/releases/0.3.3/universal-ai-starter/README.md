# Universal AI Starter 0.3.3

범용 프로젝트 템플릿과 로컬 SEV·Codex 순차 실행 도구입니다. 0.3.0 사용자 제공 ZIP을 기반으로 안전성·완료 판정·배포 재현성을 수정했습니다. 기존 모델 매핑과 분류 가중치는 유지했습니다.

## 변경과 검증

`REPAIR_NOTES.md`에 수정 범위, 호환성, 실제 검증과 남은 한계를 정리합니다. `AGENTS.md`는 이 도구 개발용이며 `assets/starter/AGENTS.md`는 생성 프로젝트용입니다. `CONTINUOUS_IMPROVEMENT.md`로 다음 개선을 이어갑니다.

Python 3.11+에서 표준 라이브러리만으로 오프라인 회귀 검사를 실행합니다. 설치·모델·소켓·Windows ACL 호출은 모형으로 검사합니다.

```text
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/package_starter.py --check
```

패키징은 출력 ZIP을 이 소스 디렉터리 밖에 지정합니다. 새 manifest를 작성하고 파일 집합·해시를 검사한 뒤 ZIP을 생성합니다.

```text
python scripts/package_starter.py --output ../universal-ai-starter-0.3.3.zip
```

## 적용

먼저 `python scripts/scaffold.py --target <project> --dry-run`으로 확인합니다. 파일만 적용하려면 `--files-only`, 기존 파일 보존은 `--adopt`를 사용합니다. SEV까지 설치할 경우 파일 전용 옵션을 생략합니다. 기존 핵심 파일이 준비된 프로젝트는 `python scripts/install_sev.py --target <project>`로 연결합니다. 로그인 시작 등록은 `--no-autostart`로 생략할 수 있습니다.

실제 설치는 인터넷·다운로드·개인 경로 쓰기를 수행합니다. 기존 설치를 덮어쓰지 않고 새 버전을 준비하며 기존 개인 스킬은 보존합니다. 기존 프로젝트는 명시적으로 연결하지 않으면 이전 runtime을 계속 사용합니다. 실패 배포와 이전 배포는 자동 삭제하지 않습니다. 설치 전후 동작은 `assets/starter/README.md`에서 확인하세요.

Windows 설치는 새 venv 생성 직후 네이티브 `codex sandbox --include-managed-config --permission-profile :workspace`에서 해당 Python의 표준 라이브러리 읽기, 자식 Python 실행, 임시 프로젝트 파일 읽기·쓰기를 검사합니다. 45초 제한이며 모델이나 인증을 호출하지 않습니다. 통과 후에만 의존성·모델 준비, 서비스 시작, 프로젝트 연결·스킬·시작 항목 등록을 진행합니다. 다른 플랫폼은 `not_applicable`로 보고하며 Windows 검사 통과로 취급하지 않습니다.

CLI 누락, 지원하지 않는 옵션, 접근 거부, 시간 초과는 설치 실패입니다. 출력의 제한된 runtime 경로를 기준으로 관리자에게 읽기·실행 접근 및 관리 정책을 확인하거나 네이티브 Codex CLI를 설치·업데이트한 뒤 재시도하세요. 검사기는 ACL·보안 설정·샌드박스 모드를 변경하거나 무제한 실행으로 재시도하지 않습니다. 서비스 시작 실패도 기존 연결과 runtime·개인 스킬을 보존하며 실패한 새 배포는 점검용으로 남깁니다. 이 검사는 설치 시점의 접근 확인이며 이후 정책 변경이나 실제 모델 추론까지 보증하지 않습니다.

0.3.3은 이 사전 검사를 포함하는 별도 버전입니다. 기존 0.3.1·0.3.2 소스와 설치는 보존하며 기존 프로젝트는 명시적으로 연결할 때만 새 runtime을 사용합니다.

이 수정본 제작 중 실제 사용자 환경에 설치하거나 시작 항목을 등록하지 않았습니다. 실제 Codex 유료 실행과 모델 추론·설치 검증은 별도 환경에서 필요합니다.
