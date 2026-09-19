# llm-wiki-factory

스킬 두 개 · 파이썬 표준 기능만 · 설치는 링크 한 줄.

**자료는 쌓이는데 찾지를 못하는 문제를, 폴더를 더 나누지 않고 푸는 스킬입니다.**

*A skill that turns your own files into a personal wiki an AI keeps writing for you.*

메일·회의록·견적서·엑셀이 다운로드 폴더에 계속 쌓이는데, 정작 "그 업체 견적이 얼마였지"를 물어보면 어디에 뒀는지 기억이 안 납니다. 폴더를 아무리 잘 나눠도 같은 일이 반복됩니다. 이 스킬은 **원본을 그대로 둔 채** AI가 읽고 정리한 위키를 옆에 만들어 둡니다. 나중엔 폴더를 뒤지는 게 아니라 위키한테 물어보면 됩니다.

> 허세임 AI 강의 수강생 편의를 위해 만든 스킬입니다. 자료를 정리하고 싶은 분이면 누구에게나 그대로 쓰입니다.

📖 **그림으로 한 장 설명 보기** · https://claude.ai/artifact/5a8v33DBZVhXUDR5QYpRwC
(같은 내용의 HTML 원본은 이 저장소의 [`docs/llm-wiki-guide.html`](docs/llm-wiki-guide.html)에 있어요. 내려받아 더블클릭하면 열려요.)

---

## 스킬 두 개

| 스킬 | 하는 일 | 첫 마디 |
|---|---|---|
| **llm-wiki-factory** | 위키를 만들고, 자료를 읽고 판정해 페이지로 씁니다 | "위키 만들어줘" |
| **llm-wiki-inbox** | 카톡과 메일을 위키 창고로 **가져오기만** 합니다. 첫 수집 앞에 한 번 **둘러보기**로 겉만 세어 보여 줍니다 | "카톡 연결해줘" · "메일 연결해줘" · "둘러봐줘" |

**가져오기와 판정은 일부러 갈라 뒀습니다.** 밤에 자동으로 도는 건 가져오기뿐입니다. 판단은 아침에 한 마디 하실 때만 합니다. 그래서 자는 사이에 위키가 바뀌는 일이 없습니다.

---

## 설치

Claude Code(데스크톱 앱의 Code 탭)에 이렇게 말하면 됩니다.

```
https://github.com/huhsame/llm-wiki-factory 여기 들어가서 세팅해줘
```

그러면 Claude가 아래 절차대로 알아서 깔아 줍니다. 다 되면 **Claude를 껐다 켜시거나 새 대화를 여신 다음** **"위키 만들어줘"** 한 마디로 시작하시면 됩니다. 스킬 목록은 대화가 시작될 때 읽히기 때문에, 설치하던 그 대화에서는 방금 깐 스킬이 아직 안 잡힙니다.

한 번 깔면 어느 폴더에서 작업하든 따라옵니다. 실습 폴더를 옮겨도 유지됩니다.

---

### AI가 읽는 설치 절차

> 사용자가 이 저장소 주소를 주면서 "세팅해줘"라고 하면, 아래를 **Claude가 직접 실행**한다. 사용자에게 명령을 받아 치게 하지 않는다. 경로에 한글이나 공백이 섞일 수 있으니 모든 경로를 큰따옴표로 감싼다.
>
> **블록은 쪼개지 말고 통째로 한 번에 실행한다.** 셸은 명령을 부를 때마다 새로 뜨기 때문에 `$tmp`·`$src`·`$dest` 같은 변수가 다음 호출로 넘어가지 않는다. 줄 단위로 나눠 실행하면 변수가 빈 값이 되어 **이미 깔려 있던 스킬을 지우고 아무것도 못 까는** 상태가 된다.
>
> **Windows는 PowerShell 문법이다.** `powershell -NoProfile -Command "<블록 전체>"` 로 한 번에 실행한다. bash 레인에 그대로 넣지 않는다.

#### ① 먼저 확인만 한다 (아무것도 바꾸지 않는다)

**Windows (PowerShell)**

```powershell
$dest = Join-Path $env:USERPROFILE ".claude\skills"
Get-Command git -ErrorAction SilentlyContinue | Select-Object -First 1 Name
Test-Path (Join-Path "$dest" "llm-wiki-factory")
Test-Path (Join-Path "$dest" "llm-wiki-inbox")
```

