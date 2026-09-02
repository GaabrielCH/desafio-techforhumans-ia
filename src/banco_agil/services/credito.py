"""Regras de credito: consulta de limite e analise de aumento.

O fluxo de aumento segue exatamente o desafio:

1. registra o pedido como ``pendente`` em solicitacoes_aumento_limite.csv;
2. consulta o teto autorizado para o score atual em score_limite.csv;
3. atualiza a mesma linha para ``aprovado`` ou ``rejeitado``.

O pedido e gravado ANTES da decisao de proposito: mesmo que a analise falhe,
fica o rastro de que o cliente pediu.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import config
from ..erros import ErroEntradaInvalida
from ..logging_config import obter_logger
from ..repositories import clientes as repo_clientes
from ..repositories import score_limite as repo_score_limite
from ..repositories import solicitacoes as repo_solicitacoes
from ..repositories.clientes import Cliente
from ..repositories.csv_base import trava_arquivo
from ..utils import mascarar_cpf

log = obter_logger("servico.credito")


@dataclass(frozen=True)
class ResultadoAnalise:
    """Desfecho de uma solicitacao de aumento de limite."""

    aprovado: bool
    status: str
    cpf: str
    limite_atual: float
    novo_limite_solicitado: float
    score: int
    limite_maximo_autorizado: float
    data_hora: str

    @property
    def motivo(self) -> str:
        """Explicacao curta e objetiva do desfecho."""
        if self.aprovado:
            return (
                f"O score atual ({self.score}) autoriza limites de ate "
                f"R$ {self.limite_maximo_autorizado:.2f}, "
                f"cobrindo os R$ {self.novo_limite_solicitado:.2f} solicitados."
            )
        return (
            f"O score atual ({self.score}) autoriza limites de ate "
            f"R$ {self.limite_maximo_autorizado:.2f}, abaixo dos "
            f"R$ {self.novo_limite_solicitado:.2f} solicitados."
        )


def consultar_limite(cpf: str, caminho_clientes: Path | None = None) -> Cliente:
    """Retorna o cadastro do cliente (limite e score atuais)."""
    return repo_clientes.buscar_por_cpf(cpf, caminho_clientes)


def analisar_aumento(
    cpf: str,
    novo_limite: float,
    caminho_clientes: Path | None = None,
    caminho_score_limite: Path | None = None,
    caminho_solicitacoes: Path | None = None,
) -> ResultadoAnalise:
    """Registra e analisa um pedido de aumento de limite."""
    cliente = repo_clientes.buscar_por_cpf(cpf, caminho_clientes)

    if novo_limite <= 0:
        raise ErroEntradaInvalida("O novo limite precisa ser maior que zero.")

    if novo_limite <= cliente.limite_credito:
        raise ErroEntradaInvalida(
            f"O limite solicitado (R$ {novo_limite:.2f}) precisa ser maior que "
            f"o limite atual (R$ {cliente.limite_credito:.2f})."
        )

    arquivo_solicitacoes = caminho_solicitacoes or config.ARQUIVO_SOLICITACOES

    # A trava cobre registrar + concluir como uma operacao so. Sem ela, outro
    # processo poderia gravar entre as duas etapas e o pedido ficaria
    # 'pendente' para sempre, ou pior, o desfecho cairia na linha errada.
    with trava_arquivo(arquivo_solicitacoes):
        # 1. Pedido formal fica gravado antes de qualquer decisao.
        solicitacao = repo_solicitacoes.registrar(
            cpf=cliente.cpf,
            limite_atual=cliente.limite_credito,
            novo_limite=novo_limite,
            status=config.STATUS_PENDENTE,
            caminho=caminho_solicitacoes,
        )

        # 2. Politica de credito conforme o score atual.
        teto = repo_score_limite.limite_maximo_para_score(
            cliente.score, caminho_score_limite
        )
        aprovado = novo_limite <= teto
        status = config.STATUS_APROVADO if aprovado else config.STATUS_REJEITADO

        # 3. Desfecho registrado na mesma linha.
        repo_solicitacoes.atualizar_status(
            cpf=cliente.cpf,
            data_hora=solicitacao.data_hora_solicitacao,
            novo_status=status,
            caminho=caminho_solicitacoes,
        )

    if aprovado:
        # O desafio nao pede explicitamente, mas sem isto o agente diria
        # "seu novo limite e X" e a consulta seguinte responderia o valor
        # antigo. Efetivar o limite mantem a base coerente com o que foi
        # comunicado ao cliente.
        try:
            repo_clientes.atualizar_limite(
                cliente.cpf, novo_limite, caminho_clientes
            )
        except Exception:  # noqa: BLE001 - o pedido aprovado ja esta gravado
            log.exception(
                "Aumento aprovado para o CPF %s, mas o limite nao pode ser "
                "efetivado na base.",
                mascarar_cpf(cliente.cpf),
            )

        log.info(
            "Aumento aprovado para o CPF %s: %.2f -> %.2f (score %d, teto %.2f).",
            mascarar_cpf(cliente.cpf),
            cliente.limite_credito,
            novo_limite,
            cliente.score,
            teto,
        )
    else:
        log.info(
            "Aumento rejeitado para o CPF %s: %.2f solicitado, teto %.2f "
            "(score %d).",
            mascarar_cpf(cliente.cpf),
            novo_limite,
            teto,
            cliente.score,
        )

    return ResultadoAnalise(
        aprovado=aprovado,
        status=status,
        cpf=cliente.cpf,
        limite_atual=cliente.limite_credito,
        novo_limite_solicitado=novo_limite,
        score=cliente.score,
        limite_maximo_autorizado=teto,
        data_hora=solicitacao.data_hora_solicitacao,
    )
