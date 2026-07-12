#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_camada2_site.py -- _registrar_no_site entende `plataforma`: Amazon nao
# busca foto na Shopee e a fila do site marca a plataforma (Shopee/Amazon).
# Roda de dentro de ~/jarvis. Depois: systemctl restart jarvis
import sys, base64, shutil, py_compile
from pathlib import Path
HUN=Path("integrations/telegram_repurpose_hunter.py")
d=lambda s: base64.b64decode(s).decode("utf-8")
JOBS=[(HUN,'plataforma: str = "shopee"',[(d("ZGVmIF9yZWdpc3RyYXJfbm9fc2l0ZShub21lOiBzdHIsIGxpbms6IHN0ciwgaW1hZ2VtOiBzdHIgPSAiIiwgbWF4X2l0ZW5zOiBpbnQgPSA4MCk6"),d("ZGVmIF9yZWdpc3RyYXJfbm9fc2l0ZShub21lOiBzdHIsIGxpbms6IHN0ciwgaW1hZ2VtOiBzdHIgPSAiIiwgbWF4X2l0ZW5zOiBpbnQgPSA4MCwKICAgICAgICAgICAgICAgICAgICAgICBwbGF0YWZvcm1hOiBzdHIgPSAic2hvcGVlIik6")),(d("ICAgIGlmIG5vdCBpbWFnZW06CiAgICAgICAgaW1hZ2VtID0gX2ZvdG9fb2ZpY2lhbF9kb19saW5rKGxpbmspICAgIyBmb3RvIG9maWNpYWwgKEFQSSBkZSBhZmlsaWFkbyk="),d("ICAgIGlmIG5vdCBpbWFnZW0gYW5kIHBsYXRhZm9ybWEgPT0gInNob3BlZSI6CiAgICAgICAgaW1hZ2VtID0gX2ZvdG9fb2ZpY2lhbF9kb19saW5rKGxpbmspICAgIyBmb3RvIG9maWNpYWwgKEFQSSBkZSBhZmlsaWFkbyBTaG9wZWUp")),(d("ZmlsYS5pbnNlcnQoMCwgewogICAgICAgICAgICAicHJvZHV0byI6IG5vbWUsICJjYW1wZWFvIjogbm9tZSwgImxpbmsiOiBsaW5rLAogICAgICAgICAgICAiaW1hZ2VtIjogaW1hZ2VtIG9yICIiLCAiY2xhc3NlIjogIiIsICJ0cyI6IGludCh0aW1lLnRpbWUoKSksCiAgICAgICAgfSk="),d("ZmlsYS5pbnNlcnQoMCwgewogICAgICAgICAgICAicHJvZHV0byI6IG5vbWUsICJjYW1wZWFvIjogbm9tZSwgImxpbmsiOiBsaW5rLAogICAgICAgICAgICAiaW1hZ2VtIjogaW1hZ2VtIG9yICIiLCAiY2xhc3NlIjogIiIsICJwbGF0YWZvcm1hIjogcGxhdGFmb3JtYSwKICAgICAgICAgICAgInRzIjogaW50KHRpbWUudGltZSgpKSwKICAgICAgICB9KQ=="))])]
def main():
    rc=0
    for alvo,marca,reps in JOBS:
        if not alvo.exists(): print("PULO (nao existe):",alvo); rc=2; continue
        s=alvo.read_text(encoding="utf-8").replace("\r\n","\n")
        if marca in s: print("JA APLICADO:",alvo); continue
        if any(o not in s for o,_ in reps): print("ABORTADO (bloco diferente):",alvo); rc=2; continue
        bak=alvo.with_suffix(alvo.suffix+".bak_camada2"); shutil.copy2(alvo,bak)
        for o,n in reps: s=s.replace(o,n,1)
        alvo.write_text(s,encoding="utf-8")
        try: py_compile.compile(str(alvo),doraise=True); print("OK:",alvo,"(backup:",bak.name,")")
        except Exception as ex: shutil.copy2(bak,alvo); print("ERRO->restaurei:",alvo,ex); rc=4
    return rc
if __name__=="__main__": sys.exit(main())
