#!/usr/bin/env bash
# setup_cron_jarvis.sh -- instala o "relogio" da maquina TopShop: coleta virais
# do TikTok + produz os videos automaticamente, todo dia. O daemon (jarvis.service)
# ja posta o que estiver pronto. Idempotente: pode rodar de novo sem duplicar e
# NAO mexe nos seus outros crons.
#
# Uso (na VPS):  bash setup_cron_jarvis.sh
# Ver depois:    crontab -l
# Remover:       bash setup_cron_jarvis.sh --remover
#
# ⚠️ NUNCA USE CRASE DENTRO DO $BLOCO. NEM EM COMENTÁRIO.
# ─────────────────────────────────────────────────────────
# O $BLOCO é uma string entre ASPAS DUPLAS, e crase dentro de aspas duplas é
# SUBSTITUIÇÃO DE COMANDO — o bash executa e cola a saída ali dentro.
#
# Em 04/08/2026 um comentário dizia:  Confira com `crontab -l` antes de...
# Aquilo não era texto: era o crontab INTEIRO sendo executado e embutido no
# meio do bloco, a cada execução do script. O rastro ficou visível no crontab
# como a linha "# JARVIS-AUTO-END antes de acrescentar qualquer coisa" — o fim
# do crontab embutido grudado no texto que vinha depois da crase.
#
# Resultado: 3 execuções deste script = 4 cópias de TUDO. O grupo do Telegram
# recebeu cada achadinho 4 vezes, o coletor puxou 4x a cota da API e o
# auto_resposta respondeu o mesmo comentário 5 vezes pro cliente.
#
# O "idempotente" da linha acima era falso e ninguém percebeu por semanas,
# porque o script SEMPRE terminava dizendo que deu certo.
#
# Em comentário, use aspas simples. A verificação no fim deste arquivo existe
# pra que, se isso voltar a acontecer, o script pare em vez de estragar o
# crontab de novo.
set -e

JARVIS=/root/jarvis
PY="$JARVIS/.venv/bin/python"
mkdir -p "$JARVIS/logs"

# tira qualquer bloco JARVIS-AUTO anterior (limpo, entre marcadores)
BASE="$(crontab -l 2>/dev/null | sed '/# JARVIS-AUTO-BEGIN/,/# JARVIS-AUTO-END/d')"

if [ "$1" = "--remover" ]; then
    printf '%s\n' "$BASE" | crontab -
    echo "🗑️  cron JARVIS-AUTO removido. O daemon continua postando o que ja esta pronto."
    exit 0
fi

