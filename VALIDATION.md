# 검증 기록 — 2026-09-29

- macOS, Python 3.14.3: 7개 통합 테스트 통과.
- macOS 기본 Python 3.9.6: 7개 통합 테스트 통과. 초기 PTY 크기가 0인 경우의 호환성 수정 포함.
- 실제 Claude Code 2.1.284: 임시 프로젝트에서 PTY 시작, 출력 수신, 실행 상태 확인, 종료·소켓 정리 성공. 모델 프롬프트 전송 없음.
- 단일 zipapp 빌드, Python 3.9 실행, zipapp 복사 빌드 확인.
- SSH 로컬 대역: 설치, 배포 패키지 실행, 명령 인자 인용, 입출력 브리지 확인. SSH 인증과 실제 네트워크는 검증 대상에서 제외.

현재 환경의 제한:

- `/usr/local/bin/codex`는 npm 런처가 참조하는 네이티브 실행 파일이 없어 `ENOENT`로 실패합니다. 전역 설치는 변경하지 않았습니다. 정상 실행 파일을 설치하거나 `start --executable`로 지정해야 실제 Codex 동작을 검증할 수 있습니다.
- tmux가 설치되어 있지 않아 네이티브 tmux 연결은 실행 검증하지 않았습니다.
- 기존 Claude 백그라운드 연결은 설치된 CLI의 `agents`·`attach` 도움말을 확인했습니다. 사용자의 기존 작업에 실제로 접속하거나 입력하지 않았습니다.
- 두 맥 간 SSH와 모델 작업·승인 왕복은 아직 실기 검증하지 않았습니다.

재현:

```sh
python3 -m unittest discover -s tests -v
/usr/bin/python3 -m unittest discover -s tests -v
python3 scripts/smoke_live.py claude
python3 run.py build
```
