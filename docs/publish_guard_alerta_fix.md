# Fix — alerta de falha vazava pro canal público (`agents/publish_guard.py`)

> ⚠️ **Drift de arquivo:** o `agents/publish_guard.py` que roda na VPS é o
> publicador REAL (`publicar_com_garantia`, `_enviar_alerta_telegram`,
> `_alertar_falha`, `_UPLOADERS`, `_postar_youtube/tiktok/instagram/facebook`).
> Ele **NÃO está versionado neste repositório** — o `publish_guard.py` da raiz
> do repo é uma versão antiga e diferente (`validar_publicacao_autonoma`).
> O arquivo real vive só na VPS (`/root/jarvis/agents/publish_guard.py`) e no
> backup do `.env`/`shared`. **TODO:** sincronizar o arquivo inteiro da VPS pra
> cá quando der, pra parar de driftar.

## O bug
A função `_enviar_alerta_telegram` mandava o aviso de "🚨 Jarvis — falha de
publicação" lendo **só** `TELEGRAM_CHAT_ID`:

```python
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()   # ← só o canal
```

Quando o `TELEGRAM_CHAT_ID` passou a apontar pro **canal do Telegram** (destino
de CONTEÚDO, público, criado em jul/2026), os alertas de erro **vazaram pro canal
público** junto com o conteúdo — os membros/clientes viam mensagem interna de
falha. Não vazou segredo (o token vem do `.env`, não do código), mas queima marca.

## O fix (já aplicado na VPS)
`_enviar_alerta_telegram`, linha ~261 — o alerta passa a **preferir** o chat de
alerta e só cair no de conteúdo se aquele não existir:

```python
chat_id = (os.environ.get("TELEGRAM_ALERT_CHAT_ID")
           or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
```

## Configuração de destino (`.env`)
| Variável                  | Valor            | Uso                                  |
|---------------------------|------------------|--------------------------------------|
| `TELEGRAM_CHAT_ID`        | id do **canal**  | CONTEÚDO (achadinhos, Fase 1)         |
| `TELEGRAM_ALERT_CHAT_ID`  | id **privado**   | ALERTAS de erro (só o operador vê)    |

Esse mesmo padrão (`ALERT_CHAT_ID or CHAT_ID`) já é usado em `produzir_tiktok.py`
e `ceo_agent.py` — então definir `TELEGRAM_ALERT_CHAT_ID` no `.env` mantém TODOS
os alertas no privado, com o canal reservado só pra conteúdo.