**macOS / Linux**

```bash
dest="$HOME/.claude/skills"
command -v git || echo "git 없음"
ls -d "$dest/llm-wiki-factory" "$dest/llm-wiki-inbox" 2>/dev/null || echo "아직 안 깔려 있음"
```

`Test-Path` 가 하나라도 `True` 면(macOS는 경로가 찍히면) **이미 깔려 있는 것**이다. 그때는 "이미 깔려 있어요. 최신 걸로 덮어쓸까요?" 라고 묻고, **답을 듣기 전에는 ②로 넘어가지 않는다.** ②는 있던 폴더를 지우고 복사하므로 되돌릴 수 없다.

#### ② 받아서 옮기고 정리까지 한 번에 한다

> **사용자 답을 받은 뒤에만 실행한다.** 아래 한 덩어리 안에 받기·복사·확인·정리가 다 들어 있다. 반드시 통째로 한 번에 실행한다.

**Windows (PowerShell)**

```powershell
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$tmp  = Join-Path $env:TEMP "llm-wiki-factory-setup"
$zip  = Join-Path $env:TEMP "llm-wiki-factory.zip"
$dest = Join-Path $env:USERPROFILE ".claude\skills"
Remove-Item -LiteralPath "$tmp" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$dest" | Out-Null

# 1) 받는다. git 이 있으면 clone, 없거나 실패하면 zip
$src = $null
if (Get-Command git -ErrorAction SilentlyContinue) {
  git clone --depth 1 https://github.com/huhsame/llm-wiki-factory.git "$tmp" 2>&1 | Out-Null
  if (Test-Path -LiteralPath (Join-Path "$tmp" "skills")) { $src = Join-Path "$tmp" "skills" }
}
if (-not $src) {
  Invoke-WebRequest -Uri "https://github.com/huhsame/llm-wiki-factory/archive/refs/heads/main.zip" -OutFile "$zip" -UseBasicParsing
  Expand-Archive -LiteralPath "$zip" -DestinationPath "$tmp" -Force
  $src = Join-Path "$tmp" "llm-wiki-factory-main\skills"
}

# 2) 받은 게 확인될 때만 옮긴다. 있던 폴더는 먼저 지운다
#    (지우지 않고 덮으면 llm-wiki-factory\llm-wiki-factory 처럼 한 겹 더 들어간다)
if ((Test-Path -LiteralPath (Join-Path "$src" "llm-wiki-factory")) -and (Test-Path -LiteralPath (Join-Path "$src" "llm-wiki-inbox"))) {
  foreach ($n in "llm-wiki-factory", "llm-wiki-inbox") {
    $target = Join-Path "$dest" $n
    if (Test-Path -LiteralPath "$target") { Remove-Item -LiteralPath "$target" -Recurse -Force }
    Copy-Item -LiteralPath (Join-Path "$src" $n) -Destination "$dest" -Recurse -Force
  }
  # 3) 제자리에 있는지 확인한다. 둘 다 True 여야 끝난 것이다
  Test-Path (Join-Path "$dest" "llm-wiki-factory\SKILL.md")
  Test-Path (Join-Path "$dest" "llm-wiki-inbox\SKILL.md")
} else {
  Write-Host "저장소를 받지 못했어요. 인터넷 연결과 주소를 확인해 주세요."
}

# 4) 임시로 받아 둔 것을 지운다
Remove-Item -LiteralPath "$tmp" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$zip" -Force -ErrorAction SilentlyContinue
```

**macOS / Linux**

