#!/usr/bin/env python3
"""IMAP 메일 수집. 표준 라이브러리만 씁니다. 지메일·네이버·회사 메일이 같은 방법입니다.

무엇을 하나
  받은편지함(INBOX)만 읽기 전용으로 열어서(읽음 표시를 바꾸지 않습니다)
  메일 한 통을 raw/메일/{연-월}/{날짜}_{id8}_{제목}.md 한 파일로 저장합니다.
  광고·알림은 버리지 않고 raw/메일/_걸러짐/{연-월}/ 로 보냅니다.
  같은 이름의 파일이 이미 있으면 건너뜁니다. 몇 번을 돌려도 결과가 같습니다.

두 트랙
  실시간 : 마지막으로 본 시각에서 1시간을 뺀 날부터 (IMAP 검색이 날짜 단위라 하루치를 다시 봅니다)
           여기서 받은 파일만 상태 파일의 realtime_files 에 적습니다(= "새로 온 것")
  과거   : backfill_cursor 부터 오래된 달 순으로, 한 회차에 --max-months 개월까지
           커서는 이번에 끝낸 마지막 달의 "다음 달" 로 올라갑니다(= 회차마다 --max-months 개월씩)

걸러낼 도메인
  <위키폴더>/.inbox/걸러낼도메인.txt 가 있으면 읽어서 상태 파일의 mail_filter_domains 에 합칩니다.

사용법
  python mail_fetch.py --wiki "C:/Users/나/Documents/내위키" \\
         --host imap.naver.com --user me@example.com --backfill-months 6   # 새 소스 등록 + 첫 수집
  python mail_fetch.py --wiki "<위키폴더>" --label "메일:me@example.com"    # 한 소스만
  python mail_fetch.py --wiki "<위키폴더>" --all                            # 등록된 메일 소스 전부(예약 작업용)
  python mail_fetch.py --wiki "<위키폴더>" --all --dry-run                  # 접속 없이 인자·상태 파일만 확인

비밀번호는 인자로 받지 않습니다. secret_store.py 에 저장된 값을 씁니다.

출력 JSON (stdout 한 줄)
  {"ok":true,"results":[{"label":"메일:me@example.com","ok":true,"mode":"imap",
   "new":12,"filtered":31,"skipped_existing":40,"dropped":0,"truncated":[],
   "months_done":["2026-06"],
   "backlog_remaining":2,"first_run_done":false,"last_epoch":1758283861}]}
  dropped   날짜를 못 읽어 건너뛴 메일 수. truncated 는 한 구간 상한(--max)에 걸린 구간
  --dry-run  {"ok":true,"dry_run":true,"results":[{"label":"...","windows":[...],"secret_found":true}]}
  오류       {"ok":false,"error":{"code":"NO_WIKI","message":"..."}}

종료코드
  0 전부 성공 · 2 사람이 손봐야 하는 문제(설정·인증·일부 실패 포함) · 3 예상 못 한 오류
  1 은 쓰지 않습니다. 예약 작업 로그에서 1과 2를 구분해 볼 사람이 없기 때문입니다.
"""
from __future__ import annotations

import argparse
import datetime
import email
import email.policy
import email.utils
import hashlib
import html
import imaplib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import secret_store  # noqa: E402

MAXCHARS = 20000
NOREPLY = re.compile(
    r"no[-_.]?reply|donotreply|do[-_.]?not[-_.]?reply|newsletter|"
    r"notifications?@|mailer-daemon|bounce", re.I)
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def out(obj, code=0):
    # 화면용 JSON 은 ASCII 로만 냅니다(Windows 콘솔에서 한글이 통째로 사라지는 일을 막습니다).
    print(json.dumps(obj, ensure_ascii=True))
    raise SystemExit(code)


def load_domain_file(wiki: pathlib.Path, state: dict) -> None:
    """<위키폴더>/.inbox/걸러낼도메인.txt 를 읽어 상태 파일에 합칩니다. 없으면 그냥 넘어갑니다."""
    path = wiki / ".inbox" / "걸러낼도메인.txt"
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    found = [x.strip().lower() for x in lines if x.strip() and not x.strip().startswith("#")]
    merged = list(dict.fromkeys([*state.get("mail_filter_domains", []), *found]))
    state["mail_filter_domains"] = merged


def imap_date(day: datetime.date) -> str:
    return f"{day.day:02d}-{MON[day.month - 1]}-{day.year}"


