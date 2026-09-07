#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_adulto.py -- o filtro +18 barra o que tem que barrar SEM comer a fila
#
# POR QUE ISTO EXISTE (07/09/2026)
# ────────────────────────────────
# O Dre: *"reparei nas promos da Alana no WhatsApp, ela postou um masturbador,
# +18. Não quero que nada disso seja postado no meu grupo!! falta de respeito."*
#
# O projeto não tinha NENHUM filtro disso — procurei em todos os .py.
#
# ⚠️ OS DOIS ERROS AQUI SÃO GRAVES, E POR MOTIVOS OPOSTOS:
#   · falso NEGATIVO → um item +18 vai pro grupo do cliente. É irreversível na
#     hora e é exatamente o que ele mandou impedir.
#   · falso POSITIVO → some produto honesto da fila EM SILÊNCIO. E as palavras
#     do vocabulário adulto são palavras COMUNS de catálogo: "plug" (adaptador
#     de tomada), "lubrificante" (de corrente de bicicleta), "boneca" (de pano),
#     "anel" (de vedação), "bomba" (d'água). Uma lista ingênua de palavras
#     proibidas destruiria dezenas de produtos bons sem ninguém entender por quê
#     — e sumir em silêncio é como este projeto vem perdendo coisa há semanas.
#
# Por isso a metade de baixo do arquivo é maior que a de cima: provar que o
# filtro NÃO dispara é mais trabalhoso do que provar que ele dispara.
#
#   python3 teste_adulto.py
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from shared.termos import conteudo_adulto           # noqa: E402

ok = falhou = 0


def barra(nome, desc="", cat=""):
    global ok, falhou
    veta, motivo = conteudo_adulto(nome, desc, cat)
    if veta:
        ok += 1
        print(f"   ✅ 🔞 {nome[:52]:54} {motivo}")
    else:
        falhou += 1
        print(f"   ❌ PASSOU e não podia: {nome}")


def passa(nome, desc="", cat=""):
    global ok, falhou
    veta, motivo = conteudo_adulto(nome, desc, cat)
    if not veta:
        ok += 1
        print(f"   ✅ ✔  {nome[:60]}")
    else:
        falhou += 1
        print(f"   ❌ BARROU produto honesto: {nome}\n      motivo: {motivo}")


print("\n── o caso do Dre, e os vizinhos dele ──")
barra("Masturbador Masculino Realista")
barra("Vibrador Ponto G Recarregável 10 Velocidades")
barra("Plug Anal Iniciante Silicone Médio")
barra("Kit Sex Shop Casal Completo")
barra("Preservativo Sensitive 12 unidades")
barra("Boneca Inflável Adulto")
barra("Gel Lubrificante Íntimo Base Água 100ml")
barra("Anel Peniano Vibratório")
barra("Calcinha Comestível Sabor Morango")
barra("Sugador de Clitóris Recarregável")

print("\n── o termo explícito só na CATEGORIA (título limpo) ──")
# a loja às vezes deixa o título neutro e revela na categoria — é o caso que
# um filtro de nome puro deixaria passar
barra("Massageador Recarregável 10 Velocidades", "",
      "Saúde > Bem-estar sexual > Estimulador")
barra("Kit Presente Especial Casal", "acompanha gel excitante e vela sensual")

print("\n── ⚠️ NÃO PODE BARRAR: 'plug' é adaptador de tomada ──")
passa("Plug Adaptador de Tomada 3 Pinos 10A")
passa("Plug Macho P2 Estéreo Dourado")
passa("Kit 10 Plugs de Vedação para Pia")

print("\n── ⚠️ NÃO PODE BARRAR: as outras palavras ambíguas ──")
passa("Lubrificante de Corrente de Bicicleta 100ml")
passa("Massageador Vibratório Muscular Portátil")
passa("Massageador de Pés Elétrico Shiatsu")
passa("Boneca de Pano Artesanal Infantil")
passa("Boneca Reborn Realista Bebê 55cm")
passa("Anel de Prata 925 Feminino Ajustável")
passa("Anel de Vedação Silicone para Panela de Pressão")
passa("Bomba d'Água Submersa 12V para Aquário")
passa("Bomba de Encher Pneu Portátil Digital")
passa("Gel Fixador de Cabelo Forte 300g")
passa("Gel Antisséptico para as Mãos 500ml")
passa("Vela Aromática Lavanda Pote de Vidro")
passa("Baralho de Cartas Plástico Impermeável")
passa("Sabonete Íntimo Feminino pH Balanceado")
passa("Óleo de Coco Extra Virgem 200ml")
passa("Kit 6 Calcinhas Algodão Feminina")
passa("Pijama de Casal Manga Longa Inverno")
passa("Jogo de Cama Casal 4 Peças 200 Fios")

print("\n── ⚠️ A ARMADILHA DO 'ANAL' DENTRO DE OUTRA PALAVRA ──")
# sem borda de palavra, "anal" casa dentro de canal/analisador/analógico — e
# "canal" já é palavra comum nesta fila (veio de chamada de canal do Telegram)
passa("Cabo Canal HDMI 2.0 4K 2 metros")
passa("Analisador de Bateria Automotivo 12V")
passa("Relógio Analógico Masculino Couro")
passa("Canal de Drenagem para Quintal 1m")
passa("Termômetro Digital com Canal Duplo")

print("\n── bordas ──")
passa("")
passa("Produto")
barra("MASTURBADOR MASCULINO")            # caixa alta
barra("Masturbador")                       # sozinho
barra("plug anal")                         # minúsculo
barra("Vibrador Erótico")                  # dois termos diretos

print(f"\n{'='*70}\n   {ok} passou · {falhou} falhou\n{'='*70}")
raise SystemExit(1 if falhou else 0)
