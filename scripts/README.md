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

## Windows 관리기용 비대화형 계약

관리기는 GitHub API `https://api.github.com/repos/sunhokim1/codex-starter-pack/commits/main`에서 main의 40자리 소문자 commit SHA를 한 번만 확인합니다. 그 SHA를 사용한 `https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/<SHA>/scripts/install_from_github.ps1`을 파일로 받아 실행해야 합니다. raw main을 `iex`로 실행하지 않습니다. API 조회와 설치기 파일 다운로드의 HTTPS 호스트·경로·크기·시간 제한 및 redirect 거부는 호출하는 관리기의 책임입니다. 설치기는 전달된 SHA로 `.ai/config.yaml`과 `distribution/releases/0.3.3/universal-ai-starter/release.json`을 다시 확인합니다. `SnapshotCommit`만 전달했다고 실행 중인 파일의 출처가 증명되는 것은 아닙니다.

저장한 설치기의 호출 인자는 다음과 같습니다. 관리기는 문자열로 PowerShell 명령을 조립하지 말고 인자 경계를 보존해야 합니다. `-EncodedCommand`를 사용하는 경우 경로를 UTF-8/Base64 데이터로 전달하고 PowerShell 안에서 복원한 뒤 `& $installer -Target $target ...`으로 호출할 수 있습니다. 경로에 작은따옴표, 공백, 한글, `$`, `&`, 대괄호가 있어도 명령으로 해석하면 안 됩니다. 큰따옴표는 Windows 폴더 이름에 사용할 수 없습니다.

```powershell
powershell.exe -NoProfile -NonInteractive -File .\install_from_github.ps1 -Manager -Target 'C:\작업\내 프로젝트' -SnapshotCommit <SHA> -ExpectedVersion 0.3.3
```

설치기의 ZIP pin은 `1f1a8e97e097e457cc1369c26cc652dfb57e15c0`이며 main snapshot SHA와 별개입니다. 현재 지원 버전은 0.3.3입니다. snapshot 설정 버전, snapshot release metadata, ZIP 내부 버전과 전체 파일별 SHA256 목록이 모두 일치해야 압축을 풉니다. 새 배포 지원 시 이 계약도 함께 갱신해야 합니다. metadata는 각각 1MiB, ZIP은 수신 중 32MiB로 제한합니다. ZIP은 최대 256개 파일과 총 64MiB의 압축 해제 크기로 제한하고 경로·중복·링크·모든 해시를 쓰기 전에 검사합니다. 설치기에서 내려받는 URL은 지정 저장소의 immutable raw 경로만 허용하며 모든 redirect를 거부합니다. 요청 및 읽기 timeout은 각각 30초이고 스트림 수신 중 60초 경과도 검사합니다. TLS 1.2를 추가로 허용하되 인증서 검증은 그대로 사용합니다.

`-Manager`의 프로세스 종료코드는 성공 `0`, 실패 `1`, 대상 미지정 취소 `2`입니다. stdout의 `schema: 1`인 마지막 JSON 객체를 결과로 읽습니다. 하위 도구의 일반 출력이나 JSON은 결과 객체가 아닙니다. 성공 객체는 `status: installed`, `exitCode`, `version`, `snapshot`, `target`, `autostart: false`, `personalSkillReplaced: false`를 포함합니다. 취소는 `status: cancelled`, 실패는 `status: error`와 일반적인 한국어 `message`를 반환하며 예외나 비밀값을 결과 JSON에 직렬화하지 않습니다. 잘못된 PowerShell 호출 문법이나 프로세스 강제 종료는 JSON을 만들지 못할 수 있으므로 결과 누락도 실패로 처리해야 합니다. 성공 전에 `.ai/sev.json`의 버전과 `python`, `service`, `state`, `runner`, `project_runner` 파일의 존재 및 링크 여부를 검사합니다.

관리기 경로는 기존 bootstrap을 실행하지 않습니다. Python 3.11 이상이 이미 있어야 하고 없으면 사용자가 준비하도록 안내하며 winget, 관리자 승격, ACL 변경을 실행하지 않습니다. GUI 자체에는 Python이 필요하지 않습니다. Codex CLI 설치와 로그인도 사용자의 준비사항입니다. 준비된 Python으로 검증된 번들의 `scaffold.py --adopt --no-autostart` 또는 기존 core 파일이 있는 경우 `install_sev.py --no-autostart`를 호출합니다. 따라서 자동시작 항목을 추가하거나 교체하지 않습니다. 번들 설치의 native sandbox 사전 점검을 그대로 사용하며 실패 시 권한을 자동 부여하지 않습니다.

프로젝트의 기존 core 파일은 `--adopt`가 보존하고 없는 파일만 추가합니다. 설치기는 AGENTS의 관리 블록과 `.gitignore`의 관리 블록, 선택한 프로젝트의 `.ai/sev.json` 연결을 갱신합니다. 모델·routing·검증 설정, PROJECT.md, README, 작업기록과 비밀값을 교체하지 않습니다. runtime은 전역 저장소 아래 새 immutable 디렉터리에 만들며 다른 프로젝트의 연결을 갱신하지 않습니다. 기존 runner/workflow 개인 스킬은 번들 정책대로 보존하고 없는 기본 파일만 추가합니다. 관리기 경로는 `universal-ai-starter` 개인 스킬 폴더를 승격하거나 교체하지 않습니다. 기존 일반 원클릭 경로의 개인 스킬 백업 후 교체 동작은 유지됩니다.

번들 설치는 실패 시 자신이 갱신한 연결·AGENTS·ignore 파일과 새 개인 스킬 파일을 복원하고 새 서비스를 정지하려고 시도하며 이전 runtime은 건드리지 않습니다. 실패한 새 deployment는 점검용으로 남을 수 있습니다. scaffold가 먼저 추가한 파일은 실패 시 남고, 관리기의 사후 검증 실패는 이미 성공한 번들 설치를 자동으로 되돌리지 않습니다. 이 경우 성공으로 보고하지 않으며 재확인·복구를 안내해야 합니다. 이 계약은 전체 설치의 원자적 복구를 보장하지 않습니다. 관리기는 별도 단계에서 기존 연결의 백업과 복구, 버전 비교 및 downgrade 차단, 정상 동일 버전 건너뛰기, 활성 workflow/중복 앱 잠금, 취소·창닫기 시 하위 프로세스 종료 대신 완료 대기를 구현해야 합니다. 번들 자체는 전역·프로젝트 설치 잠금을 보유하지만 활성 workflow 잠금을 대신하지 않습니다. pip 및 모델 파일 다운로드는 번들 런타임의 기존 정책이며 위 raw 다운로드 제한이 그 네트워크까지 포괄하지 않습니다.

추가 회귀 테스트는 URL 허용 목록, snapshot/ZIP 불일치, 인자 경계, Python 준비 실패, 설치 후 경로 검사, 저장 파일 종료코드 및 설치 경계를 대체한 성공·실패를 다룹니다. 실제 설치나 네트워크 검증을 대신하지 않습니다.
