# Codex Starter 관리자

Windows용 한국어 관리자 앱입니다. 앱 버전은 **0.1.0**, 현재 지원 스타터팩은 **0.3.3**입니다. 압축을 푼 폴더의 `CodexStarterManager.exe`로 실행하며 Python이나 별도 GUI 패키지는 앱 실행에 필요하지 않습니다. 앱 EXE 자체는 자동 교체하지 않습니다.

## 빠른 사용법

1. [Windows용 앱 ZIP 다운로드](https://github.com/sunhokim1/codex-starter-pack/releases/download/manager-v0.1.0/CodexStarterManager-0.1.0-win.zip)를 받아 별도 폴더에 압축을 푸세요. ZIP에는 EXE와 이 안내서만 포함됩니다. [배포 안내](https://github.com/sunhokim1/codex-starter-pack/releases/tag/manager-v0.1.0)의 `artifacts.json`에는 ZIP과 내부 파일의 SHA256·크기가 있습니다. 이미 ZIP을 풀었다면 다음 단계부터 진행하세요.
2. 압축을 푼 폴더에서 `CodexStarterManager.exe`를 실행하세요. 빌드는 필요하지 않습니다.
3. 첫 실행에서 빈 폴더 또는 기존 프로젝트 폴더를 선택하세요. 배포 확인 후 필요한 스타터팩 설치·업데이트·복구를 자동 진행합니다. 정상인 같은 버전은 건너뛰고 높은 버전을 낮추지 않습니다. **완료**와 스타터팩 버전을 확인하세요.
4. 이후 앱 실행부터 기억한 폴더를 자동 확인하고 필요한 갱신을 진행합니다. **폴더 선택 / 변경**, **다시 확인**으로 대상을 바꾸거나 재시도할 수 있습니다. 네트워크·준비사항·실행 중 작업 때문에 중단되면 안내된 문제를 해결한 후 다시 확인하세요.

## 설치 전 준비와 보존 범위

Windows와 PowerShell, 인터넷 연결, 의존성·로컬 분류 모델을 내려받을 디스크 공간이 필요합니다. 실제 스타터팩 설치에는 **Python 3.11 이상, 네이티브 Codex CLI와 사용자 인증, 해당 계정에서 이용 가능한 코딩 모델**을 먼저 준비하세요. 관리기는 도구 설치나 로그인, 모델 이용 권한·무료 사용량을 제공하지 않으며 Codex 인증 설정을 바꾸지 않습니다.

기존 프로젝트 문서·설정과 사용자 파일을 보존하고, 기존 `AGENTS.md`와 `.gitignore`의 관리 블록만 갱신합니다. 충돌이나 복구가 필요한 상태이면 내용을 보존하고 안내합니다. 설치 중에는 프로젝트 파일을 직접 편집하거나 개발 작업을 실행하지 마세요. 자세한 반영·복구 범위는 뒤의 **보존과 복구**를 참고하세요.

검증은 임시 프로젝트와 가짜 다운로드·설치기를 사용한 오프라인 점검입니다. 실제 네트워크 설치·로그인·서비스 준비 상태와 모든 Windows 환경의 권한·실행 정책은 검증하지 않았습니다.

## 앱 사용 중 안내

설정은 `%LOCALAPPDATA%/CodexStarterManager/settings.json`에 원자적으로 저장합니다. 설정이 손상되거나 폴더가 이동·삭제·접근 불가 상태이면 자동 작업을 시작하지 않고 다시 선택하도록 안내합니다. 폴더 선택을 취소하면 대기합니다. 같은 사용자 세션의 중복 앱은 차단하며 설치는 사용자별 코어 잠금으로도 직렬화합니다. 설치 중에는 폴더 변경과 중복 확인이 차단됩니다.

다운로드까지는 **취소**할 수 있습니다. 설치 준비·복구가 시작되면 **완료 후 닫기** 또는 창닫기는 요청을 기억하고 작업이 끝날 때까지 창과 설치 프로세스를 유지합니다. 오류가 발생하면 창을 유지해 안내를 보여 줍니다. 작업 관리자로 강제 종료하지 마세요. 화면 기록은 코어의 단계 안내만 표시하고 설치기 출력·파일 내용·일반 예외 원문을 기록하지 않습니다.

## 유지 관리자: 빌드와 독립 점검

아래 명령과 상대 경로는 소스 저장소 루트 기준이며 ZIP 사용자의 실행 절차가 아닙니다. 공개 저장소의 [관리기 소스](https://github.com/sunhokim1/codex-starter-pack/tree/main/apps/starter-manager)와 [기존 0.3.3 번들](https://github.com/sunhokim1/codex-starter-pack/tree/main/distribution/releases/0.3.3/universal-ai-starter)은 별도 경로입니다.

Windows 기본 .NET Framework와 로컬 `csc.exe`만으로 빌드합니다. GUI/코어 실행 자체에 Python은 필요하지 않습니다. 실제 스타터 runtime 설치에는 기존 설치기 계약에 따라 Python 3.11 이상, native Codex CLI와 사용자 로그인이 먼저 준비되어야 합니다. 관리기는 도구 설치, 로그인, ACL 부여, 관리자 승격, 보안정책 변경, 유료 모델 호출을 하지 않습니다.

```powershell
powershell -NoProfile -File .\apps\starter-manager\build.ps1
# Windows PowerShell 실행 정책이 위 명령을 차단하고 이미 허용된 PowerShell 7이 있다면:
# pwsh -NoProfile -File .\apps\starter-manager\build.ps1
# 아래는 격리된 진단 명령입니다. 기존 fixture 루트를 반드시 지정합니다.
$app = Join-Path $PWD 'apps/starter-manager/dist/CodexStarterManager.exe'
$check = Start-Process -FilePath $app -ArgumentList '--self-test', '.' -WindowStyle Hidden -PassThru -Wait
$check.ExitCode
Get-Content .\self-test-result.json
$smoke = Start-Process -FilePath $app -ArgumentList '--smoke-test', '.' -WindowStyle Hidden -PassThru -Wait
$smoke.ExitCode
Get-Content .\smoke-test-result.json

# 코어만 독립적으로 점검할 때 사용합니다.
& .\apps\starter-manager\build-core.ps1
& .\apps\starter-manager\bin\StarterManager.CoreTests.exe --self-test .\apps\starter-manager\bin\fixtures

# 빌드와 진단을 마친 뒤 별도 앱 ZIP 및 해시·내용 목록을 만듭니다.
powershell -NoProfile -File .\apps\starter-manager\package.ps1
Get-Content .\apps\starter-manager\dist\artifacts.json
```

이 PC에서는 위 `powershell` 빌드가 실행 정책으로 차단되어 종료코드 1을 반환했고, 현재 허용된 PowerShell 세션에서 `& .\apps\starter-manager\build.ps1`로 빌드했습니다. 정책 변경·우회·관리자 승격은 하지 않았습니다. 같은 제한이 있으면 허용된 PowerShell 환경을 사용하세요. 패키징과 코어 빌드에도 같은 원칙을 적용합니다.

코어 예시의 `bin/fixtures` 폴더는 실행 전에 생성하세요. `dist/artifacts.json`에는 ZIP의 SHA256과 내부 두 파일의 경로·크기·SHA256을 기록합니다. ZIP은 명시한 두 파일만 읽어 만들며 `.ai/verification.yaml`, workflow state, 인증 파일, 개인 로그, 진단 JSON, 코어 테스트 EXE를 포함하지 않습니다. 해시는 전송·내용 대조용이며 배포자 서명이 아닙니다.

`build.ps1`은 성공 시 0, 실패 시 1을 반환합니다. GUI 진단은 성공 0, 실패 1, 잘못된 인자/없는 fixture 루트 2를 반환합니다. 옵션 없이 실행할 때만 실제 사용자 설정과 운영용 서비스를 구성합니다. GUI 진단은 명시한 루트 아래 고유한 임시 폴더의 설정과 가짜 작업만 사용하며 정리 후 JSON 결과를 남깁니다. 경로에 공백이 있는 fixture 루트는 `Start-Process`의 인자 문자열에서 따옴표로 감싸세요. 긴 경로는 Framework 경로 제한 때문에 피하세요.

GUI `--self-test`는 설정 손상·폴더 삭제·특수문자·원자적 저장, 기억된 폴더 자동 확인, 중복 요청 차단, 취소 후 재시도, 복구·설치·반영 중 닫기 대기, 오류 후 창 유지·재시도 및 비밀값 원문 비노출을 fixture로 검사합니다. `--smoke-test`는 STA에서 실제 Form과 주요 컨트롤을 생성·해제하고 자동 작업이 호출되지 않았는지 확인합니다. 두 진단 모두 운영용 네트워크·설치기·활성 프로젝트 검사·사용자 설정 저장소를 생성하지 않으며 실제 설치나 네트워크 연결을 검증하지 않습니다. 루트 회귀 검사에서 두 모드를 별도로 실행합니다.

별도 `StarterManager.CoreTests.exe --self-test`는 지정 경로 안의 고유한 임시 fixture만 생성·삭제합니다. 실제 PowerShell 프로세스와 Windows Job Object, 자손 프로세스 강제 종료 및 byte-range 잠금 smoke를 포함합니다. 다운로드와 설치기는 fixture로 대체하며, 설치된 runtime·개인 skills·자동시작·Desktop Starter를 변경하지 않습니다. 루트 `tests/test_starter_manager.py`는 코어 빌드와 같은 self-test, Python `msvcrt`와 C# 첫 byte 잠금의 실제 상호 배제, 앱 ZIP의 정확한 내용과 해시를 검사합니다. `tests/test_bundled_regressions.py`는 별도 Python 프로세스로 기존 0.3.3 번들의 오프라인 회귀를 루트 검사에 연결합니다. 설정된 루트 검사는 controller가 실행합니다. 네트워크나 실제 설치의 검증은 아닙니다. 실제 Form 생성 smoke는 화면 배치의 육안 검수나 장시간 실제 설치 상호작용 전체를 보장하지 않습니다.

## 코어 연결 인터페이스

`ManagerCore(FileStore, ITransport, IInstaller, IActivityGuard, sharedLocks)`의 `Run(folder, CancellationToken, Action<Progress>)`을 GUI worker thread에서 호출합니다. 한 코어 인스턴스는 한 번에 한 작업만 실행합니다. `sharedLocks`는 모든 관리기 인스턴스에 동일한 사용자별 로컬 경로를 전달합니다. 실제 구현은 `FileStore`, `HttpsTransport`, `PowerShellInstaller`, `WindowsActivityGuard`입니다. 네트워크·파일 쓰기·프로세스·활성 상태 경계를 fixture로 교체할 수 있습니다.

`Progress`는 한글 상태, `Phase`, `CanCancel`을 전달합니다. 다운로드까지만 취소를 받습니다. `Preparing` 이후 취소나 창닫기를 요청하면 GUI는 요청을 기억하고 `Run`이 끝날 때까지 창과 프로세스를 유지해야 합니다. 설치 중 강제 종료 버튼을 제공하면 안 됩니다. 완료까지 시간 제한을 걸어 설치 프로세스를 임의로 끊지 않습니다. `ManagerException`과 `ProcessUncertainException`은 사용자용 한글 설명이며, 그 밖의 예외는 GUI에서 일반적인 오류로 표시하고 원문이나 경로·파일 내용을 로그에 복사하지 않습니다. 오류 후 다시 확인이 가능합니다.

## 버전과 다운로드

main SHA는 확인 주기마다 GitHub API에서 한 번 조회합니다. 동일 SHA의 설정, release metadata, 설치기와 누락 core 파일의 템플릿만 사용합니다. 템플릿은 release 해시를 대조해 staging에 채우므로 기존 프로젝트에 AGENTS와 모델 설정만 있어도 나머지 누락 파일을 보완합니다. HTTPS 지정 호스트·저장소·경로, 1 MiB 문서 제한, redirect 거부, 요청 30초·읽기 15초·전체 60초 제한을 적용합니다. 인증서 검증을 유지합니다. 저장한 설치기 바이트를 실행 직전에 다시 SHA256 대조하고 `-EncodedCommand`에서 인자 경계를 보존해 실행합니다. `exit` 전에 JSON 결과를 동기적으로 수집합니다. 가변 raw main을 실행하지 않습니다. 실행정책을 설정하거나 우회 플래그를 전달하지 않습니다.

현재 공개 설치 계약에 맞춰 `0.3.3`만 지원합니다. 미래 배포는 metadata와 설치기 계약을 검토한 뒤 지원 범위를 바꿔야 합니다. 버전은 세 정수로 비교합니다. 같은 버전은 필수 경로·배포 내부 상대 위치·전체 service/runner 소스 해시·service state 구조가 정상일 때 건너뜁니다. 낮은 버전은 업데이트하고 같은 버전의 손상은 새 deployment로 복구합니다. 높은 버전은 손상되어도 downgrade하지 않습니다. 읽을 수 없는 버전/schema는 설치를 중단합니다.

정상성 검사는 Python/venv/model 바이너리 무결성이나 서비스 통신 readiness를 증명하지 않습니다. 설치 중 서비스 시작·status 확인은 기존 번들 설치기가 수행합니다. 관리기의 성공 판정에는 프로세스 종료코드와 마지막 schema 1 결과, 버전, 필수 경로, 소스 해시가 모두 필요합니다. 네트워크 실패는 기존 연결을 건드리지 않습니다.

## 잠금과 실행 중 작업

관리기는 사용자별 `manager.lock`, 실제 대상 `.ai/installation.lock`, `.ai/project-workflow/lock`의 첫 byte를 잠급니다. 실제 설치기는 별도 staging 대상의 프로젝트 잠금과 기존 전역 runtime 잠금을 사용하므로 부모와 자식이 같은 설치 잠금을 기다리지 않습니다. 관리기끼리는 전역 잠금으로 직렬화하고 다른 설치기는 실제 대상 잠금으로 배제합니다. 파일 존재만으로 활성 상태를 판단하지 않습니다.

미완료 workflow state, `running` 작업 보고서, WMI로 확인한 runner/native 실행 또는 읽을 수 없는 개발 프로세스 상태가 있으면 중단합니다. quick runner 0.3.3은 workflow 잠금에 참여하지 않으므로 관리기는 기존 모델·routing·검증 파일을 독점적으로 열어 일반적인 새 runner의 설정 읽기를 차단하고, 검사 후 설치 및 각 반영 직전에 활성 상태를 다시 검사합니다. WMI는 작업 디렉터리를 추정하지 않고 다른 프로젝트의 runner 실행도 보수적으로 거부합니다. 사용자가 외부 설정을 지정해 직접 실행한 명령이나 독자적인 파일 변경 도구는 이 잠금 프로토콜에 참여하지 않습니다. 앱 설치 중에는 그러한 작업을 실행하지 않아야 합니다. 외부 명령 전체를 OS 차원에서 금지하는 기능은 제공하지 않습니다.

## 보존과 복구

설치기는 `.ai/starter-manager/stage`에 원래 core 파일의 복사본을 받아 `--adopt --no-autostart`로 실행합니다. native preflight도 선택한 프로젝트 아래 staging에서 수행합니다. 새 immutable runtime은 기존 번들 정책대로 전역 저장소에 만들어지며 기존 deployment나 다른 프로젝트 연결을 변경하지 않습니다. 개인 skills는 기존 파일을 보존하며 없는 기본 파일만 추가하는 기존 정책을 유지합니다. custom skills나 개인 `universal-ai-starter` 폴더를 교체하지 않습니다.

검증이 끝나면 `AGENTS.md`, `.gitignore`, `PROJECT.md`, `README.md`, `.ai/config.yaml`, `.ai/models.yaml`, `.ai/routing.yaml`, `.ai/verification.yaml`, `.ai/sev.json`만 반영합니다. 기존 프로젝트 문서와 설정은 바이트가 같아야 합니다. 기존 AGENTS의 `starter-sev` 및 ignore의 `starter-private` 관리 블록만 갱신할 수 있고, 그 밖의 내용 변경은 거부합니다. 기존 설치기가 하는 줄바꿈 정규화와 끝 공백 정리는 허용합니다. 코드·작업기록·인증·비밀파일을 열거하거나 복사하지 않습니다. 기존 사용자 파일을 임의 덮어쓰지 않습니다.

반영 전에 모든 before/after 바이트와 단계를 durable journal에 기록하고 flush합니다. journal은 Windows DPAPI `CurrentUser`로 암호화·인증하며 대상 절대 경로에도 결합됩니다. staging은 프로젝트의 기존 접근권한을 상속하며, 전용 폴더의 `.gitignore`가 중간 복사본을 Git에서 제외합니다. ACL은 변경하지 않습니다. 관리기 기록을 다른 사용자/PC로 옮기면 자동 복구할 수 없습니다. 백업 내용은 로그에 출력하지 않습니다.

파일을 바꾸기 전 현재 해시를 다시 확인합니다. 실패·재실행 시 현재 파일이 before 또는 기록된 after와 같은 경우에만 역순 복원합니다. 동시 사용자 변경이나 손상된 journal이 있으면 내용을 보존하고 수동 병합을 안내합니다. 복구 중 중단도 같은 journal로 다시 시도할 수 있습니다. 파일 교체는 개별 원자적 교체이며, 서로 다른 도구가 바로 같은 순간 파일 이름을 교체하는 경쟁까지 OS 수준의 compare-and-swap을 보장하지는 않습니다. 설치 중 직접 파일 편집은 피해야 합니다.

정상 창닫기는 완료 대기, 비정상 앱 종료는 kill-on-close Job Object가 설치기와 그 자손을 종료합니다. suspended 상태에서 Job Object에 먼저 넣고 시작하므로 시작 직후 자손이 빠져나갈 틈을 없앱니다. 성공 종료 후에만 kill-on-close를 해제해 새 서비스가 계속 실행되게 합니다. 프로세스 트리 종료를 확인할 수 없으면 `uncertain` journal을 남기고 자동 재설치를 거부합니다. 강제 종료 중에는 프로젝트 반영이 없거나 write-ahead journal에 복구 정보가 있습니다.

성공한 staging 설치 후 사후 검증·반영이 실패하면 새 deployment와 서비스 또는 새 기본 skill 파일이 남을 수 있습니다. 기존 연결 복원은 이들을 삭제하거나 다른 runtime을 정지하지 않습니다. 이들은 기존 runtime에 영향을 주지 않는 점검 대상이며, 관리기는 임의로 전역 파일을 삭제하지 않습니다. 알 수 없는 staging 파일도 삭제하지 않습니다. 정상 완료·복구 시 알려진 복사본과 journal은 지우며 빈 폴더와 전용 ignore는 남을 수 있습니다. journal 손상·사용자 편집 충돌·`uncertain` 단계는 관련 프로세스가 끝났는지 확인하고 before/after를 수동 대조한 후 전용 폴더를 정리해야 합니다. 자동 복구는 전체 전역 설치의 원자적 취소를 의미하지 않습니다.
