#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_hook_bold_preto.py -- hook BOLD + contorno + grosso no fundo PRETO
# (destaca as letras brancas); fundo branco continua fino. Env: HOOK_FONTE_PRETO, HK_STROKE_PRETO.
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO=Path(__file__).resolve().parent/"agents/narrated_video_agent.py"
PARES=[('ICAgIGVsc2U6ICAgICAgICAgICAjIGZ1bmRvIFBSRVRPOiB0ZXh0byBicmFuY28gY29tIGNvbnRvcm5vIHByZXRvIChsZWfDrXZlbCkKICAgICAgICBDX05PTUUsIFNDX05PTUUsIFNXX05PTUUgPSAid2hpdGUiLCAiYmxhY2siLCAzCiAgICAgICAgQ19IQU5ETEUgPSAid2hpdGUiCiAgICAgICAgQ19IT09LLCBTQ19IT09LLCBTV19IT09LID0gIndoaXRlIiwgImJsYWNrIiwgMwogICAgIyBmb250ZSBkbyBIT09LOiBwb3IgcGFkcsOjbyBMaWJlcmF0aW9uIFNhbnMgKH5BcmlhbCwgaWd1YWwgYSBBbGFuYSk7IGNhaSBuYSBNb250c2VycmF0CiAgICBfaGtfZm9udGUgPSBvcy5lbnZpcm9uLmdldCgiSE9PS19GT05URSIsICIvdXNyL3NoYXJlL2ZvbnRzL3RydWV0eXBlL2xpYmVyYXRpb24vTGliZXJhdGlvblNhbnMtUmVndWxhci50dGYiKQogICAgaWYgbm90IChfaGtfZm9udGUgYW5kIFBhdGgoX2hrX2ZvbnRlKS5leGlzdHMoKSk6CiAgICAgICAgX2hrX2ZvbnRlID0gZm9udGVfYm9sZAo=', 'ICAgIGVsc2U6ICAgICAgICAgICAjIGZ1bmRvIFBSRVRPOiB0ZXh0byBicmFuY28gY29tIGNvbnRvcm5vIHByZXRvIChsZWfDrXZlbCkKICAgICAgICBDX05PTUUsIFNDX05PTUUsIFNXX05PTUUgPSAid2hpdGUiLCAiYmxhY2siLCAzCiAgICAgICAgQ19IQU5ETEUgPSAid2hpdGUiCiAgICAgICAgQ19IT09LLCBTQ19IT09LID0gIndoaXRlIiwgImJsYWNrIgogICAgICAgIFNXX0hPT0sgPSBpbnQob3MuZW52aXJvbi5nZXQoIkhLX1NUUk9LRV9QUkVUTyIsIDQpKSAgIyBjb250b3JubyArIGdyb3NzbyBubyBwcmV0bwogICAgIyBmb250ZSBkbyBIT09LOiBmdW5kbyBCUkFOQ08gdXNhIFJlZ3VsYXIgKGZpbm8sIGVsZWdhbnRlLCBlc3RpbG8gQWxhbmEpOwogICAgIyBmdW5kbyBQUkVUTyB1c2EgQk9MRCBwcmEgYXMgbGV0cmFzIGJyYW5jYXMgREVTVEFDQVJFTSBzb2JyZSBvIHbDrWRlby4KICAgIF9MSUIgPSAiL3Vzci9zaGFyZS9mb250cy90cnVldHlwZS9saWJlcmF0aW9uLyIKICAgIGlmIF9jbGFybzoKICAgICAgICBfaGtfZm9udGUgPSBvcy5lbnZpcm9uLmdldCgiSE9PS19GT05URSIsIF9MSUIgKyAiTGliZXJhdGlvblNhbnMtUmVndWxhci50dGYiKQogICAgZWxzZToKICAgICAgICBfaGtfZm9udGUgPSBvcy5lbnZpcm9uLmdldCgiSE9PS19GT05URV9QUkVUTyIsIF9MSUIgKyAiTGliZXJhdGlvblNhbnMtQm9sZC50dGYiKQogICAgaWYgbm90IChfaGtfZm9udGUgYW5kIFBhdGgoX2hrX2ZvbnRlKS5leGlzdHMoKSk6CiAgICAgICAgX2hrX2ZvbnRlID0gZm9udGVfYm9sZAo=')]
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
