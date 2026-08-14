#!/usr/bin/env python3
# add_fontes.py -- adiciona canais de achadinho (que postam VÍDEO) às fontes do
# Jarvis: entra no hunter_canais (o hunter reproduz os vídeos) e no grupos.txt
# (o radar lê os produtos). Dedup, idempotente, preserva o resto do config.
#
# Uso (VPS):
#   python3 add_fontes.py @canal1 @canal2 https://t.me/canal3
#   python3 add_fontes.py            # (sem args) lê de novas_fontes.txt (1 por linha)
#   python3 add_fontes.py --listar   # só mostra as fontes atuais
import re
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG = BASE_DIR / "shared" / "content_plans" / "agendador_config.json"
GRUPOS_TXT = BASE_DIR / "grupos.txt"
NOVAS_TXT = BASE_DIR / "novas_fontes.txt"


def _norm(u: str) -> str:
    """Normaliza pra @username. Aceita @x, x, https://t.me/x, t.me/x."""
    u = (u or "").strip()
    if not u:
        return ""
    u = re.sub(r"^https?://", "", u, flags=re.I)
    u = re.sub(r"^t\.me/", "", u, flags=re.I)
    u = u.lstrip("@").strip("/").strip()
    u = u.split("/")[0].split("?")[0]
    if not u or not re.match(r"^[A-Za-z0-9_]{3,}$", u):
        return ""
    return "@" + u


def _carregar_config() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            print(f"⚠️  config ilegível em {CONFIG} — abortando (não sobrescrevo)")
            sys.exit(2)
    return {}


def _salvar_config(cfg: dict):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG)


def _grupos_txt_atuais() -> list:
    if not GRUPOS_TXT.exists():
        return []
    linhas = []
    for l in GRUPOS_TXT.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if l and not l.startswith("#"):
            linhas.append(l)
    return linhas


def _coletar_entradas() -> list:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        brutos = []
        for a in args:
            brutos += re.split(r"[,\s]+", a)
        return brutos
    if NOVAS_TXT.exists():
        return NOVAS_TXT.read_text(encoding="utf-8").splitlines()
    return []


def main():
    cfg = _carregar_config()
    hunter = cfg.get("hunter_canais") or []
    hunter_norm = {_norm(c): c for c in hunter if _norm(c)}

    if "--listar" in sys.argv[1:]:
        print(f"📡 hunter_canais ({len(hunter)}):")
        for c in hunter:
            print("   ", c)
        print(f"\n📄 grupos.txt ({len(_grupos_txt_atuais())} linhas)")
        return 0

    brutos = _coletar_entradas()
    novos = []
    for b in brutos:
        n = _norm(b)
        if n and n not in hunter_norm and n not in novos:
            novos.append(n)

    if not brutos:
        print("Nada pra adicionar. Passe canais: python3 add_fontes.py @canal1 @canal2")
        print("(ou crie novas_fontes.txt com 1 canal por linha)")
        return 1
    if not novos:
        print("Todos os canais informados já estavam nas fontes ✔")
        return 0

    # 1) hunter_canais
    hunter.extend(novos)
    cfg["hunter_canais"] = hunter
    _salvar_config(cfg)

    # 2) grupos.txt (radar) — dedup
    atuais = _grupos_txt_atuais()
    atuais_norm = {_norm(g) for g in atuais}
    add_txt = [n for n in novos if n not in atuais_norm]
    if add_txt:
        with open(GRUPOS_TXT, "a", encoding="utf-8") as f:
            if atuais and not GRUPOS_TXT.read_text(encoding="utf-8").endswith("\n"):
                f.write("\n")
            for n in add_txt:
                f.write(n + "\n")

    print(f"✅ {len(novos)} fonte(s) nova(s) adicionada(s):")
    for n in novos:
        print("   +", n)
    print(f"\n📡 hunter_canais agora: {len(hunter)} canais")
    print("Reinicie o daemon pra pegar:  systemctl restart jarvis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
