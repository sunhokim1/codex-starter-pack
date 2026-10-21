# Universal AI Starter 0.4.0과 Windows 관리자

이 저장소는 Rev 기반 순차 개발 controller와 Windows WinForms 관리자 앱 로컬 0.2.0의 소스를 관리합니다. 새 원본은 [0.4.0 번들](distribution/releases/0.4.0/universal-ai-starter/README.md)이며 기존 0.3.1·0.3.2·0.3.3과 루트 ZIP은 보관합니다. 0.4.0은 GitHub 소스 게시 대상입니다. 소스 공개는 자동 업데이트용 새 릴리스 활성화와 별개이며, 별도 GitHub Release 생성이나 기존 설치의 자동 전환을 뜻하지 않습니다.

큰 목표는 Sol 계획, 구현 선택은 로컬 Rev를 사용합니다. 사용자 실행 override는 Rev를 우회합니다. 비교 평가와 유료 분류는 실행하지 않습니다. 모델 응답만으로 완료하지 않고 controller의 실제 검증 근거를 요구합니다. 앱 대화 모델이 바뀌는 것은 아닙니다.

[명시적 이전 안내](distribution/releases/0.4.0/universal-ai-starter/MIGRATION.md)를 따르세요. 기존 프로젝트 사실·설정·완료 상태·공유 SEV·개인 skills를 자동 변경하지 않습니다. 기존 프로젝트 연결과 공유 SEV는 보존했습니다. 현재 저장소의 private bootstrap 연결과 검증 설정은 이 전환 작업 동안 그대로 사용하며 배포 템플릿과 구분합니다. 새 프로젝트 템플릿의 사실과 검증 명령은 미설정입니다. SEV/Rev 조건부 선택은 아직 미구현 제안입니다.

관리기는 고정 snapshot을 검증하여 소스·클라이언트·누락 템플릿을 자동 설치·업데이트하고 기존 사용자 지침·설정·연결·완료 기록을 보존합니다. 소스 설치와 선택적 Rev 환경 준비·연결, 인증된 실제 추론은 별도 상태입니다. 모델·서비스·환경 lock·여유 RAM 부재는 소스 업데이트를 막지 않습니다.

Windows 11·Intel Iris Xe·CUDA 없음·총 RAM 약 15.7GiB 호스트에서 실제 Rev 모델 다운로드·로드·CPU 추론을 검증했습니다. 525토큰의 단일 입력 실험에서 2스레드·Normal은 296.922초, 4스레드·AboveNormal은 180.359초였습니다. 준비 단계는 2스레드를 유지했으며 모델 로드 시간은 이 추론 시간과 별도입니다. fast router 목표에는 미달했고 GPU는 미검증이며 정확도와 비용 절감은 측정하지 않았습니다.

실제 요청의 응답은 main 0.674704, worker 0.325296였지만 정책 판정은 abstention이었습니다. 이는 Sol 코딩 실행 성공을 입증하지 않습니다. Rev 실제 smoke는 종료했습니다. Windows/CPU 일괄 금지가 아니며 선택 dtype의 자원과 실제 의존성 capability를 따로 검사합니다. fixture와 소스 빌드 결과는 실제 설치·추론의 증거가 아닙니다.

기존 검증 기록은 루트 테스트 193개, 실패 0개, 건너뜀 2개이며 번들 원본 바이트·해시와 정식 릴리스 일치를 확인했습니다. 검증된 배포 ZIP의 SHA256은 `4882497a55c507f3903681cea430ee838540928c18dd9b3d32f076143921dbc4`입니다. [관리기 안내](apps/starter-manager/README.md)와 [패키징 안내](scripts/README.md)를 확인하세요.
