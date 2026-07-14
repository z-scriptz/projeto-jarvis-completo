#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_layout_header.py -- header: nome DEPOIS do logo (sem overlap) + selo colado.
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO=Path(__file__).resolve().parent/"agents/narrated_video_agent.py"
PARES=[('ICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgICAgIGxvZy53YXJuaW5nKGYiICAg4pqg77iPICBMb2dvIFRTIGZhbGhvdToge2V9IikKCiAgICB0ZXh0b194ID0gbG9nb194ICsgbG9nb190YW0gLSAzMgoKICAgICMg4pSA4pSAICdUb3BTaG9wJyBQUkVUTyAoQm9sZCkgY29tIGNvbnRvcm5vIEJSQU5DTyDilIDilIAKICAgIG5vbWUgPSBfdGV4dGNsaXBfZXNxKFRleHRDbGlwLCBNQVJDQV9OT01FLCA1NiwgQ19OT01FLCBTV19OT01FLCBTQ19OT01FLCBmb250ZV9ib2xkKQ==', 'ICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgICAgIGxvZy53YXJuaW5nKGYiICAg4pqg77iPICBMb2dvIFRTIGZhbGhvdToge2V9IikKCiAgICB0ZXh0b194ID0gbG9nb194ICsgbG9nb190YW0gKyBpbnQob3MuZW52aXJvbi5nZXQoIlRFWFRPX0RYIiwgMTYpKSAgIyBERVBPSVMgZG8gbG9nbwoKICAgICMg4pSA4pSAICdUb3BTaG9wJyBQUkVUTyAoQm9sZCkgY29tIGNvbnRvcm5vIEJSQU5DTyDilIDilIAKICAgIG5vbWUgPSBfdGV4dGNsaXBfZXNxKFRleHRDbGlwLCBNQVJDQV9OT01FLCA1NiwgQ19OT01FLCBTV19OT01FLCBTQ19OT01FLCBmb250ZV9ib2xkKQ=='), ('ICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgIHBhc3MKICAgICAgICAgICAgaWYgbGFyZ19yZWFsOgogICAgICAgICAgICAgICAgIyArNTAgZXh0cmE6IGNvbXBlbnNhIGEgY2FpeGEgZG8gVGV4dENsaXAgcXVlIHBvZGUgY2VudHJhbGl6YXIKICAgICAgICAgICAgICAgICMgbyB0ZXh0byAodGV4dF9hbGlnbiBuZW0gc2VtcHJlIMOpIHN1cG9ydGFkbyBwZWxhIHZlcnPDo28pCiAgICAgICAgICAgICAgICBzZWxvX3ggPSB0ZXh0b194ICsgbGFyZ19yZWFsICsgNjQKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIHNlbG9feCA9IHRleHRvX3ggKyAyOTAgICMgZmFsbGJhY2sgZXN0aW1hZG8KICAgICAgICAgICAgc2VsbyA9IEltYWdlQ2xpcChzdHIoc2Vsb19hcGFyYWRvKSkKICAgICAgICAgICAgc2VsbyA9IF93aXRoX2R1cmF0aW9uKHNlbG8sIGR1cl90b3RhbCkKICAgICAgICAgICAgc2VsbyA9IF93aXRoX3N0YXJ0KHNlbG8sIDAuMCk=', 'ICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgIHBhc3MKICAgICAgICAgICAgaWYgbGFyZ19yZWFsOgogICAgICAgICAgICAgICAgIyB0ZXh0byBhZ29yYSDDqSBKVVNUTyAobGFiZWwpIOKGkiBjb2xhIG8gc2VsbyBsb2dvIGFww7NzIG8gbm9tZQogICAgICAgICAgICAgICAgc2Vsb194ID0gdGV4dG9feCArIGxhcmdfcmVhbCArIGludChvcy5lbnZpcm9uLmdldCgiU0VMT19EWCIsIDEyKSkKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIHNlbG9feCA9IHRleHRvX3ggKyAyMDAgICMgZmFsbGJhY2sgZXN0aW1hZG8gKG5vbWUganVzdG8gfjE4MHB4KQogICAgICAgICAgICBzZWxvID0gSW1hZ2VDbGlwKHN0cihzZWxvX2FwYXJhZG8pKQogICAgICAgICAgICBzZWxvID0gX3dpdGhfZHVyYXRpb24oc2VsbywgZHVyX3RvdGFsKQogICAgICAgICAgICBzZWxvID0gX3dpdGhfc3RhcnQoc2VsbywgMC4wKQ==')]
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
