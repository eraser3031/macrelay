# macrelay

**집이나 사무실에 있는 맥의 Codex·Claude Code를, 다른 맥의 터미널에서 사용합니다.**

예를 들어 사무실 맥에 프로젝트와 Claude Code가 준비되어 있다면, 노트북에서 그 맥에 접속해 작업을 요청하고 결과를 확인할 수 있습니다. 파일 수정과 명령 실행은 사무실 맥에서 이루어집니다. 프로젝트나 AI 로그인 정보를 노트북으로 옮길 필요는 없습니다.

macrelay로 시작한 작업은 접속을 끊어도 실행 맥에서 계속됩니다. 나중에 다시 접속하면 최근 출력을 확인하고 입력을 이어갈 수 있습니다. 단, 실행 맥은 켜져 있고 깨어 있어야 합니다.

## 먼저, 두 맥을 이렇게 구분합니다

이 문서에서는 접속 방향이 헷갈리지 않도록 두 이름을 사용합니다.

| 이름 | 하는 일 | 예시 |
| --- | --- | --- |
| **실행 맥** | 프로젝트 파일을 가지고 있으며 Codex·Claude Code가 실제로 작업하는 맥 | 사무실의 맥 미니 |
| **조작 맥** | 터미널에서 명령을 보내고 결과를 확인하는 맥 | 외부에서 사용하는 맥북 |

```text
조작 맥                              실행 맥
명령 입력 · 결과 확인 ─── SSH ───→ Codex / Claude Code
                                  ↓
                             프로젝트 파일 수정
```

**SSH**는 다른 컴퓨터의 터미널에 안전하게 접속하는 방법입니다. macrelay는 이 연결을 이용합니다. **세션**은 macrelay가 실행하고 관리하는 Codex 또는 Claude Code 작업 하나를 뜻합니다. 작업마다 ID가 있어서, 여러 작업 중 원하는 것을 골라 다시 접속할 수 있습니다.

