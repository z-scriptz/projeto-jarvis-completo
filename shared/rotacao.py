#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# shared/rotacao.py -- "não repete enquanto houver alternativa", num lugar só
#
# POR QUE ISTO EXISTE (09/09/2026)
# ────────────────────────────────
# O Dre, olhando um Reel do @topshoppet_ que explodiu, com os comentários
# "Eu quero" empilhados: *"esse burro respondendo quase tudo igual, parecendo um
# robozinho, o povo até desanima de comprar, ou para de comentar"*.
#
# Ele estava certo, e dá pra contar nos prints: **6 respostas, 4 frases, e
# "Bio 🔗 dá uma olhada e me fala" três vezes.**
#
# ⚠️ E A REGRA QUE IMPEDE ISSO JÁ EXISTIA — NO ARQUIVO ERRADO. O
# `comentarios.py` (1º comentário do post) tem memória de rotação desde 22/08,
# com o raciocínio todo escrito: sorteio puro repete, tira as recentes do bolo
# primeiro, lembra METADE do banco. O `auto_resposta.py` (resposta aos
# comentários) usa `random.choice` puro e nunca soube dessa regra.
#
# É a quinta vez nesta semana que o defeito tem esta forma: a regra existe, está
# certa, está documentada — e mora num arquivo só. `_so_musica` sem chamador,
# as trilhas que nada lia, o `comentarios.py` morto por 5 dias, o `_frames`
# escrevendo dentro da pasta. Por isso a regra saiu dos dois arquivos e virou
# este: quem precisar de rotação importa daqui, e consertar aqui conserta todos.
#
#   from shared.rotacao import escolher_sem_repetir
#   frase, recentes = escolher_sem_repetir(banco, recentes)
import random

# quantas frases lembrar, no máximo. Teto absoluto — o teto real é METADE do
# banco (ver `escolher_sem_repetir`).
LEMBRAR_PADRAO = 4


def escolher_sem_repetir(candidatas, recentes=None, lembrar: int = LEMBRAR_PADRAO,
                         sorteio=random.choice):
    """Sorteia de `candidatas` evitando as `recentes`. Pura e testável.

    Devolve `(escolhida, novas_recentes)`. Quem chama decide onde guardar a
    lista devolvida — por conta, por post, por formato, tanto faz.

    ⚠️ SORTEIO PURO REPETE. Com 8 frases a chance de sair a mesma da anterior é
    1 em 8; num post viral com 50 comentários isso vira a mesma frase três vezes
    seguidas, que foi exatamente o que o Dre viu.

    ⚠️ E LEMBRAR DE TUDO É O MESMO QUE NÃO LEMBRAR DE NADA. Se `recentes` cobre
    o banco inteiro, `novas` fica vazia e o `or candidatas` cai em sorteio puro
    — o defeito que este módulo existe pra impedir, sem sintoma nenhum além de
    frases repetindo. Por isso o teto é METADE.

    ⚠️ E METADE, NÃO `len-1`. Com 3 frases lembrando 2 sobra exatamente 1
    candidata, e a rotação vira o ciclo fixo 1-2-3-1-2-3: nunca repete e é lido
    como robô do mesmo jeito, só que por regularidade em vez de repetição.
    """
    candidatas = [c for c in (candidatas or []) if c]
    if not candidatas:
        return "", list(recentes or [])
    recentes = list(recentes or [])

    novas = [c for c in candidatas if c not in recentes]
    escolhida = sorteio(novas or candidatas)

    teto = max(1, min(int(lembrar), len(candidatas) // 2))
    return escolhida, ([escolhida] + [r for r in recentes if r != escolhida])[:teto]
