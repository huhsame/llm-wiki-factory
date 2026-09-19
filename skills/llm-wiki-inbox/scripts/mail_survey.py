#!/usr/bin/env python3
"""메일함 둘러보기. 받은편지함의 **머리만** 세어 봅니다. 표준 라이브러리만 씁니다.

무엇을 하나
  최근 몇 달치 받은편지함에서 보낸사람·날짜·제목 헤더만 읽어(본문은 한 바이트도 안 받습니다)
  100건씩 묶어서 한 번에 받습니다(왕복 수를 100분의 1로 줄입니다).
  자주 나온 사람 · 자주 나온 도메인 · 자주 나온 제목 낱말을 세어 JSON 한 줄로 냅니다.
  보낸편지함을 열 수 있으면 "이 사람에게 답장한 적이 있나"까지 같이 봅니다.

무엇을 안 하나
  파일을 하나도 쓰지 않습니다. 창고(raw/)도 상태 파일(raw/_수집상태.json)도 건드리지 않습니다.
  상태 파일은 접속 정보를 읽을 때만 열고, 저장은 절대 하지 않습니다.
  본문·메일 주소 전체를 출력에 담지 않습니다. 표시 이름과 도메인과 횟수만 냅니다.
  읽음 표시를 바꾸지 않습니다(readonly 로 열고 BODY.PEEK 으로 읽습니다).

사용법
  python mail_survey.py --wiki "<위키폴더>" --label "메일:me@example.com" --months 3
  python mail_survey.py --wiki "<위키폴더>" --host imap.naver.com --user me@example.com --months 3
  python mail_survey.py --wiki "<위키폴더>" --label "메일:me@example.com" --dry-run

인자
  --wiki           위키 폴더. 접속 정보를 raw/_수집상태.json 에서 읽을 때만 씁니다
  --label          등록된 소스 이름. 예 "메일:me@example.com"
  --host / --user  아직 등록 전 계정을 그대로 둘러볼 때 (--label 대신)
  --port           기본 993
  --months         몇 개월치 머리를 볼지. 기본 3
  --max-per-month  한 달 상한. 기본 400 (mail_fetch.py --max 와 같은 수)
  --sent           보낸편지함 이름. 안 주면 흔한 이름을 차례로 열어 봅니다
  --top            사람·도메인·낱말 각각 상위 몇 개를 낼지. 기본 15
  --dry-run        접속하지 않고 인자·비밀번호 존재·기간만 확인합니다

출력 JSON (stdout 한 줄)
  {"ok":true,"survey":"mail","user_domain":"naver.com","sent_box":"Sent Messages",
   "window":{"since":"2026-07-01","until":"2026-09-19","months":3},
   "seen":412,"bulk":97,"truncated":[],
   "senders":[{"name":"김선영","domain":"hanisol.co.kr","count":38,"last":"2026-09-18",
               "replied":true,"bulk":0}],
   "domains":[{"domain":"ad.example.com","count":54,"last":"2026-09-17",
               "replied":false,"bulk":54}],
   "words":[{"word":"견적","count":31}],
   "months":[{"ym":"2026-07","count":120,"truncated":false}],
   "already_filtered":["ad.example.com"]}
  already_filtered 는 이미 거르기로 정해 둔 도메인이에요. 후보 표에서 기계적으로 빼는 데 씁니다.
  sent_box 가 null 이면 보낸편지함을 못 연 거예요. 그때는 모든 replied 가 null 입니다.
  --dry-run  {"ok":true,"dry_run":true,"label":"...","window":{...},"secret_found":true,
              "sent_box_candidates":[...]}
  오류       {"ok":false,"error":{"code":"NO_SECRET","message":"..."}}
             코드는 NO_WIKI · UNKNOWN_SOURCE · NO_SECRET · AUTH_FAILED · IMAP_FAILED 다섯입니다

종료코드
  0 성공 · 2 사람이 손봐야 하는 문제(설정·인증·접속) · 3 예상 못 한 오류
  1 은 쓰지 않습니다. mail_fetch.py 와 같은 규약입니다.
"""
from __future__ import annotations

import argparse
import datetime
import email
import email.policy
import email.utils
import hashlib
import imaplib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import mail_fetch  # noqa: E402  (is_bulk 를 그대로 씁니다. 판정이 어긋나면 안 돼요)
import secret_store  # noqa: E402

HEADERS = "(BODY.PEEK[HEADER.FIELDS (FROM DATE SUBJECT LIST-UNSUBSCRIBE PRECEDENCE)])"
SENT_HEADERS = "(BODY.PEEK[HEADER.FIELDS (TO CC DATE)])"
SENT_BOXES = ["Sent", "Sent Messages", "Sent Items", "[Gmail]/&vtgs4Vrs-",
              "INBOX.Sent", "Sent Mail", "보낸편지함"]
