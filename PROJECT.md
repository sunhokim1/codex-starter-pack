# 프로젝트

## 유형과 목표

Universal AI Development Starter 0.4.0 배포 소스와 Windows용 Codex Starter 관리자 앱을 관리합니다. 관리기는 처음 선택한 프로젝트 폴더를 기억하고 고정 snapshot의 무결성을 검증하여 소스·클라이언트·누락 템플릿을 자동 설치·업데이트합니다. 빈 폴더와 기존 SEV·Rev 프로젝트를 지원하며 기존 실행 연결과 사용자 설정을 보존합니다.

## 주요 사용자

명령을 외우지 않고 프로젝트별 스타터팩을 관리하려는 Windows 사용자입니다.

## 기술 스택과 실행 환경

관리기는 Windows 기본 .NET Framework C# WinForms이며 `C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe`로 빌드합니다. 로컬 앱 버전은 0.2.0이고 지원 스타터 버전은 0.4.0입니다. 공개 앱 0.1.0과 구분하며 새 버전을 게시하지 않았습니다. EXE 자체는 외부 GUI 패키지가 필요 없고 소스 설치에는 Python 3.11 이상을 사용합니다. 실제 실행에는 설치·로그인된 native Codex CLI 및 native sandbox 준비가 별도로 필요합니다.

## 구조와 화면

`apps/starter-manager/App.cs`가 진입점, 한국어 화면, 사용자별 원자적 설정 저장을 담당합니다. `Core.cs`는 immutable snapshot, 버전 판단, 잠금, staging, 연결 검증·복구를 담당하며 `WindowsBoundary.cs`가 Windows 설치 프로세스 경계를 제공합니다. `build.ps1`은 단독 실행 가능한 `dist/CodexStarterManager.exe`를 생성합니다. `package.ps1`은 EXE와 한국어 README만 포함하는 별도 앱 ZIP과 SHA256 목록을 생성합니다. 기존 `build-core.ps1`과 코어 진단 EXE도 유지합니다.

첫 실행은 폴더 선택, 이후 실행은 기억한 폴더의 자동 확인으로 시작합니다. 폴더 변경·다시 확인, 단계별 상태와 진행 표시, 준비사항 및 오류 안내를 제공합니다. 설치 준비 이후 취소·닫기는 작업 완료까지 기다립니다. 오류가 나면 창을 유지해 복구 안내를 확인할 수 있습니다.

## 검증

루트 회귀 검사는 `tests/test_starter_manager.py`, 코어 fixture는 `CoreSelfTest.cs`, GUI fixture와 실제 STA Form 생성 검사는 `AppDiagnostics.cs`에 있습니다. GUI 진단은 명시한 기존 fixture 루트 안에서만 동작하며 네트워크·실제 설치·사용자 설정 변경을 하지 않습니다. 구성된 검사 명령은 `.ai/verification.yaml`을 기준으로 controller가 실행합니다. 빌드와 진단 사용법은 `apps/starter-manager/README.md`에 있습니다.

## 제약과 기존 배포 사실

canonical runtime은 `distribution/releases/0.4.0/universal-ai-starter/`이며 root/experiments 호환 진입점은 이를 사용합니다. 기존 immutable 0.3.1·0.3.2·0.3.3 번들, ZIP, manifest는 관리기 구현 때문에 변경하지 않습니다. 프로젝트 코드·문서·사용자 지침·모델/routing/검증 설정·작업기록·인증·비밀값과 개인 skills를 보존합니다. 자동 권한 부여·관리자 승격·정책/인증 변경·유료 모델 호출·실제 PC 설치·자동시작 변경은 수행하지 않습니다. 앱 자체 자동 교체와 외부 게시는 범위 밖입니다. 관리기의 로컬 빌드 산출물은 기존 스타터 ZIP과 별도로 취급합니다.

소스 버전·무결성 영수증은 `.ai/source-install.json`, 관리 소스는 `.ai/starter-source/`에 둡니다. 모델·환경 lock·서비스·연결·여유 RAM 부재는 소스 업데이트를 막지 않습니다. 수정된 관리 파일, 활성·불확실한 workflow와 모호한 journal은 개별 검토를 위해 중단하며 잠금·백업·롤백·취소 보호를 유지합니다. 호환되지 않는 실행 설정·상태는 자동 변환하거나 완료 작업을 재생하지 않습니다.

선택적 Rev 환경 준비·연결 이전과 인증된 실제 추론은 별도 명시 작업입니다. CPU와 Windows CUDA도 선택 가능하며 dtype별 메모리 추정과 실제 의존성·장치 capability를 확인합니다. Windows 11·Intel Iris Xe 호스트의 총 RAM 약 15.7GiB는 CPU fp32 추정 약 39.53GiB에 부족합니다. OS 금지가 아니며 이 장비에서 모델 다운로드·로드·추론을 수행하지 않았습니다. 검토된 환경 lock과 실제 추론, 원격 0.4.0 게시도 미완료입니다.
