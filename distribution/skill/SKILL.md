---
name: universal-ai-starter
description: Rev 0.4.0 프로젝트 템플릿과 명시적 격리 연결을 준비합니다.
---
# Rev 스타터 적용
scripts/scaffold.py --target <project> --adopt --files-only로 누락 템플릿만 준비한다. 실제 프로젝트 사실과 사용자 모델·routing·검증 설정을 덮어쓰지 않는다.
연결 이전은 scripts/install_rev.py의 plan을 검토한 뒤 명시적 --migrate --connection-file과 별도 --runtime-root로 실행한다. 기존 SEV·개인 skill·완료 상태를 삭제하지 않는다. 지원 하드웨어와 인증 readiness를 확인하기 전 연결하지 않는다.
큰 목표는 assets/runner/project.py, 작은 요청은 assets/runner/run.py를 사용한다. --execution-model override는 Rev를 우회하며 --planning-model은 실행 모델을 고정하지 않는다. 앱 대화 모델 변경을 주장하지 않는다.