SPLIT = re.compile(r"[\s\[\]()<>\-_.,:;/|\"'!?~*+=#%&@\\]+")
ADDRLIKE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
CHUNK = 100  # 한 번에 머리를 받아올 메일 수
STOP = {"re", "fw", "fwd", "전달", "답장", "회신", "광고", "웹발신", "자동", "알림",
        "뉴스레터", "수신거부", "님", "귀하", "메일", "안내메일", "no", "reply",
        "noreply", "the", "and", "for", "your", "you"}


def out(obj, code=0):
    # 화면용 JSON 은 ASCII 로만 냅니다(Windows 콘솔에서 한글이 통째로 사라지는 일을 막습니다).
    print(json.dumps(obj, ensure_ascii=True))
    raise SystemExit(code)


def key_of(addr: str) -> str:
    """집계용 열쇠. 주소 자체는 이 함수 밖으로 나가지 않습니다."""
    return hashlib.sha1((addr or "").strip().lower().encode("utf-8", "replace")).hexdigest()[:10]


def domain_of(addr: str) -> str:
    return (addr or "").rsplit("@", 1)[-1].strip().lower() if "@" in (addr or "") else ""


def clean_name(name: str) -> str:
    """표시 이름에서 메일 주소 토큰을 지웁니다.

    한국 그룹웨어·일부 웹메일은 표시 이름에 주소를 그대로 박아 보냅니다
    ('"홍길동(hong@a.co.kr)" <hong@a.co.kr>'). 손질하지 않으면 제3자 주소가
    후보 표와 씨앗 파일에 그대로 남습니다. 지우고 나서 빈 문자열이면 표에서
    '(이름 없음)' 으로 나갑니다.
    """
    text = ADDRLIKE.sub("", C.nfc(name or ""))
    text = re.sub(r"[(\[<{]\s*[)\]>}]", "", text)   # 주소를 뺀 뒤 남은 빈 괄호
    return " ".join(text.split()).strip(" \u00b7,-")


def words_of(subject: str) -> list:
    picked = []
    for token in SPLIT.split(ADDRLIKE.sub(" ", C.nfc(subject or ""))):
        low = token.lower()
        if len(token) < 2 or low in STOP or token.isdigit():
            continue
        picked.append(token)
    return picked


def month_window(months: int, today: datetime.date):
    """(첫날, 오늘, 달 목록). 이번 달을 포함해 months 개월입니다."""
    start_ym = C.shift_month(today.strftime("%Y-%m"), max(months - 1, 0))
    ym_list = C.months_between(start_ym, today.strftime("%Y-%m"))
    first, _ = C.month_bounds(ym_list[0])
    return first.date(), today, ym_list


def header_bytes(payload) -> bytes:
    for part in payload or []:
        if isinstance(part, tuple) and len(part) > 1 and part[1]:
            return part[1]
    return b""


def header_chunks(payload) -> list:
    """묶음 응답에서 머리 바이트를 순서대로 모읍니다."""
    found = []
    for part in payload or []:
        if isinstance(part, tuple) and len(part) > 1 and part[1]:
            found.append(part[1])
    return found


def fetch_headers(box, ids, spec):
    """id 를 CHUNK 개씩 묶어 한 번에 받아옵니다.

    한 건씩 받으면 1,200 통짜리 메일함에서 왕복이 1,200 번이라 느린 서버에서 몇 분이
    걸립니다. 묶음이 통째로 실패하는 서버가 있어서, 그때만 그 묶음을 한 건씩 다시 받습니다.
    """
    for start in range(0, len(ids), CHUNK):
        group = ids[start:start + CHUNK]
        try:
            typ, payload = box.fetch(b",".join(group), spec)
        except Exception:
            typ, payload = "NO", None
        if typ == "OK":
            got = header_chunks(payload)
            if len(got) >= len(group):
                for raw in got:
                    yield raw
                continue
        for num in group:
            try:
                typ, payload = box.fetch(num, spec)
            except Exception:
                continue
            if typ != "OK":
                continue
            raw = header_bytes(payload)
            if raw:
                yield raw


def parse_when(msg, ym: str):
    try:
        when = email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
    except (TypeError, ValueError):
        when = None
    if when is None:
        first, _ = C.month_bounds(ym)
        return first
    if when.tzinfo is None:
        when = when.astimezone()
    return when


def search_month(box, ym: str, today: datetime.date, limit: int):
    first, nxt = C.month_bounds(ym)
    since = first.date()
    before = min(nxt.date(), today + datetime.timedelta(days=1))
    typ, data = box.search(None, "SINCE", mail_fetch.imap_date(since),
                           "BEFORE", mail_fetch.imap_date(before))
    if typ != "OK":
        raise RuntimeError("SEARCH_FAILED")
    ids = (data[0] or b"").split()
    if limit and len(ids) > limit:
        return ids[-limit:], len(ids)
    return ids, len(ids)