```bash
tmp="${TMPDIR:-/tmp}/llm-wiki-factory-setup"
zip="$tmp.zip"
dest="$HOME/.claude/skills"
rm -rf "$tmp" "$zip"
mkdir -p "$dest"

# 1) 받는다. git 이 있으면 clone, 없거나 실패하면 zip
src=""
if command -v git >/dev/null 2>&1 && git clone --depth 1 https://github.com/huhsame/llm-wiki-factory.git "$tmp" >/dev/null 2>&1; then
  src="$tmp/skills"
fi
if [ ! -d "$src" ]; then
  curl -fsSL -o "$zip" https://github.com/huhsame/llm-wiki-factory/archive/refs/heads/main.zip
  mkdir -p "$tmp" && unzip -q "$zip" -d "$tmp"
  src="$tmp/llm-wiki-factory-main/skills"
fi

# 2) 받은 게 확인될 때만 옮긴다. 있던 폴더는 먼저 지운다
if [ -d "$src/llm-wiki-factory" ] && [ -d "$src/llm-wiki-inbox" ]; then
  for n in llm-wiki-factory llm-wiki-inbox; do
    rm -rf "$dest/$n"
    cp -R "$src/$n" "$dest/$n"
  done
  # 3) 제자리에 있는지 확인한다. 두 경로가 그대로 찍혀야 끝난 것이다
  ls "$dest/llm-wiki-factory/SKILL.md" "$dest/llm-wiki-inbox/SKILL.md"
else
  echo "저장소를 받지 못했어요. 인터넷 연결과 주소를 확인해 주세요."
fi

# 4) 임시로 받아 둔 것을 지운다
rm -rf "$tmp" "$zip"
```

가져갈 것은 `skills/llm-wiki-factory` 와 `skills/llm-wiki-inbox` 두 폴더뿐이다. 목적지는 Windows가 `%USERPROFILE%\.claude\skills\`, macOS가 `~/.claude/skills/` 다.

확인 줄이 하나라도 `False` 거나 경로가 안 찍히면 ②를 다시 한 번 통째로 실행한다.

#### ③ 이 두 줄로 끝낸다

> 다 됐어요. **Claude를 껐다 켜시거나 새 대화를 열어** 주세요.
> 그다음 **"위키 만들어줘"** 라고 하시면 시작합니다.

**재시작 안내를 빼먹지 않는다.** 스킬 목록은 대화가 시작될 때 한 번 읽히기 때문에, 방금 복사한 스킬은 설치하던 이 대화에서는 아직 안 잡힌다.

## 설치하고 처음 할 말

```
위키 만들어줘
```

폴더 두 개와 파일 다섯 개가 생기고, 질문은 딱 하나만 받습니다. "무슨 자료를 모을 위키예요?"
넣을 자료가 아직 없으시면 세 가지를 더 여쭤봅니다(무슨 일을 하시는지, 진행 중인 일, 자주 연락하는 곳).
그다음은 자료를 `raw/` 폴더에 넣고 **"위키에 넣어줘"** 라고만 하면 됩니다.

평소에 쓰는 말은 네 가지뿐입니다. 이미 만들어 두신 폴더가 있으면 처음 한 번 쓰는 말이 하나, 카톡·메일을 붙이시면 첫날 한 번 쓰는 말이 하나 더 있습니다.

| 말 | 하는 일 |
|---|---|
| "위키 만들어줘" | 폴더와 규칙 파일을 만듭니다 |
| "내 위키 봐줘" | **이미 만들어 두신 폴더**를 읽기만 해서 지금 어떻게 돼 있는지 표로 보여 줍니다(처음 한 번) |
| "위키에 넣어줘" | `raw/`의 새 자료를 읽고 올림·버림·보류를 정해 페이지로 씁니다 |
| "위키에서 ~ 찾아줘" | 목차부터 읽고, 답에 출처 페이지를 붙여 대답합니다 |
| "위키 점검해줘" | 목차에 빠진 페이지, 깨진 링크, 서로 어긋나는 내용을 세어 줍니다 |
| "둘러봐줘" | 메일과 카톡의 **겉만** 1분쯤 세어 표로 보여 주고, 세 가지만 고르게 합니다(연결한 뒤 첫날 한 번) |

---

## 이미 만든 위키가 있어도 됩니다

수업에서 카파시 gist만 보고 폴더를 만들어 두셨거나, 손으로 페이지를 몇 장 써 두셨어도 그대로 이어서 쓰면 됩니다. **갈아엎지 않습니다.** 그 폴더에서 **"내 위키 봐줘"** 라고 하시면 이 순서로 갑니다.

```
진단(읽기만)  →  계획 설명  →  확인 한 번  →  실행  →  안내 페이지
```

1. **진단** · 창고·페이지·목차·장부·서랍·출처 등 열다섯 줄짜리 표로 지금 상태를 보여 줍니다. **이 단계에서는 아무것도 고치지 않습니다.**
2. **계획** · 진단표에서 걸린 줄만 번호를 붙여 무엇을 할지 적어 드립니다.
3. **확인** · **딱 한 번** 물어봅니다(① 그대로 ② 백업만 하고 멈춤 ③ 몇 가지는 빼고). 고칠 게 없으면 이 질문도 하지 않습니다.
4. **실행** · 위키 폴더 바깥에 통째로 백업한 다음, **없는 것만 채웁니다.**

실행이 지키는 다섯 가지입니다.

- **이미 있는 페이지를 지우지 않습니다.** 한 장도요.
- **페이지 본문을 고치지 않습니다.** 맨 위 정보 몇 줄과 맨 아래 `## 출처`만 더합니다.
- **창고(`raw/`)를 건드리지 않습니다.** 이름도 내용도 자리도 그대로입니다.
- **`CLAUDE.md`를 덮어쓰지 않습니다.** 맨 아래에 절 하나를 더합니다.
- **파일 이름을 바꾸지 않습니다.**

