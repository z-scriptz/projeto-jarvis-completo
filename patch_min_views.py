#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_min_views.py -- MIN_VIEWS tunavel por .env (aplicado apos _carregar_env).
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO=Path(__file__).resolve().parent/"tiktok_coletor.py"
PARES=[('VklTVE9TID0gQkFTRV9ESVIgLyAic2hhcmVkIiAvICJ0aWt0b2tfdmlzdG9zLmpzb24iCklOQk9YID0gQkFTRV9ESVIgLyAiaW5ib3hfdGlrdG9rIgoKTUlOX1ZJRVdTID0gNTBfMDAwICAgICAgIyBzw7MgbyBxdWUgasOhIHByb3ZvdSB0cmHDp8OjbwpNQVhfRFVSID0gOTAgICAgICAgICAgICAjIHNlZ3VuZG9zClBPUl9QRVJGSUwgPSA0MCAgICAgICAgICMgcXVhbnRvcyB2w61kZW9zIHJlY2VudGVzIGNoZWNhciBwb3IgcGVyZmlsICgtLWxpbWl0ZSBtdWRhKQo=', 'VklTVE9TID0gQkFTRV9ESVIgLyAic2hhcmVkIiAvICJ0aWt0b2tfdmlzdG9zLmpzb24iCklOQk9YID0gQkFTRV9ESVIgLyAiaW5ib3hfdGlrdG9rIgoKTUlOX1ZJRVdTID0gNTBfMDAwICAgICAgIyBtaW4gZGUgdmlld3MgKGRlZmF1bHQ7IG92ZXJyaWRlIHBvciBNSU5fVklFV1Mgbm8gLmVudiDigJQgYXBsaWNhZG8gYXDDs3MgX2NhcnJlZ2FyX2VudikKTUFYX0RVUiA9IDkwICAgICAgICAgICAgIyBzZWd1bmRvcwpQT1JfUEVSRklMID0gNDAgICAgICAgICAjIHF1YW50b3MgdsOtZGVvcyByZWNlbnRlcyBjaGVjYXIgcG9yIHBlcmZpbCAoLS1saW1pdGUgbXVkYSkK'), ('CgpfY2FycmVnYXJfZW52KCkKCnRyeToKICAgIGZyb20gaW50ZWdyYXRpb25zLnNob3BlZV9hZmZpbGlhdGUgaW1wb3J0IG1pbmVyYXJfb3BvcnR1bmlkYWRlcywgZ2VyYXJfbGlua19hZmlsaWFkbw==', 'CgpfY2FycmVnYXJfZW52KCkKCiMgYWdvcmEgcXVlIG8gLmVudiBlc3TDoSBjYXJyZWdhZG8sIGFwbGljYSBvIG92ZXJyaWRlIGRvIG1pbiBkZSB2aWV3cyAoc2UgaG91dmVyKQpNSU5fVklFV1MgPSBpbnQob3MuZW52aXJvbi5nZXQoIk1JTl9WSUVXUyIsIE1JTl9WSUVXUykpCgp0cnk6CiAgICBmcm9tIGludGVncmF0aW9ucy5zaG9wZWVfYWZmaWxpYXRlIGltcG9ydCBtaW5lcmFyX29wb3J0dW5pZGFkZXMsIGdlcmFyX2xpbmtfYWZpbGlhZG8=')]
def main():
    if not ALVO.exists(): print("nao achei",ALVO); return 1
    txt=ALVO.read_text(encoding="utf-8").replace("\r\n","\n")
    pares=[(base64.b64decode(o).decode(),base64.b64decode(n).decode()) for o,n in PARES]
    if all(n in txt for _,n in pares): print("JA APLICADO"); return 0
    novo=txt
    for old,new in pares:
        if new in novo: continue
        if old not in novo: print("ABORTADO: nao achou:"); print("  "+old.strip().splitlines()[0][:80]); return 2
        if novo.count(old)!=1: print("ABORTADO: ambiguo"); return 2
        novo=novo.replace(old,new)
    bak=ALVO.with_suffix(ALVO.suffix+".bak_"+time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(ALVO,bak); ALVO.write_text(novo,encoding="utf-8")
    try: py_compile.compile(str(ALVO),doraise=True)
    except Exception as e: shutil.copy2(bak,ALVO); print("py_compile falhou, RESTAUREI:",e); return 3
    print("APLICADO (backup",bak.name,")"); return 0
if __name__=="__main__": sys.exit(main())
