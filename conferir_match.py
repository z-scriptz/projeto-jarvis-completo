#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# conferir_match.py -- o vídeo mostra o MESMO produto que o link vende?
#
# POR QUE ISSO EXISTE (05/09/2026)
# ────────────────────────────────
# O match com a loja é por SOBREPOSIÇÃO DE PALAVRAS, e isso deixa passar coisas
# que nenhum humano deixaria — todos tirados do log de verdade:
#
#   'Abridor de Casca de Ovo'  → 'Copo Térmico 360ml Inox'   (casou: abridor, casca)
#   'Estação de pintura'       → 'Estação Férrea Miniatura'  (casou: estacao)
#   'July July'                → 'Kit 3 Sutiã Básico'        (casou: july)
#   'This'                     → 'Camiseta THIS & THAT'      (casou: this)
#
# O post sai bonito, o link ABRE, e a pessoa recebe outra coisa. Isso é pior que
# link morto: o clique acontece e queima a confiança de quem clicou.
#
# 📌 O DRE PERGUNTOU "daria pra tirar print do produto e jogar no Google?".
# A ideia está certa; o Google é que não serve — o Lens não tem API pública,
# e o SerpAPI custa ~US$50/mês. Mas nós temos algo MELHOR e já pago: o frame do
# vídeo E a foto do produto na loja. Comparar os dois é mais preciso que busca
# reversa, porque confere contra o candidato específico em vez de procurar no
# mundo inteiro.
#
# ⚠️ RODA NO QUE JÁ ESTÁ NA FILA. Os 2171 pacotes do inbox já têm o vídeo
# baixado e a URL da foto no plano.json — dá pra achar os matches errados que
# JÁ estão lá, sem coletar nada de novo.
#
# Uso (VPS):
#   .venv/bin/python conferir_match.py --amostra 20     # MEDE custo e acerto
#   .venv/bin/python conferir_match.py                  # confere tudo (só lista)
#   .venv/bin/python conferir_match.py --marcar         # bloqueia os errados
#
# ── SEGUNDA VIA: os que não têm foto de loja (06/09/2026) ───────────────────
# 657 pacotes têm link de BUSCA da Amazon, sem foto de produto. O juiz de
# imagem×imagem não tinha o que comparar e pulava todos — e são justamente
# esses que estão produzindo agora. `--sem-foto` compara o frame com o NOME do
# produto. Juiz mais fraco (texto descreve menos que foto), então passa pelo
# MESMO controle negativo antes de bloquear:
#   .venv/bin/python conferir_match.py --sem-foto --controle 40
#   .venv/bin/python conferir_match.py --sem-foto --marcar
import argparse
import json
import os
import random
import subprocess
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INBOX = BASE_DIR / "inbox_tiktok"
MODELO = os.getenv("GEMINI_MODELO_MATCH", "gemini-2.5-flash")


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        return cand
    return None


def _frame(video: Path, dur: float = 0) -> bytes:
    """UM frame do meio do vídeo. Um só, de propósito: dois frames dobram o
    custo da imagem e a pergunta aqui é binária ('é o mesmo objeto?'), não
    'que produto é este?' — essa já foi respondida lá atrás pela visão."""
    pos = max(1.0, (float(dur) or 6.0) * 0.5)
    f = video.with_suffix(".match.jpg")
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", f"{pos:.1f}", "-i", str(video),
                        "-vframes", "1", "-vf", "scale=512:-2", "-q:v", "4",
                        str(f)], capture_output=True, timeout=40)
        return f.read_bytes() if f.exists() and f.stat().st_size > 500 else b""
    except Exception:
        return b""
    finally:
        try:
            f.unlink()
        except Exception:
            pass


