# 🚀 Deploy do Jarvis na VPS Linux (24/7)

Guia pra tirar o Jarvis do seu PC Windows e rodar sozinho numa VPS Linux,
como serviço que sobe no boot e reinicia se cair.

---

## 0) Visão geral do que vai acontecer

```
PC Windows  ──(git push)──▶  GitHub  ──(git clone)──▶  VPS Linux
   │                                                       │
   └──(copiar à parte: .session, tokens, .env, config)────▶┘
```

O **código** vai pelo Git. Os **segredos e o estado** (sessões do Telegram,
token do YouTube, chaves de API, config) **NÃO** vão pro Git — você copia à mão.

---

## 1) O que NÃO vai pro Git

O `.gitignore` já bloqueia isso, mas pra deixar claro — estes ficam SÓ na sua
máquina e você copia manualmente pra VPS:

| Arquivo | O que é |
|---|---|
| `shared/telegram_radar.session` | login do Telegram (radar + descobridor) |
| `shared/jarvis_hunter_session.session` | login do Telegram (hunter) |
| `shared/credentials/youtube_token.json` | token do YouTube (já autorizado) |
| `shared/credentials/client_secret.json` | credencial OAuth do YouTube |
| `.env` | suas chaves de API (Shopee, Meta, Fal, Telegram...) |
| `shared/content_plans/agendador_config.json` | seu config (tem seus canais) |
| `grupos.txt` | seus grupos iniciais do radar |

---

## 2) Subir o código pro Git (no PC Windows)

Na raiz do projeto (`C:\AgenteIA`):

```powershell
git init                       # se ainda não for repo
git add .                      # o .gitignore já exclui segredos/mídia
git status                     # CONFIRA que nenhum .session/.env/token aparece!
git commit -m "Jarvis pronto pra VPS"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
git push -u origin main
```

⚠️ Antes do commit, rode `git status` e confirme que **NÃO** aparece nenhum
`.session`, `.env`, `youtube_token.json` nem pasta `videos/`. Se aparecer, o
`.gitignore` não está pegando — pare e me chame.

---

## 3) Preparar a VPS Linux (uma vez só)

Conecte na VPS por SSH e instale o sistema:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git ffmpeg fonts-dejavu
```

- **ffmpeg** é obrigatório (o MoviePy usa ele pra renderizar vídeo).
- **fonts-dejavu** garante a fonte de legenda de fallback.

Confira o Python (precisa ser 3.10+):
```bash
python3 --version
```

---

## 4) Clonar + ambiente virtual + dependências

```bash
cd ~
git clone https://github.com/SEU_USUARIO/SEU_REPO.git jarvis
cd jarvis
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> Se `moviepy` ou `Pillow` reclamarem, garanta que o `ffmpeg` do passo 3 foi
> instalado. NÃO instale `pyautogui` na VPS (é só pro TikTok no PC).

---

## 5) Copiar os segredos pra VPS

Do seu PC (PowerShell), use `scp` pra mandar os arquivos que não vão no Git.
Troque `usuario@IP_DA_VPS` e o caminho:

```powershell
# sessões do Telegram
scp shared\telegram_radar.session       usuario@IP_DA_VPS:~/jarvis/shared/
scp shared\jarvis_hunter_session.session usuario@IP_DA_VPS:~/jarvis/shared/

# credenciais do YouTube
scp shared\credentials\youtube_token.json   usuario@IP_DA_VPS:~/jarvis/shared/credentials/
scp shared\credentials\client_secret.json   usuario@IP_DA_VPS:~/jarvis/shared/credentials/

# config e grupos
scp shared\content_plans\agendador_config.json usuario@IP_DA_VPS:~/jarvis/shared/content_plans/
scp grupos.txt usuario@IP_DA_VPS:~/jarvis/
```

> Os `.session` são SQLite e **funcionam igual no Linux** (mesmo TELEGRAM_API_ID).
> Copiando eles, o Telegram já entra logado e NÃO pede código na VPS.
> (Crie as pastas antes se não existirem: `mkdir -p ~/jarvis/shared/credentials`)

