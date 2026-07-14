#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_logo_conta.py -- logo POR CONTA/NICHO (TOPSHOP_LOGO). Mexe em
# agents/narrated_video_agent.py + produzir_tiktok.py. Backup+py_compile+idempotente.
import base64, py_compile, shutil, sys, time
from pathlib import Path
RAIZ=Path(__file__).resolve().parent
MAPA={'agents/narrated_video_agent.py': [('ICAgICAgICBkcmF3ID0gSW1hZ2VEcmF3LkRyYXcobWFzaykKICAgICAgICBkcmF3LmVsbGlwc2UoKDAsIDAsIHRhbSwgdGFtKSwgZmlsbD0yNTUpCiAgICAgICAgaW1nLnB1dGFscGhhKG1hc2spCiAgICAgICAgb3V0ID0gVE1QX0RJUiAvICJsb2dvX3RzX2NpcmN1bGFyLnBuZyIKICAgICAgICBvdXQucGFyZW50Lm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKICAgICAgICBpbWcuc2F2ZShzdHIob3V0KSkKICAgICAgICByZXR1cm4gb3V0', 'ICAgICAgICBkcmF3ID0gSW1hZ2VEcmF3LkRyYXcobWFzaykKICAgICAgICBkcmF3LmVsbGlwc2UoKDAsIDAsIHRhbSwgdGFtKSwgZmlsbD0yNTUpCiAgICAgICAgaW1nLnB1dGFscGhhKG1hc2spCiAgICAgICAgb3V0ID0gVE1QX0RJUiAvIGYibG9nb19jaXJjX3tsb2dvX3BhdGguc3RlbX0ucG5nIgogICAgICAgIG91dC5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgICAgIGltZy5zYXZlKHN0cihvdXQpKQogICAgICAgIHJldHVybiBvdXQ='), ('ICAgIGxvZ29fdGFtID0gaW50KG9zLmVudmlyb24uZ2V0KCJMT0dPX1RBTSIsIDEyMCkpCgogICAgIyDilIDilIAgTG9nbyBUUyBSRURPTkRPIChjYW50byBzdXBlcmlvciBlc3F1ZXJkbykg4pSA4pSACiAgICBsb2dvX3BhdGggPSBfYnJhbmRfYXNzZXQoImxvZ29fdHMucG5nIikKICAgIGlmIGxvZ29fcGF0aCBpcyBub3QgTm9uZToKICAgICAgICBjaXJjdWxhciA9IF9sb2dvX2NpcmN1bGFyKGxvZ29fcGF0aCwgdGFtPWxvZ29fdGFtKSBvciBsb2dvX3BhdGgKICAgICAgICB0cnk6', 'ICAgIGxvZ29fdGFtID0gaW50KG9zLmVudmlyb24uZ2V0KCJMT0dPX1RBTSIsIDEyMCkpCgogICAgIyDilIDilIAgTG9nbyBUUyBSRURPTkRPIChjYW50byBzdXBlcmlvciBlc3F1ZXJkbykg4pSA4pSACiAgICAjIGxvZ28gUE9SIENPTlRBL05JQ0hPOiBhIHByb2R1w6fDo28gc2V0YSBUT1BTSE9QX0xPR08gKGV4LjogbG9nb190c190ZWNoLnBuZywKICAgICMgbG9nb190c19iZWF1dHkucG5nKSBhbnRlcyBkZSByZW5kZXJpemFyOyBjYWkgbmEgbG9nb190cy5wbmcgcGFkcsOjby4KICAgIGxvZ29fcGF0aCA9IF9icmFuZF9hc3NldChvcy5lbnZpcm9uLmdldCgiVE9QU0hPUF9MT0dPIiwgImxvZ29fdHMucG5nIikpCiAgICBpZiBsb2dvX3BhdGggaXMgTm9uZToKICAgICAgICBsb2dvX3BhdGggPSBfYnJhbmRfYXNzZXQoImxvZ29fdHMucG5nIikKICAgIGlmIGxvZ29fcGF0aCBpcyBub3QgTm9uZToKICAgICAgICBjaXJjdWxhciA9IF9sb2dvX2NpcmN1bGFyKGxvZ29fcGF0aCwgdGFtPWxvZ29fdGFtKSBvciBsb2dvX3BhdGgKICAgICAgICB0cnk6')], 'produzir_tiktok.py': [('ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBvciBvcy5lbnZpcm9uLmdldCgiQkdfIiArIG5pY2hvLnVwcGVyKCksIF9iZ19wYWRyYW8pKQogICAgX2xvZyhmIiAgIPCfjqggZnVuZG8gJ3tvcy5lbnZpcm9uWydUT1BTSE9QX0JHJ119JyAobmljaG8ge25pY2hvIG9yICdnZXJhbCd9KSIpCgogICAgIyBIT09LIGVzdGlsbyBBbGFuYSAoImZyYXNlIHJlbGF0YWJsZSDwn5ipIiAvICJBIFNob3BlZToiKSDigJQgw6kgbyBxdWUgY29udmVydGUuCiAgICAjIFVzYSBHZW1pbmkgKEhPT0tfQUxBTkE9MSArIEdFTUlOSV9BUElfS0VZKTsgc2Vuw6NvIGJhbmNvIHJlbGF0YWJsZSBwb3IgbmljaG8uCiAgICBpZiBvcy5nZXRlbnYoIkhPT0tfQUxBTkEiLCAiMSIpLnN0cmlwKCkubG93ZXIoKSBpbiAoIjEiLCAidHJ1ZSIsICJzaW0iKTo=', 'ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBvciBvcy5lbnZpcm9uLmdldCgiQkdfIiArIG5pY2hvLnVwcGVyKCksIF9iZ19wYWRyYW8pKQogICAgX2xvZyhmIiAgIPCfjqggZnVuZG8gJ3tvcy5lbnZpcm9uWydUT1BTSE9QX0JHJ119JyAobmljaG8ge25pY2hvIG9yICdnZXJhbCd9KSIpCgogICAgIyBMT0dPIHBvciBjb250YS9uaWNobzogY2FkYSBwZXJmaWwgdGVtIHN1YSBtYXJjYSAodGVjaD10ZWFsLCBiZWF1dHk9cm9zYSkuCiAgICAjIENvbG9xdWUgb3MgUE5HcyBlbSBhc3NldHMvYnJhbmQvLiBDYWkgbmEgbG9nb190cy5wbmcgc2UgbyBhcnF1aXZvIG7Do28gZXhpc3Rpci4KICAgIF9MT0dPX05JQ0hPID0geyJiZWxlemEiOiAibG9nb190c19iZWF1dHkucG5nIiwgInRlY2giOiAibG9nb190c190ZWNoLnBuZyJ9CiAgICBvcy5lbnZpcm9uWyJUT1BTSE9QX0xPR08iXSA9IChvcy5lbnZpcm9uLmdldCgiRk9SQ0VfTE9HTyIpCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBvciBfTE9HT19OSUNITy5nZXQobmljaG8sICJsb2dvX3RzLnBuZyIpKQogICAgX2xvZyhmIiAgIPCfhaMgbG9nbyAne29zLmVudmlyb25bJ1RPUFNIT1BfTE9HTyddfSciKQoKICAgICMgSE9PSyBlc3RpbG8gQWxhbmEgKCJmcmFzZSByZWxhdGFibGUg8J+YqSIgLyAiQSBTaG9wZWU6Iikg4oCUIMOpIG8gcXVlIGNvbnZlcnRlLgogICAgIyBVc2EgR2VtaW5pIChIT09LX0FMQU5BPTEgKyBHRU1JTklfQVBJX0tFWSk7IHNlbsOjbyBiYW5jbyByZWxhdGFibGUgcG9yIG5pY2hvLgogICAgaWYgb3MuZ2V0ZW52KCJIT09LX0FMQU5BIiwgIjEiKS5zdHJpcCgpLmxvd2VyKCkgaW4gKCIxIiwgInRydWUiLCAic2ltIik6')]}
def aplicar(rel, pares_b64):
    alvo=RAIZ/rel
    if not alvo.exists(): print("  nao achei",alvo); return False
    txt=alvo.read_text(encoding="utf-8").replace("\r\n","\n")
    pares=[(base64.b64decode(o).decode(),base64.b64decode(n).decode()) for o,n in pares_b64]
    if all(n in txt for _,n in pares): print("  JA APLICADO:",rel); return True
    novo=txt
    for old,new in pares:
        if new in novo: continue
        if old not in novo: print("  ABORTADO",rel,":",old.strip().splitlines()[0][:70]); return False
        if novo.count(old)!=1: print("  ABORTADO",rel,": ambiguo"); return False
        novo=novo.replace(old,new)
    bak=alvo.with_suffix(alvo.suffix+".bak_"+time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(alvo,bak); alvo.write_text(novo,encoding="utf-8")
    try: py_compile.compile(str(alvo),doraise=True)
    except Exception as e: shutil.copy2(bak,alvo); print("  py_compile falhou",rel,",RESTAUREI:",e); return False
    print("  APLICADO",rel,"(backup",bak.name,")"); return True
def main():
    ok=all(aplicar(r,p) for r,p in MAPA.items())
    if ok: print("OK. Reinicie: systemctl restart jarvis")
    return 0 if ok else 1
if __name__=="__main__": sys.exit(main())
