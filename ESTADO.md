# ESTADO — o que é este sistema e onde ele está

**Leia este arquivo primeiro.** Ele existe porque a janela de contexto reinicia e
porque, em 03/08, eu afirmei que uma correção estava no ar quando ela estava
parada havia um dia. Sem registro escrito, o que eu "lembro" é o que commitei —
não o que roda.

Atualizado em: **03/08/2026**

---

## 1. A coisa mais importante: são DUAS árvores

| | `projeto-jarvis-completo` (este repo) | `~/jarvis` na VPS |
|---|---|---|
| estrutura | **chapada** — tudo na raiz | **em pacotes** — `agents/`, `creative_engine/`, `integrations/`, `shared/`, `memory/`, `brain/` |
| como saber o lugar real | 1ª linha do arquivo: `# agents/validar_fila.py` | é o lugar real |
| git | branch `claude/opa-clau-dgs591` | branch `main`, remotes `origin`→`agenteia.git` e `pjc`→este repo |

O repo chapado tem cara de upload pela web do GitHub (o commit `480ae63 "Add
files via upload"`, 01/07, achatou as pastas).

**`git pull pjc` dentro de `~/jarvis` é a coisa errada.** Despejaria
`validar_fila.py` na raiz ao lado do `agents/validar_fila.py` vivo — criaria
mais duplicata, que é justamente a doença.

**`~/jarvis` tem ~262 arquivos não commitados.** O git de lá não é usado como
controle. Qualquer `checkout`/`reset`/`stash` ali destrói trabalho. Automação
sobre aquela árvore precisa ser **aditiva**: copia, faz backup, nunca reverte.

## 2. Como o código chega na produção (e por que isso dói)

Não existe deploy. Eu gero um script `aplicar_*.py` que carrega o arquivo novo
em base64, confere o sha do que está lá, faz backup e escreve. O usuário manda
por `scp` e roda.

Três armadilhas que já morderam:

1. **Trocar o arquivo não recarrega o processo.** Python lê o módulo uma vez, na
   subida. Se o agente roda dentro do daemon, **exige `sudo systemctl restart
   jarvis`**. Em 03/08 o daemon estava no ar desde 02/08 23:43 com sete
   correções paradas no disco.
2. **Rodar pelo terminal não carrega o `.env`** — só o systemd carrega. Sem
   `SHOPEE_APP_ID/SECRET` a busca falha em *todos* os produtos. Já mordeu
   `repescagem.py` (09010fa) e `validar_fila.py` (6f74589).
3. **Arquivos duplicados entre raiz e subpasta, divergentes.** O daemon importa
   o da subpasta; o da raiz é código morto:
   - `daemon_maestro.py` — raiz 44.506b (morto) · `agents/` 58.470b (vivo)
   - `telegram_repurpose_hunter.py` — raiz (morto) · `integrations/` (vivo)
   - `engine.py` e `publish_guard.py` aparecem em dois pacotes, mas são módulos
     diferentes de verdade, não cópias.

## 3. Verificando o que roda de verdade

```bash
# qual versão de um arquivo está na VPS
sha256sum integrations/telegram_repurpose_hunter.py | cut -c1-16
```
```bash
# no repo: qual commit tem esse sha
for c in $(git log --format=%h -8 -- ARQUIVO.py); do
  printf "%s %s\n" "$c" "$(git show $c:ARQUIVO.py | sha256sum | cut -c1-16)"
done
```

Foi assim que descobri em 03/08 que `integrations/telegram_repurpose_hunter.py`
estava no commit `581b840`, com `6f74d22` e `b435f3c` nunca implantados.

## 4. Trabalho de 03/08 — commit e estado real

| commit | o que faz | na VPS? |
|---|---|---|
| `db8cae2` | nome-lixo: `_identificar_produto` devolve `(termo, tem_juizo)`; só termo avaliado pelo Gemini sustenta entrada na Amazon; `_ES_WORDS` | **sim** (restart 14:31) |
| `68ae6d1` | busca vazia não é veredito: validador retenta com nome curto; extrator vira `shared/termos.py` | **sim** (14:13) |
| `6f74589` | validador carrega `.env`; recusa gravar relatório de 100% deserto; curador não grava se aprovar < ¼ da fila | **sim** (12:50) |
| `e2b43f8` | a foto se perdia em 3 pontos: `validar_fila` não copiava, `curar_fila` reescrevia a fila do zero, `bio_page_builder` zerava | **sim** (12:29) |
| `b435f3c` | extrator do hunter: prova social descartada, comprimento com teto | **sim** — só em 03/08 15:55, um dia atrasado |
| `6f74d22` | preços: média + data em vez de valor exato | **sim** (junto com o acima) |

Resultado medido: desertos **27 → 16**, vitrine **80 → 101 produtos**, zero
placeholders sem foto.

## 5. Roadmap

- [x] **Etapa 1** — sincronizar `telegram_repurpose_hunter.py` (feito 03/08)
- [ ] **Etapa 2 — `conferir.py`**: só LÊ. Para cada arquivo do repo, acha o
      correspondente na VPS, compara o hash e diz quantos commits atrás está.
      Vem antes do deploy de propósito: preciso enxergar antes de agir.
      Ideia de desenho: `~/jarvis` já tem o remote `pjc`, então dá pra
      `git fetch pjc` e comparar contra os objetos do git, sem mapa embutido.
- [ ] **Etapa 3 — `deploy.py`**: o conferidor com permissão de escrever.
      Aditivo, com backup, nunca reverte. Pedir *ultracode* aqui.
- [ ] Desarmar as duplicatas mortas (`daemon_maestro.py` e
      `telegram_repurpose_hunter.py` da raiz)
- [ ] Varrer os ~45 `aplicar_*.py`/`patch_*.py` acumulados na raiz da VPS
- [ ] Conteúdo da comunidade — parado esperando 15–20 perguntas do usuário
- [ ] WhatsApp
- [ ] Consolidar os dois repositórios (o certo, mas mexe em import de dezenas
      de arquivos com o sistema rodando)

## 6. Pendências pequenas conhecidas

- `validar_fila`: quando a retentativa também falha, o relatório mostra o motivo
  da **primeira** tentativa (nome comprido). O log mostra as duas; o relatório
  não. Corrigir na próxima mexida no arquivo.
- 3 entradas-lixo ainda na fila (`Cosas deberías...`, `Tips pelo huela...`,
  `fidget spinner arma`) e `2 mil vendidos`. A vitrine já as esconde e a janela
  rolante (~80) as empurra pra fora. Não apagadas de propósito: mexer em dado
  de produção é escolha do usuário.
- 5 produtos seguem "deserto" com razão honesta (nome errado ou nicho): Cerveja
  "heneinken", Chopp ecobier, Hot Wheels 2-Pack, Boné Rabo de Cavalo, Lixeira
  Suspensa.
- Amazon: entradas com link `/s?k=` são busca, não produto — nunca terão foto.
  `preencher_fotos` não resolve; `amazon_playwright` resolveria abrindo o
  navegador, mas para termo-lixo produziria lixo.

## 7. Como o usuário trabalha

- Responde em português; prefere explicação do **porquê**, não só do quê.
- Manda a saída crua do terminal — é a fonte de verdade sobre a VPS.
- "ultracode" é um modo de esforço maior que **só ele ativa**, e custa tokens.
  Pedir explicitamente quando a tarefa for grande ou muito sensível.
- Vai por etapas e confirma antes de seguir. Não empilhar etapas sem aval.
