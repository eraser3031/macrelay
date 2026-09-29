# macrelay

Remote CLI control for Codex and Claude Code over SSH, with persistent PTY sessions.

**우리 맥에서 Codex·Claude Code를 실행하고, 다른 맥의 CLI에서 조작합니다.**

```text
다른 맥의 macrelay CLI ── SSH ── 우리 맥의 세션 브로커 ── PTY ── Codex / Claude Code
```

실행 위치, 프로젝트 파일, 인증 정보는 호스트 맥에 있습니다. SSH 연결이 끊겨도 브로커와 에이전트는 계속 실행됩니다. 다시 `attach`하면 최근 출력을 받고 입력을 이어갈 수 있습니다. 로컬에서도 동일한 세션에 붙을 수 있습니다.

첫 버전은 **터미널 기반 MVP**입니다. Codex app-server의 구조화된 이벤트 API는 아직 구현하지 않았습니다. 두 CLI의 터미널 UI와 승인 질문을 그대로 다루기 위해 공통 PTY 계층부터 구현했습니다. 별도 pip 의존성이나 tmux는 필요 없습니다.

## 요구 사항

- 현재 검증한 운영체제는 macOS입니다. POSIX PTY·Unix 소켓을 사용하므로 Windows 네이티브 실행은 지원하지 않습니다. Linux/WSL은 아직 검증하지 않았습니다.
- 두 맥 모두 Python 3.9 이상, OpenSSH 클라이언트
- 호스트 맥에 로그인된 Codex CLI 또는 Claude Code
- 원격 맥에서 호스트 맥으로 접속 가능한 SSH 계정
- 호스트 맥이 켜져 있고 깨어 있어야 합니다. 재부팅·절전 중 실행 지속이나 자동 재시작은 지원하지 않습니다.

macOS 기본 Python은 개발자 도구 설치 여부에 따라 없을 수 있습니다. `python3 --version`으로 먼저 확인하세요.

## 다운로드 및 설치

