# Universal AI Development Starter 0.3.3

0.3.3 버전은 설치 과정에서 Windows 권한 사전 점검을 자동으로 수행합니다. 새 venv를 만든 뒤 설치 프로그램은 의존성이나 모델을 준비하고, 서비스를 시작하거나, 프로젝트를 연결하고, 스킬을 승격하거나, 선택적 시작 항목을 등록하기 전에 네이티브 관리 Codex `:workspace` 샌드박스에서 해당 Python의 권한을 확인합니다. 점검에 실패하면 진단 정보와 함께 설치를 중단합니다. 이 점검은 ACL 권한을 부여하거나 장치 정책을 우회하지 않습니다.

유지 관리 원본은 [0.3.3 번들](distribution/releases/0.3.3/universal-ai-starter/README.md)입니다. 루트 `universal-ai-starter.zip`은 `distribution/manifest.json`에 따라 빌드되며 전체 소스와 회귀 테스트를 포함합니다. 배포된 0.3.1 및 0.3.2 소스는 변경하지 않습니다. 기존 프로젝트, 모델 매핑 및 가중치는 보존됩니다.

```text
python scripts/package_starter.py
python scripts/package_starter.py --check
python distribution/releases/0.3.3/universal-ai-starter/scripts/package_starter.py --check
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s distribution/releases/0.3.3/universal-ai-starter/tests -p "test_*.py" -v
```

신뢰할 수 있는 출처의 ZIP을 사용하고 적용 전에 무결성을 확인하세요. 공개 설치 프로그램은 0.3.3 릴리스를 요구하며, 준비 단계에 들어가기 전에 ZIP 전체를 검증합니다. 게시하려면 검증된 ZIP 커밋을 가리키는 변경 불가 다운로드 핀이 필요합니다. 제한 사항은 [릴리스 안내](docs/release-0.3.3.md)와 번들의 복구 안내를 참고하세요. 실제 설치, 모델 추론 및 시작 동작은 별도로 검증해야 합니다. 오프라인 회귀 테스트 결과만으로 모든 Windows PC에서 접근 가능하다고 단정할 수는 없습니다.

호환성을 위한 runner/service/install/scaffold 진입점은 0.3.3 구현으로 연결됩니다. 남은 작업은 [지속적 개선](CONTINUOUS_IMPROVEMENT.md) 문서에 기록되어 있습니다.
