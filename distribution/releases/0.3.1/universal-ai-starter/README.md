# Universal AI Starter 0.3.1

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
python scripts/package_starter.py --output ../universal-ai-starter-0.3.1.zip
```

## 적용

먼저 `python scripts/scaffold.py --target <project> --dry-run`으로 확인합니다. 파일만 적용하려면 `--files-only`, 기존 파일 보존은 `--adopt`를 사용합니다. SEV까지 설치할 경우 파일 전용 옵션을 생략합니다. 기존 핵심 파일이 준비된 프로젝트는 `python scripts/install_sev.py --target <project>`로 연결합니다. 로그인 시작 등록은 `--no-autostart`로 생략할 수 있습니다.

실제 설치는 인터넷·다운로드·개인 경로 쓰기를 수행합니다. 기존 설치를 덮어쓰지 않고 새 버전을 준비하며 기존 개인 스킬은 보존합니다. 기존 프로젝트는 명시적으로 연결하지 않으면 이전 runtime을 계속 사용합니다. 실패 배포와 이전 배포는 자동 삭제하지 않습니다. 설치 전후 동작은 `assets/starter/README.md`에서 확인하세요.

이 수정본 제작 중 실제 사용자 환경에 설치하거나 시작 항목을 등록하지 않았습니다. 실제 Codex 유료 실행과 모델 추론·설치 검증은 별도 환경에서 필요합니다.