def read_sent(box, name: str, since: datetime.date, limit: int):
    """보낸편지함에서 받는사람의 집계 열쇠와 도메인만 모읍니다. 주소는 안 남깁니다."""
    typ, _ = box.select(name, readonly=True)
    if typ != "OK":
        return None
    typ, data = box.search(None, "SINCE", mail_fetch.imap_date(since))
    if typ != "OK":
        return None
    ids = (data[0] or b"").split()
    if limit and len(ids) > limit:
        ids = ids[-limit:]
    keys, domains = set(), set()
    for raw in fetch_headers(box, ids, SENT_HEADERS):
        try:
            msg = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception:
            continue
        people = email.utils.getaddresses(
            [str(msg.get("To") or ""), str(msg.get("Cc") or "")])
        for _name, addr in people:
            if not addr:
                continue
            keys.add(key_of(addr))
            if domain_of(addr):
                domains.add(domain_of(addr))
    return {"keys": keys, "domains": domains}


def survey(src: dict, args) -> dict:
    password = secret_store.fetch(src["secret_label"])
    if not password:
        out({"ok": False, "error": {"code": "NO_SECRET",
                                    "message": "앱 비밀번호가 저장돼 있지 않아요."}}, 2)
    today = datetime.date.today()
    since, until, ym_list = month_window(args.months, today)
    try:
        box = imaplib.IMAP4_SSL(src["host"], src.get("port", 993))
        box.login(src["user"], password)
    except imaplib.IMAP4.error as err:
        out({"ok": False, "error": {"code": "AUTH_FAILED", "message": str(err)[:200]}}, 2)
    except OSError as err:
        out({"ok": False, "error": {"code": "IMAP_FAILED", "message": str(err)[:200]}}, 2)
    finally:
        password = None

    # 보낸편지함을 먼저 봅니다. 받은편지함을 열어 둔 채 다른 함을 select 하면 창이 바뀌어요.
    sent = None
    sent_box = None
    for name in ([args.sent] if args.sent else SENT_BOXES):
        try:
            found = read_sent(box, name, since, args.max_per_month * max(args.months, 1))
        except Exception:
            found = None
        if found is not None:
            sent, sent_box = found, name
            break

    try:
        typ, _ = box.select("INBOX", readonly=True)  # 읽음 표시를 바꾸지 않습니다
        if typ != "OK":
            raise RuntimeError("INBOX_SELECT_FAILED")
    except Exception as err:
        out({"ok": False, "error": {"code": "IMAP_FAILED", "message": str(err)[:200]}}, 2)

    # 일부러 빈 목록입니다. 이미 거르기로 정한 도메인을 여기 넣으면 그 도메인이
    # 다시 '거를 후보' 조건(bulk == count)을 만족해 후보 표에 또 올라옵니다.
    # 이미 고른 것은 출력의 already_filtered 로 알려 주고 표에서 빼게 합니다.
    domains_filter = []
    senders, domains, words = {}, {}, {}
    months, truncated = [], []
    seen = bulk_total = 0

    for ym in ym_list:
        try:
            ids, total = search_month(box, ym, today, args.max_per_month)
        except Exception as err:
            months.append({"ym": ym, "count": 0, "truncated": False, "error": str(err)[:80]})
            continue
        if total > len(ids):
            truncated.append({"ym": ym, "seen": total, "taken": len(ids)})
        months.append({"ym": ym, "count": len(ids), "truncated": total > len(ids)})
        for raw in fetch_headers(box, ids, HEADERS):  # PEEK = 읽음 표시 안 바꿈
            try:
                msg = email.message_from_bytes(raw, policy=email.policy.default)
            except Exception:
                continue
            sender = str(msg.get("From") or "")
            name, addr = email.utils.parseaddr(sender)
            name = clean_name(name)  # 표시 이름에 박힌 주소를 여기서 지웁니다
            if not addr:
                continue
            seen += 1
            is_bulk = bool(mail_fetch.is_bulk(msg, sender, domains_filter))
            bulk_total += 1 if is_bulk else 0
            when = parse_when(msg, ym)
            day = when.strftime("%Y-%m-%d")
            key, dom = key_of(addr), domain_of(addr)
            row = senders.setdefault(key, {"name": name, "domain": dom,
                                           "count": 0, "last": day, "bulk": 0, "_key": key})
            if not row["name"] and name:
                row["name"] = name
            row["count"] += 1
            row["bulk"] += 1 if is_bulk else 0
            row["last"] = max(row["last"], day)
            if dom:
                drow = domains.setdefault(dom, {"domain": dom, "count": 0, "last": day,
                                                "bulk": 0, "_keys": set()})
                drow["count"] += 1
                drow["bulk"] += 1 if is_bulk else 0
                drow["last"] = max(drow["last"], day)
                drow["_keys"].add(key)
            if not is_bulk:  # 광고 제목이 낱말 순위를 덮지 않게 합니다
                for word in words_of(str(msg.get("Subject") or "")):
                    words[word] = words.get(word, 0) + 1

    try:
        box.logout()
    except Exception:
        pass

    def replied_key(key):
        return None if sent is None else (key in sent["keys"])

    sender_rows = []
    for row in sorted(senders.values(), key=lambda x: (-x["count"], x["domain"], x["name"])):
        sender_rows.append({"name": row["name"] or "", "domain": row["domain"],
                            "count": row["count"], "last": row["last"],
                            "replied": replied_key(row["_key"]), "bulk": row["bulk"]})
    domain_rows = []
    for row in sorted(domains.values(), key=lambda x: (-x["count"], x["domain"])):
        replied = None if sent is None else (row["domain"] in sent["domains"])
        domain_rows.append({"domain": row["domain"], "count": row["count"],
                            "last": row["last"], "replied": replied, "bulk": row["bulk"]})
    word_rows = [{"word": w, "count": c}
                 for w, c in sorted(words.items(), key=lambda x: (-x[1], x[0]))]

    return {"ok": True, "survey": "mail", "user_domain": domain_of(src.get("user", "")),
            "sent_box": sent_box,
            "window": {"since": since.isoformat(), "until": until.isoformat(),
                       "months": args.months},
            "seen": seen, "bulk": bulk_total, "truncated": truncated,
            "senders": sender_rows[:args.top], "domains": domain_rows[:args.top],
            "words": word_rows[:args.top], "months": months}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="메일함 둘러보기 (머리만 셉니다. 본문·파일 쓰기 없음)")
    parser.add_argument("--wiki", required=True, help="위키 폴더. wiki/ 가 있는 곳")
    parser.add_argument("--label", help='등록된 소스 이름. 예 "메일:me@example.com"')
    parser.add_argument("--host", help="IMAP 주소. 아직 등록 전 계정을 볼 때")
    parser.add_argument("--port", type=int, default=993, help="기본 993")
    parser.add_argument("--user", help="메일 주소. 아직 등록 전 계정을 볼 때")
    parser.add_argument("--months", type=int, default=3, help="몇 개월치 머리를 볼지")
    parser.add_argument("--max-per-month", type=int, default=400, help="한 달 상한")
    parser.add_argument("--sent", help="보낸편지함 이름. 안 주면 흔한 이름을 차례로 열어 봐요")
    parser.add_argument("--top", type=int, default=15, help="상위 몇 개씩 낼지")
    parser.add_argument("--dry-run", action="store_true",
                        help="접속하지 않고 인자와 비밀번호 존재만 확인합니다")
    return parser


