#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_layout_ajuste2.py -- logo (direita+baixo) + emoji CTA (desce). Env-driven.
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO = Path(__file__).resolve().parent / "agents/narrated_video_agent.py"
PARES = [('ICAgIGlmIG5vdCAoX2hrX2ZvbnRlIGFuZCBQYXRoKF9oa19mb250ZSkuZXhpc3RzKCkpOgogICAgICAgIF9oa19mb250ZSA9IGZvbnRlX2JvbGQKCiAgICBsb2dvX3gsIGxvZ29feSwgbG9nb190YW0gPSA2NSwgOTAsIDEyMAoKICAgICMg4pSA4pSAIExvZ28gVFMgUkVET05ETyAoY2FudG8gc3VwZXJpb3IgZXNxdWVyZG8pIOKUgOKUgAogICAgbG9nb19wYXRoID0gX2JyYW5kX2Fzc2V0KCJsb2dvX3RzLnBuZyIp', 'ICAgIGlmIG5vdCAoX2hrX2ZvbnRlIGFuZCBQYXRoKF9oa19mb250ZSkuZXhpc3RzKCkpOgogICAgICAgIF9oa19mb250ZSA9IGZvbnRlX2JvbGQKCiAgICBsb2dvX3ggPSBpbnQob3MuZW52aXJvbi5nZXQoIkxPR09fWCIsIDEwMCkpICAgICMgKyDDoCBkaXJlaXRhIChlcmEgNjUpCiAgICBsb2dvX3kgPSBpbnQob3MuZW52aXJvbi5nZXQoIkxPR09fWSIsIDExMikpICAgICMgKyBwcmEgYmFpeG8gKGVyYSA5MCkKICAgIGxvZ29fdGFtID0gaW50KG9zLmVudmlyb24uZ2V0KCJMT0dPX1RBTSIsIDEyMCkpCgogICAgIyDilIDilIAgTG9nbyBUUyBSRURPTkRPIChjYW50byBzdXBlcmlvciBlc3F1ZXJkbykg4pSA4pSACiAgICBsb2dvX3BhdGggPSBfYnJhbmRfYXNzZXQoImxvZ29fdHMucG5nIik='), ('ICAgICAgICBpZiBfZXAgaXMgbm90IE5vbmU6CiAgICAgICAgICAgIGUgPSBJbWFnZUNsaXAoc3RyKF9lcCkpCiAgICAgICAgICAgIGUgPSBfd2l0aF9kdXJhdGlvbihlLCBkdXJfdG90YWwpOyBlID0gX3dpdGhfc3RhcnQoZSwgMC4wKQogICAgICAgICAgICBlID0gX3dpdGhfcG9zaXRpb24oZSwgKG1pbihfZmltICsgMTQsIExBUkdVUkEgLSBfZXQgLSA4KSwgY3RhX3kgKyA0KSkKICAgICAgICAgICAgY2FtYWRhcy5hcHBlbmQoZSkKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICBsb2cud2FybmluZyhmIiAgIOKaoO+4jyAgRW1vamkgZG8gQ1RBIGZhbGhvdSAoc2VndWUgc2VtKToge2V9Iik=', 'ICAgICAgICBpZiBfZXAgaXMgbm90IE5vbmU6CiAgICAgICAgICAgIGUgPSBJbWFnZUNsaXAoc3RyKF9lcCkpCiAgICAgICAgICAgIGUgPSBfd2l0aF9kdXJhdGlvbihlLCBkdXJfdG90YWwpOyBlID0gX3dpdGhfc3RhcnQoZSwgMC4wKQogICAgICAgICAgICBfZWR5ID0gaW50KG9zLmVudmlyb24uZ2V0KCJDVEFfRU1PSklfRFkiLCAyMikpICAgIyBkZXNjZSBvIPCfkYcgcC8gYWxpbmhhcgogICAgICAgICAgICBlID0gX3dpdGhfcG9zaXRpb24oZSwgKG1pbihfZmltICsgMTQsIExBUkdVUkEgLSBfZXQgLSA4KSwgY3RhX3kgKyBfZWR5KSkKICAgICAgICAgICAgY2FtYWRhcy5hcHBlbmQoZSkKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICBsb2cud2FybmluZyhmIiAgIOKaoO+4jyAgRW1vamkgZG8gQ1RBIGZhbGhvdSAoc2VndWUgc2VtKToge2V9Iik=')]
def main():
    if not ALVO.exists(): print("nao achei",ALVO); return 1
    txt=ALVO.read_text(encoding="utf-8").replace("\r\n","\n")
    pares=[(base64.b64decode(o).decode(),base64.b64decode(n).decode()) for o,n in PARES]
    if all(n in txt for _,n in pares): print("JA APLICADO"); return 0
    novo=txt
    for old,new in pares:
        if new in novo: continue
        if old not in novo: print("ABORTADO:",old.strip().splitlines()[0][:80]); return 2
        novo=novo.replace(old,new,1)
    bak=ALVO.with_suffix(ALVO.suffix+".bak_"+time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(ALVO,bak); ALVO.write_text(novo,encoding="utf-8")
    try: py_compile.compile(str(ALVO),doraise=True)
    except Exception as e: shutil.copy2(bak,ALVO); print("py_compile falhou, restaurei:",e); return 3
    print("APLICADO (backup",bak.name,"). systemctl restart jarvis"); return 0
if __name__=="__main__": sys.exit(main())