끝나면 위키 폴더에 **`안내.html`** 한 장이 놓입니다. 더블클릭하면 브라우저에서 열리고, 지금 폴더가 어떻게 생겼는지·무슨 말을 하면 되는지·지금 숫자가 몇인지·다음에 뭘 하면 좋은지가 한 화면에 있습니다. 자료를 넣거나 점검할 때마다 저절로 다시 채워집니다. 인터넷 없이도 열립니다.

---

## 카톡·메일 연결은 llm-wiki-inbox

자료를 손으로 넣는 게 번거로워지면 **"카톡 연결해줘"** 또는 **"메일 연결해줘"** 라고 하세요. 두 번째 스킬이 질문 여섯 개 안에서 세팅을 끝냅니다.

- **메일** · 앱 비밀번호와 IMAP 하나로 지메일·네이버·회사 메일을 같은 방법으로 가져옵니다. 받은편지함만 보고, 읽음 표시를 바꾸지 않습니다. 광고·알림은 버리지 않고 `_걸러짐` 폴더로 보냅니다.
- **카톡** · 수업에서 받은 카톡 읽기 스킬이 있으면 그 결과를 창고로 옮깁니다(Windows 전용). 없으면 카카오톡 PC의 **대화 내보내기** 로도 됩니다.
- **두 트랙** · 새로 오는 것은 마지막으로 본 시각 이후만, 예전 것은 오래된 달부터 조금씩 받습니다. 1년치를 고르셔도 창고에 받아만 두고 회차마다 스무 건씩 정리합니다.
- **밤마다 자동** · 윈도우 작업 스케줄러(맥은 launchd)에 한 줄 걸면 가져오기만 자동으로 돕니다. AI 사용량이 들지 않습니다.
- **둘러보기** · 연결한 다음 **"둘러봐줘"** 한 마디면 메일함 머리(보낸 사람·제목·날짜) 3개월치와 카톡 방 목록의 겉만 세어 표로 보여 줍니다. **메일 본문은 받지 않고, 카톡 대화는 몇 줄인지만 세고 어디에도 남기지 않습니다. AI도 안 씁니다.** 업무가 아닌 이름을 빼고, 넣을 방을 고르고, 광고 보내는 곳을 거르시면 그 답이 서랍 세 줄과 「내 일 소개」 한 문단으로 들어갑니다.
- **비밀번호** · 화면에도 파일에도 남기지 않습니다. 윈도우는 그 사용자만 풀 수 있는 잠금으로, 맥은 키체인에 둡니다.

메일 수집과 카톡 옮기기에는 **파이썬이 필요합니다**(표준 기능만 씁니다. `pip` 로 받을 건 없습니다). 위키 본체(llm-wiki-factory)는 여전히 아무것도 필요 없습니다.

---

## 막아주는 사고 다섯 가지

**① 파일 15개를 페이지 15장으로 그냥 옮기기**
그건 정리가 아니라 복사입니다. 사람·회사·프로젝트 이름이 **서로 다른 파일 두 건 이상**에 나올 때만 페이지를 만듭니다. 한 번만 나온 이름은 그 자료 페이지 안에 한 줄로 남습니다.

