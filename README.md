# llm-wiki-factory

**자료는 쌓이는데 찾지를 못하는 문제를, 폴더를 더 나누지 않고 푸는 스킬입니다.**

*A skill that turns your own files into a personal wiki an AI keeps writing for you.*

메일·회의록·견적서·엑셀이 다운로드 폴더에 계속 쌓이는데, 정작 "그 업체 견적이 얼마였지"를 물어보면 어디에 뒀는지 기억이 안 납니다. 폴더를 아무리 잘 나눠도 같은 일이 반복됩니다. 이 스킬은 **원본을 그대로 둔 채** AI가 읽고 정리한 위키를 옆에 만들어 둡니다. 나중엔 폴더를 뒤지는 게 아니라 위키한테 물어보면 됩니다.

> 허세임 AI 강의 수강생 편의를 위해 만든 스킬입니다. 자료를 정리하고 싶은 분이면 누구에게나 그대로 쓰입니다.

---

## 설치

```
/plugin marketplace add huhsame/llm-wiki-factory
/plugin install llm-wiki-factory@llm-wiki-factory
```

명령이 안 먹으면 그냥 이렇게 말해도 됩니다.
**"https://github.com/huhsame/llm-wiki-factory 여기 들어가서 이 Skill 설치해 줘"**

설치하면 어느 폴더에서 작업하든 따라옵니다. 실습 폴더를 옮겨도 유지됩니다.

---

## 설치하고 처음 할 말

```
위키 만들어줘
```

폴더 두 개와 파일 다섯 개가 생기고, 질문은 딱 하나만 받습니다. "무슨 자료를 모을 위키예요?"
그다음은 자료를 `raw/` 폴더에 넣고 **"위키에 넣어줘"** 라고만 하면 됩니다.

평소에 쓰는 말은 네 가지뿐입니다.

| 말 | 하는 일 |
|---|---|
| "위키 만들어줘" | 폴더와 규칙 파일을 만듭니다 |
| "위키에 넣어줘" | `raw/`의 새 자료를 읽고 올림·버림·보류를 정해 페이지로 씁니다 |
| "위키에서 ~ 찾아줘" | 목차부터 읽고, 답에 출처 페이지를 붙여 대답합니다 |
| "위키 점검해줘" | 목차에 빠진 페이지, 깨진 링크, 서로 어긋나는 내용을 세어 줍니다 |

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

**뭘 깔아야 하나요?** 아닙니다. 이건 프로그램이 아니라 **규칙 모음**입니다. 설치할 것도, 깃도, 네트워크를 쓰는 것도 없습니다. Claude가 자료를 정리하기 전에 읽는 문서 한 장과 **파일 틀 다섯 개, 페이지 틀 하나**가 전부입니다. Word·PPT·메일이 잘 안 읽히는 경우에만 파이썬에 처음부터 들어 있는 기능으로 글자를 뽑습니다. 따로 받을 건 없습니다.

**이미 제 손으로 위키를 만들었는데요.** 그대로 두고 "위키 점검해줘"만 돌려 보세요. 목차에 빠진 페이지와 어긋나는 내용을 찾아 줍니다.

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

**아직 안 돌려 본 것**은 Windows 실제 환경, 자료 100건 이상, 그리고 정해진 시각에 자동으로 돌리는 4단계입니다. 4단계는 문서로만 안내하고 있습니다.

카파시의 LLM Wiki 구상과 구글의 Open Knowledge Format에서 개념을 가져왔습니다. 원문은 스킬 맨 아래 링크에 있습니다.

---

## In English

Your files pile up, and you still can't answer "how much was that quote?" This skill has Claude build a small wiki next to your files: you drop originals into `raw/`, say "put this in the wiki" in Korean or English, and Claude decides what to promote, what to drop (with a reason, in a ledger), and what to ask you about. Every page lands in a one-line index, every answer cites its page, and a weekly check counts what's missing or contradictory. Nothing to install, no git, no network. It is a set of rules plus five file templates and one page template, written for Windows users with Korean filenames who are not developers. Obsidian works out of the box.

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
