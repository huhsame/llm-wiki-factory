#!/usr/bin/env python3
"""수집 스크립트 공통부. 표준 라이브러리만 씁니다.

혼자서는 돌지 않습니다. mail_fetch.py · kakao_collect.py · inbox_status.py 가 가져다 씁니다.

담고 있는 것
  force_utf8()          stdout/stderr 를 UTF-8 로 맞춥니다(Windows 콘솔 한글 깨짐 방지)
  load_state/save_state raw/_수집상태.json 읽기·쓰기(원자적, BOM 없는 UTF-8)
                        파일 이름이 NFD 로 저장돼 있어도 찾습니다(macOS 에서 만든 폴더)
  safe_name()           Windows 에서 쓸 수 있는 파일 이름으로 다듬기(한글 유지, NFC)
  write_text()          BOM 없는 UTF-8 로 원자적 저장
  months_between()      "2026-04" ~ "2026-09" 같은 달 목록
  next_month()          "2026-06" -> "2026-07" (과거 트랙 커서를 다음 달로 올릴 때)
  month_bounds()        그 달의 시작·다음 달 시작(로컬 시간대)

종료코드는 이 파일이 정하지 않습니다. 부르는 쪽 규약을 따릅니다.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys
import unicodedata

FORMAT = 2  # 1 -> 2: last_run_files(트랙 구분 없음) 를 realtime_files 로 바꿨습니다
OVERLAP_SEC = 3600
BAD = set('\\/:*?"<>|')
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def force_utf8() -> None:
    """Windows 콘솔에서도 한글이 안 깨지게 합니다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def now_local() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def state_path(wiki: pathlib.Path) -> pathlib.Path:
    """raw/_수집상태.json. 한글 이름이 NFD 로 저장돼 있어도 그 파일을 돌려줍니다."""
    root = wiki / "raw"
    want = nfc("_수집상태.json")
    if root.is_dir():
        try:
            for one in root.iterdir():
                if one.is_file() and nfc(one.name) == want:
                    return one
        except OSError:
            pass
    return root / "_수집상태.json"


def blank_state(wiki: pathlib.Path) -> dict:
    return {
        "format": FORMAT,
        "wiki_root": str(wiki),
        "updated_at": None,
        "realtime_files": [],
        "mail_filter_domains": [],
        "survey": None,  # 둘러보기 회차 기록(고른 방·뺀 방·거른 곳). 수집 진행에는 안 씁니다
        "sources": {},
    }


def load_state(wiki: pathlib.Path) -> dict:
    path = state_path(wiki)
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("format") == 1:  # 옛 칸은 트랙 구분이 없어서 버립니다
                state.pop("last_run_files", None)
                state["format"] = FORMAT
            if state.get("format") == FORMAT:
                state.setdefault("realtime_files", [])
                state.setdefault("mail_filter_domains", [])
                state.setdefault("survey", None)
                state.setdefault("sources", {})
                return state
        except Exception:
            pass
    return blank_state(wiki)


def save_state(wiki: pathlib.Path, state: dict) -> None:
    """회차 끝에서 한 번만 부릅니다. 중간에 멈추면 이전 값이 그대로 남습니다."""
    state["wiki_root"] = str(wiki)
    state["updated_at"] = now_local().isoformat(timespec="seconds")
    path = state_path(wiki)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def safe_name(name: str, fallback: str = "unknown") -> str:
    """Windows 에서 쓸 수 있는 파일 이름으로. 한글은 그대로 둡니다."""
    text = nfc(name)
    text = "".join(ch for ch in text if ch not in BAD and ord(ch) >= 32)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if text.upper().split(".")[0] in RESERVED:
        text += "_방"
    return (text or fallback)[:60]


def write_text(path: pathlib.Path, text: str) -> None:
    """BOM 없는 UTF-8 로 원자적으로 씁니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def months_between(start_ym: str, end_ym: str) -> list:
    year, month = int(start_ym[:4]), int(start_ym[5:7])
    end_year, end_month = int(end_ym[:4]), int(end_ym[5:7])
    months = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def month_bounds(ym: str):
    tz = now_local().tzinfo
    year, month = int(ym[:4]), int(ym[5:7])
    first = datetime.datetime(year, month, 1, tzinfo=tz)
    nxt = datetime.datetime(year + (1 if month == 12 else 0), (month % 12) + 1, 1, tzinfo=tz)
    return first, nxt


def next_month(ym: str) -> str:
    year, month = int(ym[:4]), int(ym[5:7]) + 1
    if month > 12:
        year, month = year + 1, 1
    return f"{year:04d}-{month:02d}"


def shift_month(ym: str, back: int) -> str:
    year, month = int(ym[:4]), int(ym[5:7]) - back
    while month <= 0:
        year, month = year - 1, month + 12
    return f"{year:04d}-{month:02d}"


def ym_of(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(max(epoch, 0)).strftime("%Y-%m")


def record_files(state: dict, rels: list, track: str) -> None:
    """실시간 트랙이 가져온 파일만 모읍니다. 최대 200개.

    과거(백필) 트랙이 받은 파일은 처음부터 "밀린 것"이라 여기 넣지 않습니다.
    아직 장부에 안 올라간 실시간 파일은 다음 회차에도 "새로 온 것"으로 남습니다.
    """
    if track != "realtime":
        return
    fresh = [nfc(r).replace("\\", "/") for r in rels if r]
    kept = [r for r in state.get("realtime_files", []) if r not in fresh]
    state["realtime_files"] = (fresh + kept)[:200]
