# 0.4.0 설치·배포 통합 전달

이 문서는 선행 통합 단계 기록이다. 마지막 소스 복구 단계와 최종 package 재생성은 RECOVERY_HANDOFF.md가 추가하며 이전 package identity는 최종 증거로 재사용하지 않는다.

## 변경 범위

루트 manifest/버전/패키징과 experiments·distribution/skill 호환 진입점을 0.4.0으로 전환했다. active MiniLM·ONNX·선형 가중치·키워드 분류 구현은 제거하거나 명시적으로 거부하며 보관 릴리스의 역사적 구현은 유지한다. 원본은 새 0.4.0 하나이며 root bootstrap 설정과 설치된 개인 skill/runtime은 변경하지 않았다.

새 설치기는 검토한 번들의 전체 해시·경로·링크·목록과 인증 readiness/lock identity를 확인한 후 별도 디렉터리에 소스를 배치한다. 기존 연결·설정·완료 상태는 자동 덮어쓰기/재개하지 않는다. 기존 SEV가 있으면 --migrate가 필요하다. 완전한 starter-sev 관리 블록만 starter-rev로 교체하고 나머지 프로젝트 지침·사실·설정은 보존한다. 새로운 private ignore 블록을 추가한다. fixture가 실패 시 이번에 만든 연결/runtime과 지침 변경만 복구함을 검사한다. 비정상 종료/외부 동시 편집은 수동 검토가 필요하며 자동 replay하지 않는다.

관리기 Core.cs/WindowsBoundary.cs/App.cs/AppDiagnostics.cs와 CoreSelfTest.cs의 새 경계는 0.4.0 source/connection 정적 검증이다. 기존 transaction/journal/Job Object 구현은 보존하지만 새 자동 설치 경로로 호출하지 않는다. 새 설치·SEV 이전·손상·불확실한 journal은 명시적 검토를 안내한다. 높은 버전을 낮추지 않는다. 전역 설치 또는 개인 skill을 교체하지 않는다. 과거 자동 설치 fixture 코드는 참조 자료로 보존했으며 현재 코어 진단은 새 정적 검증 계약을 실행한다.

템플릿의 프로젝트 사실/검증은 미설정이다. 사용자 모델·routing·검증 설정은 명시적 검토 대상으로 보존하며 구 schema이면 중단한다. 실제 기존 프로젝트용 이전 명령은 MIGRATION.md 안내일 뿐 이 작업에서 실행하지 않았다. 공유 참조 확인은 명시적으로 전달한 프로젝트만 다루며 전역 사용 여부는 알 수 없다. deletion_allowed=false이고 공유 SEV를 삭제하지 않는다.

## 실행한 보조 검증

새 설치·이전 contract fixture 14개 통과(표준 라이브러리 unittest, readiness/hardware mock). Python AST 39개 분석과 PowerShell installer AST parser 성공. 새 PowerShell 설치기 보안 fixture 7개도 통과했다. 로컬 .NET Framework 코어/GUI 빌드 성공, 코어 fixture 18 assertions와 GUI self-test 50/smoke 17 assertions 통과. GUI는 실제 STA Form을 만들지만 network=false, realInstallation=false, userSettings=false다. 긴 fixture 경로에서 PathTooLong이 발생해 작업공간의 짧은 fixture 루트로 변경했다. Windows PowerShell의 -File은 실행 정책으로 차단됐고 정책 변경 없이 기존 PowerShell 7 및 직접 csc를 사용했다.

root와 standalone bundle 패키저의 ZIP byte 일치·전체 entry/hash·metadata·재현성을 대조한다. 보호 fingerprint 목록의 manifest만 의도적으로 변경하며 private bootstrap 두 파일과 보관된 release/source/ZIP은 원래 fingerprint와 대조한다. 전체 configured root unittest는 외부 controller 소유로 이 작업에서 중복 실행하지 않는다. 루트 discovery는 기존 0.3.3 회귀와 0.4.0 계약 검사를 별도로 연결한다.

## 미검증과 후속 경계

실제 사용자 프로젝트 설치·이전·개인 skills 교체·공유 runtime 삭제·모델 다운로드·로드·유료 모델·비교 평가·ACL/auth/startup 변경·게시/배포/push를 하지 않았다. 현재 Windows 11 Intel Iris Xe/CUDA 없음/15.7GiB 총 RAM/1.9GiB 가용은 실제 inference 부적합 환경이다. 실제 서비스 readiness/추론·지원 장비 설치·latency/memory는 측정하지 않았다. 환경 dependency lock 완성은 지원 호스트에서 별도 검토가 필요하며 무측정 성능/절감 주장을 하지 않는다. 0.4.0은 공개되지 않은 로컬 검토용 source/package다. 마지막 conditional failure recovery 단계는 여기서 구현하지 않았으며 선행 gates 통과 후 별도 단계에서 수행한다.

최종 읽기 전용 hardware 진단은 Windows 11 AMD64, Intel Iris Xe, NVIDIA/CUDA 없음, 총 RAM 16847327232 bytes/가용 2300887040 bytes를 관측했다. 가용 RAM은 시점별로 바뀌며 설치 후보 modes=[]와 verified_inference=false다. 두 패키저의 metadata 줄바꿈 차이를 발견해 ZIP 내부 metadata를 동일한 UTF-8 LF로 정규화했다. 전체 패키지 재현성은 이 최종 소스를 대상으로 대조한다.