**② 버린 자료가 어디에도 안 남기**
위키에 안 올린 자료도 장부에 한 줄씩 남습니다. 왜 버렸는지까지 적어 두기 때문에, 나중에 "이거 왜 없지"가 아니라 "아, 중복이라 뺐구나"가 됩니다.

**③ `최종`과 `진짜최종`을 둘 다 올려서 금액이 두 개 생기기**
같은 문서의 다른 버전을 알아보고 대표 하나만 올립니다. 버린 쪽 이유에 대표 파일 이름을 적어 둡니다.

**④ 목차에 없어서 페이지가 있는 줄도 모르기**
모든 페이지가 목차에 한 줄씩 들어갑니다. 예외가 없습니다. 검색으로 찾는 것과, 그런 게 있다는 걸 아는 것은 다릅니다.

**⑤ AI가 위키에 없는 내용을 지어내기**
답에는 출처 페이지를 `[[이렇게]]` 붙입니다. 위키에 없으면 없다고 먼저 말하고 원본을 찾아보고, 그래도 없으면 어디를 찾아봤는지 목록으로 보여 줍니다.

---

## 자주 묻는 것

**옵시디언으로 볼 수 있나요?** 위키 폴더를 볼트로 열기만 하면 됩니다. 플러그인은 필요 없습니다. `[[링크]]`를 쓰고 페이지 맨 위 정보를 한 줄짜리 값으로만 쓴 게 이것 때문입니다.

**뭘 깔아야 하나요?** 위키 본체는 아닙니다. 이건 프로그램이 아니라 **규칙 모음**입니다. 쓰는 동안 돌아가는 프로그램도, 깃도, 네트워크도 없습니다(파일을 받아오는 설치 때만 인터넷을 씁니다). Claude가 자료를 정리하기 전에 읽는 문서 한 장과 **파일 틀 다섯 개, 페이지 틀 하나**가 전부입니다. Word·PPT·메일이 잘 안 읽히는 경우에만 파이썬에 처음부터 들어 있는 기능으로 글자를 뽑습니다. 따로 받을 건 없습니다. 카톡·메일 자동 수집(llm-wiki-inbox)을 쓰실 때만 파이썬이 깔려 있어야 하고, 그때도 표준 기능만 씁니다.

**이미 제 손으로 위키를 만들었는데요.** 그 폴더에서 "내 위키 봐줘"라고 하세요. 갈아엎지 않고 지금 상태를 표로 먼저 보여 드립니다(위의 「이미 만든 위키가 있어도 됩니다」).

**되돌리려면요?** 점검이나 대량 정리 전에 위키 폴더를 **바깥에 통째로 복사**해 두세요. 깃을 쓰지 않는 대신 이 방법으로 되돌립니다.