BLOCO="# JARVIS-AUTO-BEGIN  (TopShop — coleta+producao; use setup_cron_jarvis.sh, nao edite a mao)
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# 03:00 -> coleta MAIS virais NOVOS (alimenta as 3 contas) -> inbox_tiktok/
0 3 * * * cd $JARVIS && $PY tiktok_coletor.py --limite 20 >> $JARVIS/logs/cron_coletor.log 2>&1
# PRODUCAO POR NICHO (cota por conta, ~11/dia) -> pronto_para_postar/
#   tech 4/dia (2+2) · beleza 4/dia (2+2) · geral 3/dia (1+1+1)
#   horarios ESCALONADOS p/ nao empilhar render no VPS (cada video ~7min)
0 5 * * *   cd $JARVIS && $PY produzir_tiktok.py --nicho tech 2   >> $JARVIS/logs/cron_produzir.log 2>&1
0 16 * * *  cd $JARVIS && $PY produzir_tiktok.py --nicho tech 2   >> $JARVIS/logs/cron_produzir.log 2>&1
30 6 * * *  cd $JARVIS && $PY produzir_tiktok.py --nicho beleza 2 >> $JARVIS/logs/cron_produzir.log 2>&1
30 17 * * * cd $JARVIS && $PY produzir_tiktok.py --nicho beleza 2 >> $JARVIS/logs/cron_produzir.log 2>&1
0 8 * * *   cd $JARVIS && $PY produzir_tiktok.py --nicho geral 1  >> $JARVIS/logs/cron_produzir.log 2>&1
0 13 * * *  cd $JARVIS && $PY produzir_tiktok.py --nicho geral 1  >> $JARVIS/logs/cron_produzir.log 2>&1
0 20 * * *  cd $JARVIS && $PY produzir_tiktok.py --nicho geral 1  >> $JARVIS/logs/cron_produzir.log 2>&1
# casa 2/dia (a conta nasceu em 04/08). Somado ao piso do daemon -- que le o
# contas.json e ja garante 1/conta/dia -- da 3/dia, mesma cota do geral.
# Horarios escolhidos nas JANELAS VAZIAS entre os outros renders (cada video
# ~7min) e fora dos slots de postagem, pra nao disputar CPU com o upload.
0 10 * * *  cd $JARVIS && $PY produzir_tiktok.py --nicho casa 1   >> $JARVIS/logs/cron_produzir.log 2>&1
30 14 * * * cd $JARVIS && $PY produzir_tiktok.py --nicho casa 1   >> $JARVIS/logs/cron_produzir.log 2>&1
# 03:40 -> AMAZON: resolve os produtos que entraram como LINK DE BUSCA (/s?k=)
#   e vira produto de verdade (ASIN + preco + foto). Precisa do .venv: o
#   playwright so existe la, e rodar com o python do sistema falha o import.
#   Conservador de proposito -- teto 5, pausa longa, para sozinho se ver captcha.
40 3 * * * cd $JARVIS && $PY amazon_playwright.py --limite 5 >> $JARVIS/logs/cron_amazon.log 2>&1
# NAO ponha deploy_site aqui. Ele JA roda a cada 2h por uma entrada propria do
# crontab, fora deste bloco (0 */2 * * *), e a das 04:00 cai 20min depois da
# rodada Amazon acima -- o encaixe ja existe. Duplicar so dobra health-check e
# chamada de API. Confira com 'crontab -l' antes de acrescentar qualquer coisa
# (ASPAS SIMPLES, NUNCA CRASE: veja o aviso no topo deste arquivo)
# aqui: este bloco nao enxerga o que foi posto a mao.
# DOMINGO 09:00 -> CEO Conselheiro: relatorio semanal (vai pro Telegram privado)
0 9 * * 0 cd $JARVIS && $PY ceo_agent.py 7 >> $JARVIS/logs/cron_ceo.log 2>&1
# AUTO-RESPOSTA em duas passadas (so roda se AUTO_RESPONDER=1 no .env).
# FB responde com link clicavel, IG manda pra bio (link em comentario nao clica).
#
# Por que duas: quem comenta quer resposta rapida, mas rodar a janela INTEIRA de
# 5 em 5 minutos multiplica as chamadas do Graph por 12 e estoura o limite da
# API. Entao a passada rapida olha so os posts novos, e a funda -- de hora em
# hora -- varre a janela toda e pega o que caiu em post mais antigo.
#
#   rapida  a cada 5min  · 3 posts por conta, ultimas 12h
#   funda   1x por dia    · 130 posts por conta, ultimos 30 dias
#
# A funda alcanca UM MES pra tras, que e o que o Dre pediu: responder comentario
# que a pessoa deixou ha semanas. A conta: sao ~4 videos por conta por dia, entao
# 30 dias = ~120 posts. Com 25 posts ela so chegava a uns 7 dias.
#
# 1x POR DIA e nao de hora em hora: 130 posts x 24 rodadas passa de 17 mil
# chamadas do Graph por dia. Uma vez basta -- o que cai em post antigo durante o
# dia espera ate a madrugada, e o que cai em post novo a rapida ja pegou.
#
# 3 na rapida, nao mais: comentario novo cai quase sempre no post mais recente,
# e o limite do Graph escala com IMPRESSAO -- com conta pequena ele aperta. Se o
# log mostrar erro de rate limit, baixe o --midias da linha de 5min PRIMEIRO.
#
# AUTO_RESP_MAX (padrao 40) limita as respostas POR RODADA. Na primeira varredura
# do mes pode haver mais comentarios velhos que isso; ele responde 40 por dia ate
# zerar, o que tambem evita despejar 200 respostas de uma vez e parecer spam.
# TRES passadas, nao duas. A do MEIO nasceu em 04/08: um comentario ficou 40min
# sem resposta e o Dre queria 5-10min. A rapida olhava so os 3 posts mais
# recentes -- com ~4 videos por conta por dia, isso cobre umas 18h. Comentario
# em post mais antigo so era visto na funda das 02:25, ou seja podia esperar o
# dia inteiro. Nao era lentidao: era um BURACO entre as duas passadas.
#
# Custo medido em chamadas do Graph por dia, com 4 contas:
#   antes  rapida(3)x288 + funda(130)x1              =  5.132
#   agora  rapida(5)x288 + meio(25)x48 + funda(130)  = 12.428
#
# Cobertura por passada:
#   rapida  a cada 5min  ·  5 posts  ~ ultimo dia e meio
#   meio    a cada 30min · 25 posts  ~ ultima semana
#   funda   1x por dia   · 130 posts ~ ultimos 30 dias
#
# SE O LOG MOSTRAR ERRO DE RATE LIMIT, baixe NESTA ORDEM: primeiro os 25 da
# passada do meio, depois a frequencia dela (*/30 -> 0,30 = 2x/h), e so por
# ultimo os 5 da rapida -- que e a que entrega os 5 minutos pedidos.
*/5 * * * * cd $JARVIS && $PY auto_resposta.py --midias 5 --horas 36 >> $JARVIS/logs/cron_autoresp.log 2>&1
*/30 * * * * cd $JARVIS && $PY auto_resposta.py --midias 25 --horas 168 >> $JARVIS/logs/cron_autoresp.log 2>&1
25 2 * * *  cd $JARVIS && $PY auto_resposta.py --midias 130 --horas 720 >> $JARVIS/logs/cron_autoresp.log 2>&1
# JARVIS-AUTO-END"

