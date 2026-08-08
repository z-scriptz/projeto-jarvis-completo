#!/usr/bin/env bash
# raio-x.sh -- diagnóstico READ-ONLY do Jarvis. Não muda nada, não posta nada.
cd ~/jarvis 2>/dev/null || { echo "não achei ~/jarvis"; exit 1; }
L() { echo; echo "══════ $* ══════"; }

L "1. POR QUE O PUSH DO SITE FALHOU"
grep -h "push falhou\|commit falhou\|ERRO" logs/cron_site.log deploy_site.log 2>/dev/null \
  | sort | uniq -c | sort -rn | head -8
echo "-- estado do repo do site --"
S=${TOPSHOP_SITE_DIR:-~/topshop-site}
if [ -d "$S/.git" ]; then
  git -C "$S" status -sb 2>&1 | head -3
  echo "-- local vs remoto --"
  git -C "$S" fetch -q origin 2>&1 | head -2
  echo "   à frente: $(git -C "$S" rev-list --count @{u}..HEAD 2>/dev/null)  atrás: $(git -C "$S" rev-list --count HEAD..@{u} 2>/dev/null)"
  echo "   últimos commits:"; git -C "$S" log --oneline -3 2>&1 | sed 's/^/     /'
else
  echo "   !! $S não é repo git"
fi

L "2. CRON — duplicou de novo?"
echo "blocos JARVIS-AUTO: $(crontab -l 2>/dev/null | grep -c 'JARVIS-AUTO-BEGIN')  (tem que ser 1)"
echo "linhas repetidas:"
crontab -l 2>/dev/null | grep -v '^#' | grep -v '^[[:space:]]*$' | sort | uniq -d | head -5
echo "   (vazio acima = ok)"

L "3. ERROS NOS ÚLTIMOS 3 DIAS"
for f in logs/*.log *.log; do
  [ -f "$f" ] || continue
  n=$(find "$f" -mtime -3 2>/dev/null | wc -l); [ "$n" = 0 ] && continue
  e=$(grep -ciE "traceback|erro |error|falh|rate limit|❌" "$f" 2>/dev/null)
  [ "$e" -gt 0 ] && printf "  %-34s %4d ocorrência(s)\n" "$(basename $f)" "$e"
done | sort -k2 -rn | head -12

L "4. RATE LIMIT / GRAPH API (auto-resposta)"
grep -hoiE "rate limit|#4\)|#17\)|limite.{0,30}|permission" logs/cron_autoresp.log 2>/dev/null \
  | sort | uniq -c | sort -rn | head -6
echo "respostas dadas nos últimos 3 dias:"
grep -c "💬" logs/cron_autoresp.log 2>/dev/null || echo "  0"

L "5. ESPELHAMENTO (texto invertido)"
grep -h "Espelhamento" logs/*.log 2>/dev/null | sort | uniq -c | sort -rn | head -4

L "6. LOGOS POR CONTA"
ls -1 assets/brand/logo_ts*.png 2>/dev/null | sed 's/^/  /' || echo "  nenhuma"
grep -h "LOGO DA CONTA AUSENTE" logs/*.log 2>/dev/null | tail -3

L "7. FILA E VITRINE"
python3 - <<'PY' 2>/dev/null || echo "  (não consegui ler)"
import json, pathlib, collections
f = pathlib.Path("shared/produtos_fila.json")
d = json.loads(f.read_text()) if f.exists() else []
print(f"  fila: {len(d)} itens")
print("  sem imagem:", sum(1 for i in d if isinstance(i,dict) and not i.get("imagem")))
print("  sem link:  ", sum(1 for i in d if isinstance(i,dict) and not i.get("link")))
c = collections.Counter((i.get("plataforma") or "shopee").lower() for i in d if isinstance(i,dict))
print("  por loja: ", dict(c))
PY

L "8. TRAVAS PRESAS / PROCESSOS"
ls -la shared/.trava_* 2>/dev/null | sed 's/^/  /' || echo "  nenhuma trava em disco"
echo "processos jarvis rodando:"; pgrep -af "jarvis|produzir_tiktok|auto_resposta|deploy_site" | head -5

L "9. DISCO E SERVIÇO"
df -h / | tail -1 | awk '{print "  disco: "$5" usado, "$4" livre"}'
systemctl is-active jarvis 2>/dev/null | sed 's/^/  daemon jarvis: /'
echo "  último post do daemon:"; grep -h "postad\|✅" logs/*.log 2>/dev/null | tail -2 | sed 's/^/    /'

L "10. SESSÃO DO INSTAGRAM (scraping)"
ls -la shared/*cookie* shared/*sessao* shared/*session* 2>/dev/null | sed 's/^/  /' || echo "  nada encontrado"
grep -hiE "login|cookie|sess|checkpoint|challenge" logs/cron_coletor.log 2>/dev/null | tail -4

echo; echo "══════ fim ══════"
