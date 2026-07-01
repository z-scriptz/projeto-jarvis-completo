# providers/base_provider.py
# Contrato comum pra todos os providers de geração de mídia IA do Jarvis.
#
# Cada ferramenta (HeyGen, Pixverse, Hedra, etc) implementa esta interface.
# O Creative Asset Generator não sabe QUAL ferramenta está usando — só chama
# o contrato. Isso permite trocar de ferramenta sem mexer no agente.
#
# Filosofia:
#   - disponivel() checa se dá pra usar AGORA (tem API key, lib instalada)
#   - gerar() retorna SEMPRE um dict padronizado (nunca lança exceção pro caller)
#   - se a ferramenta não tem API, retorna status='no_credentials' graciosamente

from pathlib import Path
from typing import Optional


class ResultadoGeracao(dict):
    """
    Dict padronizado de retorno de qualquer provider.

    Campos:
        sucesso:          bool — gerou arquivo de fato?
        status:           "ok" | "queued" | "no_credentials" | "erro" | "dry_run"
        provider:         nome do provider
        cena:             cena alvo (dor/demo/resultado/close/cta)
        tipo:             "video" | "imagem"
        prompt:           prompt usado
        arquivo:          caminho do arquivo gerado (se sucesso) ou None
        arquivo_esperado: nome que o arquivo DEVE ter pro Hunter classificar
        mensagem:         texto humano
        erro:             detalhe do erro (se status='erro')
    """
    pass


def novo_resultado(provider: str, cena: str, tipo: str, prompt: str,
                    arquivo_esperado: str, **kwargs) -> ResultadoGeracao:
    base = {
        "sucesso":          False,
        "status":           "erro",
        "provider":         provider,
        "cena":             cena,
        "tipo":             tipo,
        "prompt":           prompt,
        "arquivo":          None,
        "arquivo_esperado": arquivo_esperado,
        "mensagem":         "",
        "erro":             None,
    }
    base.update(kwargs)
    return ResultadoGeracao(base)


class BaseProvider:
    """
    Classe base. Subclasses sobrescrevem nome, tipo_saida, disponivel(), gerar().
    """
    nome = "base"
    tipo_saida = "video"   # "video" ou "imagem"
    descricao = "provider base abstrato"

    def disponivel(self) -> bool:
        """True se o provider pode ser usado agora (API key, lib, etc)."""
        return False

    def motivo_indisponivel(self) -> str:
        """Explica por que não está disponível (pra log)."""
        return "provider base não é utilizável diretamente"

    def gerar(self, prompt: str, cena: str, produto: str,
              arquivo_esperado: str, output_dir: Path,
              dry_run: bool = False) -> ResultadoGeracao:
        """
        Gera (ou enfileira) uma mídia a partir do prompt.
        NUNCA lança exceção — sempre retorna ResultadoGeracao.
        """
        raise NotImplementedError