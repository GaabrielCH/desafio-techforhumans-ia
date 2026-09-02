"""Ferramentas disponiveis para todos os agentes."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from ..logging_config import obter_logger

log = obter_logger("ferramenta.comuns")


@tool("encerrar_atendimento")
def encerrar_atendimento(
    mensagem_final: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Encerra o atendimento e finaliza o loop de execucao.

    Use quando o cliente pedir para encerrar, se despedir, disser que nao
    precisa de mais nada, ou quando a autenticacao falhar em definitivo.

    Args:
        mensagem_final: despedida curta e cordial que sera exibida ao cliente.
    """
    log.info("Atendimento encerrado. Mensagem final: %s", mensagem_final)
    return Command(
        update={
            "encerrado": True,
            "messages": [
                ToolMessage(
                    content=(
                        "Atendimento encerrado. Responda ao cliente apenas com "
                        f"esta despedida: {mensagem_final}"
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