def main() -> None:
    C.force_utf8()
    args = build_parser().parse_args()

    wiki = pathlib.Path(args.wiki).expanduser().resolve()
    if not (wiki / "wiki").is_dir():
        out({"ok": False, "error": {"code": "NO_WIKI",
                                    "message": "위키 폴더가 아니에요. wiki/ 가 있는 폴더를 알려 주세요."}}, 2)
    state = C.load_state(wiki)  # 읽기만 합니다. 저장하지 않아요

    if args.host and args.user:
        label = f"메일:{args.user}"
        src = {"host": args.host, "port": args.port, "user": args.user,
               "secret_label": f"mail:{args.user}"}
    elif args.label:
        label = args.label
        src = state.get("sources", {}).get(label)
        if not src or src.get("kind") != "mail":
            out({"ok": False, "error": {"code": "UNKNOWN_SOURCE",
                                        "message": "등록되지 않은 메일이에요."}}, 2)
    else:
        out({"ok": False, "error": {"code": "UNKNOWN_SOURCE",
                                    "message": "어느 메일인지 알려 주세요(--label 또는 --host와 --user)."}}, 2)

    today = datetime.date.today()
    since, until, _ym = month_window(args.months, today)
    if args.dry_run:
        out({"ok": True, "dry_run": True, "label": label, "host": src.get("host"),
             "window": {"since": since.isoformat(), "until": until.isoformat(),
                        "months": args.months},
             "secret_found": secret_store.fetch(src["secret_label"]) is not None,
             "sent_box_candidates": [args.sent] if args.sent else SENT_BOXES,
             "state_file": str(C.state_path(wiki)), "writes": []})

    result = survey(src, args)
    result["already_filtered"] = list(state.get("mail_filter_domains", []) or [])
    out(result)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as err:  # 예상 못 한 오류도 JSON 한 줄로 냅니다
        out({"ok": False, "error": {"code": "UNEXPECTED", "message": type(err).__name__}}, 3)
