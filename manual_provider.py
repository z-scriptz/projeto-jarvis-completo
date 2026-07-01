# providers/manual_provider.py
# Provider MANUAL — o que realmente funciona HOJE, sem depender de API.
#
# Não gera arquivo automaticamente. Em vez disso:
#   1. Produz o prompt pronto pra copiar/colar em qualquer plataforma
#      (Pixverse, HeyGen, Higgsfield, etc — você escolhe na hora)
#   2. Registra na fila (ai_video_generation_queue.json) com o nome que o
#      arquivo DEVE ter quando você baixar e jogar na inbox
#   3. Asset Hunter depois classifica pelo nome (cena no prefixo)
#
# Fluxo humano:
#   gerador --provider manual → copia prompts → gera nas plataformas →
#   baixa → salva em assets/inbox/videos/ com o nome sugerido → roda Hunter

from pathlib import Path

from providers.base_provider import BaseProvider, novo_resultado


class ManualProvider(BaseProvider):
    nome = "manual"
    tipo_saida = "video"
    descricao = "Gera prompts prontos pra colar nas plataformas + fila (sem API)"

    def disponivel(self) -> bool:
        # Manual está SEMPRE disponível — é só texto
        return True

    def motivo_indisponivel(self) -> str:
        return ""

    def gerar(self, prompt, cena, produto, arquivo_esperado, output_dir,
              dry_run=False) -> "novo_resultado":
        if dry_run:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="dry_run",
                mensagem="[dry-run] prompt gerado, nada enfileirado",
            )
        # Modo manual: não baixa nada, só sinaliza que está na fila.
        # A escrita na fila é feita pelo agente (que agrega todas as cenas).
        return novo_resultado(
            self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
            sucesso=False, status="queued",
            mensagem=(f"Prompt pronto. Gere na plataforma de sua escolha e salve "
                      f"como '{arquivo_esperado}' em assets/inbox/videos/"),
        )