---

## 6) Variáveis de ambiente (.env)

Crie o arquivo `~/jarvis/.env` na VPS com suas chaves (as MESMAS do PC):

```ini
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SHOPEE_APP_ID=xxxxxxxxxx
SHOPEE_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
META_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
FACEBOOK_PAGE_ID=xxxxxxxxxxxxxx
INSTAGRAM_USER_ID=xxxxxxxxxxxxxx
FAL_KEY=xxxxxxxx:xxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxx
```

Para testar no terminal, carregue elas na sessão atual:
```bash
set -a; source ~/jarvis/.env; set +a
```
(No systemd, o passo 9 carrega esse `.env` automaticamente.)

---

## 7) Teste de fumaça na VPS (com a venv ativa e o .env carregado)

```bash
cd ~/jarvis
source .venv/bin/activate
set -a; source .env; set +a

python check_ambiente.py                      # tudo verde?
python -m agents.daemon_maestro --once --dry-run   # 1 ciclo simulado
python -m agents.daemon_maestro --once             # 1 ciclo REAL (produz + posta 1)
```

Se o `--once` real produzir vídeo em `pronto_para_postar/<slug>/video.mp4` e
postar sem erro, está pronto pro loop.

---

## 8) Autorizar Telegram na VPS (SÓ se você NÃO copiou os .session)

Se preferir não copiar os `.session`, autorize uma vez, interativo:
```bash
python -m integrations.telegram_radar --grupos "@qualquer" --limite 1
# ele vai pedir seu telefone + código (e senha 2FA se tiver)
```
Depois disso o `.session` fica salvo e o daemon não pede mais nada.

---

## 9) Rodar como serviço 24/7 (systemd — sobe no boot e reinicia se cair)

Crie o serviço (troque `SEU_USUARIO` e os caminhos se necessário):

```bash
sudo nano /etc/systemd/system/jarvis.service
```

Cole:

```ini
[Unit]
Description=Jarvis Daemon Maestro (24/7)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=SEU_USUARIO
WorkingDirectory=/home/SEU_USUARIO/jarvis
EnvironmentFile=/home/SEU_USUARIO/jarvis/.env
ExecStart=/home/SEU_USUARIO/jarvis/.venv/bin/python -m agents.daemon_maestro
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Ative e suba:
```bash
sudo systemctl daemon-reload
sudo systemctl enable jarvis      # sobe sozinho no boot
sudo systemctl start jarvis       # inicia agora
```

---

## 10) Operação do dia a dia

```bash
sudo systemctl status jarvis          # está rodando?
journalctl -u jarvis -f               # ver os logs AO VIVO
journalctl -u jarvis --since "1 hour ago"   # logs da última hora
sudo systemctl restart jarvis         # reiniciar
sudo systemctl stop jarvis            # parar
```

**Atualizar o código depois (quando você mexer em algo):**
```bash
cd ~/jarvis
git pull
source .venv/bin/activate
pip install -r requirements.txt       # se mudou dependência
sudo systemctl restart jarvis
```

---

## ✅ Checklist final antes de deixar sozinho

- [ ] `check_ambiente.py` 100% verde na VPS
- [ ] `.session` (radar + hunter) copiados → Telegram entra sem pedir código
- [ ] `youtube_token.json` copiado (você ativou YouTube nas plataformas)
- [ ] Credenciais Meta no `.env` (IG + FB são seu canal principal)
- [ ] `--once` real produziu e postou 1 sem erro
- [ ] `grupos.txt` com seus grupos iniciais (base da descoberta orgânica)
- [ ] **"tiktok" NÃO está em `plataformas`** (precisa de tela, não roda na VPS)
- [ ] (Opcional 1º dia) `"publico": false` pra revisar os primeiros posts

Rodou o `status` e apareceu `active (running)`? Tá no ar. 🎉