def to_text(msg) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        part = None
    if part is None:
        return ""
    try:
        body = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        body = payload.decode(part.get_content_charset() or "utf-8", "replace")
    if part.get_content_type() == "text/html":
        body = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
        body = html.unescape(re.sub(r"<[^>]+>", " ", body))
        body = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", body))
    return body.strip()


def slug(text: str, limit: int = 40) -> str:
    cleaned = re.sub(r"\s+", " ", C.safe_name(text or "", "무제")).strip()
    return cleaned[:limit] or "무제"


def is_bulk(msg, sender: str, domains: list) -> bool:
    if msg.get("List-Unsubscribe"):
        return True
    if "bulk" in (msg.get("Precedence") or "").lower():
        return True
    if NOREPLY.search(sender or ""):
        return True
    addr = email.utils.parseaddr(sender or "")[1].lower()
    return any(addr.endswith(d.strip().lower()) for d in domains if d and d.strip())


def plan_windows(src: dict, max_months: int, today: datetime.date) -> list:
    """이번 회차에 볼 구간 목록. (시작일, 끝일 또는 None, 이름)"""
    windows = []
    if not src.get("first_run_done"):
        todo = C.months_between(src.get("backfill_cursor") or src["backfill_start"],
                                today.strftime("%Y-%m"))
        for ym in todo[:max_months]:
            first, nxt = C.month_bounds(ym)
            windows.append((first.date(), nxt.date(), ym))
    else:
        base = src.get("last_epoch") or 0
        if base:
            start = datetime.date.fromtimestamp(max(base - C.OVERLAP_SEC, 0))
        else:
            start = today - datetime.timedelta(days=1)
        windows.append((start, None, "실시간"))
    return windows


def search_ids(box, since: datetime.date, before, limit: int):
    """(이번에 볼 메일 번호들, 서버에 있던 전체 수)"""
    query = ["SINCE", imap_date(since)]
    if before:
        query += ["BEFORE", imap_date(before)]
    typ, data = box.search(None, *query)
    if typ != "OK":
        raise RuntimeError("SEARCH_FAILED")
    ids = (data[0] or b"").split()
    if limit and len(ids) > limit:
        return ids[-limit:], len(ids)
    return ids, len(ids)


def internal_date(head):
    """Date 헤더가 없거나 깨졌을 때 서버가 준 도착 시각(INTERNALDATE)으로 대신합니다."""
    try:
        stamp = imaplib.Internaldate2tuple(head if isinstance(head, bytes) else str(head).encode())
        if not stamp:
            return None
        import time
        return datetime.datetime.fromtimestamp(time.mktime(stamp)).astimezone()
    except Exception:
        return None


