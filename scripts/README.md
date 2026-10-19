# 0.3.3 유지 관리 및 배포

유지 관리 원본은 `distribution/releases/0.3.3/universal-ai-starter/`입니다. `distribution/manifest.json`은 Windows 사전 점검 테스트를 포함한 모든 공개 소스 파일을 명시적으로 매핑합니다. 루트 패키징은 프로젝트 디렉터리를 열거하지 않습니다. 번들 패키지 빌더도 명시적인 소스 목록을 사용하며, 무결성 검사에서 목록에 없는 파일을 거부합니다. 공개 소스를 추가할 때 두 목록을 일치시켜야 합니다.

```text
python scripts/package_starter.py
python scripts/package_starter.py --check
python distribution/releases/0.3.3/universal-ai-starter/scripts/package_starter.py --check
```

첫 번째 명령은 `.ai/config.yaml`의 릴리스 버전을 사용하고 각 소스 항목의 SHA256을 기록해 재현 가능한 `universal-ai-starter.zip`을 작성합니다. 기준 번들의 `release.json`을 다시 만들려면 해당 패키지 스크립트에 `--output <outside-bundle.zip>`을 지정한 뒤 루트 재현 가능 ZIP을 빌드하세요. 출력물은 기준 소스 외부에 두어야 합니다. 이전 0.3.1 및 0.3.2 소스는 변경하지 않습니다.

`distribution/skill/scripts/`와 실험용 runner/service 진입점은 유지 관리 원본으로 연결됩니다. 루트 `tests/`는 패키징과 설치 프로그램 통합을 테스트하고, 번들의 `tests/`는 런타임 동작을 다룹니다. 로컬 실행 설정과 보고서는 배포 매핑에서 제외됩니다.

`install_from_github.ps1`은 `-Target <folder>`를 받거나 대상 폴더를 입력받습니다. 단계별 bootstrap을 실행하기 전에 경로, 0.3.3 릴리스, ZIP 전체 및 해시를 검증합니다. 개인 스킬 승격은 bootstrap 성공 후 진행됩니다. 기존 프로젝트와 이전 스킬은 보존됩니다. Windows 사전 점검에 실패하면 이후 설정을 중단하며 설치 프로그램은 자동으로 권한을 부여하지 않습니다. 게시 전에 변경 불가 URL이 검증된 릴리스 ZIP을 포함한 커밋을 가리켜야 합니다.

설치 프로그램 테스트는 함수를 분석·로드하고 오프라인 ZIP과 모의 bootstrap을 사용합니다. Python을 설치하거나 ACL을 변경하거나 인증하거나 모델을 실행하거나 시작 항목을 수정하지는 않습니다.
