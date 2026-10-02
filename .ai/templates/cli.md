# CLI preset

선택 사항을 `PROJECT.md`에 기록한다. 특정 언어나 package manager를 강제하지 않는다.

- Language / runtime과 target OS
- Command/subcommand 구조
- Arguments, flags, help, configuration 우선순위
- stdin/stdout/stderr와 출력 형식
- Exit codes와 오류 처리
- Interactive / non-interactive 동작
- Filesystem/network 접근 여부
- Packaging/distribution 방식
- Testing strategy: 명령 실행, 출력, exit code, 경계 조건

선택 후 command entry point와 tests를 map에 기록하고 검증 명령을 설정한다.
