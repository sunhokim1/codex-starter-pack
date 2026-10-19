# Universal AI Development Starter 0.3.2

0.3.2는 계획 JSON 보존·작업별 전달 문맥 축소·재개 시 파일 변경 재검증을 개선했습니다. 계획과 각 작업의 SEV 선택은 유지합니다.
수정 소스는 `distribution/releases/0.3.2/universal-ai-starter/`, 배포물은 루트 `universal-ai-starter.zip`입니다.
기존 프로젝트와 개인 설정은 자동으로 변경하지 않습니다. [수정·호환성·검증 한계](docs/repair-0.3.2.md)를 확인하세요.

- 원본 소스·회귀 검사: [0.3.2 폴더](distribution/releases/0.3.2/universal-ai-starter/README.md)
- 저장소에서 재빌드: `python scripts/package_starter.py` (manifest가 범용 템플릿만 사용)
- 새 bundle 검증: `python distribution/releases/0.3.2/universal-ai-starter/scripts/package_starter.py --check`
- 회귀 검사: `python -m unittest discover -s distribution/releases/0.3.2/universal-ai-starter/tests -p "test_*.py" -v`
- 기존 호환 경로의 runner/service/install/scaffold는 최신 소스로 전달됩니다.
- [지속 개선 지침](CONTINUOUS_IMPROVEMENT.md)

ZIP을 신뢰한 출처에서 내려받아 확인한 뒤 적용하세요. 저장된 `scripts/install_from_github.ps1`은
고정 commit의 0.3.2 ZIP을 검증하며 이전 개인 스킬 백업을 보존합니다. 실제 설치·Codex 실행·모델 추론은
오프라인 회귀 검사와 별도로 검증해야 합니다. 비밀값은 요청문 대신 환경/비밀 저장소 참조를 사용하세요.

이전 0.3.0 개발 기록은 Git 이력과 docs에 남아 있습니다. 모델 매핑과 기존 프로젝트 사실은 보존합니다.