**한글 파일 이름이 자꾸 말썽인데요.** [korean-safe-windows](https://github.com/huhsame/korean-safe-windows)를 같이 설치하면 한글 경로·인코딩 사고를 더 촘촘히 막아 줍니다.

---

## 어디까지 확인했나

Windows 한글 환경과 비개발자 사용을 기준으로 만들었습니다. 규칙과 파일 틀이라 macOS에서도 그대로 쓰입니다.

2026-09-19에 가상 업무자료 15건으로 **macOS에서** 다음을 실제로 돌려 봤습니다.

| 돌려 본 것 | 결과 |
|---|---|
| 위키 만들기 | 파일 다섯 개 생성, 서랍 13개, 질문 1회 |
| 자료 15건 넣기 | 페이지 5장, 장부 15행, 대기 잔존 0, 모든 페이지에 출처와 `type` |
| 원본 읽기 | Word 3·PPT 2·메일 2·엑셀 3을 설치 없이 열었습니다 |
| 찾기 | 금액을 원문 그대로 답하고 출처 페이지를 붙였습니다 |
| 점검 | 세는 것 다섯이 전부 0 |
| 같은 자료 다시 넣기 | 이름이 같을 때도, `(1)`이 붙었을 때도 알아봤습니다 |

**llm-wiki-inbox(카톡·메일 수집)는 2026-09-19 기준 모의 테스트만 마쳤습니다.** 가짜 카톡 CLI와 가짜 메일 서버로 다음을 돌렸습니다.

| 돌려 본 것 | 결과 |
|---|---|
| 카톡 6개월 백필(방 2개) | 월 파일 12개, 보고 숫자와 파일 안 줄 수가 같음(36 = 36) |
| 같은 명령 세 번 | 파일 내용 그대로 |
| 방 하나가 막혔을 때 | 나머지 방은 다 돌고, 막힌 방만 그 자리에 멈춤. 종료코드 2 |
| 메일 6개월 백필 | 회차마다 3개월씩 두 번에 끝남 |
| 새 메일 1통 도착 | 새로 온 것 1 · 밀린 것 6 으로 갈려서 보고됨 |
| 같은 등록 명령 재실행 | 진행 상태(커서·마지막 시각·건수) 보존 |
| 날짜 헤더가 깨진 메일 | 서버 도착 시각으로 대신하고, 그것도 없으면 `dropped` 로 셈 |
| 한 달 메일이 상한을 넘을 때 | `truncated` 로 몇 통 중 몇 통인지 보고 |
| 장부 파일 이름이 NFD일 때 | 그대로 읽힘. 못 찾으면 못 찾았다고 알려 줌 |
| 예상 못 한 오류(읽기 권한 없음) | JSON 한 줄 + 종료코드 3, 트레이스백 없음 |
| 앱 비밀번호 | 창고·위키·상태 파일·화면 어디에도 0건. 맥 키체인 왕복 확인 |
| 둘러보기(메일 40통) | 사람·도메인·낱말 순위가 나오고, 답장한 상대만 `replied: true`. 본 실행 출력에 메일 주소 0건(표시 이름과 도메인만) |
| 둘러보기(카톡 방 4개) | 방 2개 집계·빈 방 1개 건너뜀·막힌 방 1개는 `failed`. 줄 수가 실제 수집 결과와 같음(3 = 3) |
| 둘러보기 뒤 상태 파일 | 바이트 그대로. 창고 파일 수 그대로. 임시 폴더 잔여 0 |

**실제 네이버·지메일 계정 연결, 실제 카카오톡 PC, Windows 작업 스케줄러 등록은 아직 돌려 보지 않았습니다.** 야간 수집 배치 파일(`야간수집.cmd`)도 아직 Windows에서 돌려 보지 못했습니다.

**그 밖에 아직 안 돌려 본 것**은 Windows 실제 환경, 자료 100건 이상입니다.

카파시의 LLM Wiki 구상과 구글의 Open Knowledge Format에서 개념을 가져왔습니다. 원문은 스킬 맨 아래 링크에 있습니다.

---

## In English

Your files pile up, and you still can't answer "how much was that quote?" This skill has Claude build a small wiki next to your files: you drop originals into `raw/`, say "put this in the wiki" in Korean or English, and Claude decides what to promote, what to drop (with a reason, in a ledger), and what to ask you about. Every page lands in a one-line index, every answer cites its page, and a weekly check counts what's missing or contradictory. Nothing runs in the background, no git, no network while you use it. It is a set of rules plus five file templates and one page template, written for Windows users with Korean filenames who are not developers. Obsidian works out of the box. A second skill, `llm-wiki-inbox`, pulls KakaoTalk and email into the same `raw/` folder on two tracks (new mail since last run, plus an old backlog drained a month at a time) using only the Python standard library; app passwords are stored in Windows DPAPI or the macOS keychain, never in a file you can read. It has been smoke-tested with fixtures only, not against live accounts.

---

## 라이선스

MIT. [LICENSE](LICENSE) 참고. Copyright (c) 2026 허세임 (Huhsame).

---

## 만든 이

**허세임 (huhsame)** · AI 교육자, 데바대이(DaybydAI).

- 기업 AI 교육 · AX(AI 전환) 컨설팅 / Corporate AI training and AX consulting
- 웹: **https://huhsame.com**
- 교육·컨설팅 문의: **ai@huhsame.com**

같이 쓰면 좋은 것 · **[korean-safe-windows](https://github.com/huhsame/korean-safe-windows)** : 한글 경로·인코딩 사고를 첫 시도부터 막아 줍니다.

도움이 됐으면 ⭐ 하나가 다른 사람이 찾는 데 도움이 됩니다.
