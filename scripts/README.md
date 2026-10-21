# 0.4.0 유지 관리와 로컬 패키징

`distribution/manifest.json`은 새 canonical 번들의 전체 파일을 명시적으로 매핑합니다. private bootstrap 설정의 버전을 배포 버전으로 사용하지 않습니다. 보관된 릴리스와 루트 ZIP은 변경하지 않습니다.

```powershell
python scripts/package_starter.py --check
python scripts/package_starter.py
python distribution/releases/0.4.0/universal-ai-starter/scripts/package_starter.py --check
```

새 출력은 `distribution/releases/0.4.0/universal-ai-starter.zip`입니다. 동일 입력은 동일 ZIP을 생성하며 파일별 SHA256과 전체 목록을 검사합니다. 번들 자체 빌더는 `release.json`의 명시적 목록을 사용합니다. 소스를 수정하면 새 metadata와 manifest를 함께 갱신하세요. 기존 릴리스 경로로 출력하거나 루트 보관 ZIP을 덮어쓰지 마세요.

`install_from_github.ps1`은 0.4.0의 기본 main 조회 후 immutable commit을 고정하며, 검토한 로컬 번들/ZIP 또는 명시적 snapshot도 받습니다. 소스·클라이언트를 자동 설치·업데이트하고 기존 설정·실행 연결을 보존합니다. Rev 모델·환경·서비스 준비는 별도 명시 작업입니다. URL·크기·시간·redirect·ZIP 경로·중복·링크·전체 해시를 검증합니다. 게시되지 않은 0.4.0의 다운로드 성공을 가정하지 않습니다. 개인 skill 승격·startup·인증/ACL 변경은 수행하지 않습니다. [기존 설치 이전 절차](../distribution/releases/0.4.0/universal-ai-starter/MIGRATION.md)를 확인하세요.

루트 unittest는 보관된 0.3.3 회귀와 새 0.4.0 계약 fixture를 구분해 실행합니다. 모델 호출은 mock이며 다운로드·유료 분류·비교 평가가 아닙니다. 지원 하드웨어의 실제 inference와 설치는 별도 미검증 항목입니다.
