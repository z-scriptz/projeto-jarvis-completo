#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_hook_greedy.py -- quebra do hook em 2 linhas GULOSA (enche a 1a ate a
# borda, resto na 2a). Backup+py_compile+idempotente+restaura.
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO=Path(__file__).resolve().parent/"agents/narrated_video_agent.py"
PARES=[('ICAgICAgICBfbGluaGFzID0gW2hvb2tfdHh0X2xpbXBvXQogICAgICAgIF9lbW9qaV9saW5oYSA9IDAKICAgIGVsc2U6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBfbGluaGFzID0gW2wgZm9yIGwgaW4gX3F1ZWJyYXJfaG9va18ybGluaGFzKGhvb2tfdHh0X2xpbXBvKSBpZiBsXQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIF9saW5oYXMgPSBbaG9va190eHRfbGltcG9dCiAgICAgICAgX2Vtb2ppX2xpbmhhID0gbGVuKF9saW5oYXMpIC0gMQogICAgICAgIHdoaWxlIEhLX0ZPTlQgPiBIS19GT05UX01JTiBhbmQgbWF4KF9sYXJnKGwsIEhLX0ZPTlQpIGZvciBsIGluIF9saW5oYXMpID4gSEtfTUFYX0xBUkc6CiAgICAgICAgICAgIEhLX0ZPTlQgLT0gMg==', 'ICAgICAgICBfbGluaGFzID0gW2hvb2tfdHh0X2xpbXBvXQogICAgICAgIF9lbW9qaV9saW5oYSA9IDAKICAgIGVsc2U6CiAgICAgICAgIyBHUkVFRFk6IGVuY2hlIGEgMcKqIGxpbmhhIGRhIGVzcXVlcmRhIGF0w6kgYSBkaXJlaXRhIChsYXJndXJhIG3DoXgpIGUgam9nYSBvCiAgICAgICAgIyByZXN0byBuYSAywqog4oCUIGVtIHZleiBkZSBkaXZpZGlyIG5vIG1laW8gKHF1ZSBkZWl4YXZhIGEgMcKqIGxpbmhhIGN1cnRhKS4KICAgICAgICB0cnk6CiAgICAgICAgICAgIF9wYWwgPSBob29rX3R4dF9saW1wby5zcGxpdCgpCiAgICAgICAgICAgIF9sMSwgX2xpbmhhcyA9IFtdLCBOb25lCiAgICAgICAgICAgIGZvciBfaywgX3cgaW4gZW51bWVyYXRlKF9wYWwpOgogICAgICAgICAgICAgICAgaWYgX2wxIGFuZCBfbGFyZygiICIuam9pbihfbDEgKyBbX3ddKSwgSEtfRk9OVCkgPiBIS19NQVhfTEFSRzoKICAgICAgICAgICAgICAgICAgICBfbGluaGFzID0gWyIgIi5qb2luKF9sMSksICIgIi5qb2luKF9wYWxbX2s6XSldCiAgICAgICAgICAgICAgICAgICAgYnJlYWsKICAgICAgICAgICAgICAgIF9sMS5hcHBlbmQoX3cpCiAgICAgICAgICAgIGlmIF9saW5oYXMgaXMgTm9uZToKICAgICAgICAgICAgICAgIF9saW5oYXMgPSBbIiAiLmpvaW4oX2wxKSBvciBob29rX3R4dF9saW1wb10KICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICBfbGluaGFzID0gW2wgZm9yIGwgaW4gX3F1ZWJyYXJfaG9va18ybGluaGFzKGhvb2tfdHh0X2xpbXBvKSBpZiBsXQogICAgICAgIF9lbW9qaV9saW5oYSA9IGxlbihfbGluaGFzKSAtIDEKICAgICAgICB3aGlsZSBIS19GT05UID4gSEtfRk9OVF9NSU4gYW5kIG1heChfbGFyZyhsLCBIS19GT05UKSBmb3IgbCBpbiBfbGluaGFzKSA+IEhLX01BWF9MQVJHOgogICAgICAgICAgICBIS19GT05UIC09IDI=')]
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
