#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_prompt_vazado.py -- pega o prompt vazado sem levar produto bom junto?
#
# ⚠️ O RISCO AQUI É O FALSO POSITIVO, não o falso negativo. Nome de produto de
# verdade é caótico: CAIXA ALTA, número, barra, parêntese, medida. Se o padrão
# for guloso, ele bloqueia produto bom — e bloquear produto bom custa mais que
# deixar passar um nome estranho, porque a fila é o nosso ativo.
#
# Por isso METADE deste teste são nomes REAIS da fila que NÃO podem ser pegos.
#
#   python3 teste_prompt_vazado.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from caca_prompt_vazado import marca_de_prompt          # noqa: E402

ok = falhou = 0


def pega(desc, nome):
    global ok, falhou
    m = marca_de_prompt(nome)
    if m:
        ok += 1
        print(f"   ✅ pegou · {nome[:52]}")
    else:
        falhou += 1
        print(f"   ❌ DEIXOU PASSAR · {nome[:60]}")


def poupa(nome):
    global ok, falhou
    m = marca_de_prompt(nome)
    if not m:
        ok += 1
        print(f"   ✅ poupou · {nome[:52]}")
    else:
        falhou += 1
        print(f"   ❌ MARCOU PRODUTO BOM · {nome[:48]} → {m}")


print("\n── o caso real, e os parentes dele ──")
pega("o que apareceu na fila", "1) É O NOME DE UM PRODUTO FÍSICO À VENDA")
pega("item numerado", "2. Nome curto do produto em português")
pega("instrução de formato", "Responda APENAS o nome do produto")
pega("rótulo de prompt", "Formato: nome curto, sem marca")
pega("idioma", "Traduza o nome para português do Brasil")
pega("placeholder", "Compre já o {nome} com desconto")
pega("sem markdown", "Nome do produto, sem markdown e sem aspas")

print("\n── PRODUTOS REAIS DA FILA: nenhum pode ser marcado ──")
# ⚠️ todos estes saíram dos logs de produção de verdade
poupa("KIT PLASÚTIL LUXO CESTO ROUPAS INFANTIL BACIA BALDE LIXEIRA")
poupa("Kit 2 Moletom Canguru Com Capuz e Bolso Sem Estampa Liso Unissex")
poupa("Super Rodo 2 em 1 vassoura magica, 78-150cm Escalável")
poupa("Cama Box Baú Queen 158x198x42cm Courino")
poupa("3L Picador De Alimentos Moedor De Carne Elétrico")
poupa("YESOP Escorredor De Louças Rosa 2 Andares")
poupa("Chave do Limpador de Para-brisa Corsa 1996 até 2010 Wind Classic")
poupa("【SHANYIN】Panela de Pressão Inox 10L com Válvula")
poupa("5 Metros Papel De Alumínio Adesivo Impermeável")
poupa("(até 15 kg)Mochila Sling Ajustável para Cachorro")
poupa("1 pa ck/30p cs Pintura Marcadores Papel")
poupa("Kit 3 Sacos Silicone Reutilizável Para Alimentos")
poupa("Filamento Impressora Creality CR-PETG Oficial Premium 3d-1kg 1.75mm")
poupa("Escova de dentes de três lados OralGoso")
poupa("Boneco Colecionável Estátua Action Figure Groot Vaso Pose Marvel")

print("\n── bordas ──")
poupa("")                       # vazio não é prompt vazado
poupa("Torneira")               # nome curto e legítimo
# ⚠️ '1 pa ck/30p cs' começa com número mas NÃO com item numerado ('1)' ou '1.')
poupa("1 Peça Gancho Adesivo De Parede Dobrável")
poupa("2 Limpa Tênis Branco e Colorido Espuma")
# ...e este começa com número E ponto, mas é medida, não item de lista
poupa("2.5L Pote Hermético Com Copo Medidor")

print(f"\n{'='*60}\n   {ok} passou · {falhou} falhou\n{'='*60}")
raise SystemExit(1 if falhou else 0)
