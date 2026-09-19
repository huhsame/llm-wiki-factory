#!/usr/bin/env python3
"""앱 비밀번호 보관함. 표준 라이브러리만 쓰고, 값은 화면 어디에도 찍지 않습니다.

어디에 두나
  Windows : DPAPI(CryptProtectData) 로 잠가 %USERPROFILE%\\.llm-wiki-inbox\\secrets.dat
            같은 Windows 사용자 계정에서만 풀립니다. 다른 PC로 복사해도 안 풀립니다.
  macOS   : 로그인 키체인(security 명령), 서비스 이름 llm-wiki-inbox
  그 밖   : ~/.llm-wiki-inbox/secrets.dat + 권한 600 (암호화 아님. 경고를 같이 냅니다)

사용법
  python secret_store.py set    --label "mail:me@example.com"     # 표준 입력으로만 받습니다
  python secret_store.py get    --label "mail:me@example.com"     # 있는지만 알려 줍니다
  python secret_store.py delete --label "mail:me@example.com"
  python secret_store.py list

set 은 값을 인자로 받지 않습니다. 사람이 직접 연 창에서 치는 것이 기본입니다.
  창이 있는 곳(터미널)  : 명령을 치면 물어봅니다. 화면에 안 보입니다.
  PowerShell 에서 한 줄 : Read-Host -AsSecureString 으로 받아 이 명령에 파이프로 넘깁니다.
값을 명령줄에 적는 길(--password 같은 것)은 일부러 만들지 않았습니다. 기록에 남기 때문입니다.

출력 JSON (stdout 한 줄)
  set     {"ok":true,"label":"...","backend":"dpapi","stored":true,"warning":null}
  get     {"ok":true,"label":"...","found":true,"backend":"dpapi"}   # 값은 안 나옵니다
  delete  {"ok":true,"label":"...","deleted":true}
  list    {"ok":true,"backend":"dpapi","labels":["mail:..."],"note":"..."}
  오류    {"ok":false,"error":{"code":"EMPTY_SECRET","message":"..."}}

종료코드
  0 성공 · 2 사람이 손봐야 하는 문제(값 없음·보관함 오류) · 3 예상 못 한 오류
  1 은 쓰지 않습니다.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SERVICE = "llm-wiki-inbox"


def out(obj, code=0):
    # 화면용 JSON 은 ASCII 로만 냅니다(Windows 콘솔에서 한글이 통째로 사라지는 일을 막습니다).
    print(json.dumps(obj, ensure_ascii=True))
    raise SystemExit(code)


def home() -> pathlib.Path:
    path = pathlib.Path.home() / ".llm-wiki-inbox"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    """Windows 사용자 계정에 묶인 잠금. ctypes 라 설치할 게 없습니다."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buf = ctypes.create_string_buffer(data, len(data))  # 길이를 명시해야 NUL 이 안 붙습니다
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):  # UI_FORBIDDEN
        raise OSError("SECRET_PROTECT_FAILED")
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree(dst.pbData)


def backend() -> str:
    if os.name == "nt":
        return "dpapi"
    if sys.platform == "darwin":
        return "keychain"
    return "file"


def _store_path() -> pathlib.Path:
    return home() / "secrets.dat"


def _load_map() -> dict:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_map(data: dict) -> None:
    path = _store_path()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", newline="\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def put(label: str, secret: str) -> str:
    kind = backend()
    if kind == "keychain":
        # -w 뒤에 값을 붙이지 않습니다. 붙이면 같은 맥의 다른 프로그램이 ps 로 볼 수 있습니다.
        # security 는 값을 두 번 물어보므로 두 줄로 넣습니다.
        proc = subprocess.run(
            ["security", "add-generic-password", "-U", "-a", label, "-s", SERVICE, "-w"],
            input=f"{secret}\n{secret}\n", capture_output=True, text=True)
        if proc.returncode or fetch(label) != secret:  # 빈 값이 들어가는 일을 막습니다
            raise OSError("KEYCHAIN_WRITE_FAILED")
        return kind
    store = _load_map()
    raw = secret.encode("utf-8")
    store[label] = base64.b64encode(_dpapi(raw) if kind == "dpapi" else raw).decode("ascii")
    _save_map(store)
    return kind


def fetch(label: str):
    kind = backend()
    if kind == "keychain":
        proc = subprocess.run(
            ["security", "find-generic-password", "-a", label, "-s", SERVICE, "-w"],
            capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else None
    store = _load_map()
    if label not in store:
        return None
    raw = base64.b64decode(store[label])
    return (_dpapi(raw, decrypt=True) if kind == "dpapi" else raw).decode("utf-8")


def drop(label: str) -> bool:
    kind = backend()
    if kind == "keychain":
        proc = subprocess.run(
            ["security", "delete-generic-password", "-a", label, "-s", SERVICE],
            capture_output=True, text=True)
        return proc.returncode == 0
    store = _load_map()
    if label in store:
        del store[label]
        _save_map(store)
        return True
    return False


def main() -> None:
    C.force_utf8()
    parser = argparse.ArgumentParser(description="앱 비밀번호 보관함 (값은 화면에 안 찍힙니다)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("set", "비밀번호 저장"), ("get", "있는지 확인"), ("delete", "지우기")):
        one = sub.add_parser(name, help=help_text)
        one.add_argument("--label", required=True, help='이름표. 예 "mail:me@example.com"')
    sub.add_parser("list", help="이름표 목록")
    args = parser.parse_args()

    try:
        if args.cmd == "set":
            if sys.stdin.isatty():
                secret = getpass.getpass("앱 비밀번호를 붙여넣고 엔터를 눌러 주세요(화면에 안 보여요): ")
            else:
                secret = sys.stdin.readline().rstrip("\r\n")
            if not secret:
                out({"ok": False, "error": {"code": "EMPTY_SECRET",
                                            "message": "아무것도 입력되지 않았어요. "
                                                       "이 명령은 사용자가 직접 연 창에서 쳐야 해요."}}, 2)
            kind = put(args.label, secret)
            warn = None if kind != "file" else "이 컴퓨터에는 잠금 보관함이 없어서 권한만 건 파일에 뒀어요."
            out({"ok": True, "label": args.label, "backend": kind, "stored": True, "warning": warn})
        if args.cmd == "get":
            value = fetch(args.label)
            if value is None:
                out({"ok": False, "label": args.label, "found": False,
                     "error": {"code": "NO_SECRET", "message": "저장된 게 없어요."}}, 2)
            del value  # 있는지만 알려 줍니다. 값은 화면으로 내보내지 않습니다
            out({"ok": True, "label": args.label, "found": True, "backend": backend()})
        if args.cmd == "delete":
            out({"ok": True, "label": args.label, "deleted": drop(args.label)})
        if args.cmd == "list":
            labels = sorted(_load_map().keys()) if backend() != "keychain" else []
            out({"ok": True, "backend": backend(), "labels": labels,
                 "note": "키체인은 목록을 안 보여줘요. 이름표는 수집 상태 파일에 있어요."})
    except SystemExit:
        raise
    except OSError as err:
        out({"ok": False, "error": {"code": str(err) or "SECRET_ERROR",
                                    "message": "보관함을 쓸 수 없어요."}}, 2)
    except Exception as err:
        out({"ok": False, "error": {"code": "UNEXPECTED", "message": type(err).__name__}}, 3)


if __name__ == "__main__":
    main()
