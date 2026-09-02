"""Ferramentas de redirecionamento entre agentes.

O redirecionamento e implicito para o cliente: a ferramenta apenas troca
``agente_atual`` no estado e devolve uma instrucao interna. O proximo no do
grafo ja responde com a nova especialidade, sem anunciar transferencia.

O texto do ToolMessage e escrito para o LLM, nunca para o cliente - por isso
ele repete que a transicao nao deve ser mencionada.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from .. import config
from ..logging_config import obter_logger

log = obter_logger("ferramenta.handoff")

_INSTRUCAO = (
    "Contexto interno (nao mencione ao cliente): voce agora atua com a "
    "especialidade de {especialidade}. Continue a conversa naturalmente, "
    "como se fosse o mesmo atendente do inicio. Nunca diga que houve "
    "transferencia, encaminhamento ou mudanca de setor."
)


def _redirecionar(
    destino: str, especialidade: str, tool_call_id: str
) -> Command:
    log.info("Redirecionamento implicito para o agente '%s'.", destino)
    return Command(
        update={
            "agente_atual": destino,
            "messages": [
                ToolMessage(
                    content=_INSTRUCAO.format(especialidade=especialidade),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool("direcionar_para_credito")
def direcionar_para_credito(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Assume os assuntos de limite de credito e aumento de limite.

    Use quando o cliente falar sobre limite, cartao, aumento de limite,
    credito disponivel ou analise de credito. Exige cliente autenticado.
    """
    if not state.get("autenticado"):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Bloqueado: o cliente ainda nao foi autenticado. "
                            "Peca CPF e data de nascimento antes de tratar "
                            "qualquer assunto de credito."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    return _redirecionar(
        config.AGENTE_CREDITO, "limite e aumento de credito", tool_call_id
    )


@tool("direcionar_para_cambio")
def direcionar_para_cambio(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Assume os assuntos de cotacao de moedas.

    Use quando o cliente perguntar sobre dolar, euro, cotacao ou cambio.
    Exige cliente autenticado.
    """
    if not state.get("autenticado"):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Bloqueado: o cliente ainda nao foi autenticado. "
                            "Peca CPF e data de nascimento antes de atender "
                            "qualquer solicitacao."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    return _redirecionar(
        config.AGENTE_CAMBIO, "cotacao de moedas", tool_call_id
    )


@tool("direcionar_para_entrevista")
def direcionar_para_entrevista(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Assume a entrevista financeira para recalcular o score do cliente.

    Use somente depois que o cliente aceitar responder algumas perguntas
    sobre a situacao financeira dele para tentar reajustar o score.
    """
    if not state.get("autenticado"):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Bloqueado: o cliente ainda nao foi autenticado."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    return _redirecionar(
        config.AGENTE_ENTREVISTA, "entrevista financeira de credito", tool_call_id
    )
