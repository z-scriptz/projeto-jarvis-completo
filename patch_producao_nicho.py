#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_producao_nicho.py -- modo --nicho no produzir_tiktok.py: produz priorizando
# um nicho (tech/beleza/geral). Ex: produzir_tiktok.py --nicho tech 4. Alvo: raiz.
import base64, py_compile, shutil, sys, time
from pathlib import Path
ALVO=Path(__file__).resolve().parent/"produzir_tiktok.py"
PARES=[('ICAgIHJldHVybiBUcnVlCgoKZGVmIG1haW4oKToKICAgIHF1YW50b3MgPSBNQVhfUEFEUkFPCiAgICBpZiBsZW4oc3lzLmFyZ3YpID4gMToKICAgICAgICB0cnk6CiAgICAgICAgICAgIHF1YW50b3MgPSBtYXgoMSwgaW50KHN5cy5hcmd2WzFdKSkKICAgICAgICBleGNlcHQgVmFsdWVFcnJvcjoKICAgICAgICAgICAgcGFzcwoKICAgIGZpbGEgPSBfcGVuZGVudGVzKCkKICAgIGlmIG5vdCBmaWxhOgogICAgICAgIF9sb2coImluYm94X3Rpa3RvayB2YXppbyDigJQgcm9kYSBvIHRpa3Rva19jb2xldG9yLnB5IHByaW1laXJvIChzZW0gLS1kcnkpIikKICAgICAgICByZXR1cm4gMQogICAgX2xvZyhmIntsZW4oZmlsYSl9IHZpcmFsKGlzKSBubyBpbmJveCDCtyBwcm9kdXppbmRvIGF0w6kge3F1YW50b3N9IG5lc3RhIHJvZGFkYSIpCgogICAgb2sgPSAw', 'ICAgIHJldHVybiBUcnVlCgoKZGVmIF9uaWNob19kYV9wYXN0YShwajogUGF0aCkgLT4gc3RyOgogICAgIiIiTmljaG8gZG8gcHJvZHV0byBkZSB1bWEgcGFzdGEgZGEgZmlsYSAocHJhIGZpbHRyYXIgcHJvZHXDp8OjbyBwb3IgY29udGEpLiIiIgogICAgdHJ5OgogICAgICAgIGluZm8gPSBqc29uLmxvYWRzKHBqLnJlYWRfdGV4dChlbmNvZGluZz0idXRmLTgiKSkKICAgICAgICBub21lID0gaW5mby5nZXQoInByb2R1dG8iKSBvciBpbmZvLmdldCgidGVybW8iKSBvciAiIgogICAgICAgIGNhdCA9ICIiCiAgICAgICAgdHJ5OgogICAgICAgICAgICBmcm9tIGNyZWF0aXZlX2VuZ2luZS5uYXJyYXRpb25fc2NyaXB0X2J1aWxkZXIgaW1wb3J0IF9jYXRlZ29yaWFfZG9fcHJvZHV0bwogICAgICAgICAgICBjYXQgPSBfY2F0ZWdvcmlhX2RvX3Byb2R1dG8obm9tZSkgb3IgIiIKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICBwYXNzCiAgICAgICAgaW1wb3J0IHJvdGVhZG9yX2NvbnRhcyBhcyBfUkMKICAgICAgICByZXR1cm4gX1JDLm5pY2hvX2RvX3Byb2R1dG8obm9tZSwgY2F0KQogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXR1cm4gImdlcmFsIgoKCmRlZiBtYWluKCk6CiAgICAjIGFyZ3M6IFtOXSBlL291ICItLW5pY2hvIFgiLiBFeC46ICdwcm9kdXppcl90aWt0b2sucHkgLS1uaWNobyB0ZWNoIDQnCiAgICBxdWFudG9zID0gTUFYX1BBRFJBTwogICAgbmljaG9fYWx2byA9ICIiCiAgICBfYXJncyA9IHN5cy5hcmd2WzE6XQogICAgZm9yIF9pLCBfYSBpbiBlbnVtZXJhdGUoX2FyZ3MpOgogICAgICAgIGlmIF9hID09ICItLW5pY2hvIiBhbmQgX2kgKyAxIDwgbGVuKF9hcmdzKToKICAgICAgICAgICAgbmljaG9fYWx2byA9IF9hcmdzW19pICsgMV0uc3RyaXAoKS5sb3dlcigpCiAgICAgICAgZWxpZiBfYS5pc2RpZ2l0KCk6CiAgICAgICAgICAgIHF1YW50b3MgPSBtYXgoMSwgaW50KF9hKSkKCiAgICBmaWxhID0gX3BlbmRlbnRlcygpCiAgICBpZiBub3QgZmlsYToKICAgICAgICBfbG9nKCJpbmJveF90aWt0b2sgdmF6aW8g4oCUIHJvZGEgbyB0aWt0b2tfY29sZXRvci5weSBwcmltZWlybyAoc2VtIC0tZHJ5KSIpCiAgICAgICAgcmV0dXJuIDEKICAgIGlmIG5pY2hvX2Fsdm86CiAgICAgICAgZmlsYSA9IFt0IGZvciB0IGluIGZpbGEgaWYgX25pY2hvX2RhX3Bhc3RhKHRbMV0pID09IG5pY2hvX2Fsdm9dCiAgICAgICAgaWYgbm90IGZpbGE6CiAgICAgICAgICAgIF9sb2coZiJuZW5odW0gcHJvZHV0byBkbyBuaWNobyAne25pY2hvX2Fsdm99JyBuYSBmaWxhIGFnb3JhIOKAlCBuYWRhIGEgcHJvZHV6aXIiKQogICAgICAgICAgICByZXR1cm4gMAogICAgICAgIF9sb2coZiJmaWx0cm8gZGUgbmljaG8gJ3tuaWNob19hbHZvfScg4oaSIHtsZW4oZmlsYSl9IG5hIGZpbGEiKQogICAgX2xvZyhmIntsZW4oZmlsYSl9IHZpcmFsKGlzKSBubyBpbmJveCDCtyBwcm9kdXppbmRvIGF0w6kge3F1YW50b3N9IG5lc3RhIHJvZGFkYSIpCgogICAgb2sgPSAw')]
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