[최신 릴리스](https://github.com/eraser3031/macrelay/releases/latest)에서 `macrelay.pyz`와 `SHA256SUMS`를 내려받으면 별도 pip 패키지 없이 실행할 수 있습니다.

```sh
shasum -a 256 -c SHA256SUMS
python3 macrelay.pyz --help
python3 macrelay.pyz install user@our-mac.local
python3 macrelay.pyz --host user@our-mac.local doctor
```

소스에서 시작하려면:

```sh
git clone https://github.com/eraser3031/macrelay.git
cd macrelay
python3 run.py --help
python3 run.py build
```

선택적으로 가상 환경에서 `python3 -m pip install .`로 설치하면 `macrelay` 명령도 사용할 수 있습니다.

## 지금 이 맥에서 사용하기

```sh
cd macrelay
python3 run.py doctor
python3 run.py start claude --cwd ~/Projects/your-project --name dev
# 출력 JSON의 id를 사용합니다.
python3 run.py attach SESSION_ID
```

`Ctrl-]`는 접속만 종료합니다. `Ctrl-C`는 에이전트 터미널로 전달됩니다. 에이전트를 완전히 종료하려면 `stop`을 사용하세요.

```sh
python3 run.py list
python3 run.py attach SESSION_ID --read-only
python3 run.py send SESSION_ID '테스트 실패 원인을 확인해줘'
python3 run.py logs SESSION_ID
python3 run.py stop SESSION_ID
```

`send`는 활성 조작자가 없는 세션에 텍스트와 Enter를 전달합니다. CLI가 승인 질문이나 선택 메뉴를 표시 중이면 그 입력으로 해석될 수 있습니다. **대화 상태를 해석하는 구조화된 프롬프트 API가 아닙니다.** 입력 상태가 불확실하면 `attach`를 사용하세요. 여러 줄 입력은 에이전트별 입력 동작에 따라 달라집니다.

## 다른 맥에서 우리 맥 조작하기

1. 우리 맥의 시스템 설정에서 **일반 → 공유 → 원격 로그인**을 켜고 접속할 사용자만 허용합니다. 기존 SSH 설정이 있다면 그대로 사용합니다. macrelay는 시스템 설정을 변경하지 않습니다.
2. 다른 맥에서 `ssh user@our-mac.local`로 먼저 연결을 확인합니다. 인터넷을 사이에 두고 연결할 때는 두 맥 간 SSH 경로가 별도로 필요합니다. macrelay는 NAT 중계 서비스를 제공하지 않습니다.
3. 패키지를 생성하고 다른 맥으로 복사합니다.

```sh
# 소스가 있는 맥
python3 run.py build
# 생성된 dist/macrelay.pyz를 다른 맥에 복사합니다.
```

이후 다음은 **조작하는 다른 맥에서** 실행합니다.

```sh
python3 macrelay.pyz install user@our-mac.local
python3 macrelay.pyz --host user@our-mac.local doctor
python3 macrelay.pyz --host user@our-mac.local start claude \
  --cwd /Users/you/Projects/your-project --name dev
python3 macrelay.pyz --host user@our-mac.local list
python3 macrelay.pyz --host user@our-mac.local attach SESSION_ID
```

`--host`에는 `~/.ssh/config`의 별칭도 쓸 수 있습니다. 포트·키·점프 호스트는 SSH 설정에서 지정합니다. 비밀번호나 API 키는 macrelay에 저장하지 않습니다. Python 경로가 다르면 `--remote-python /path/to/python3`를 전역 옵션으로 지정하세요. SSH 옵션은 하위 명령 앞에 둡니다.

원격 `--cwd`는 호스트 맥의 경로입니다. 조작하는 맥에서 `~`가 먼저 확장되지 않도록 절대 경로 또는 따옴표로 감싼 `'~/Projects/your-project'`를 사용하세요.

`install`은 호스트의 `~/.local/share/macrelay/macrelay.pyz`에 현재 버전을 복사합니다. 셸 프로필이나 로그인 항목을 수정하지 않습니다. 호스트의 `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`을 PATH 앞에 추가합니다. 실행 파일이 다른 위치에 있으면 `start --executable /absolute/path/to/claude`를 사용하세요.

## 이미 실행 중인 세션

| 세션 종류 | 지원 방식 |
| --- | --- |
| macrelay로 시작한 Codex·Claude | `list` → `attach ID`. 실행 중 작업 유지, 원격 재접속 지원 |
| Claude Code가 제공하는 백그라운드 세션 | `discover claude` → `attach-existing claude ID`. 해당 명령을 지원하는 Claude 버전 필요 |
| tmux 안에서 실행 중인 CLI | `discover tmux` → `attach-existing tmux NAME`. 호스트에 tmux 필요 |
| 일반 터미널에서 임의로 실행 중인 CLI | 실행 중 터미널 인계 미지원. 기존 실행을 종료한 뒤 저장된 대화 재개 가능 |
| Codex 데스크톱 앱 대화 | 미지원 |

```sh
python3 macrelay.pyz --host our-mac discover claude
python3 macrelay.pyz --host our-mac attach-existing claude BACKGROUND_ID

python3 macrelay.pyz --host our-mac discover tmux
python3 macrelay.pyz --host our-mac attach-existing tmux SESSION_NAME
```

`attach-existing`은 제공자의 네이티브 연결 명령을 실행합니다. 종료 키도 제공자의 동작을 따릅니다(설치된 Claude의 안내 또는 tmux의 `Ctrl-b d`). macrelay의 조작자 잠금·출력 기록은 적용되지 않습니다. Claude 목록에 표시되는 모든 대화가 백그라운드 attach를 지원하는 것은 아닙니다.

Claude 백그라운드 세션에 대한 연결을 macrelay로 관리하려면 다음을 사용할 수 있습니다.

```sh
python3 run.py start claude --cwd /path/to/project --background-id BACKGROUND_ID
```

이 경우 `stop`은 macrelay가 실행한 연결 클라이언트를 종료합니다. 원래 Claude 백그라운드 작업은 계속 실행될 수 있습니다. 원래 작업의 종료는 호스트의 `claude stop BACKGROUND_ID`로 관리하세요.

저장된 대화를 재개할 때는 기존 실행을 먼저 종료합니다. `--resume`은 저장된 대화를 새 프로세스에서 이어가는 기능으로, 다른 프로세스의 실행 중 작업을 가져오지 않습니다.

```sh
python3 run.py start codex --cwd /path/to/project --resume CODEX_THREAD_ID
python3 run.py start claude --cwd /path/to/project --resume CLAUDE_SESSION_ID
```

## 동작과 한계

- SSH 인증·암호화·호스트 키 검증을 그대로 사용합니다. 별도 TCP 포트를 열지 않습니다.
- 호스트의 세션별 Unix 소켓만 사용합니다. `~/.macrelay` 권한은 0700, 소켓과 기록 파일은 0600입니다.
- SSH 사용자와 동일한 권한으로 에이전트가 실행됩니다. 에이전트의 원래 승인 정책을 우회하는 옵션을 넣지 않습니다.
- 한 세션에 입력 가능한 조작자는 한 명입니다. `--read-only` 관찰자는 추가할 수 있습니다. 연결 종료 후 다시 붙으면 입력 권한이 풀립니다.
- 느린 관찰자의 대기 출력은 제한되며, 에이전트가 멈추지 않도록 해당 연결만 끊습니다.
- 최근 256 KiB의 터미널 바이트를 유지하고 약 2초 간격으로 디스크에 기록합니다. 전체 대화 보관이나 완전한 터미널 화면 스냅샷은 아닙니다. TUI 재접속 화면은 리사이즈로 다시 그려야 할 수 있습니다.
- `logs`는 제어 문자를 이스케이프합니다. 원본 ANSI 출력이 필요하면 `logs --raw`를 사용합니다.
- 세션 브로커가 강제 종료되거나 맥이 재부팅되면 작업 복구를 보장하지 않습니다. 메타데이터가 남아 있으면 `unreachable`로 표시합니다.
- `stop`은 관리하는 프로세스 그룹에 TERM을 보내고 3초 뒤 KILL로 전환합니다. 별도 세션으로 분리된 하위 작업은 남을 수 있습니다.
- 에이전트 종료 후 메타데이터와 출력은 자동 삭제하지 않습니다. 민감한 내용이 출력 기록에 포함될 수 있습니다.
- `MACRELAY_HOME=/short/private/path`로 호스트 상태 경로를 바꿀 수 있습니다. 해당 폴더는 사용자 소유, 권한 0700이어야 합니다. 원격 호스트에도 동일한 환경 설정을 적용해야 합니다.

## 개발 및 검증

```sh
python3 -m unittest discover -s tests -v
python3 run.py build
python3 dist/macrelay.pyz --version
```

테스트는 실제 PTY·Unix 소켓·별도 프로세스를 사용해 입출력, 화면 크기, Ctrl-C, detach, 재접속, 읽기 전용, 단일 조작자, 종료, 기록 상한을 검증합니다. SSH 부분은 로컬 대역으로 배포된 zipapp과 셸 인자 전달을 검증합니다. 실제 두 맥 사이 SSH 인증·네트워크와 실제 모델 응답은 별도의 실기 검증이 필요합니다.

관련 문서: [Codex app-server](https://learn.chatgpt.com/docs/app-server), [Claude Code CLI](https://code.claude.com/docs/en/cli-reference).
