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
내용이 바뀐 릴리스에서는 이 버전을 갱신한다. ZIP 내부 release.json이 버전과 파일 해시를 기록한다.
개인 스킬 교체와 GitHub 업로드는 수행하지 않는다. 각각 필요할 때 명시적으로 실행한다.

도구 검증: `python -m unittest discover -s tests -v`.
이 배포 도구와 그 테스트는 원본 관리 저장소 전용이며, 생성되는 프로젝트에는 포함하지 않는다.
프로젝트 자체의 실제 검증 명령은 `.ai/verification.yaml`에 설정한다.
