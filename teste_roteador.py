#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_roteador.py -- o produto vai pra conta certa?
#
# OS DEFEITOS QUE ISTO TRAVA (05/09/2026)
# ───────────────────────────────────────
# Numa rodada de 6 vídeos, 2 foram pra conta errada e um terceiro tinha ido no
# dia anterior. Todos com a mesma raiz: a lista de palavras decidia por ORDEM,
# não por quem descreve melhor o produto.
#
#   'Sutiã ... tipo Orelha De Coelho'      → @topshoppet_    (bicho é o FORMATO)
#   'Naninha Para Bebê ... Coelho ou Cão'  → @topshoppet_    (é pra BEBÊ)
#   'Saboneteira ... Para Sabonete Líq.'   → @topshopbeauty._ ('sabonete' venceu
#                                                             'saboneteira')
#
# Um sutiã no perfil de pet não flopa só aquele post: desalinha a conta inteira,
# que é justamente o que precisa de 1.000 seguidores coerentes.
#
#   python3 teste_roteador.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roteador_contas as R          # noqa: E402

ok = falhou = 0


def nicho(txt: str) -> str:
    return R._por_palavra_chave(R._sem_acento(txt.lower()))


def checa(esperado, txt, nota=""):
    global ok, falhou
    obtido = nicho(txt)
    rotulo = f"{txt[:52]}{'…' if len(txt) > 52 else ''}"
    if obtido == esperado:
        ok += 1
        print(f"   ✅ {esperado or '(IA decide)':10} {rotulo}")
    else:
        falhou += 1
        print(f"   ❌ {rotulo}\n      esperava {esperado!r}, veio {obtido!r} {nota}")


print("\n── os três que foram pra conta errada de verdade ──")
checa("moda", "KIT Sutiã Adesivo Levantador de seios invisível Pushup tipo "
              "Orelha De Coelho reutilizável Promoção")
checa("casa", "Saboneteira Dispenser Automático Sensor Infravermelho Para "
              "Sabonete Líquido Detergente Espuma")
# ⚠️ este NÃO tem resposta óbvia por palavra-chave (porta-chupeta de pelúcia
# pra bebê). O certo é a lista SE CALAR e a camada 2 (IA) decidir — devolver
# um palpite errado é pior que devolver nada.
checa("", "Naninha Para Bebê Antialérgica Suporte Para Chupeta Aconchego "
          "Coelho ou Cachorro Pelúcia 40 cm Lavável")

print("\n── o que o veto NÃO pode quebrar: pet de verdade ──")
checa("pet", "Shampoo para cachorro filhote")
checa("pet", "Escova Removedora de Pelos para Cães e Gatos")
checa("pet", "Ração para gato castrado 10kg")
checa("pet", "Coleira antipulgas ajustável")
checa("pet", "Escada Cachorro Gato 60 cm 4 Degraus Segurança")
checa("pet", "Newpet Bebedouro Gato Fonte Água Inox com Filtro")
# o veto 'para bebe' perde pro pet certo — senão isto sairia de pet
checa("pet", "Caminha para pet do quarto do bebê")

print("\n── as regras que os comentários das listas já documentavam ──")
# a ordem PET-primeiro existia por causa deste: 'shampoo' é beleza
checa("pet", "Shampoo para cachorro", "(a ordem antiga protegia este)")
# 'roupa de cama' tinha que ser casa, não moda
checa("casa", "Jogo de roupa de cama casal 4 peças")
# 'escova para pet' não podia virar beleza
checa("pet", "Escova para pet removedora de pelo")

print("\n── prefixo não pode mais comer palavra de outra lista ──")
# 'sabonete'(beleza) casava com o começo de 'saboneteira'(casa)
checa("beleza", "Sabonete facial esfoliante em barra")
checa("beleza", "Creme hidratante para pele seca")
# ...e 'pele' continua pegando o plural, que era o motivo do prefixo existir
checa("beleza", "Máscara para peles oleosas")

print("\n── gênero: a lista tem o masculino, o produto vem no feminino ──")
# ⚠️ ACHADOS PELO diff_roteador NO INBOX REAL, não por mim. Meu primeiro fecho
# aceitava só plural `(?:es|s)?` e derrubou 12 produtos de casa que os meus 18
# testes escolhidos a dedo não pegavam.
checa("casa", "caixas organizadoras")
checa("casa", "Cestinha Organizadora Empilháveis Multiuso 19x14x6,5cm")
checa("casa", "Sapateira Organizadora Dobrável Transparente Kit 5 Unidades")

print("\n── 'pet' escondido DENTRO de outra palavra ──")
# estes dois iam pro @topshoppet_ e ninguém tinha percebido
checa("", "Filamento Impressora Creality CR-PETG Oficial Premium 3d-1kg 1.75mm")
checa("moda", "2 Limpa Tênis Branco e Colorido Espuma Limpa Tenis Petroplus Spray")

print("\n── comprimento não é especificidade ──")
# 'roupas'(6) ganhava de 'varal'(5) POR UMA LETRA e mandava varal pra moda
checa("casa", "Varal de Parede Alumínio Retrátil Reforçado Roupas Pesadas 80kg")
checa("casa", "KIT PLASÚTIL LUXO CESTO ROUPAS INFANTIL BACIA BALDE LIXEIRA")
# ...mas quando é decisivamente mais específico, tem que virar mesmo
checa("casa", "Saboneteira Dispenser Automático Para Sabonete Líquido")
checa("moda", "Cinta Modeladora Abdominal Modelform Esbelt Pós Parto")

# ⚠️ NÃO AFIRMO ESTE: 'Organizador Acrílico Para Cosméticos Perfumes Skincare'
# hoje sai BELEZA. Cabe em casa (organização) ou beleza (acessório de
# cosmético) — é decisão de curadoria do Dre, não defeito de código. Fica
# registrado aqui pra não virar "bug" numa próxima leitura do diff.

print("\n── produtos dos vídeos que saíram certos (não pode regredir) ──")
checa("moda", "botas pantufa Dragon Ball Z")
checa("casa", "Kit 2 Travesseiro De Corpo Xuxão")

print(f"\n{'='*60}\n   {ok} passou · {falhou} falhou\n{'='*60}")
raise SystemExit(1 if falhou else 0)