def run_source(wiki: pathlib.Path, state: dict, label: str, args) -> dict:
    src = state["sources"][label]
    password = secret_store.fetch(src["secret_label"])
    if not password:
        return {"label": label, "ok": False,
                "error": {"code": "NO_SECRET", "message": "앱 비밀번호가 저장돼 있지 않아요."}}
    try:
        box = imaplib.IMAP4_SSL(src["host"], src.get("port", 993))
        box.login(src["user"], password)
        box.select("INBOX", readonly=True)  # 읽음 표시를 바꾸지 않습니다
    except imaplib.IMAP4.error as err:
        return {"label": label, "ok": False,
                "error": {"code": "LOGIN_FAILED", "message": str(err)[:200]}}
    except OSError as err:
        return {"label": label, "ok": False,
                "error": {"code": "CONNECT_FAILED", "message": str(err)[:200]}}
    finally:
        password = None

    domains = state.get("mail_filter_domains", [])
    today = datetime.date.today()
    made = filtered = skipped = dropped = 0
    truncated = []
    months_done = []
    newest = src.get("last_epoch") or 0

    for since, before, tag in plan_windows(src, args.max_months, today):
        try:
            ids, seen = search_ids(box, since, before, args.max)
        except Exception as err:
            months_done.append({"month": tag, "error": str(err)[:120]})
            continue
        if seen > len(ids):  # 상한에 걸려 오래된 쪽이 잘렸습니다. 조용히 버리지 않고 적습니다
            truncated.append({"window": tag, "seen": seen, "taken": len(ids)})
        for num in ids:
            typ, payload = box.fetch(num, "(INTERNALDATE BODY.PEEK[])")  # PEEK = 읽음 표시 안 바꿈
            if typ != "OK" or not payload or not isinstance(payload[0], tuple):
                continue
            raw = payload[0][1]
            try:
                msg = email.message_from_bytes(raw, policy=email.policy.default)
            except Exception:
                continue
            sender = str(msg.get("From") or "")
            subject = str(msg.get("Subject") or "(제목 없음)")
            try:
                when = email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
            except (TypeError, ValueError):
                when = None
            if when is None:  # 날짜 헤더가 없거나 깨진 메일은 서버 도착 시각으로 대신합니다
                when = internal_date(payload[0][0])
            if when is None:
                dropped += 1
                continue
            if when.tzinfo is None:
                when = when.astimezone()
            newest = max(newest, int(when.timestamp()))
            mid = msg.get("Message-ID") or f"{sender}|{subject}|{when.isoformat()}"
            id8 = hashlib.sha1(str(mid).strip().encode("utf-8", "replace")).hexdigest()[:8]
            body = to_text(msg)
            names = [p.get_filename() for p in msg.walk() if p.get_filename()] \
                if msg.is_multipart() else []
            # 짧다고 광고로 보지 않습니다. "네, 그 금액으로 진행할게요" 같은 확정 회신이 걸립니다
            bulk = is_bulk(msg, sender, domains) or len(body) < 5
            ym = when.strftime("%Y-%m")
            base = wiki / "raw" / "메일"
            folder = (base / "_걸러짐" / ym) if bulk else (base / ym)
            path = folder / f"{when.strftime('%Y-%m-%d')}_{id8}_{slug(subject)}.md"
            if path.exists():
                skipped += 1
                continue
            head = "\n".join([
                "---",
                f"메일id: {id8}",
                f"날짜: {when.isoformat(timespec='seconds')}",
                f"보낸사람: {json.dumps(sender, ensure_ascii=False)}",
                f"받는사람: {json.dumps(str(msg.get('To') or ''), ensure_ascii=False)}",
                f"제목: {json.dumps(subject, ensure_ascii=False)}",
                f"첨부: {json.dumps([n for n in names if n], ensure_ascii=False)}",
                "---", "",
            ])
            C.write_text(path, head + body[:MAXCHARS] + "\n")
            if bulk:
                filtered += 1
            else:
                made += 1
                rel = str(path.relative_to(wiki / "raw")).replace("\\", "/")
                # 실시간 트랙이 가져온 것만 "새로 온 것"이에요. 과거분은 처음부터 밀린 것입니다
                C.record_files(state, [rel], "realtime" if tag == "실시간" else "backfill")
        if tag != "실시간":
            months_done.append(tag)
            src["backfill_cursor"] = C.next_month(tag)  # 다음 회차는 그다음 달부터

    try:
        box.logout()
    except Exception:
        pass

    if not src.get("first_run_done"):
        left = C.months_between(src.get("backfill_cursor") or src["backfill_start"],
                                today.strftime("%Y-%m"))
        src["backlog_remaining"] = len(left)  # 커서가 "다음에 시작할 달"이라 그대로 남은 달 수예요
        if not left:
            src["first_run_done"] = True
            src["backfill_cursor"] = None
    src["last_epoch"] = max(newest, src.get("last_epoch") or 0)
    src["last_run"] = C.now_local().isoformat(timespec="seconds")
    src["collected"] = src.get("collected", 0) + made
    src["filtered"] = src.get("filtered", 0) + filtered
    src["last_error"] = None
    return {"label": label, "ok": True, "mode": "imap", "new": made, "filtered": filtered,
            "skipped_existing": skipped, "dropped": dropped, "truncated": truncated,
            "months_done": months_done,
            "backlog_remaining": src.get("backlog_remaining", 0),
            "first_run_done": src.get("first_run_done", False),
            "last_epoch": src["last_epoch"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IMAP 메일 수집 (받은편지함만, 읽음 표시 안 바꿈)")
    parser.add_argument("--wiki", required=True, help="위키 폴더. wiki/ 와 raw/ 가 있는 곳")
    parser.add_argument("--label", help='소스 이름. 예 "메일:me@example.com"')
    parser.add_argument("--all", action="store_true", help="등록된 메일 소스 전부 (예약 작업용)")
    parser.add_argument("--host", help="IMAP 주소. 예 imap.naver.com (새 소스 등록)")
    parser.add_argument("--port", type=int, default=993, help="기본 993")
    parser.add_argument("--user", help="메일 주소 (새 소스 등록)")
    parser.add_argument("--backfill-months", type=int, default=1, help="예전 것을 몇 달치까지")
    parser.add_argument("--max", type=int, default=400, help="한 구간에서 볼 메일 수 상한")
    parser.add_argument("--max-months", type=int, default=3, help="한 회차에 받을 과거 달 수")
    parser.add_argument("--dry-run", action="store_true",
                        help="접속하지 않고 인자와 상태 파일만 확인합니다")
    return parser


def register(state: dict, args) -> str:
    """이미 등록된 메일이면 접속 정보만 고치고 진행 상태는 그대로 둡니다.

    같은 명령을 한 번 더 쳐도 과거 트랙이 처음으로 되돌아가지 않게 하려는 것입니다.
    """
    label = f"메일:{args.user}"
    today = datetime.date.today()
    start_ym = C.shift_month(today.strftime("%Y-%m"), max(args.backfill_months - 1, 0))
    old = state["sources"].get(label)
    if old and old.get("kind") == "mail":
        old.update({"host": args.host, "port": args.port, "user": args.user,
                    "secret_label": f"mail:{args.user}", "mode": "imap", "deterministic": True})
        return label
    state["sources"][label] = {
        "kind": "mail", "mode": "imap", "host": args.host, "port": args.port, "user": args.user,
        "secret_label": f"mail:{args.user}", "deterministic": True, "first_run_done": False,
        "backfill_start": start_ym, "backfill_cursor": start_ym,
        "backlog_remaining": max(args.backfill_months, 1), "last_epoch": 0, "last_run": None,
        "collected": 0, "filtered": 0, "last_error": None,
    }
    return label


def main() -> None:
    C.force_utf8()
    args = build_parser().parse_args()

    wiki = pathlib.Path(args.wiki).expanduser().resolve()
    if not (wiki / "wiki").is_dir():
        out({"ok": False, "error": {"code": "NO_WIKI",
                                    "message": "위키 폴더가 아니에요. wiki/ 가 있는 폴더를 알려 주세요."}}, 2)
    state = C.load_state(wiki)
    load_domain_file(wiki, state)

    if args.host and args.user:
        if args.dry_run:
            targets = [f"메일:{args.user}"]
        else:
            targets = [register(state, args)]
    elif args.all:
        targets = [k for k, v in state["sources"].items() if v.get("kind") == "mail"]
        if not targets:  # 야간 수집 첫날. 할 일이 없는 것은 실패가 아니에요
            out({"ok": True, "results": [], "note": "등록된 메일이 없어요."})
    elif args.label:
        targets = [args.label]
    else:
        out({"ok": False, "error": {"code": "NO_TARGET",
                                    "message": "어느 메일인지 알려 주세요(--label 또는 --all 또는 --host와 --user)."}}, 2)

    if args.dry_run:
        today = datetime.date.today()
        plans = []
        for label in targets:
            src = state["sources"].get(label)
            if src is None:
                if args.host and args.user:
                    plans.append({"label": label, "registered": False, "would_register": True,
                                  "host": args.host, "port": args.port,
                                  "backfill_months": args.backfill_months})
                else:
                    plans.append({"label": label, "registered": False,
                                  "error": {"code": "UNKNOWN_SOURCE", "message": "등록되지 않았어요."}})
                continue
            windows = [{"since": s.isoformat(), "before": b.isoformat() if b else None, "tag": t}
                       for s, b, t in plan_windows(src, args.max_months, today)]
            plans.append({"label": label, "registered": True, "host": src.get("host"),
                          "first_run_done": src.get("first_run_done"),
                          "backfill_cursor": src.get("backfill_cursor"),
                          "windows": windows,
                          "secret_found": secret_store.fetch(src["secret_label"]) is not None})
        out({"ok": True, "dry_run": True, "wiki": str(wiki),
             "state_file": str(C.state_path(wiki)), "results": plans})

    results = []
    for label in targets:
        if label not in state["sources"]:
            results.append({"label": label, "ok": False,
                            "error": {"code": "UNKNOWN_SOURCE", "message": "등록되지 않았어요."}})
            continue
        try:
            results.append(run_source(wiki, state, label, args))
        except Exception as err:  # 한 소스가 죽어도 나머지는 돕니다
            state["sources"][label]["last_error"] = type(err).__name__
            results.append({"label": label, "ok": False,
                            "error": {"code": "UNEXPECTED", "message": type(err).__name__}})
    C.save_state(wiki, state)
    ok = bool(results) and all(r.get("ok") for r in results)
    out({"ok": ok, "results": results}, 0 if ok else 2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as err:  # 예상 못 한 오류도 JSON 한 줄로 냅니다
        out({"ok": False, "error": {"code": "UNEXPECTED", "message": type(err).__name__}}, 3)
