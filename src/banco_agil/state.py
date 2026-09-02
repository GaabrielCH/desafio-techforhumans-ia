"""Estado compartilhado do atendimento.

Um unico dicionario atravessa todo o grafo. Alem do historico de mensagens,
ele carrega o que precisa sobreviver a uma troca de agente: quem esta
falando, se o cliente ja se autenticou e quantas tentativas restam.

Guardar isso no estado (e nao no prompt) e o que impede o LLM de
"alucinar" uma autenticacao: as ferramentas sensiveis leem ``autenticado``
diretamente daqui.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from . import config


class EstadoAtendimento(TypedDict, total=False):
    """Estado do grafo de atendimento."""

    # Historico da conversa (reducer oficial do LangGraph).
    messages: Annotated[list[Any], add_messages]

    # Roteamento entre agentes.
    agente_atual: str

    # Sessao do cliente.
    autenticado: bool
    cpf: str | None
    nome: str | None
    tentativas_autenticacao: int

    # Contexto de negocio util entre agentes.
    ultimo_status_solicitacao: str | None

    # Sinaliza fim do loop de execucao.
    encerrado: bool


def estado_inicial() -> EstadoAtendimento:
    """Estado de uma conversa nova: ninguem autenticado, triagem no comando."""
    return {
        "messages": [],
        "agente_atual": config.AGENTE_TRIAGEM,
        "autenticado": False,
        "cpf": None,
        "nome": None,
        "tentativas_autenticacao": 0,
        "ultimo_status_solicitacao": None,
        "encerrado": False,
    }
