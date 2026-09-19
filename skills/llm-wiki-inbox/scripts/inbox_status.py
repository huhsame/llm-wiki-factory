#!/usr/bin/env python3
"""두 트랙 현황을 셉니다. 창고(raw/)와 장부(wiki/장부.md)를 NFC 로 맞춰 견줍니다.

세는 것
  raw_files      raw/ 안 파일 수. 이름이 _ 로 시작하는 파일과 폴더는 빼고 셉니다
  ledger_rows    장부에 적힌 원본 파일 줄 수
  unprocessed    장부에 아직 없는 창고 파일 수 (= 아직 안 들어간 것)
  realtime_new   그중 실시간 트랙이 가져온 것 (상태 파일의 realtime_files 기준)
  backlog        그 나머지 (= 밀린 것. 과거 트랙이 받아 둔 것이 여기로 갑니다)
  ledger_found   장부 파일을 찾았는지. false 면 unprocessed 숫자를 믿으면 안 됩니다

사용법
  python inbox_status.py --wiki "C:/Users/나/Documents/내위키"
  python inbox_status.py --wiki "<위키폴더>" --list       # 아직 안 들어간 파일 이름까지

출력 JSON (stdout 한 줄)
  {"ok":true,"raw_files":163,"ledger_rows":23,"ledger_found":true,
   "unprocessed":140,"realtime_new":3,"backlog":137,
   "sources":[{"label":"메일:me@example.com","kind":"mail","first_run_done":false,
   "backfill_start":"2026-04","backfill_cursor":"2026-06","backlog_remaining":2,
   "last_run":"2026-09-19T23:04:11+09:00","last_error":null}]}
  오류  {"ok":false,"error":{"code":"NO_WIKI","message":"..."}}

종료코드
  0 성공 · 2 위키 폴더가 아님 · 3 예상 못 한 오류. 1 은 쓰지 않습니다.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _common as C  # noqa: E402


def out(obj, code=0):
    # 화면용 JSON 은 ASCII 로만 냅니다(Windows 콘솔에서 한글이 통째로 사라지는 일을 막습니다).
    print(json.dumps(obj, ensure_ascii=True))
    raise SystemExit(code)


def raw_files(wiki: pathlib.Path) -> list:
    root = wiki / "raw"
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith("_") for part in rel.parts):  # _수집상태.json, _걸러짐/
            continue
        if path.name.endswith(".tmp"):
            continue
        found.append(C.nfc(str(rel).replace("\\", "/")))
    return found


def ledger_path(wiki: pathlib.Path):
    """wiki/장부.md. 한글 이름이 NFD 로 저장돼 있어도 찾습니다. 없으면 None."""
    folder = wiki / "wiki"
    want = C.nfc("장부.md")
    if folder.is_dir():
        try:
            for one in folder.iterdir():
                if one.is_file() and C.nfc(one.name) == want:
                    return one
        except OSError:
            pass
    return None


def ledger_rows(path) -> set:
    rows = set()
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):  # 예시 블록 안은 세지 않습니다
            fenced = not fenced
            continue
        if fenced or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("날짜", "") or set(cells[0]) <= set("-: "):
            continue
        name = re.sub(r"^`|`$", "", cells[1])
        if name and name != "-":
            rows.add(C.nfc(name.replace("\\", "/")))
    return rows


def main() -> None:
    C.force_utf8()
    parser = argparse.ArgumentParser(description="수집 현황 (새로 온 것과 밀린 것을 갈라서 셉니다)")
    parser.add_argument("--wiki", required=True, help="위키 폴더. wiki/ 와 raw/ 가 있는 곳")
    parser.add_argument("--list", action="store_true", help="아직 안 들어간 파일 이름까지 보여 줍니다")
    args = parser.parse_args()

    wiki = pathlib.Path(args.wiki).expanduser().resolve()
    if not (wiki / "wiki").is_dir():
        out({"ok": False, "error": {"code": "NO_WIKI",
                                    "message": "위키 폴더가 아니에요. wiki/ 가 있는 폴더를 알려 주세요."}}, 2)

    state = C.load_state(wiki)
    files = raw_files(wiki)
    book = ledger_path(wiki)
    ledger = ledger_rows(book) if book else set()
    # 장부에 파일 이름만 적힌 옛 줄도 맞다고 봅니다(경로 규칙이 바뀌기 전 자료).
    # 다만 같은 이름이 여러 폴더에 있으면 어느 것인지 모르므로 그때는 안 맞다고 봅니다.
    legacy = {row for row in ledger if "/" not in row}
    counts = {}
    for one in files:
        tail = one.rsplit("/", 1)[-1]
        counts[tail] = counts.get(tail, 0) + 1
    unprocessed = [f for f in files
                   if f not in ledger
                   and not (counts[f.rsplit("/", 1)[-1]] == 1 and f.rsplit("/", 1)[-1] in legacy)]
    recent = {C.nfc(f) for f in state.get("realtime_files", [])}
    realtime = [f for f in unprocessed if f in recent]

    report = {
        "ok": True,
        "wiki": str(wiki),
        "raw_files": len(files),
        "ledger_rows": len(ledger),
        "ledger_found": book is not None,
        "unprocessed": len(unprocessed),
        "realtime_new": len(realtime),
        "backlog": len(unprocessed) - len(realtime),
        "mail_filter_domains": state.get("mail_filter_domains", []),
        "sources": [{"label": key, "kind": src.get("kind"),
                     "first_run_done": src.get("first_run_done"),
                     "backfill_start": src.get("backfill_start"),
                     "backfill_cursor": src.get("backfill_cursor"),
                     "backlog_remaining": src.get("backlog_remaining", 0),
                     "last_run": src.get("last_run"),
                     "last_error": src.get("last_error")}
                    for key, src in state.get("sources", {}).items()],
    }
    if book is None:
        report["note"] = "장부(wiki/장부.md)를 못 찾았어요. 아직 안 들어간 숫자를 그대로 믿지 마세요."
    if args.list:
        report["unprocessed_files"] = unprocessed[:200]
        report["realtime_files"] = realtime[:200]
    out(report)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as err:  # 예상 못 한 오류도 JSON 한 줄로 냅니다
        out({"ok": False, "error": {"code": "UNEXPECTED", "message": type(err).__name__}}, 3)
