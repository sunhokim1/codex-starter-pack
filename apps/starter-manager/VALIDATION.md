# 로컬 산출물 검증 기록

2026-10-20 작업 기준입니다. 설정된 루트 unittest는 controller 소유이며 이 단계에서는 실행하지 않았습니다. 아래는 앱 구현 단계의 로컬 빌드와 진단 기록입니다. 실제 프로젝트 설치는 검증하지 않았습니다. 게시 여부는 [배포 안내](https://github.com/sunhokim1/codex-starter-pack/releases/tag/manager-v0.1.0)에서 확인하세요.

| 구분 | 실제 명령 | 종료코드와 증거 |
| --- | --- | --- |
| 요청된 Windows PowerShell 빌드 | `powershell -NoProfile -File .\apps\starter-manager\build.ps1` | 1, 실행 정책에 의해 스크립트 로드 차단 |
| 허용된 현재 PowerShell 세션의 GUI 빌드 | `& .\apps\starter-manager\build.ps1` | 0, 최종 EXE 62,976바이트 |
| 별도 코어 빌드 | `& .\apps\starter-manager\build-core.ps1` | 0, 코어 DLL과 진단 EXE 생성 |
| GUI 동작 fixture | 아래 `Start-Process`에서 `--self-test` | 최종 0, 50 assertions, JSON `status=passed` |
| 실제 Form 생성 | 아래 `Start-Process`에서 `--smoke-test` | 0, 17 assertions, JSON `actualForm=true` |
| 코어 fixture와 native 프로세스 smoke | `& .\apps\starter-manager\bin\StarterManager.CoreTests.exe --self-test .` | 0, `PASS: 81 deterministic fixture assertions; native process/byte-lock smoke. No network or real installation.` |
| 앱 전용 패키징 | `& .\apps\starter-manager\package.ps1` | 0, ZIP과 `dist/artifacts.json` 생성. 문서 갱신 후 다시 패키징하며 최종 크기와 해시는 `artifacts.json` 기준 |
| 기존 배포 읽기 전용 비교 | `git diff --exit-code HEAD -- distribution universal-ai-starter.zip` | 0, 기존 manifest·릴리스 소스·스타터 ZIP 변경 없음 |

GUI 진단은 각각 다음 명령을 사용했습니다. 각 프로세스의 `ExitCode`와 결과 JSON을 확인했습니다.

```powershell
$app = Join-Path $PWD 'apps/starter-manager/dist/CodexStarterManager.exe'
$check = Start-Process -FilePath $app -ArgumentList '--self-test', '.' -WindowStyle Hidden -PassThru -Wait
$check.ExitCode
Get-Content .\self-test-result.json
$check = Start-Process -FilePath $app -ArgumentList '--smoke-test', '.' -WindowStyle Hidden -PassThru -Wait
$check.ExitCode
Get-Content .\smoke-test-result.json
```

최종 JSON 두 파일은 배포에서 제외되는 `bin/`으로 옮겼습니다. 최초 GUI self-test는 14번째 assertion에서 `InvalidOperationException`으로 실패했습니다. 진단용 `DoEvents`가 임시 메시지 루프 종료 시 WinForms 동기화 컨텍스트를 해제할 수 있어, 진단 STA 컨텍스트를 유지하도록 수정하고 GUI EXE를 다시 빌드한 후 재검증했습니다. 운영용 `Application.Run` 경로는 변경하지 않았습니다. 실행 정책은 변경하거나 우회하지 않았습니다.

ZIP을 읽기 전용으로 열어 내부 경로가 정확히 `CodexStarterManager.exe`, `README.md`인지 확인했고, 각 항목의 크기·SHA256 및 ZIP 전체 SHA256을 `artifacts.json`과 대조해 통과했습니다. 이 두 파일 외의 workflow state·설정·비밀값·진단 결과는 포함되지 않습니다. 기본 `git diff --check`는 기존 변경 파일의 CRLF를 공백 오류로 보고해 2를 반환했습니다. 설정 파일을 수정하지 않고 `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check`로 CRLF를 인정한 검사는 0을 반환했습니다.

## controller가 확인할 회귀 범위

| 요구사항 | 검사 근거 | 검증 경계 |
| --- | --- | --- |
| 버전 숫자 비교·미설치·동일·업데이트·손상·downgrade 금지 | `CoreSelfTest.cs` | 네트워크와 설치기는 fixture |
| 네트워크 실패·불완전 설치·특수문자·잠금 | 코어 fixture와 `tests/test_starter_manager.py` | byte 잠금·프로세스는 실제, 다운로드는 mock |
| 프로젝트 내용 보존·실패 복원·중단 복구·동시 편집 충돌 | 코어 fixture | 임시 프로젝트에만 쓰기 |
| 폴더 기억·취소·재시도·닫기 대기·오류 표시 | `AppDiagnostics.cs` | 실제 Form과 가짜 작업 |
| ZIP 범위·해시·EXE와 문서 일치 | 새 패키지 회귀 | controller 실행 전 |
| 기존 installer·native preflight·bundled regressions | 기존 루트 테스트와 새 `test_bundled_regressions.py` 연결 | controller 실행 전, 설치·모델 호출은 mock |

설정된 검사를 통과했다고 보고하지 않습니다. controller의 최종 결과 확인이 남아 있습니다. 라이브 네트워크, 실제 설치·로그인·서비스 readiness, 모든 Windows 환경의 실행 정책과 권한, 화면 배치 육안 검수, 장시간 실제 설치 상호작용은 이번 오프라인 검증의 범위 밖입니다. Desktop Starter·설치된 runtime·개인 skills·자동시작과 사용자 설정을 변경하지 않았습니다.