def _contato(pares, destino: Path) -> Path:
    """Uma folha com os pares lado a lado: vídeo à esquerda, loja à direita.

    ⚠️ ISTO EXISTE PORQUE O JUIZ PRECISA SER JULGADO (05/09/2026). A primeira
    amostra reprovou 12 de 20 (60%) e deu ZERO "talvez" — num julgamento de
    imagem ambígua, zero incerteza é sinal de modelo defaultando pro NAO, não
    de modelo criterioso. Bloquear 900 pacotes com base num juiz não validado
    seria o mesmo erro de confiar numa medição que eu não conferi.
    O olho do Dre em 10 pares resolve o que nenhuma métrica minha resolve."""
    from PIL import Image, ImageDraw
    import io
    LADO, PAD, ROT = 320, 8, 22
    linhas = len(pares)
    folha = Image.new("RGB", (LADO * 2 + PAD * 3, (LADO + ROT + PAD) * linhas + PAD),
                      (250, 250, 250))
    d = ImageDraw.Draw(folha)
    for i, (nome, veredito, fr, ft) in enumerate(pares):
        y = PAD + i * (LADO + ROT + PAD)
        d.text((PAD, y), f"[{veredito.upper()}] {nome[:70]}", fill=(20, 20, 20))
        for j, raw in enumerate((fr, ft)):
            x = PAD + j * (LADO + PAD)
            try:
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((LADO, LADO))
                folha.paste(im, (x, y + ROT))
            except Exception:
                d.rectangle([x, y + ROT, x + LADO, y + ROT + LADO],
                            outline=(200, 60, 60))
    destino.parent.mkdir(parents=True, exist_ok=True)
    folha.save(str(destino), quality=88)
    return destino


def _baixar_imagem(url: str) -> bytes:
    if not url or not url.startswith("http"):
        return b""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read(3_000_000)
        return b if len(b) > 500 else b""
    except Exception:
        return b""


_PROMPT = (
    "Duas imagens. A PRIMEIRA é um quadro de um vídeo que mostra um produto. "
    "A SEGUNDA é a foto de um produto anunciado numa loja.\n\n"
    "PERGUNTA: é o MESMO produto, ou pelo menos o mesmo TIPO de produto que "
    "resolve a mesma coisa?\n\n"
    "Responda SÓ uma palavra:\n"
    "SIM  — mesmo produto ou mesmo tipo (cor/marca/modelo diferentes tudo bem)\n"
    "NAO  — produtos diferentes, quem clicasse receberia outra coisa\n"
    "TALVEZ — o quadro do vídeo não deixa ver o produto direito\n\n"
    "⚠️ Na dúvida entre SIM e NAO, responda TALVEZ. Só diga NAO quando as duas "
    "imagens mostram claramente coisas diferentes."
)


def ler_controle(rep_ctl: float, rep_real: float, piso=0.75, margem=0.15) -> str:
    """A leitura do controle negativo, separada pra poder ser testada sem API.

    'frouxo'  — deixou passar par errado de fábrica: os ✅ dele não valem nada
    'cego'    — reprova real e embaralhado quase igual: não está julgando
    'presta'  — separa os dois: os ❌ dos reais são pra levar a sério

    ⚠️ piso é 0.75 e não 1.0 de propósito: dois produtos diferentes podem ser do
    MESMO TIPO (dois suportes de celular), e aí o SIM no embaralhado está certo.
    """
    # ⚠️ A ORDEM IMPORTA e eu errei ela na primeira versão (o teste pegou).
    # 'cego' vem PRIMEIRO porque engole 'frouxo': se ele reprova real e
    # embaralhado na mesma taxa, não adianta dizer "os ✅ é que não prestam" —
    # os ❌ também não prestam. Só depois de provar que ele DISCRIMINA é que
    # faz sentido reclamar que ele aprova par errado demais.
    if rep_real >= rep_ctl - margem:
        return "cego"
    if rep_ctl < piso:
        return "frouxo"
    return "presta"


