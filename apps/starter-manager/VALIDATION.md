# 로컬 0.2.0 최종 검증 기록

2026-10-20 자동 소스 설치·업데이트와 Windows/CPU 경로 수정 후의 기록입니다. 공개 앱 0.1.0과 구분하며 게시하지 않았습니다. 설정된 루트 unittest는 controller 소유로 실행하지 않았습니다.

| 실제 검사 | 결과 |
| --- | --- |
| `& apps/starter-manager/build-core.ps1` | 종료 0 |
| `& apps/starter-manager/build.ps1` | 종료 0 |
| `StarterManager.CoreTests.exe --self-test <소유 fixture>` | 종료 0, 49 assertions |
| `CodexStarterManager.exe --self-test <소유 fixture>` | 종료 0, 50 assertions |
| `CodexStarterManager.exe --smoke-test <소유 fixture>` | 종료 0, 17 assertions |
| `& apps/starter-manager/package.ps1` | 종료 0, 로컬 0.2.0 ZIP·artifacts.json 생성 |
| 설치된 Python의 `-m unittest discover -s distribution/releases/0.4.0/universal-ai-starter/tests -p 'test_*.py' -v` | 종료 0, 133개 통과 |
| 루트·canonical `scripts/package_starter.py --check` | 각각 종료 0, 72개 소스 |
| 두 빌더의 임시 ZIP과 최종 ZIP | 세 출력 바이트 동일, 73개 항목의 전체 목록·해시·소스 일치 |
| 작업 시작 116개·이전 보호 113개 지문 | private 설정, 보관 릴리스·ZIP 및 루트 ZIP 변경 없음 |

GUI는 `Start-Process -WindowStyle Hidden -PassThru`로 소유 프로세스만 생성하고 45초 제한으로 완료를 기다려 실제 종료 코드와 JSON을 수집했습니다. 네트워크·실제 프로젝트 설치·사용자 설정 쓰기를 사용하지 않았습니다. 코어 fixture는 신규 자동 설치·Rev 부재 업데이트·현재 no-op·내용 보존·변경/활성/불확실 상태 차단·취소·복구·고정 설치기 해시·소유 프로세스 완료를 확인합니다. Windows CPU/CUDA 로더·서비스는 실제 인터페이스를 호출하되 무거운 모델·의존성을 mock으로 대체합니다.

첫 Windows PowerShell 자식 빌드는 기본 실행 정책으로 종료 1이었습니다. 정책 변경 없이 허용된 현재 PowerShell에서 빌드했습니다. 기본 `git diff --check`는 기존 CRLF를 공백 오류로 보고했고, 설정 변경 없는 `git -c core.whitespace=cr-at-eol diff --check`는 종료 0입니다.

앱 ZIP은 정확히 `CodexStarterManager.exe`, `README.md`만 포함합니다. 크기·파일 SHA256·전체 ZIP SHA256이 `dist/artifacts.json`과 일치합니다. 상세 근거는 `.ai/reports/integration-final-evidence.json`, 번들 로그는 `.ai/reports/integration-bundle-tests.log`입니다.

최종 스타터 ZIP SHA256은 `d69d669ab7b17f0678b128f33322e89d315c78e1133fe97f07c9cd047c32ae1d`입니다. 원본은 `distribution/releases/0.4.0/universal-ai-starter/`, 출력은 `distribution/releases/0.4.0/universal-ai-starter.zip`입니다.

읽기 전용 진단에서 총 RAM 15.69GiB·가용 7.29GiB, Intel Iris Xe, NVIDIA 관측 없음입니다. CPU fp32 추정 39.53GiB에 부족하며 OS 금지가 아닙니다. 환경 lock 완성·실제 모델 준비/다운로드/로드/추론·원격 0.4.0 게시·controller 최종 루트 검사 결과는 이 검증에 포함하지 않습니다. 기존 사용자 설치·프로젝트·개인 runtime/skills·startup·인증·ACL은 변경하지 않았습니다.
