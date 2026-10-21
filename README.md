# Universal AI Starter와 Windows 관리자

이 저장소는 Rev 기반 순차 개발 controller와 Windows 관리자 앱을 관리합니다. 이 문서는 0.4.0 이후 라우팅 변경안을 설명합니다. 현재 공개된 0.4.0 소스 번들과 ZIP은 이 변경과 아직 동기화되지 않았으며, 동기화가 끝나기 전까지 기존 설치에 새 동작이 배포된 것으로 보아서는 안 됩니다.

큰 목표는 `gpt-6.1-sol`이 계획하고 Python controller가 구현 작업을 순차 실행합니다. 작은 요청은 계획 호출 없이 시작할 수 있습니다. 구현 요청의 전체 문맥은 Unicode JSON 문자열로 로컬 Rev에 전달하고, Rev가 worker(`gpt-6-luna`) 또는 main(`gpt-6.1-sol`)을 선택합니다. 실행 모델 override가 있으면 Rev를 건너뜁니다. 계획 모델은 구현 모델을 고정하지 않으며 Codex 앱 대화 모델도 자동으로 바꾸지 않습니다.

새 라우팅 규칙에서는 유효한 정상 응답의 두 점수 중 큰 쪽을 선택하고 정확한 동률은 main에 배정합니다. 낮은 점수만으로 기권하지 않습니다. 점수는 선택지 확률이지 코딩 성공 확률이 아닙니다. 응답 오류, 인증 실패, 시간 초과, 입력 한도 초과는 중단하며 자동 fallback이나 유료 분류를 사용하지 않습니다.

모델 응답만으로 작업을 완료 처리하지 않습니다. 프로젝트에 설정된 검증 명령의 실제 근거가 있어야 완료됩니다. 오류나 시간 초과 뒤에는 원인과 부분 변경을 검토하고 명시적으로 재개합니다. 하위 에이전트, 자동 병렬 실행, 비교 평가는 사용하지 않습니다.

소스·클라이언트 설치, 실행 환경 준비, Rev 연결, 실제 인증 추론은 각각 별개 상태입니다. Windows나 CPU라는 이유만으로 일괄 거부하지 않으며 선택한 장치와 dtype의 메모리 및 의존성 역량을 검사합니다. 후보 진단 통과는 실제 추론 성공을 증명하지 않습니다.

기존 프로젝트의 지침·설정·연결·완료 기록은 보존합니다. 기존 SEV 설정은 자동 이전하지 않으며 호환되지 않는 실행 상태도 자동 재생하지 않습니다. 새 프로젝트 템플릿의 프로젝트 사실과 검증 명령은 사용자가 설정해야 합니다. [이전 안내](distribution/releases/0.4.0/universal-ai-starter/MIGRATION.md), [Rev 안내](distribution/releases/0.4.0/universal-ai-starter/assets/rev/README.md), [순차 실행 안내](distribution/releases/0.4.0/universal-ai-starter/assets/runner/README.md)를 확인하세요.

번들 테스트는 다음 명령으로 실행합니다.

```powershell
python -B -X utf8 -m unittest discover -s distribution/releases/0.4.0/universal-ai-starter/tests
```

격리된 Windows 환경에서는 파일·소켓 권한 때문에 일부 통합 테스트가 제한될 수 있습니다. 실행 환경과 테스트 결과를 함께 해석해야 합니다.