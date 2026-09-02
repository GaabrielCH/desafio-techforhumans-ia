"""Ferramenta do Agente de Cambio."""

from __future__ import annotations

from typing import Annotated

from langgraph.prebuilt import InjectedState

from langchain_core.tools import tool

from ..erros import ErroEntradaInvalida, ErroServicoExterno
from ..logging_config import obter_logger
from ..services import cambio as servico_cambio

log = obter_logger("ferramenta.cambio")


@tool("consultar_cotacao_moeda")
def consultar_cotacao_moeda(
    moeda: str,
    state: Annotated[dict, InjectedState],
    moeda_destino: str = "BRL",
) -> str:
    """Consulta a cotacao atual de uma moeda em tempo real.

    Args:
        moeda: moeda desejada ('dolar', 'euro', 'USD', 'EUR'...).
        moeda_destino: moeda de referencia da conversao. Padrao 'BRL'.
    """
    if not state.get("autenticado"):
        return (
            "Bloqueado: o cliente ainda nao foi autenticado. Peca CPF e data "
            "de nascimento antes de atender."
        )

    try:
        cotacao = servico_cambio.consultar_cotacao(moeda, moeda_destino)
    except ErroEntradaInvalida as exc:
        log.info("Moeda invalida solicitada: %s", exc)
        return (
            f"{exc} Peca ao cliente que confirme qual moeda deseja consultar."
        )
    except ErroServicoExterno as exc:
        log.error("Servico de cotacao indisponivel: %s", exc)
        return (
            "O provedor de cotacoes esta indisponivel no momento. Informe o "
            "cliente com clareza, sem inventar nenhum valor, e ofereca tentar "
            "novamente em instantes ou tratar outro assunto."
        )

    return (
        f"Cotacao obtida ({cotacao.nome}): {cotacao.resumo()} "
        f"Maxima do dia: {cotacao.maxima:.4f}. Minima: {cotacao.minima:.4f}. "
        "Apresente a cotacao ao cliente de forma clara e pergunte se pode "
        "ajudar em algo mais antes de encerrar."
    )
