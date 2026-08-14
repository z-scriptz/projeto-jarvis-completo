#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_produzir_hook.py -- pluga o gerador Alana no produzir_tiktok.py (raiz).
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO = Path(__file__).resolve().parent / "produzir_tiktok.py"
OLD = base64.b64decode("ICAgIF9sb2coZiIgICDwn46oIGZ1bmRvICd7b3MuZW52aXJvblsnVE9QU0hPUF9CRyddfScgKG5pY2hvIHtuaWNobyBvciAnZ2VyYWwnfSkiKQoKICAgIHBsYW5vID0gew==").decode()
NEW = base64.b64decode("ICAgIF9sb2coZiIgICDwn46oIGZ1bmRvICd7b3MuZW52aXJvblsnVE9QU0hPUF9CRyddfScgKG5pY2hvIHtuaWNobyBvciAnZ2VyYWwnfSkiKQoKICAgICMgSE9PSyBlc3RpbG8gQWxhbmEgKCJmcmFzZSByZWxhdGFibGUg8J+YqSIgLyAiQSBTaG9wZWU6Iikg4oCUIMOpIG8gcXVlIGNvbnZlcnRlLgogICAgIyBVc2EgR2VtaW5pIChIT09LX0FMQU5BPTEgKyBHRU1JTklfQVBJX0tFWSk7IHNlbsOjbyBiYW5jbyByZWxhdGFibGUgcG9yIG5pY2hvLgogICAgaWYgb3MuZ2V0ZW52KCJIT09LX0FMQU5BIiwgIjEiKS5zdHJpcCgpLmxvd2VyKCkgaW4gKCIxIiwgInRydWUiLCAic2ltIik6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBmcm9tIGhvb2tfYWxhbmEgaW1wb3J0IGdlcmFyX2hvb2tfYWxhbmEKICAgICAgICAgICAgX2hhID0gZ2VyYXJfaG9va19hbGFuYShub21lLCBpbmZvLmdldCgiZGVzY3JpY2FvIiwgIiIpLCBuaWNobykKICAgICAgICAgICAgaWYgX2hhOgogICAgICAgICAgICAgICAgaG9vayA9IF9oYQogICAgICAgICAgICAgICAgX2xvZyhmIiAgIOKcje+4jyAgaG9vayBBbGFuYTogXCJ7aG9vay5zcGxpdGxpbmVzKClbMF19XCIgLyB7aG9vay5zcGxpdGxpbmVzKClbLTFdfSIpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBfZToKICAgICAgICAgICAgX2xvZyhmIiAgIGhvb2sgQWxhbmEgb2ZmICh7c3RyKF9lKVs6NTBdfSkg4oCUIHVzYSBvIGhvb2sgcGFkcsOjbyIpCgogICAgcGxhbm8gPSB7").decode()
def main():
    if not ALVO.exists():
        print("nao achei", ALVO); return 1
    txt = ALVO.read_text(encoding="utf-8").replace("\r\n", "\n")
    if NEW in txt:
        print("JA APLICADO"); return 0
    if txt.count(OLD) != 1:
        print("ABORTADO: anchor !=1x (count=" + str(txt.count(OLD)) + ")"); return 2
    novo = txt.replace(OLD, NEW)
    bak = ALVO.with_suffix(ALVO.suffix + ".bak_" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(ALVO, bak)
    ALVO.write_text(novo, encoding="utf-8")
    try:
        py_compile.compile(str(ALVO), doraise=True)
    except Exception as e:
        shutil.copy2(bak, ALVO)
        print("py_compile falhou, RESTAUREI:", e); return 3
    print("APLICADO (backup", bak.name, ")")
    return 0
if __name__ == "__main__":
    sys.exit(main())
