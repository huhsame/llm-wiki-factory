#!/usr/bin/env python3
"""카톡 둘러보기. 방 목록과 방마다 몇 줄인지만 셉니다. 표준 라이브러리만 씁니다.

무엇을 하나
  수업에서 받은 kakao-windows 스킬의 rooms 로 방 목록을 받고,
  최근 몇 달치를 방마다 read 해서 **줄 수·날짜 수·말한 사람 수**만 세어 JSON 한 줄로 냅니다.
  받은 결과는 임시 폴더에 잠깐 두고 집계가 끝나면 지웁니다.

무엇을 안 하나
  창고(raw/)에 파일을 하나도 안 씁니다. 상태 파일(raw/_수집상태.json)도 건드리지 않습니다.
  대화 내용은 **세기만 하고 어디에도 안 남깁니다.** 낱말도 세지 않습니다.
  출력에 나가는 것은 카톡 표시 이름과 숫자뿐이고, 이름이 전화번호 모양이면 그것도 지웁니다.
  kakao-windows 스킬을 고치지 않습니다.

세는 규칙은 kakao_collect.py 와 같습니다. 빈 메시지와 방 목록 미리보기 줄은 안 셉니다.
그래서 여기 나온 줄 수와 나중에 실제로 쌓이는 파일의 「메시지:」 줄 수가 같습니다.

사용법
  python kakao_survey.py --wiki "<위키폴더>"
  python kakao_survey.py --wiki "<위키폴더>" --months 2 --max-rooms 15
  python kakao_survey.py --from-json "<messages.json 경로>"
  python kakao_survey.py --wiki "<위키폴더>" --dry-run

인자
  --wiki        위키 폴더 (--from-json 이 없으면 필수)
  --skill-dir   kakao-windows 자리. 없으면 kakao_collect.py 와 같은 두 곳을 찾습니다
  --account     카톡 계정 폴더가 여럿일 때
  --months      최근 몇 달을 셀지. 기본 1
  --max-rooms   셀 방 수 상한(최근 활동 순). 기본 12
  --budget      전체 시간 예산(초). 기본 180. 넘으면 남은 방은 skipped 로 넘깁니다
  --room        특정 방 이름만. 여러 번 쓸 수 있어요
  --room-id     특정 방 번호(chat_id)만. 여러 번 쓸 수 있어요
  --from-json   이미 받아 둔 read 결과로 세기만 합니다(카톡을 안 부릅니다)
  --dry-run     카톡을 안 부르고 스킬 자리와 계획만 확인합니다

출력 JSON (stdout 한 줄)
  {"ok":false,"partial":true,"survey":"kakao","window":{"months":1,"since":"2026-08-01"},
   "rooms":[{"room":"현장 단톡방","room_id":"1234567890","messages":412,"days":28,
             "first":"2026-08-20","last":"2026-09-18","people":6,"my_share":0.24,
             "top_senders":[{"name":"김선영","count":120}],"guess":"업무후보"}],
   "skipped":[{"room":"공지방","why":"메시지 0"}],
   "failed":[{"room":"옛방","why":"KEYS_REQUIRED"}]}
  guess 는 결정론 힌트일 뿐이에요. 넣을지 뺄지는 사람이 정합니다.
  **ok 가 false 인데 rooms 가 비어 있지 않으면 일부 방만 막힌 것입니다**(partial: true).
  그 방은 failed 에 있고 나머지 방 집계는 그대로 쓸 수 있어요. 둘러보기 전체가 실패한 게 아닙니다.
  오류  {"ok":false,"error":{"code":"WINDOWS_REQUIRED","message":"..."}}
        코드는 NO_WIKI · WINDOWS_REQUIRED · KAKAO_SKILL_NOT_FOUND · KAKAO_VENV_MISSING ·
        ROOMS_FAILED · BAD_JSON 입니다

종료코드
  0 성공 · 2 사람이 손봐야 하는 문제(윈도우 아님·스킬 없음·일부 방 실패) · 3 예상 못 한 오류
  1 은 쓰지 않습니다. 한 방이 막혀도 나머지 방은 계속 셉니다(그때 종료코드는 2, partial 은 true).
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import shutil
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import kakao_collect as K  # noqa: E402  (스킬 찾기·부르기를 그대로 씁니다)

# 낱말은 세지 않습니다. 대화 내용은 "몇 줄인가"를 셀 때만 지나가고 어디에도 안 남습니다.
# 주소록에 없는 상대는 표시 이름이 전화번호일 수 있어서, 그 모양이면 이름을 지웁니다.
PHONE = re.compile(r"^\+?\d[\d\-\s()]{7,}$")
NO_NAME = "(이름 없음)"


def out(obj, code=0):
    # 화면용 JSON 은 ASCII 로만 냅니다(Windows 콘솔에서 한글이 통째로 사라지는 일을 막습니다).
    print(json.dumps(obj, ensure_ascii=True))
    raise SystemExit(code)


def month_list(months: int, today: datetime.date) -> list:
    start_ym = C.shift_month(today.strftime("%Y-%m"), max(months - 1, 0))
    return C.months_between(start_ym, today.strftime("%Y-%m"))


def blank(room: str, room_id) -> dict:
    return {"room": room, "room_id": str(room_id or ""), "messages": 0, "days": set(),
            "first": None, "last": None, "senders": {}, "mine": 0}


def tally(acc: dict, msgs: list) -> None:
    """kakao_collect.render() 와 같은 규칙으로 셉니다. 빈 줄과 미리보기 줄은 안 셉니다."""
    for one in msgs:
        if one.get("source") != "chat_db":
            continue
        text = " ".join(str(one.get("message") or "").split())
        if not text:
            continue
        who = "나" if one.get("direction") == "sent" else (one.get("sender") or "알 수 없음")
        who = C.nfc(str(who)).strip()
        if not who or PHONE.match(who):   # 표시 이름이 전화번호면 안 담습니다
            who = NO_NAME
        when = datetime.datetime.fromtimestamp(one.get("sent_at") or 0)
        day = when.strftime("%Y-%m-%d")
        acc["messages"] += 1
        acc["days"].add(day)
        acc["first"] = day if acc["first"] is None else min(acc["first"], day)
        acc["last"] = day if acc["last"] is None else max(acc["last"], day)
        acc["senders"][who] = acc["senders"].get(who, 0) + 1
        if who == "나":
            acc["mine"] += 1


def finish(acc: dict, top: int = 8) -> dict:
    total = acc["messages"]
    mine = acc["mine"] / total if total else 0.0
    senders = sorted(acc["senders"].items(), key=lambda x: (-x[1], x[0]))
    people = len([name for name in acc["senders"] if name != "나"]) + (1 if acc["mine"] else 0)
    guess = "업무후보" if (people >= 3 or 0.10 <= mine <= 0.60) else "사적후보"
    return {"room": acc["room"], "room_id": acc["room_id"], "messages": total,
            "days": len(acc["days"]), "first": acc["first"], "last": acc["last"],
            "people": people, "my_share": round(mine, 2),
            "top_senders": [{"name": n, "count": c} for n, c in senders[:top]],
            "guess": guess}


def norm_rooms(data: dict) -> list:
    raw = data.get("rooms")
    if raw is None and isinstance(data.get("data"), dict):
        raw = data["data"].get("rooms")
    rooms = []
    for one in raw or []:
        if isinstance(one, str):
            rooms.append({"name": C.nfc(one), "chat_id": "", "last_at": 0})
            continue
        name = one.get("name") or one.get("title") or one.get("room") or ""
        chat_id = one.get("chat_id") or one.get("id") or one.get("room_id") or ""
        last_at = one.get("last_at") or one.get("last_message_at") or one.get("updated_at") or 0
        try:
            last_at = float(last_at)
        except (TypeError, ValueError):
            last_at = 0
        rooms.append({"name": C.nfc(str(name)), "chat_id": str(chat_id), "last_at": last_at})
    return [r for r in rooms if r["name"] or r["chat_id"]]


def read_month(skill, target: str, ym: str, state_dir, account) -> list:
    """한 방의 한 달치를 읽어 messages 목록만 돌려줍니다. 임시 폴더는 반드시 지웁니다."""
    first, nxt = C.month_bounds(ym)
    end_at = min(nxt - datetime.timedelta(seconds=1), C.now_local())
    if end_at <= first:
        return []
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="inbox-survey-"))
    shutil.rmtree(tmp, ignore_errors=True)  # read 는 없거나 빈 폴더를 원합니다
    try:
        result = K.call(skill, ["read",
                                "--start", first.isoformat(timespec="seconds"),
                                "--end", end_at.isoformat(timespec="seconds"),
                                "--direction", "all",
                                "--room", target,
                                "--out", str(tmp)], state_dir, account)
        payload = json.loads(pathlib.Path(result["files"]["json"]).read_text(encoding="utf-8"))
        return payload.get("messages", [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def from_json(path: pathlib.Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as err:
        out({"ok": False, "error": {"code": "BAD_JSON", "message": str(err)[:200]}}, 2)
    groups = {}
    for one in payload.get("messages", []):
        room = C.nfc(str(one.get("room") or one.get("chat_id") or "이름 없는 방"))
        groups.setdefault(room, blank(room, one.get("chat_id")))
        tally(groups[room], [one])
    rooms = [finish(acc) for acc in groups.values() if acc["messages"]]
    skipped = [{"room": acc["room"], "why": "메시지 0"}
               for acc in groups.values() if not acc["messages"]]
    rooms.sort(key=lambda x: -x["messages"])
    return {"ok": True, "partial": False, "survey": "kakao", "source": "from-json",
            "window": {"months": None, "since": None},
            "rooms": rooms, "skipped": skipped, "failed": []}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="카톡 둘러보기 (방 목록과 줄 수만 셉니다. 파일 쓰기 없음)")
    parser.add_argument("--wiki", help="위키 폴더. wiki/ 가 있는 곳")
    parser.add_argument("--skill-dir", help="kakao-windows 폴더. 없으면 직접 찾습니다")
    parser.add_argument("--account", help="카톡 계정 폴더가 여럿일 때")
    parser.add_argument("--kakao-state-dir", help="kakao-windows 상태 폴더가 기본값이 아닐 때만")
    parser.add_argument("--months", type=int, default=1, help="최근 몇 달을 셀지")
    parser.add_argument("--max-rooms", type=int, default=12, help="셀 방 수 상한")
    parser.add_argument("--budget", type=int, default=180,
                        help="전체 시간 예산(초). 넘으면 남은 방은 skipped 로 넘깁니다. 0이면 무제한")
    parser.add_argument("--room", action="append", default=[], help="특정 방 이름만")
    parser.add_argument("--room-id", action="append", default=[], help="특정 방 번호만")
    parser.add_argument("--from-json", help="이미 받아 둔 read 결과로 세기만 합니다")
    parser.add_argument("--dry-run", action="store_true",
                        help="카톡을 부르지 않고 스킬 자리와 계획만 확인합니다")
    return parser


def main() -> None:
    C.force_utf8()
    args = build_parser().parse_args()

    if args.from_json:
        out(from_json(pathlib.Path(args.from_json).expanduser()))

    if not args.wiki:
        out({"ok": False, "error": {"code": "NO_WIKI",
                                    "message": "위키 폴더를 알려 주세요(--wiki)."}}, 2)
    wiki = pathlib.Path(args.wiki).expanduser().resolve()
    if not (wiki / "wiki").is_dir():
        out({"ok": False, "error": {"code": "NO_WIKI",
                                    "message": "위키 폴더가 아니에요. wiki/ 가 있는 폴더를 알려 주세요."}}, 2)
    # 카톡 스킬은 Windows 전용이에요. --skill-dir 로 자리를 직접 주면 그 자리를 그대로 씁니다(모의 시험용).
    if sys.platform != "win32" and not args.skill_dir:
        out({"ok": False, "error": {"code": "WINDOWS_REQUIRED",
                                    "message": "카톡 둘러보기는 Windows 에서만 돼요. 메일만 둘러볼게요."}}, 2)

    try:
        skill = K.find_skill(args.skill_dir)
    except FileNotFoundError as err:
        out({"ok": False, "error": {"code": str(err),
                                    "message": "수업에서 받은 카톡 스킬을 못 찾았어요."}}, 2)

    today = datetime.date.today()
    months = month_list(args.months, today)
    since, _ = C.month_bounds(months[0])

    targets = []
    if args.room or args.room_id:
        for idx, room in enumerate(args.room):
            targets.append({"name": C.nfc(room),
                            "chat_id": args.room_id[idx] if idx < len(args.room_id) else ""})
        for extra in args.room_id[len(args.room):]:
            targets.append({"name": "", "chat_id": str(extra)})
    else:
        if args.dry_run:
            targets = []
        else:
            try:
                data = K.call(skill, ["rooms"], args.kakao_state_dir, args.account)
            except Exception as err:
                out({"ok": False, "error": {"code": "ROOMS_FAILED",
                                            "message": str(err)[:200]}}, 2)
            rooms = norm_rooms(data)
            rooms.sort(key=lambda r: -r["last_at"])
            targets = rooms[:args.max_rooms]

    if args.dry_run:
        out({"ok": True, "dry_run": True, "survey": "kakao", "wiki": str(wiki),
             "skill_dir": str(skill), "months": months, "max_rooms": args.max_rooms,
             "rooms": [t["name"] for t in targets], "writes": [],
             "state_file": str(C.state_path(wiki))})

    rows, skipped, failed = [], [], []
    started = time.monotonic()
    for idx, target in enumerate(targets):
        name = target.get("name") or f"방 {target.get('chat_id')}"
        if args.budget and idx and time.monotonic() - started > args.budget:
            skipped.append({"room": name, "why": "시간 상한"})
            continue
        acc = blank(name, target.get("chat_id"))
        broke = None
        for ym in months:
            try:
                msgs = read_month(skill, str(target.get("chat_id") or name), ym,
                                  args.kakao_state_dir, args.account)
            except Exception as err:
                broke = str(err)[:200]
                break
            tally(acc, msgs)
        if broke:
            failed.append({"room": name, "why": broke})
            continue
        if not acc["messages"]:
            skipped.append({"room": name, "why": "메시지 0"})
            continue
        rows.append(finish(acc))

    rows.sort(key=lambda x: -x["messages"])
    out({"ok": not failed, "partial": bool(failed and rows), "survey": "kakao",
         "window": {"months": args.months, "since": since.date().isoformat()},
         "rooms": rows, "skipped": skipped, "failed": failed}, 0 if not failed else 2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as err:  # 예상 못 한 오류도 JSON 한 줄로 냅니다
        out({"ok": False, "error": {"code": "UNEXPECTED", "message": type(err).__name__}}, 3)
