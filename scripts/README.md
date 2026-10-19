## 0.3.1 유지보수 경로

현재 배포 소스는 `distribution/releases/0.3.1/universal-ai-starter/`입니다.
`distribution/manifest.json`은 이 소스의 모든 배포 파일을 매핑하며,
`python scripts/package_starter.py --check`와 옵션 없는 빌드로 루트 ZIP을 재현합니다.
`distribution/skill/scripts/`와 실험용 runner/service 진입점은 새 소스로 전달하는 호환 경로입니다.
실제 설치 전에 새 bundle의 README와 REPAIR_NOTES를 확인하세요.

아래 0.3.0 설명은 이전 구조의 참고 자료입니다.

# Scripts

## 스타터 원본 관리 저장소에서 배포

```text
python scripts/package_starter.py
```

원본 파일 점검 → ZIP 생성 → 버전·SHA256·원본 내용 일치 확인 → 기존 ZIP 교체를 수행한다.
기본 출력은 `universal-ai-starter.zip`이다. 임시 ZIP 검증에 실패하면 기존 ZIP을 보존한다.
점검만 하려면 `--check`, 별도 출력 경로는 `--output <path>`를 사용한다.

원본 기준은 repository의 핵심 파일 7개, `distribution/skill/`의 스킬 지침·복사 스크립트,
`distribution/manifest.json`의 포함 목록이다. 버전은 `.ai/config.yaml`의 starter.version을 따른다.
ZIP 내부 release.json이 버전과 파일 해시를 기록한다. 현재 배포 버전은 0.3.0으로 유지한다.
개인 스킬 교체와 GitHub 업로드는 수행하지 않는다. 각각 필요할 때 명시적으로 실행한다.

도구 검증: `python -m unittest discover -s tests -v`.
이 배포 도구와 그 테스트는 원본 관리 저장소 전용이며, 생성되는 프로젝트에는 포함하지 않는다.
프로젝트 자체의 실제 검증 명령은 `.ai/verification.yaml`에 설정한다.

## Windows 설치기

`install_from_github.ps1`은 전체를 붙여넣을 수 있는 독립 명령 블록이다.
`-Target <folder>` 또는 폴더 선택 후 공개 GitHub ZIP 다운로드(인증/CLI 불필요),
경로·릴리스·해시 확인, 스킬 교체, 번들 bootstrap 순으로 실행한다. 다운로드 실패나
검증 실패는 기존 스킬을 교체하지 않는다. 대상 프로젝트 핵심 파일 충돌은 보존하며,
이미 AGENTS.md와 .ai/models.yaml이 있는 프로젝트는 install_sev.py로 바로 연결한다.
runner 지침은 패키지에서 `SKILL.template.md`로 보관하고 설치 때만 `SKILL.md`로 만든다.
실제 인증·winget·코딩 호출 없이 PowerShell Parser와 모의 부트스트랩/ZIP 테스트를 실행한다.
