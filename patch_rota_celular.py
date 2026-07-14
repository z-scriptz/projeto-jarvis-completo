#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_rota_celular.py -- roteia acessorios de celular (capinha/capa/pelicula/
# iphone/suporte) pra conta TECH (antes caiam em 'geral'). Alvo: roteador_contas.py.
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO=Path(__file__).resolve().parent/"roteador_contas.py"
PARES=[('ICAgICJwb3dlcmJhbmsiLCAicG93ZXIgYmFuayIsICJwcm9qZXRvciIsICJkcm9uZSIsICJjYWl4YSBkZSBzb20iLCAiYmx1ZXRvb3RoIiwKICAgICJ3ZWJjYW0iLCAibW91c2UiLCAidGVjbGFkbyIsICJyaW5nIGxpZ2h0IiwgImx1bWluw6FyaWEgbGVkIiwgImx1bWluYXJpYSBsZWQiLAogICAgImdhbWVyIiwgInNtYXJ0IHR2IiwgInJvdGVhZG9yIHdpIiwgInNzZCIsICJwZW5kcml2ZSIsICJnYWRnZXQiLAopCgo=', 'ICAgICJwb3dlcmJhbmsiLCAicG93ZXIgYmFuayIsICJwcm9qZXRvciIsICJkcm9uZSIsICJjYWl4YSBkZSBzb20iLCAiYmx1ZXRvb3RoIiwKICAgICJ3ZWJjYW0iLCAibW91c2UiLCAidGVjbGFkbyIsICJyaW5nIGxpZ2h0IiwgImx1bWluw6FyaWEgbGVkIiwgImx1bWluYXJpYSBsZWQiLAogICAgImdhbWVyIiwgInNtYXJ0IHR2IiwgInJvdGVhZG9yIHdpIiwgInNzZCIsICJwZW5kcml2ZSIsICJnYWRnZXQiLAogICAgIyBjZWx1bGFyICsgYWNlc3PDs3Jpb3MgKGNhcGluaGEvY2FwYS9wZWzDrWN1bGEgZGUgaVBob25lIGlhbSBwcm8gJ2dlcmFsJyBhbnRlcykKICAgICJjZWx1bGFyIiwgInNtYXJ0cGhvbmUiLCAiaXBob25lIiwgImFuZHJvaWQiLCAidGVsZWZvbmUiLCAiY2FwaW5oYSIsCiAgICAiY2FwYSBkZSBjZWx1bGFyIiwgImNhcGEgZGUgdGVsZWZvbmUiLCAiY2FwYSBtYWduZXRpY2EiLCAiY2FwYSBtYWduw6l0aWNhIiwKICAgICJtYWdzYWZlIiwgInBlbGljdWxhIiwgInBlbMOtY3VsYSIsICJzdXBvcnRlIGRlIGNlbHVsYXIiLCAic3Vwb3J0ZSBjZWx1bGFyIiwKICAgICJzdXBvcnRlIHZlaWN1bGFyIiwgImNhYm8gdXNiIiwgImNhYm8gdGlwbyBjIiwgImNhYm8gbGlnaHRuaW5nIiwKICAgICJjYXJyZWdhZG9yIHNlbSBmaW8iLCAiaHViIHVzYiIsICJhZGFwdGFkb3IgdXNiIiwKKQoK')]
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