처음 사용한다면 아래의 **준비 → 다운로드 → 연결 → 작업 시작** 순서로 따라 하세요. 이미 실행 중인 작업에 접속하려면 뒤의 [기존 작업에 연결하기](#기존-작업에-연결하기)를 확인하세요.

## 시작하기 전에 준비할 것

| 어디에서 | 준비할 것 | 확인 방법 |
| --- | --- | --- |
| 두 맥 모두 | Python 3.9 이상 | 터미널에서 `python3 --version` 실행 |
| 두 맥 모두 | OpenSSH 클라이언트 | 터미널에서 `ssh -V` 실행 |
| 실행 맥 | 사용할 Codex CLI 또는 Claude Code 설치와 로그인 | 그 맥에서 `codex` 또는 `claude`를 직접 실행해 사용 가능한지 확인 |
| 실행 맥 | 작업할 프로젝트 폴더 | 예: `/Users/min/Projects/my-app` |
| 두 맥 사이 | 실행 맥으로 SSH 접속할 수 있는 계정과 네트워크 | 아래 연결 단계에서 확인 |

macOS에서는 개발자 도구 설치 여부에 따라 `python3`가 없을 수 있습니다. Python부터 확인한 뒤 진행하세요. 실행 맥에는 사용할 AI 도구만 있으면 됩니다. Codex와 Claude를 모두 설치할 필요는 없습니다.

현재 동작을 검증한 운영체제는 **macOS**입니다. Windows에서 직접 실행하는 방식은 지원하지 않습니다. Linux와 WSL은 아직 검증하지 않았습니다.

## 1. 조작 맥에 macrelay 내려받기

**조작 맥에서** [최신 릴리스](https://github.com/eraser3031/macrelay/releases/latest)를 열고, 다음 두 파일을 같은 폴더에 내려받으세요.

| 파일 | 용도 |
| --- | --- |
| `macrelay.pyz` | macrelay 프로그램. Python으로 실행하는 단일 파일입니다. |
| `SHA256SUMS` | 내려받은 프로그램이 릴리스 파일과 일치하는지 확인하는 값입니다. |

터미널에서 두 파일이 있는 폴더로 이동한 뒤 실행합니다. 다운로드 폴더에 받았다면 다음과 같습니다.

```sh
cd ~/Downloads
shasum -a 256 -c SHA256SUMS
python3 macrelay.pyz --help
```

첫 명령의 결과가 `macrelay.pyz: OK`이면 파일이 일치합니다. 두 번째 명령은 사용 가능한 명령어를 보여줍니다. `.pyz` 파일은 압축을 풀 필요가 없고, 별도 pip 패키지나 tmux를 설치하지 않아도 됩니다.

이후 예시도 **`macrelay.pyz`가 있는 폴더에서 실행**한다고 가정합니다. 다른 폴더에서 실행하려면 `python3 ~/Downloads/macrelay.pyz ...`처럼 파일의 경로를 적으세요.

## 2. 조작 맥에서 실행 맥으로 연결하기

### 실행 맥에서 할 일

macOS 시스템 설정의 **일반 → 공유 → 원격 로그인**을 켜고, 접속할 사용자 계정에 접근을 허용하세요. 이미 SSH를 사용 중이라면 기존 설정을 그대로 사용할 수 있습니다. macrelay가 이 시스템 설정을 대신 변경하지는 않습니다.

원격 로그인 화면에서 접속 주소를 확인하세요. 예를 들어 계정 이름이 `min`, 맥의 네트워크 이름이 `office-mac.local`이면 접속 대상은 다음과 같습니다.

```text
min@office-mac.local
│   └─ 실행 맥의 주소
└───── 실행 맥에서 사용할 사용자 계정
```

### 조작 맥에서 할 일

아래 주소를 **실제 실행 맥의 계정과 주소로 바꿔** 연결을 확인합니다.

```sh
ssh min@office-mac.local
```

접속에 성공하면 실행 맥의 셸이 열립니다. 확인을 마쳤으면 다음을 입력해 조작 맥으로 돌아오세요.

```sh
exit
```

이 SSH 접속이 되어야 macrelay도 사용할 수 있습니다. 서로 다른 네트워크에서 사용할 때도 실행 맥에 도달할 수 있는 SSH 연결 경로가 필요합니다. macrelay는 공유기 밖에서 접속하도록 해 주는 중계 서버나 NAT 우회 기능을 제공하지 않습니다.

이 문서의 나머지 원격 사용 예시는 모두 `min@office-mac.local`을 사용합니다. 자신의 접속 주소로 바꿔 주세요.

## 3. 실행 맥에 macrelay 복사하고 상태 확인하기

이제부터 다음 명령은 모두 **조작 맥에서** 실행합니다.

```sh
python3 macrelay.pyz install min@office-mac.local
```

`install`은 조작 맥에 있는 macrelay를 SSH로 실행 맥에 복사합니다. 실행 맥에서 직접 파일을 내려받을 필요가 없습니다. 복사 위치는 실행 맥의 `~/.local/share/macrelay/macrelay.pyz`입니다. 셸 시작 설정이나 로그인 항목은 변경하지 않습니다.

복사가 끝나면 실행 맥의 도구 상태를 확인합니다.

```sh
python3 macrelay.pyz --host min@office-mac.local doctor
```

`--host`는 **“이 명령을 실행할 맥”**을 지정합니다. `doctor`는 그 맥에서 Python과 AI 실행 파일을 확인합니다. 출력의 `agents` 아래에서 사용할 도구의 `ok`가 `true`인지 보세요. `false`이면 `detail`에 실패 이유가 나옵니다. 이 확인은 실행 파일 점검이며, AI 로그인이나 실제 응답까지 검증하지는 않습니다.

## 4. 새 작업 시작하고 입력하기

다음 예시는 **실행 맥에 있는** `/Users/min/Projects/my-app` 폴더에서 Claude Code를 시작합니다. 폴더는 미리 존재해야 합니다.

```sh
python3 macrelay.pyz --host min@office-mac.local start claude \
  --cwd /Users/min/Projects/my-app --name dev
```

| 부분 | 뜻 |
| --- | --- |
| `start claude` | Claude Code를 새로 실행합니다. Codex를 쓰려면 `start codex`로 바꿉니다. |
| `--cwd ...` | AI가 작업할 **실행 맥의 프로젝트 폴더**입니다. |
| `--name dev` | 작업 목록에서 알아보기 쉽게 붙이는 이름입니다. 생략할 수 있습니다. |

`start`는 작업을 시작하고 세션 정보를 출력합니다. 아직 대화 화면에 접속한 상태는 아닙니다. 출력에서 `id` 값을 찾으세요. 아래는 일부 필드만 보여 주는 예시입니다.

```json
{"id": "a1b2c3d4e5f6", "agent": "claude", "name": "dev", "status": "running"}
```

그 ID로 접속합니다. **예시 ID 대신 실제 출력된 ID를 사용하세요.**

```sh
python3 macrelay.pyz --host min@office-mac.local attach a1b2c3d4e5f6
```

이제 Claude Code의 터미널 화면을 보고 입력할 수 있습니다. 작업 요청뿐 아니라 도구 실행 승인 질문에도 이 화면에서 응답합니다. macrelay가 승인 질문에 자동으로 답하거나 AI 도구의 승인 정책을 우회하지는 않습니다.

`--cwd`에 `~`를 쓸 때는 `'~/Projects/my-app'`처럼 따옴표로 감싸세요. 따옴표 없이 쓰면 조작 맥의 홈 경로로 먼저 바뀔 수 있습니다. 원격 작업에서는 위 예시처럼 실행 맥의 절대 경로를 쓰면 구분하기 쉽습니다.

## 5. 접속만 끊기, 다시 접속하기, 작업 끝내기

**접속을 끊는 것과 AI 작업을 종료하는 것은 다릅니다.**

| 원하는 동작 | 방법 | 실행 맥의 작업은? |
| --- | --- | --- |
| 터미널에서 빠져나오기 | 접속 화면에서 `Ctrl-]` | 계속 실행됩니다. |
| 같은 작업에 다시 접속하기 | `attach 세션ID` | 기존 작업으로 돌아갑니다. |
| AI에 중단 키 보내기 | 접속 화면에서 `Ctrl-C` | AI 도구가 그 키를 처리합니다. macrelay의 접속 종료 키가 아닙니다. |
| macrelay가 실행한 작업 종료하기 | `stop 세션ID` | 종료를 요청합니다. |

`Ctrl-]`는 Control 키를 누른 채 `]` 키를 누르는 것입니다. 접속을 끊은 뒤 목록을 보거나 작업을 끝내려면 다음처럼 실행합니다.

```sh
# ID를 잊었다면 작업 목록부터 확인합니다.
python3 macrelay.pyz --host min@office-mac.local list

# 기존 작업으로 돌아갑니다.
python3 macrelay.pyz --host min@office-mac.local attach a1b2c3d4e5f6

# 접속 화면에서 Ctrl-]로 나온 뒤, 작업을 종료합니다.
python3 macrelay.pyz --host min@office-mac.local stop a1b2c3d4e5f6

# 종료 상태를 확인합니다.
python3 macrelay.pyz --host min@office-mac.local list
```

네트워크 연결이 끊겨도 실행 맥의 세션은 유지됩니다. 연결이 복구되면 같은 ID로 다시 접속하세요. 다만 실행 맥의 절전·재부팅이나 macrelay의 세션 관리 프로세스가 강제 종료된 경우에는 작업 유지·복구를 보장하지 않습니다. 자동 재시작 기능도 없습니다.

## 작업을 확인하고 입력하는 다른 방법

아래 예시에서도 `a1b2c3d4e5f6`은 실제 세션 ID로 바꿔야 합니다. 모두 조작 맥에서 실행합니다.

### 화면을 보기만 하기

```sh
python3 macrelay.pyz --host min@office-mac.local attach a1b2c3d4e5f6 --read-only
```

출력은 볼 수 있지만 입력은 보낼 수 없습니다. 한 세션에는 입력하는 접속을 하나만 허용하며, 보기 전용 접속은 추가할 수 있습니다. 기존 조작자가 접속을 끊고 호스트가 그 종료를 감지하면 다른 접속이 입력 권한을 얻을 수 있습니다.

### 최근 출력 확인하기

```sh
python3 macrelay.pyz --host min@office-mac.local logs a1b2c3d4e5f6
```

대화 화면에 들어가지 않고 최근 출력을 한 번 확인합니다. 전체 대화 기록이 아니라 최근 **256 KiB**까지의 터미널 출력입니다. 자세한 보관 방식은 아래 [출력 기록과 저장 위치](#출력-기록과-저장-위치)를 참고하세요.

### 접속하지 않은 작업에 한 줄 보내기

```sh
python3 macrelay.pyz --host min@office-mac.local send a1b2c3d4e5f6 '테스트 실패 원인을 확인해줘'
```

`send`는 해당 터미널에 텍스트를 입력하고 Enter를 누르는 동작입니다. Enter를 보내지 않으려면 `--no-enter`를 붙입니다. 다른 조작자가 접속해 입력 중이면 `send`는 거부됩니다.

macrelay는 현재 화면이 “새 요청을 입력하는 곳”인지 “승인 질문”인지 구분하지 않습니다. 승인 질문이 떠 있다면 보낸 텍스트가 그 질문의 답으로 들어갈 수 있습니다. 상태를 모를 때는 `attach`로 화면을 보고 입력하세요. 여러 줄을 보냈을 때의 처리도 AI 도구의 입력 방식에 따라 달라집니다.

## 실행 맥에서 직접 쓰거나, 한 맥에서 먼저 시험하기

`--host`를 생략하면 **명령을 입력한 바로 그 맥**에서 동작합니다. SSH 준비 전에 한 맥에서 시험하거나, 실행 맥에 직접 앉아 같은 작업을 조작할 때 사용할 수 있습니다.

그 맥에 `macrelay.pyz`를 내려받은 뒤 다음처럼 실행합니다.

```sh
python3 macrelay.pyz doctor
python3 macrelay.pyz start claude --cwd ~/Projects/my-app --name local-test
python3 macrelay.pyz list
# start 또는 list에서 확인한 실제 ID를 사용합니다.
python3 macrelay.pyz attach a1b2c3d4e5f6
```

로컬과 원격은 같은 사용자 계정과 같은 상태 저장 경로를 사용할 때 같은 세션 목록을 봅니다. 원격 접속 중이라고 해서 로컬에서 두 번째 조작자가 동시에 입력할 수 있는 것은 아닙니다. 보기만 하려면 `--read-only`를 사용하세요.

## 기존 작업에 연결하기

이미 실행 중인 작업은 **어떻게 시작했는지**에 따라 연결 방법이 달라집니다.

| 기존 작업의 종류 | 연결 방법 |
| --- | --- |
| macrelay의 `start`로 시작한 Codex·Claude | `list`에서 ID를 찾고 `attach ID`로 접속합니다. |
| Claude Code 자체의 백그라운드 기능으로 시작한 작업 | 지원되는 Claude 버전이라면 아래의 `discover claude`와 `attach-existing claude`를 사용합니다. |
| tmux 안에서 실행 중인 CLI | 아래의 `discover tmux`와 `attach-existing tmux`를 사용합니다. 실행 맥에 tmux가 필요합니다. |
| 일반 터미널에서 직접 실행한 Codex·Claude | 실행 중인 터미널을 그대로 가져오는 기능은 없습니다. 기존 실행을 종료한 뒤 저장된 대화를 재개할 수 있습니다. |
| Codex 데스크톱 앱의 대화 | 현재 지원하지 않습니다. |

### Claude의 기존 백그라운드 작업

**조작 맥에서** 목록을 확인하고, 연결 가능한 백그라운드 작업의 ID로 접속합니다.

```sh
python3 macrelay.pyz --host min@office-mac.local discover claude
python3 macrelay.pyz --host min@office-mac.local attach-existing claude BACKGROUND_ID
```

`BACKGROUND_ID`는 목록에서 확인한 Claude의 작업 ID입니다. macrelay가 새로 만든 세션 ID와는 다릅니다. 목록에 표시되는 모든 Claude 대화가 이 연결 기능을 지원하는 것은 아니며, 실행 맥의 Claude 버전이 해당 기능을 제공해야 합니다.

### tmux에서 실행 중인 작업

tmux는 터미널 작업을 유지하고 다시 접속할 수 있게 해 주는 별도 도구입니다. **이미 tmux 안에서 실행 중인 작업**이 있을 때 이 방법을 사용합니다. macrelay로 새 작업을 시작하는 데에는 tmux가 필요 없습니다.

```sh
python3 macrelay.pyz --host min@office-mac.local discover tmux
python3 macrelay.pyz --host min@office-mac.local attach-existing tmux SESSION_NAME
```

`SESSION_NAME`은 tmux 목록에 나온 이름으로 바꾸세요.

`attach-existing`은 Claude 또는 tmux가 제공하는 연결 명령을 직접 실행합니다. 따라서 macrelay의 단일 조작자 제한과 출력 기록 기능은 적용되지 않습니다. 빠져나오는 키도 해당 도구의 규칙을 따릅니다. Claude에서는 설치된 버전의 안내를 확인하고, tmux에서는 기본 설정 기준으로 `Ctrl-b`를 누른 뒤 `d`를 누릅니다.

### Claude 백그라운드 작업에 대한 접속을 macrelay로 관리하기

기존 Claude 작업에 접속하는 터미널 자체를 macrelay 세션으로 관리할 수도 있습니다.

```sh
python3 macrelay.pyz --host min@office-mac.local start claude \
  --cwd /Users/min/Projects/my-app --background-id BACKGROUND_ID
```

이 명령은 기존 Claude 작업으로 연결되는 **새 macrelay 세션 ID**를 출력합니다. 이후 그 새 ID로 `attach`, `logs`, `stop`을 사용합니다.

이때 macrelay의 `stop`은 **연결용 프로그램**을 종료합니다. 원래 Claude 백그라운드 작업은 계속 실행될 수 있습니다. 원래 작업까지 끝내려면 실행 맥에서 `claude stop BACKGROUND_ID`를 사용하세요. macrelay의 입력 제한 역시 이 연결을 통한 입력에 적용되며, 다른 경로로 접속한 Claude 사용자를 통제하지는 않습니다.

### 종료한 대화를 이어서 시작하기

`--resume`은 저장된 대화를 새 프로그램 실행에서 이어가는 옵션입니다. 실행 중인 프로그램 자체를 옮기는 기능은 아닙니다. 같은 대화에 두 실행이 동시에 기록하지 않도록 **기존 실행을 먼저 종료**하세요.

```sh
python3 macrelay.pyz --host min@office-mac.local start codex \
  --cwd /Users/min/Projects/my-app --resume CODEX_THREAD_ID

python3 macrelay.pyz --host min@office-mac.local start claude \
  --cwd /Users/min/Projects/my-app --resume CLAUDE_SESSION_ID
```

두 예시 중 사용할 도구의 명령을 선택합니다. `CODEX_THREAD_ID`와 `CLAUDE_SESSION_ID`는 해당 도구가 저장한 대화 ID입니다. macrelay의 `list`에 나오는 세션 ID를 대신 넣는 것이 아닙니다.

## 연결 설정을 바꿔야 할 때

### SSH 주소 대신 짧은 이름 사용하기

조작 맥의 `~/.ssh/config`에 등록한 별칭도 `--host`에 사용할 수 있습니다. 예를 들어 `office`라는 별칭이 있다면 다음처럼 실행합니다.

```sh
python3 macrelay.pyz --host office list
```

SSH 포트, 인증 키, 중간 접속 서버인 점프 호스트 설정은 `~/.ssh/config`에서 관리합니다. macrelay에 비밀번호나 API 키를 따로 저장하지 않습니다.

### 실행 맥의 Python 경로 지정하기

SSH 환경에서 `python3`를 찾지 못하거나 다른 Python을 써야 한다면 경로를 지정합니다.

```sh
python3 macrelay.pyz --host min@office-mac.local \
  --remote-python /path/to/python3 doctor
```

처음 복사할 때도 지정할 수 있습니다.

```sh
python3 macrelay.pyz --remote-python /path/to/python3 install min@office-mac.local
```

`--host`와 `--remote-python`은 `doctor`, `start`, `list` 같은 **명령 이름 앞에** 둡니다.

### 실행 맥의 Codex·Claude 경로 지정하기

macrelay는 SSH로 명령을 실행할 때 실행 파일을 찾는 경로인 `PATH` 앞에 `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`을 추가합니다. 이는 해당 원격 명령에만 적용되며 셸 설정 파일을 수정하지 않습니다.

AI 실행 파일이 다른 위치에 있다면 `--executable`로 지정합니다.

```sh
python3 macrelay.pyz --host min@office-mac.local start claude \
  --cwd /Users/min/Projects/my-app --executable /absolute/path/to/claude
```

`doctor`에 나오는 “실행 파일을 찾을 수 없음”과 “파일은 있지만 실행에 실패함”은 다릅니다. 후자는 실행 맥에서 해당 도구의 설치 상태를 확인해야 합니다.

## 출력 기록과 저장 위치

macrelay는 실행 맥의 `~/.macrelay` 아래에 세션 정보와 최근 출력을 저장합니다.

| 항목 | 동작 |
| --- | --- |
| 출력 보관량 | 세션마다 최근 256 KiB의 터미널 출력 바이트를 유지합니다. 그보다 오래된 출력은 이 기록에서 빠집니다. |
| 디스크 저장 주기 | 실행 중 약 2초 간격으로 최근 출력을 저장합니다. 갑자기 종료되면 마지막 일부 출력은 저장되지 않을 수 있습니다. |
| 재접속 화면 | 최근 출력을 다시 보여 줍니다. 화면 전체를 저장한 스냅샷은 아니어서 표시가 어긋나면 터미널 창 크기를 바꿔 다시 그리게 해야 할 수 있습니다. |
| 작업 종료 후 | 세션 정보와 출력 파일은 자동 삭제하지 않습니다. 출력에 민감한 내용이 있었다면 기록에도 남을 수 있습니다. |

`logs`는 색상·커서 이동 같은 터미널 제어 문자를 그대로 실행하지 않고 읽을 수 있는 문자열로 바꿔 표시합니다. 원래의 색상과 제어 코드를 포함한 바이트가 필요하면 `logs 세션ID --raw`를 사용합니다.

저장 위치를 바꾸려면 **실행 맥에서** `MACRELAY_HOME` 환경 변수를 지정합니다.

```sh
export MACRELAY_HOME="$HOME/.macrelay-custom"
```

이미 존재하는 폴더를 지정할 경우 본인 소유이며 권한이 `0700`이어야 합니다. `0700`은 폴더 소유자만 접근할 수 있다는 뜻입니다. 내부 통신에 사용하는 Unix 소켓에는 경로 길이 제한이 있으므로 짧은 경로를 사용하세요.

로컬 터미널에서 이 변수를 지정해도 SSH 명령에 자동으로 전달되지는 않습니다. 원격 접속에서도 같은 저장 위치를 쓰려면 실행 맥의 SSH 명령 환경에도 동일하게 설정해야 합니다. 처음에는 기본 위치를 그대로 사용하는 편이 간단합니다.

## 내부 동작과 알아둘 한계

현재 버전은 두 AI 도구의 **터미널 화면과 키 입력을 전달**합니다. Codex app-server의 메시지·도구 호출 등을 개별 이벤트로 주고받는 API 연동은 아직 구현하지 않았습니다.

실행 맥에서는 세션마다 작은 관리 프로그램인 **브로커**가 AI 프로세스를 유지합니다. AI에는 실제 터미널처럼 동작하는 **가상 터미널(PTY)**을 연결합니다. 그래서 조작 맥과의 연결이 종료되어도 AI의 터미널은 실행 맥에 남아 있습니다.

- **통신과 권한:** 맥 사이의 인증·암호화·호스트 키 확인은 SSH를 그대로 사용합니다. macrelay가 별도 TCP 포트를 열지는 않습니다. AI는 접속한 SSH 사용자 계정의 권한으로 실행되며, AI 도구 자체의 승인 설정도 그대로 적용됩니다.
- **실행 맥 안의 통신:** 브로커와 연결 프로그램은 Unix 소켓으로 통신합니다. 이는 같은 컴퓨터 안의 프로그램끼리 통신하는 통로입니다. 상태 폴더는 `0700`, 소켓과 기록 파일은 `0600`으로 만들어 다른 사용자 계정의 접근을 제한합니다.
- **느린 연결:** 출력 수신이 너무 느려 대기량이 한도를 넘으면 해당 접속을 끊습니다. 그 접속 때문에 AI 작업 전체가 멈추지 않도록 하기 위한 처리입니다.
- **실행 상태를 확인할 수 없을 때:** 목록에 세션 정보는 있지만 브로커에 연결되지 않으면 `unreachable`로 표시합니다. 작업이 실행 중인지 종료됐는지는 이 상태만으로 확정할 수 없습니다.
- **작업 종료:** `stop`은 관리하는 프로세스 그룹에 정상 종료 요청인 `TERM`을 보내고, 3초가 지나도 종료되지 않으면 강제 종료인 `KILL`을 보냅니다. 별도 실행 세션으로 분리된 하위 작업까지 모두 종료한다고 보장하지는 않습니다.

## 소스에서 실행하거나 개발하기

릴리스 파일 대신 소스를 사용하려면 저장소를 내려받습니다.

```sh
git clone https://github.com/eraser3031/macrelay.git
cd macrelay
python3 run.py --help
```

소스 폴더에서는 앞의 예시에 있는 `python3 macrelay.pyz`를 **`python3 run.py`로 바꿔** 실행하면 됩니다. 나머지 옵션은 같습니다.

다른 맥으로 옮길 단일 파일을 만들려면 다음을 실행합니다.

```sh
python3 run.py build
python3 dist/macrelay.pyz --version
```

생성된 `dist/macrelay.pyz`를 조작 맥에 복사하면 됩니다. 소스 전체를 함께 복사할 필요는 없습니다.

선택적으로 Python 가상 환경에 설치하면 `macrelay`라는 짧은 명령으로 사용할 수도 있습니다. 가상 환경은 이 프로젝트의 Python 설치 항목을 따로 모아 두는 폴더입니다.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
macrelay --help
```

테스트는 소스 폴더에서 실행합니다.

```sh
python3 -m unittest discover -s tests -v
```

## 어디까지 검증했나요?

실제 가상 터미널, Unix 소켓, 별도 프로세스를 사용하는 통합 테스트로 입력·출력, 창 크기 변경, `Ctrl-C`, 접속 해제와 재접속, 읽기 전용 접속, 단일 조작자 제한, 종료, 출력 보관량을 확인했습니다. Python 3.9와 3.14에서 7개 테스트를 통과했습니다.

SSH 배포는 **실제 다른 맥 대신 로컬에서 SSH 역할을 대신하는 테스트 프로그램**으로 확인했습니다. 이를 통해 파일 복사, 배포 파일 실행, 명령 인자 전달, 입출력 연결을 검사했습니다. 두 맥 사이의 실제 SSH 인증과 네트워크까지 검증한 것은 아닙니다.

설치된 Claude Code는 실제로 시작해 초기 출력을 받고 종료했습니다. 모델에 작업을 요청하거나 승인 질문을 왕복 처리하는 실기 테스트는 아직 하지 않았습니다. 테스트 환경의 Codex CLI는 실행 파일이 누락되어 실제 Codex 실행을 검증하지 못했습니다. 자세한 결과와 환경 제약은 [검증 기록](VALIDATION.md)에 있습니다.

관련 문서: [Codex app-server](https://learn.chatgpt.com/docs/app-server), [Claude Code CLI](https://code.claude.com/docs/en/cli-reference).
