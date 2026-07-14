#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_emoji_hook.py -- emoji do hook: folga horizontal (HK_EMOJI_DX) + altura
# consistente claro/escuro (HK_EMOJI_DY). Backup+py_compile+idempotente+restaura.
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO=Path(__file__).resolve().parent/"agents/narrated_video_agent.py"
PARES=[('ICAgICAgICAgICAgaWYgX2VwYXRoIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgX3lfZW1vID0gSEtfWSArIF9lbW9qaV9saW5oYSAqIEhLX0FMVFVSQV9MSU5IQQogICAgICAgICAgICAgICAgX2x3ID0gX2xhcmcoX2xpbmhhc1tfZW1vamlfbGluaGFdLCBIS19GT05UKQogICAgICAgICAgICAgICAgX2V4ID0gbWF4KDEwLCBtaW4oSEtfTUFSR0VNICsgKF9sdyBvciBpbnQoTEFSR1VSQSAqIDAuNSkpICsgMTIsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBMQVJHVVJBIC0gSEtfRU1PSklfVEFNIC0gMTApKQogICAgICAgICAgICAgICAgX2hrX3JlZiA9IF9oa19wb3JfbGluaGFbX2Vtb2ppX2xpbmhhXQogICAgICAgICAgICAgICAgX2FsdCA9IGdldGF0dHIoX2hrX3JlZiwgImgiLCBOb25lKSBpZiBfaGtfcmVmIGlzIG5vdCBOb25lIGVsc2UgTm9uZQogICAgICAgICAgICAgICAgX2V5ID0gaW50KF95X2VtbyArIG1heCgwLCAoKF9hbHQgb3IgSEtfRk9OVCkgLSBIS19FTU9KSV9UQU0pIC8gMikpCiAgICAgICAgICAgICAgICBfZW1vID0gSW1hZ2VDbGlwKHN0cihfZXBhdGgpKQogICAgICAgICAgICAgICAgX2VtbyA9IF93aXRoX2R1cmF0aW9uKF9lbW8sIGR1cl90b3RhbCkKICAgICAgICAgICAgICAgIF9lbW8gPSBfd2l0aF9zdGFydChfZW1vLCAwLjAp', 'ICAgICAgICAgICAgaWYgX2VwYXRoIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgX3lfZW1vID0gSEtfWSArIF9lbW9qaV9saW5oYSAqIEhLX0FMVFVSQV9MSU5IQQogICAgICAgICAgICAgICAgX2x3ID0gX2xhcmcoX2xpbmhhc1tfZW1vamlfbGluaGFdLCBIS19GT05UKQogICAgICAgICAgICAgICAgX3R4bSA9IGludChvcy5lbnZpcm9uLmdldCgiVFhUX01BUkdFTSIsIDgpKQogICAgICAgICAgICAgICAgIyB4OiBkZXBvaXMgZG8gZmltIFJFQUwgZG8gdGV4dG8gKG1hcmdlbSArIGxhcmd1cmEpICsgZm9sZ2EgdHVuw6F2ZWwKICAgICAgICAgICAgICAgIF9leCA9IG1heCgxMCwgbWluKEhLX01BUkdFTSArIF90eG0gKyAoX2x3IG9yIGludChMQVJHVVJBICogMC41KSkKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICsgaW50KG9zLmVudmlyb24uZ2V0KCJIS19FTU9KSV9EWCIsIDE4KSksCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBMQVJHVVJBIC0gSEtfRU1PSklfVEFNIC0gMTApKQogICAgICAgICAgICAgICAgIyB5OiBjZW50cmEgcGVsYSBBTFRVUkEgREEgRk9OVEUgKGNvbnNpc3RlbnRlIGVudHJlIGNsYXJvL2VzY3VybzsgbwogICAgICAgICAgICAgICAgIyBfYWx0IGRvIGNsaXAgdmFyaWEgY29tIG8gY29udG9ybm8pICsgbnVkZ2UgZmlubyBIS19FTU9KSV9EWS4KICAgICAgICAgICAgICAgIF9leSA9IGludChfeV9lbW8gKyBfdHhtICsgKEhLX0ZPTlQgLSBIS19FTU9KSV9UQU0pIC8gMgogICAgICAgICAgICAgICAgICAgICAgICAgICsgaW50KG9zLmVudmlyb24uZ2V0KCJIS19FTU9KSV9EWSIsIDApKSkKICAgICAgICAgICAgICAgIF9lbW8gPSBJbWFnZUNsaXAoc3RyKF9lcGF0aCkpCiAgICAgICAgICAgICAgICBfZW1vID0gX3dpdGhfZHVyYXRpb24oX2VtbywgZHVyX3RvdGFsKQogICAgICAgICAgICAgICAgX2VtbyA9IF93aXRoX3N0YXJ0KF9lbW8sIDAuMCk=')]
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
