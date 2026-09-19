#!/usr/bin/env python3
"""수업에서 받은 kakao-windows 스킬의 결과를 위키 창고로 옮깁니다.

카카오톡 데이터베이스를 직접 건드리지 않습니다. kakao-windows 의 read 명령을 부르고,
그 결과 파일(messages.json)을 읽어 우리 형식으로 다시 씁니다. kakao-windows 는 고치지 않습니다.

무엇을 하나
  달마다 read --start/--end 를 한 번 불러서 그 달을 통째로 다시 씁니다(= 몇 번을 돌려도 같습니다).
  파일은 raw/카톡/{연-월}/{방이름}_{방번호뒤4자리}.md, 한 달 한 방이 한 파일입니다.
  (방 번호를 모르면 방 이름만 씁니다. 이름이 같은 방이 둘이면 덮어써지니 번호를 같이 적어 주세요.)
  본인이 보낸 줄은 [나] 로 적습니다. 방 목록 미리보기 줄과 빈 메시지는 넣지 않습니다.
  한 회차에 만드는 파일은 --max-files 개까지(기본 30). 오래된 달부터 채웁니다.

등록할 때 방 이름과 함께 방 번호(chat_id)를 적어 두면 방 이름이 바뀌어도 계속 잡힙니다.
카톡 계정 폴더가 여럿이면 --account 로 어느 계정인지 알려 주세요(accounts 결과의 값).

사용법
  python kakao_collect.py --wiki "<위키폴더>" --room "현장 단톡방" --room-id 1234567890 \
         --backfill-months 6
  python kakao_collect.py --wiki "<위키폴더>" --label "카톡:현장 단톡방"
  python kakao_collect.py --wiki "<위키폴더>" --all                 # 등록된 방 전부(예약 작업용)
  python kakao_collect.py --wiki "<위키폴더>" --all --dry-run       # 카톡을 부르지 않고 확인만

--skill-dir 를 안 주면 두 곳을 직접 찾습니다.
  %USERPROFILE%\\.claude\\skills\\kakao-windows  그리고  <지금 폴더>\\.claude\\skills\\kakao-windows

출력 JSON (stdout 한 줄)
  {"ok":true,"rooms":["현장 단톡방"],"months":["2026-09"],"files":1,"messages":128,
   "missing_rooms":[],"failed":[],"backlog_remaining":0,"first_run_done":true}
  messages 는 실제로 파일에 적힌 줄 수입니다. failed 는 못 읽고 건너뛴 달입니다
  --dry-run  {"ok":true,"dry_run":true,"skill_dir":"...","plan":{"2026-09":["카톡:..."]}}
  오류       {"ok":false,"error":{"code":"KAKAO_NOT_RUNNING","message":"..."}}

종료코드
  0 성공 · 2 사람이 손봐야 하는 문제(키 없음·스킬 못 찾음·일부 달 실패) · 3 예상 못 한 오류
  1 은 쓰지 않습니다. 한 달이 막혀도 나머지 달은 계속 돕니다.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _common as C  # noqa: E402


def out(obj, code=0):
    # 화면용 JSON 은 ASCII 로만 냅니다(Windows 콘솔에서 한글이 통째로 사라지는 일을 막습니다).
    print(json.dumps(obj, ensure_ascii=True))
    raise SystemExit(code)


def candidates() -> list:
    return [
        pathlib.Path.home() / ".claude" / "skills" / "kakao-windows",
        pathlib.Path.cwd() / ".claude" / "skills" / "kakao-windows",
    ]


def find_skill(given) -> pathlib.Path:
    for one in ([pathlib.Path(given).expanduser()] if given else candidates()):
        if (one / "tool" / "entrypoint.py").is_file():
            return one.resolve()
    raise FileNotFoundError("KAKAO_SKILL_NOT_FOUND")


def skill_python(skill: pathlib.Path) -> pathlib.Path:
    for rel in ("tool/.venv/Scripts/python.exe", "tool/.venv/bin/python"):
        path = skill / rel
        if path.is_file():
            return path
    raise FileNotFoundError("KAKAO_VENV_MISSING")


def call(skill: pathlib.Path, args: list, state_dir, account=None) -> dict:
    cmd = [str(skill_python(skill)), str(skill / "tool" / "entrypoint.py"), *args]
    if account:
        cmd += ["--account", str(account)]
    if state_dir:
        cmd += ["--state-dir", str(state_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=900)
    text = (proc.stdout or "").strip()
    start = text.find("{")
    if start < 0:
        raise RuntimeError("KAKAO_NO_JSON")
    data = json.loads(text[start:])
    if data.get("status") == "error":
        raise RuntimeError(json.dumps(data.get("error", {}), ensure_ascii=False))
    return data


def render(room: str, ym: str, msgs: list):
    """(파일 내용, 실제로 적힌 줄 수). 빈 메시지는 세지 않습니다."""
    body_lines = []
    for one in sorted(msgs, key=lambda x: (x.get("sent_at") or 0, str(x.get("log_id")))):
        text = " ".join(str(one.get("message") or "").split())
        if not text:
            continue
        who = "나" if one.get("direction") == "sent" else (one.get("sender") or "알 수 없음")
        stamp = datetime.datetime.fromtimestamp(one.get("sent_at") or 0).strftime("%m-%d %H:%M")
        body_lines.append(f"- **{stamp}** [{who}] {text}")
    head = [
        "---",
        f"방: {room}",
        f"달: {ym}",
        f"메시지: {len(body_lines)}",
        f"수집: {C.now_local().strftime('%Y-%m-%d %H:%M')}",
        "---", "",
    ]
    return "\n".join(head + body_lines) + "\n", len(body_lines)


def file_stem(src: dict) -> str:
    """방 이름만 쓰면 이름이 같은 방 둘이 한 파일로 덮어써집니다. 방 번호 뒤 4자리를 붙입니다."""
    name = C.safe_name(src["room"])
    room_id = str(src.get("room_id") or "").strip()
    return f"{name}_{room_id[-4:]}" if room_id else name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="카톡 수집 (kakao-windows 결과 옮기기)")
    parser.add_argument("--wiki", required=True, help="위키 폴더. wiki/ 와 raw/ 가 있는 곳")
    parser.add_argument("--label", help='소스 이름. 예 "카톡:현장 단톡방"')
    parser.add_argument("--all", action="store_true", help="등록된 방 전부 (예약 작업용)")
    parser.add_argument("--skill-dir", help="kakao-windows 폴더. 없으면 직접 찾습니다")
    parser.add_argument("--room", action="append", default=[],
                        help="모을 방 이름. 여러 번 쓸 수 있어요 (새 방 등록)")
    parser.add_argument("--room-id", action="append", default=[],
                        help="방 번호(chat_id). --room 과 같은 순서로 적어요. 이름이 바뀌어도 잡혀요")
    parser.add_argument("--account", help="카톡 계정 폴더가 여럿일 때. accounts 결과의 값")
    parser.add_argument("--kakao-state-dir", help="kakao-windows 상태 폴더가 기본값이 아닐 때만")
    parser.add_argument("--backfill-months", type=int, default=1, help="예전 것을 몇 달치까지")
    parser.add_argument("--max-files", type=int, default=30, help="한 회차에 만들 파일 수 상한")
    parser.add_argument("--dry-run", action="store_true",
                        help="카톡을 부르지 않고 인자와 상태 파일만 확인합니다")
    return parser


def make_plan(state: dict, targets: list, today: datetime.date) -> dict:
    plan = {}
    for label in targets:
        src = state["sources"].get(label)
        if not src:
            continue
        if not src.get("first_run_done"):
            months = C.months_between(src.get("backfill_cursor") or src["backfill_start"],
                                      today.strftime("%Y-%m"))
        else:
            base = src.get("last_epoch") or 0
            start_ym = C.ym_of(base - C.OVERLAP_SEC) if base else today.strftime("%Y-%m")
            months = C.months_between(start_ym, today.strftime("%Y-%m"))
        for ym in months:
            plan.setdefault(ym, []).append(label)
    return plan


def main() -> None:
    C.force_utf8()
    args = build_parser().parse_args()

    wiki = pathlib.Path(args.wiki).expanduser().resolve()
    if not (wiki / "wiki").is_dir():
        out({"ok": False, "error": {"code": "NO_WIKI",
                                    "message": "위키 폴더가 아니에요. wiki/ 가 있는 폴더를 알려 주세요."}}, 2)
    state = C.load_state(wiki)

    try:
        skill = find_skill(args.skill_dir)
    except FileNotFoundError as err:
        out({"ok": False, "error": {"code": str(err),
                                    "message": "수업에서 받은 카톡 스킬을 못 찾았어요."}}, 2)

    today = datetime.date.today()
    if args.room:
        if args.room_id and len(args.room_id) != len(args.room):
            out({"ok": False, "error": {"code": "ROOM_ID_MISMATCH",
                                        "message": "--room 과 --room-id 개수가 달라요."}}, 2)
        start_ym = C.shift_month(today.strftime("%Y-%m"), max(args.backfill_months - 1, 0))
        for idx, room in enumerate(args.room):
            room_id = args.room_id[idx] if idx < len(args.room_id) else None
            src = state["sources"].setdefault(f"카톡:{room}", {
                "kind": "kakao", "skill_dir": str(skill),
                "kakao_state_dir": args.kakao_state_dir, "room": room, "room_id": room_id,
                "account": args.account, "deterministic": True,
                "first_run_done": False, "backfill_start": start_ym, "backfill_cursor": start_ym,
                "backlog_remaining": max(args.backfill_months, 1), "last_epoch": 0,
                "last_run": None, "months": [], "collected": 0, "last_error": None})
            if room_id:  # 이미 등록된 방이어도 번호·계정은 최신으로
                src["room_id"] = room_id
            if args.account:
                src["account"] = args.account
        targets = [f"카톡:{room}" for room in args.room]
    elif args.all:
        targets = [k for k, v in state["sources"].items() if v.get("kind") == "kakao"]
        if not targets:  # 야간 수집 첫날. 할 일이 없는 것은 실패가 아니에요
            out({"ok": True, "rooms": [], "months": [], "files": 0, "messages": 0,
                 "missing_rooms": [], "failed": [], "note": "등록된 방이 없어요."})
    elif args.label:
        targets = [args.label]
    else:
        out({"ok": False, "error": {"code": "NO_TARGET",
                                    "message": "어느 방인지 알려 주세요(--room 또는 --label 또는 --all)."}}, 2)

    unknown = [label for label in targets if label not in state["sources"]]
    if unknown:
        out({"ok": False, "error": {"code": "UNKNOWN_SOURCE",
                                    "message": "등록되지 않은 방이에요: " + ", ".join(unknown)}}, 2)

    plan = make_plan(state, targets, today)

    if args.dry_run:
        out({"ok": True, "dry_run": True, "wiki": str(wiki), "skill_dir": str(skill),
             "state_file": str(C.state_path(wiki)),
             "rooms": [state["sources"][label]["room"] for label in targets],
             "room_ids": [state["sources"][label].get("room_id") for label in targets],
             "max_files": args.max_files,
             "plan": {ym: plan[ym] for ym in sorted(plan)}})

    files = total = 0
    missing_all = []
    failed = []
    done = []
    blocked = set()  # 한 번 막힌 방은 그 방의 커서를 더 올리지 않습니다(다음 회차에 다시 해요)
    for ym in sorted(plan):  # 오래된 달부터
        if files >= args.max_files:
            break
        first, nxt = C.month_bounds(ym)
        # 달 경계가 양끝 포함이라 다음 달 첫 순간을 빼야 같은 메시지가 두 달에 안 들어가요
        end_at = min(nxt - datetime.timedelta(seconds=1), C.now_local())
        if end_at <= first:
            continue
        touched = False
        for label in plan[ym]:  # 방마다 따로 부릅니다. 한 방이 막혀도 다른 방은 돕니다
            if files >= args.max_files:
                break
            src = state["sources"][label]
            tmp = pathlib.Path(tempfile.mkdtemp(prefix="inbox-kakao-"))
            shutil.rmtree(tmp, ignore_errors=True)  # read 는 없거나 빈 폴더를 원합니다
            call_args = ["read",
                         "--start", first.isoformat(timespec="seconds"),
                         "--end", end_at.isoformat(timespec="seconds"),
                         "--direction", "all",
                         "--room", str(src.get("room_id") or src["room"]),
                         "--out", str(tmp)]
            try:
                result = call(skill, call_args, src.get("kakao_state_dir"), src.get("account"))
                payload = json.loads(
                    pathlib.Path(result["files"]["json"]).read_text(encoding="utf-8"))
            except Exception as err:
                src["last_error"] = str(err)[:200]
                failed.append({"month": ym, "room": src["room"],
                               "code": "KAKAO_READ_FAILED", "message": str(err)[:200]})
                blocked.add(label)
                continue
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

            touched = True
            missing_all += [m.get("title") or m.get("room")
                            for m in payload.get("missing_rooms", [])]
            msgs = [one for one in payload.get("messages", [])
                    if one.get("source") == "chat_db"]  # 방 목록 미리보기 한 줄은 대화가 아닙니다
            if msgs:
                text, lines = render(src["room"], ym, msgs)
                rel = f"카톡/{ym}/{file_stem(src)}.md"
                C.write_text(wiki / "raw" / rel, text)
                # 예전 것을 받는 동안은 처음부터 "밀린 것"이에요
                C.record_files(state, [rel],
                               "realtime" if src.get("first_run_done") else "backfill")
                files += 1
                total += lines
                src["months"] = sorted(set(src.get("months", []) + [ym]))
                src["collected"] = src.get("collected", 0) + lines
                src["last_epoch"] = max(src.get("last_epoch") or 0,
                                        max(m.get("sent_at") or 0 for m in msgs))
            if not src.get("first_run_done") and label not in blocked:
                src["backfill_cursor"] = C.next_month(ym)  # 다음 회차는 그다음 달부터
            src["last_run"] = C.now_local().isoformat(timespec="seconds")
            if label not in blocked:
                src["last_error"] = None
        if touched:
            done.append(ym)

    for label in targets:
        src = state["sources"][label]
        if not src.get("first_run_done"):
            left = C.months_between(src.get("backfill_cursor") or src["backfill_start"],
                                    today.strftime("%Y-%m"))
            src["backlog_remaining"] = len(left)  # 커서가 "다음에 시작할 달"이에요
            if not left and label not in blocked:  # 막힌 달이 있으면 아직 끝난 게 아니에요
                src["first_run_done"] = True
                src["backfill_cursor"] = None
        if not src.get("last_epoch"):
            src["last_epoch"] = int(C.now_local().timestamp())
    C.save_state(wiki, state)
    out({"ok": not failed,
         "rooms": [state["sources"][label]["room"] for label in targets],
         "months": done, "files": files, "messages": total,
         "missing_rooms": sorted(set(x for x in missing_all if x)),
         "failed": failed,
         "backlog_remaining": max((state["sources"][label].get("backlog_remaining", 0)
                                   for label in targets), default=0),
         "first_run_done": all(state["sources"][label].get("first_run_done")
                               for label in targets)}, 0 if not failed else 2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as err:  # 예상 못 한 오류도 JSON 한 줄로 냅니다
        out({"ok": False, "error": {"code": "UNEXPECTED", "message": type(err).__name__}}, 3)
