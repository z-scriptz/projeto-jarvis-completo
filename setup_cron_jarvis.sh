#!/usr/bin/env bash
# setup_cron_jarvis.sh -- instala o "relogio" da maquina TopShop: coleta virais
# do TikTok + produz os videos automaticamente, todo dia. O daemon (jarvis.service)
# ja posta o que estiver pronto. Idempotente: pode rodar de novo sem duplicar e
# NAO mexe nos seus outros crons.
#
# Uso (na VPS):  bash setup_cron_jarvis.sh
# Ver depois:    crontab -l
# Remover:       bash setup_cron_jarvis.sh --remover
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
# 03:00 -> coleta virais NOVOS do TikTok (dedup automatico) -> inbox_tiktok/
0 3 * * * cd $JARVIS && $PY tiktok_coletor.py --limite 10 >> $JARVIS/logs/cron_coletor.log 2>&1
# 04:00 / 12:00 / 18:00 -> produz 1 video cada (3/dia) -> pronto_para_postar/
0 4 * * * cd $JARVIS && $PY produzir_tiktok.py 1 >> $JARVIS/logs/cron_produzir.log 2>&1
0 12 * * * cd $JARVIS && $PY produzir_tiktok.py 1 >> $JARVIS/logs/cron_produzir.log 2>&1
0 18 * * * cd $JARVIS && $PY produzir_tiktok.py 1 >> $JARVIS/logs/cron_produzir.log 2>&1
# JARVIS-AUTO-END"

# recompoe o crontab: o que ja existia (sem o bloco antigo) + o bloco novo
{ [ -n "$BASE" ] && printf '%s\n' "$BASE"; printf '%s\n' "$BLOCO"; } | crontab -

echo "✅ cron instalado. A maquina agora roda sozinha:"
echo "   • 03:00  coleta virais do TikTok"
echo "   • 04h/12h/18h  produz 1 video cada (3/dia)"
echo "   • daemon posta nos horarios de sempre"
echo
echo "Logs:  tail -f $JARVIS/logs/cron_produzir.log"
echo "Ver cron:  crontab -l"
# aviso se o servico do cron nao estiver ativo
if ! systemctl is-active --quiet cron 2>/dev/null && ! systemctl is-active --quiet crond 2>/dev/null; then
    echo "⚠️  ATENCAO: o servico de cron parece INATIVO. Ative com:  systemctl enable --now cron"
fi
