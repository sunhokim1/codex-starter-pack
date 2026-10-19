# 0.3.1 GitHub 통합 검증

2026-10-19, Windows Python 3.14.

- 기존 저장소 검사 32개와 새 bundle 회귀 검사 40개, 총 72개 통과.
- Windows PowerShell에서 ZIP 검사 함수·경로 거부·무결성·bootstrap 모형 검사 통과.
- 루트 manifest 기반 ZIP 재빌드 성공. ZIP의 모든 파일과 내부 SHA256을 확인.
- 모델 가중치·역할 매핑 보존. 데스크톱 원본 저장소·ZIP·미공개 작업 변경 없음.
- 이 세션의 Windows sandbox 임시 디렉터리 ACL 제약 때문에 테스트 임시 폴더는
  작업 공간 ACL을 상속하는 폴더로 대체했습니다. 제품 권한 검사를 완화하지 않았습니다.
- 실제 설치, 공개 모델 다운로드/추론, Codex 유료 실행과 로그인 시작 등록은 수행하지 않았습니다.

재현 명령:

```text
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s distribution/releases/0.3.1/universal-ai-starter/tests -p "test_*.py" -v
python scripts/package_starter.py --check
```

quick 검증은 모델 보고이며 controller 검증은 실제 subprocess 결과라는 차이를 유지합니다.
강제 종료 복구 journal, 자손 프로세스 종료와 재개 시 파일 변경 검출,
분류 품질 benchmark는 지속 개선 backlog에 남아 있습니다.
