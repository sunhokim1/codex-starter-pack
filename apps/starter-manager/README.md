# Codex Starter 관리자

Windows 한국어 WinForms 앱의 로컬 버전은 0.2.0이며 starter 0.4.0 소스·클라이언트·누락 템플릿을 자동 설치·업데이트합니다. 설치 성공과 Rev 실행 준비는 별도 상태입니다. GPU·모델·환경 lock·서비스·연결 JSON 부재 또는 현재 여유 RAM 부족은 소스 설치 실패 사유가 아닙니다. 실제 추론은 확인하지 않습니다.

기본 경로는 main을 한 번 조회한 뒤 immutable commit의 release와 설치기 해시, ZIP 전체 파일 목록·해시를 검증합니다. 전송은 크기·시간·호스트·경로 제한과 최대 두 번의 시도로 제한합니다. 공개 main에 0.4.0이 없으면 구체적인 다운로드 오류로 중단하고 기존 파일을 보존합니다. 자동 기능은 유지하며, 미게시 commit을 만들거나 게시하지 않습니다. 검토한 로컬 번들은 PowerShell `-BundlePath`로 사용할 수 있습니다.

## 소스 소유권과 보존 경계

`.ai/starter-source/`는 실행 가능한 Python client/controller와 템플릿을 포함한 검증 번들입니다. `.ai/source-install.json`은 소스 버전·snapshot·파일 해시 영수증이며 실행 연결이 아닙니다. 이 영수증은 `.ai/sev.json`, `.ai/rev.json`, `.ai/rev-install.json`을 대체하지 않습니다. 기존 AGENTS·PROJECT·README·모델·routing·검증·설정은 바이트 그대로 보존하고 누락 템플릿만 생성합니다. 기존 완료 기록·비밀·사용자 코드도 유지합니다. 관리 소스 실행 시 `python -B`로 bytecode 생성을 막으세요.

소스 업데이트는 모델 다운로드·환경 설치·서비스 시작·실행 연결 전환·완료 작업 재생을 수행하지 않습니다. 새 폴더는 소스 설치 후에도 Rev 준비가 필요합니다. 연결·환경 준비는 [명시적 이전 안내](../../distribution/releases/0.4.0/universal-ai-starter/MIGRATION.md)를 검토한 뒤 별도로 실행하세요. 현재 Windows Intel Iris Xe 장비의 약 2GiB 여유 RAM으로 실제 모델 준비·추론을 검증하지 않았습니다. 운영체제 자체를 금지 사유로 삼지 않습니다.

사용자별 manager 잠금, 대상 installation/SEV workflow/Rev workflow byte 잠금, 설정 읽기 guard, WMI 활동 확인, 링크·junction 거부를 유지합니다. 수정된 관리 파일·알 수 없는 파일·활성 또는 불확실한 작업·모호한 journal은 해당 사례만 검토하도록 중단합니다. 높은 소스 버전은 낮추지 않습니다. DPAPI journal의 before/after 이미지로 staging·반영·복구를 보호하고 동시 편집은 덮어쓰지 않습니다. 확인된 중단 transaction은 소스를 복구하며 작업 자체를 재실행하지 않습니다. Python CLI도 별도 bounded write-ahead journal과 동일 byte 잠금을 사용합니다. manager는 격리 staging에서 CLI를 완료하고 자신의 transaction으로 대상에 반영합니다.

## 로컬 빌드와 진단

`build-core.ps1`, `build.ps1`로 로컬 .NET Framework 빌드를 생성합니다. `StarterManager.CoreTests.exe --self-test <짧은 fixture 루트>`는 가짜 전송·설치와 실제 Job Object 프로세스 완료 계약을 검사합니다. GUI의 `--self-test`, `--smoke-test`는 실제 Form과 가짜 operation을 사용합니다. 진단은 사용자 설치·설정·모델·네트워크를 사용하지 않습니다. .NET Framework 경로 길이 제한 때문에 짧은 경로가 필요합니다. 정책·권한·인증·startup을 변경하지 않습니다.

`package.ps1`은 EXE와 이 문서만 ZIP으로 묶고 `artifacts.json`에 해시를 기록합니다. 공개 앱 0.1.0과 이 로컬 0.2.0은 다릅니다. 실제 원격 게시·환경 준비·모델 추론은 미검증이며 별도 작업입니다.