# ── CONFERE ANTES DE ESCREVER ──────────────────────────────────────────────
# Este script se dizia idempotente e nao era: uma crase num comentario fazia
# ele embutir o crontab inteiro dentro do proprio bloco, e ninguem percebeu
# por semanas porque ele SEMPRE terminava dizendo "✅ cron instalado".
#
# Agora ele mede antes de gravar. Um bloco bem formado tem exatamente 1 BEGIN
# e 1 END; mais que isso significa que alguma coisa foi interpolada ali dentro,
# e gravar seria repetir o estrago.
N_BEGIN=$(printf '%s\n' "$BLOCO" | grep -c 'JARVIS-AUTO-BEGIN' || true)
N_END=$(printf '%s\n' "$BLOCO" | grep -c 'JARVIS-AUTO-END' || true)
if [ "$N_BEGIN" != "1" ] || [ "$N_END" != "1" ]; then
    echo "❌ ABORTADO: o bloco tem $N_BEGIN BEGIN e $N_END END (o certo e 1 e 1)."
    echo "   Alguma coisa foi executada e embutida dentro do \$BLOCO."
    echo "   Procure CRASE ou \$( ) nas linhas entre BLOCO=\" e JARVIS-AUTO-END."
    echo "   O crontab NAO foi alterado."
    exit 1
fi

# Numero de linhas de tarefa: um bloco normal tem algumas dezenas. Se explodir,
# e sinal de interpolacao que passou pela conferencia acima.
N_LINHAS=$(printf '%s\n' "$BLOCO" | grep -vc '^[[:space:]]*#' || true)
if [ "$N_LINHAS" -gt 60 ]; then
    echo "❌ ABORTADO: o bloco tem $N_LINHAS linhas de tarefa — muito acima do esperado."
    echo "   O crontab NAO foi alterado."
    exit 1
fi

# recompoe o crontab: o que ja existia (sem o bloco antigo) + o bloco novo
{ [ -n "$BASE" ] && printf '%s\n' "$BASE"; printf '%s\n' "$BLOCO"; } | crontab -

# e confere o RESULTADO: se sobrou mais de um bloco, o sed de limpeza falhou
N_DEPOIS=$(crontab -l 2>/dev/null | grep -c 'JARVIS-AUTO-BEGIN' || true)
if [ "$N_DEPOIS" != "1" ]; then
    echo "⚠️  ATENCAO: o crontab ficou com $N_DEPOIS blocos JARVIS-AUTO (esperado 1)."
    echo "   Rode:  crontab -l | grep -n JARVIS-AUTO"
    echo "   e limpe os blocos sobrando a mao antes de confiar no agendamento."
fi

echo "✅ cron instalado. A maquina agora roda sozinha:"
echo "   • 03:00  coleta virais do TikTok"
echo "   • producao por nicho: tech 4 · beleza 4 · geral 3 · casa 2 (+1 do piso)"
echo "   • 03:40  resolve produtos da Amazon (link de busca -> produto real)"
echo "   • a cada 5min  auto-resposta nos posts novos (se AUTO_RESPONDER=1)"
echo "   • 02:25  varredura funda (30 dias, 130 posts por conta)"
echo "   • daemon posta nos horarios de sempre"
echo
echo "Logs:  tail -f $JARVIS/logs/cron_produzir.log"
echo "Ver cron:  crontab -l"
# aviso se o servico do cron nao estiver ativo
if ! systemctl is-active --quiet cron 2>/dev/null && ! systemctl is-active --quiet crond 2>/dev/null; then
    echo "⚠️  ATENCAO: o servico de cron parece INATIVO. Ative com:  systemctl enable --now cron"
fi