_PROMPT_NOME = (
    "Um quadro de um vídeo curto que mostra alguém usando ou exibindo um "
    "produto.\n\n"
    "PERGUNTA: o produto que aparece neste quadro é «{nome}», ou pelo menos "
    "algo do MESMO TIPO, que serve pra mesma coisa?\n\n"
    "Responda SÓ uma palavra:\n"
    "SIM  — é esse produto ou um do mesmo tipo (marca/cor/modelo diferentes "
    "tudo bem)\n"
    "NAO  — o vídeo mostra outra coisa; quem clicasse receberia outro produto\n"
    "TALVEZ — o quadro não deixa ver o produto direito\n\n"
    "⚠️ Na dúvida entre SIM e NAO, responda TALVEZ. Só diga NAO quando o que "
    "aparece claramente não é isso."
)


def conferir_nome(frame: bytes, nome: str) -> tuple:
    """(veredito, tokens) — o vídeo mostra o produto que o LINK diz vender?

    ⚠️ POR QUE ESTA SEGUNDA VIA EXISTE (06/09/2026). 657 pacotes do inbox têm
    link de BUSCA da Amazon, sem foto de produto — o `conferir()` não tinha o
    que comparar e pulava todos. São justamente esses que estão produzindo
    agora, e é deles que vem boa parte do "o hook diz uma coisa e o vídeo é
    outra" que o Dre viu.

    Sem foto, o único lado confiável é o NOME. É um juiz mais fraco que o de
    imagem×imagem (texto descreve menos que uma foto), e por isso ele passa
    pelo MESMO controle negativo antes de bloquear qualquer coisa.
    """
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not frame or not (nome or "").strip():
        return "erro", 0
    try:
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=key)
        r = cli.models.generate_content(
            model=MODELO,
            contents=[types.Part.from_bytes(data=frame, mime_type="image/jpeg"),
                      _PROMPT_NOME.format(nome=nome.strip()[:120])])
        t = (r.text or "").strip().upper()
        u = getattr(r, "usage_metadata", None)
        toks = int(getattr(u, "total_token_count", 0) or 0) if u else 0
        if t.startswith("SIM"):
            return "sim", toks
        if t.startswith("NAO") or t.startswith("NÃO"):
            return "nao", toks
        if t.startswith("TALVEZ"):
            return "talvez", toks
        return "erro", toks
    except Exception as e:
        print(f"      ⚠️ {str(e)[:70]}")
        return "erro", 0


