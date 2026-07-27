# App Review do Meta — DM automática no Instagram (`instagram_manage_messages`)

Guia pronto pra pedir o **Acesso Avançado** que destrava a auto-DM ao comentarista
(o erro `(#3) Application does not have the capability` some quando isso é aprovado).
É um caso de uso **legítimo e comumente aprovado** (private reply a comentário) —
diferente do TikTok, aqui dá pra passar.

## Pré-requisitos (você faz no painel do Meta)
1. **Meta Business Suite** com o **negócio verificado** (Business Verification).
2. No app (developers.facebook.com → seu app):
   - Adicionar o produto **Instagram** (Graph API) e **Messenger/Instagram messaging**.
   - Conta IG **Profissional/Business** conectada a uma **Página do Facebook**.
   - Configurar o webhook de mensagens (se pedir) e o token da Página.
3. Ir em **App Review → Permissions and Features** → pedir **Advanced Access** de:
   - `instagram_manage_messages` (a DM/private reply) ← a que falta
   - `instagram_manage_comments` (responder comentário) — se ainda não tiver avançado
   - (já usamos `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`)

## Descrição do caso de uso (cole no formulário — em inglês, os revisores leem inglês)
> TopShop is a Brazilian affiliate business that manages its own official Instagram
> Business accounts. When a user comments on one of OUR posts asking for a product
> (e.g. "eu quero", "quanto custa", "link"), our system sends that user a **private
> reply (DM)** containing a helpful link to the product they asked about. We use
> `instagram_manage_messages` only to reply privately to users who comment on our
> own content, improving their experience by giving them the info they requested.
> We do not send unsolicited messages and only reply to users who engaged first.

(pt-BR, se o formulário aceitar: "Respondemos, por mensagem privada, os usuários
que comentam pedindo o produto nos NOSSOS posts, enviando o link que eles pediram.
Só respondemos quem comentou primeiro — nada de mensagem não solicitada.")

## Vídeo demo (screencast) — mostre o fluxo ponta a ponta
1. Um usuário comenta **"eu quero"** num post da conta TopShop (mostre o comentário).
2. O sistema detecta o gatilho e envia a **private reply (DM)** com o link
   (mostre rodando o `auto_resposta.py` OU o log com `💬 IG respondeu` + a DM saindo).
3. Mostre a **DM chegando** na caixa de entrada do usuário, com o link clicável.
Dicas: mostra a UI e as interações claramente, 30-90s, .mp4 ≤ tamanho pedido.

## Depois de aprovado
1. Confirma que o token da Página tem o escopo `instagram_manage_messages`
   (re-autoriza o login do Meta pedindo esse escopo se necessário).
2. Religa a DM: `AUTO_RESP_DM=1` no `.env` (hoje está `0`).
3. Testa: comenta "eu quero" de outra conta → roda `auto_resposta.py` → a DM chega.

## ⚠️ Ordem de prioridade (honesto)
A DM só paga no VOLUME de leads — e volume vem de ALCANCE. Com reach ~90 e ~0-1
lead/dia, a DM manual já cobre. Submeta isto quando quiser, mas **não deixe roubar
o foco do alcance** (o gargalo real). Aprovado, é só o flip do `AUTO_RESP_DM=1`.