def conferir(frame: bytes, foto: bytes) -> tuple:
    """(veredito, custo_tokens). Veredito: sim / nao / talvez / erro."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not frame or not foto:
        return "erro", 0
    try:
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=key)
        r = cli.models.generate_content(
            model=MODELO,
            contents=[types.Part.from_bytes(data=frame, mime_type="image/jpeg"),
                      types.Part.from_bytes(data=foto, mime_type="image/jpeg"),
                      _PROMPT])
        t = (r.text or "").strip().upper()
        # ⚠️ o número de tokens vem do PRÓPRIO retorno, não de estimativa minha.
        # Foi estimativa minha ("são centavos") que virou R$50 em 04/09.
        u = getattr(r, "usage_metadata", None)
        toks = int(getattr(u, "total_token_count", 0) or 0) if u else 0
        if t.startswith("SIM"):
            return "sim", toks
        if t.startswith("NAO") or t.startswith("NÃO"):
            return "nao", toks
        if t.startswith("TALVEZ"):
            return "talvez", toks
        return "erro", toks
    except Exception as e:
        print(f"      ⚠️ {str(e)[:70]}")
        return "erro", 0


def main() -> int:
    ap = argparse.ArgumentParser(description="o vídeo mostra o produto do link?")
    ap.add_argument("--amostra", type=int, default=0,
                    help="confere só N pacotes sorteados e MEDE custo/acerto")
    ap.add_argument("--marcar", action="store_true",
                    help="bloqueia os reprovados (sem isto, só lista)")
    ap.add_argument("--sem-foto", action="store_true", dest="sem_foto",
                    help="confere os pacotes SEM foto de loja (link de busca "
                         "da Amazon, 657 deles) comparando o vídeo com o NOME "
                         "do produto em vez da foto")
    ap.add_argument("--controle", type=int, default=0, metavar="N",
                    help="CONTROLE NEGATIVO: confere N pacotes de verdade E os "
                         "mesmos N com os pares EMBARALHADOS (frame de um, foto "
                         "de outro). Mede se o juiz sabe julgar, sem depender de "
                         "ninguém olhar. Gasta 2N chamadas e não marca nada.")
    ap.add_argument("--provas", metavar="DIR", default="",
                    help="salva os pares (frame do vídeo | foto da loja) num "
                         "contato pra CONFERIR O JUIZ com o olho, antes de "
                         "confiar no veredito. NÃO gasta API a mais.")
    a = ap.parse_args()
    if a.controle:
        # o controle é uma MEDIÇÃO do juiz. Deixar ele escrever no plano.json
        # seria gravar veredito de uma rodada montada pra testar, não pra valer.
        a.amostra = a.controle
        a.marcar = False

    arq = _carregar_env()
    print(f"📄 .env: {arq or '(não achei — vai falhar)'}")
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY vazio — abortando antes de gastar tempo")
        return 1
    if not INBOX.exists():
        print(f"❌ {INBOX} não existe")
        return 1

    # só o que dá pra conferir: precisa de vídeo E de foto da loja.
    # Pacote de Amazon não tem foto (o link é busca), então fica de fora — e
    # isso é metade do inbox. Dizer "confere tudo" seria mentira.
    alvos = []
    sem_foto = 0
    for pj in sorted(INBOX.glob("*/plano.json")):
        try:
            info = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if info.get("nao_e_produto") or info.get("match_conferido"):
            continue
        vids = list(pj.parent.glob("video.*"))
        if not vids:
            continue
        tem_foto = (info.get("imagem") or "").startswith("http")
        if tem_foto == a.sem_foto:      # cada modo pega o conjunto que é seu
            sem_foto += 1
            continue
        if a.sem_foto and not (info.get("produto") or "").strip():
            sem_foto += 1               # sem foto E sem nome: não há o que conferir
            continue
        alvos.append((pj, info, vids[0]))

    if a.sem_foto:
        print(f"📦 {len(alvos)} pacote(s) SEM foto de loja (confere pelo NOME) "
              f"· {sem_foto} fora deste modo\n")
    else:
        print(f"📦 {len(alvos)} pacote(s) conferíveis "
              f"(vídeo + foto da loja) · {sem_foto} sem foto (Amazon/busca)\n")
    if not alvos:
        print("✅ nada a conferir")
        return 0

    total_conferivel = len(alvos)      # guardado ANTES de cortar a amostra
    if a.amostra:
        random.shuffle(alvos)
        alvos = alvos[:a.amostra]
        print(f"🔬 MODO AMOSTRA: {len(alvos)} de {total_conferivel} sorteados, "
              f"nada será marcado\n")

    t0 = time.time()
    tot = {"sim": 0, "nao": 0, "talvez": 0, "erro": 0}
    tokens = 0
    reprovados = []
    provas = []
    coletados = []          # (nome, frame, foto) — só usado pelo --controle

    for pj, info, vid in alvos:
        nome = (info.get("produto") or "?")[:38]
        # ⚠️ o plano.json NÃO guarda duração (conferi os campos que o coletor
        # escreve). Passar `info.get("duracao")` seria ler um campo que não
        # existe e achar que estou usando a duração real — o `_frame` cai no
        # padrão de 6s e tira o quadro aos 3s, que é o que de fato acontece.
        frame = _frame(vid)
        if a.sem_foto:
            foto = b""                      # não há foto: o outro lado é o nome
            veredito, tk = conferir_nome(frame, info.get("produto") or "")
        else:
            foto = _baixar_imagem(info.get("imagem", ""))
            veredito, tk = conferir(frame, foto)
        tokens += tk
        tot[veredito] = tot.get(veredito, 0) + 1

        marca = {"sim": "✅", "nao": "❌", "talvez": "🤔", "erro": "⚠️"}[veredito]
        print(f"   {marca} {nome:40} · {pj.parent.name[:30]}")
        if veredito == "nao":
            reprovados.append((pj, info, nome))
        if a.provas and frame and foto:
            provas.append((nome, veredito, frame, foto))
        if a.controle and frame and (foto or a.sem_foto):
            # guarda o que JÁ foi baixado — o controle não baixa nada de novo.
            # No modo --sem-foto o 3º item é o NOME COMPLETO, que é contra o
            # que o juiz compara ali.
            coletados.append((nome, frame,
                              (info.get("produto") or "") if a.sem_foto else foto))

        if a.marcar and veredito == "nao":
            # ⚠️ MARCA, NÃO APAGA — mesma regra do limpar_inbox. Um veredito de
            # modelo errado tem de ser reversível tirando uma chave do JSON.
            info["nao_e_produto"] = True
            # ⚠️ o motivo diz QUAL juiz bloqueou. O do nome é mais fraco que o
            # de imagem×imagem, e se um dia a gente quiser revisar só o que ele
            # barrou, tem que dar pra separar.
            info["motivo_bloqueio"] = (
                "conferir_match(nome): vídeo não mostra o produto do link"
                if a.sem_foto else
                "conferir_match: vídeo não mostra o produto do link")
        if a.marcar:
            info["match_conferido"] = veredito
            pj.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    seg = time.time() - t0
    n = len(alvos)
    print(f"\n── resultado ──")
    print(f"   ✅ {tot['sim']} confere · ❌ {tot['nao']} ERRADO · "
          f"🤔 {tot['talvez']} incerto · ⚠️ {tot['erro']} falhou")
    print(f"   ⏱️  {seg:.0f}s ({seg/max(1,n):.1f}s por pacote)")

    if tokens:
        # ⚠️ CUSTO MEDIDO, NÃO ESTIMADO. Em 04/09 eu disse "são centavos" sobre
        # 2171 chamadas e o Dre gastou R$50+. O preço vem do .env pra não ficar
        # chumbado errado aqui dentro.
        usd_mtok = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
        brl_usd = float(os.getenv("USD_BRL", "5.40"))
        custo = tokens / 1_000_000 * usd_mtok * brl_usd
        print(f"   🪙 {tokens:,} tokens · R$ {custo:.2f} nesta rodada "
              f"(R$ {custo/max(1,n):.4f} por pacote)")
        if a.amostra:
            proj = custo / max(1, n) * total_conferivel
            print(f"   📊 PROJEÇÃO pros {total_conferivel} conferíveis: "
                  f"R$ {proj:.2f}  ({seg/max(1,n)*total_conferivel/60:.0f} min)")
            print(f"      ⚠️ projeção, não medição — o número real sai da rodada "
                  f"cheia. Mas é conta, não palpite.")

    if a.controle:
        if len(coletados) < 4:
            print(f"\n⚠️ só {len(coletados)} par(es) completo(s) — poucos pra "
                  f"controle. Rode com --controle maior.")
        else:
            print(f"\n── controle negativo ──")
            print(f"   mesmos {len(coletados)} frames, mas cada um contra a foto "
                  f"do produto SEGUINTE.")
            print(f"   são pares errados de fábrica: o juiz TEM que reprovar.\n")
            ctl = {"sim": 0, "nao": 0, "talvez": 0, "erro": 0}
            tk_ctl = 0
            for i, (nome, frame, _f) in enumerate(coletados):
                outro_nome, _fr, outro_lado = coletados[(i + 1) % len(coletados)]
                v, tk = (conferir_nome(frame, outro_lado) if a.sem_foto
                         else conferir(frame, outro_lado))
                tk_ctl += tk
                ctl[v] = ctl.get(v, 0) + 1
                marca = {"sim": "✅", "nao": "❌", "talvez": "🤔", "erro": "⚠️"}[v]
                print(f"   {marca} {nome[:30]:32} × foto de {outro_nome[:28]}")
                if a.provas and not a.sem_foto:
                    provas.append((f"[EMBARALHADO] {nome} × {outro_nome}",
                                   v, frame, outro_lado))

            n_ctl = len(coletados)
            rep_ctl = ctl["nao"] / n_ctl                    # devia ser ~1.0
            rep_real = tot["nao"] / max(1, n)               # o que medimos antes
            if tk_ctl:
                usd_mtok = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
                brl_usd = float(os.getenv("USD_BRL", "5.40"))
                print(f"\n   🪙 controle: {tk_ctl:,} tokens · "
                      f"R$ {tk_ctl/1_000_000*usd_mtok*brl_usd:.2f}")
            print(f"\n   reprova nos pares EMBARALHADOS: {ctl['nao']}/{n_ctl} "
                  f"({rep_ctl*100:.0f}%)")
            print(f"   reprova nos pares REAIS:         {tot['nao']}/{n} "
                  f"({rep_real*100:.0f}%)")

            # ⚠️ A LEITURA É O PONTO. Sem isto, o número volta a virar palpite.
            # O juiz só serve se separar par certo de par errado. Se ele reprova
            # os dois igual, ele não está olhando — está chutando NAO.
            print()
            leitura = ler_controle(rep_ctl, rep_real)
            if leitura == "frouxo":
                print(f"   ❌ JUIZ QUEBRADO ao contrário: deixou passar "
                      f"{n_ctl - ctl['nao']} par(es) que são errados de fábrica.")
                print(f"      Ele diz SIM fácil demais. Os ❌ dos reais podem até "
                      f"estar certos, mas os ✅ não valem nada.")
            elif leitura == "cego":
                print(f"   ❌ JUIZ NÃO ESTÁ JULGANDO: reprova real e embaralhado "
                      f"quase igual.")
                print(f"      O defeito é meu (1 frame só / foto de kit vs produto "
                      f"em uso). Conserto antes de qualquer bloqueio.")
            else:
                print(f"   ✅ JUIZ DISCRIMINA: separa par errado de par certo por "
                      f"{(rep_ctl - rep_real)*100:.0f} pontos.")
                print(f"      Então os {tot['nao']} ❌ dos reais são pra levar a "
                      f"sério: {rep_real*100:.0f}% da fila vende outra coisa.")
            print(f"\n   ⚠️ ressalva honesta: dois produtos DIFERENTES podem ser do "
                  f"mesmo TIPO\n      (dois suportes de celular), e aí SIM no "
                  f"embaralhado está certo. Por isso\n      o corte é 75%, não 100%.")

    if a.provas and a.sem_foto:
        print("\n   ⚠️ --provas não vale no modo --sem-foto: o outro lado da "
              "comparação é\n      TEXTO, não imagem. Não há par pra olhar. "
              "Quem julga o juiz aqui\n      é o --controle.")

    if provas:
        try:
            alvo = Path(a.provas)
            if alvo.is_dir() or not alvo.suffix:
                alvo = alvo / "provas_match.jpg"
            _contato(provas, alvo)
            print(f"\n   🖼️  provas em {alvo}  ({len(provas)} pares)")
            print(f"      esquerda = frame do vídeo · direita = foto da loja")
            print(f"      ⚠️ OLHE ANTES DE MARCAR. Se os ❌ parecerem certos pra")
            print(f"         você, o juiz presta. Se não, o defeito é meu.")
        except Exception as e:
            print(f"\n   ⚠️ não consegui montar as provas: {str(e)[:70]}")

    if reprovados and not a.marcar:
        print(f"\n❌ {len(reprovados)} com link de produto ERRADO:")
        for _pj, _i, nm in reprovados[:20]:
            print(f"   • {nm}")
        print(f"\n📋 pra bloquear: .venv/bin/python conferir_match.py --marcar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
