"""Dubles compartilhados pelos testes de grafo e de seguranca."""

from __future__ import annotations

from langchain_core.messages import AIMessage


class LLMFalso:
    """Dublê de chat model: devolve mensagens roteirizadas, em ordem.

    Implementa apenas ``bind_tools`` e ``invoke``, que e tudo que o no do
    agente consome. Quando o roteiro acaba, responde algo neutro - assim um
    turno a mais nao quebra o teste com IndexError.
    """

    def __init__(self, roteiro: list[AIMessage] | None = None) -> None:
        self.roteiro = list(roteiro or [])
        self.chamadas: list[list] = []
        self.ultimas_ferramentas: list[str] | None = None

    def bind_tools(self, ferramentas):  # noqa: D102 - interface do LangChain
        self.ultimas_ferramentas = [f.name for f in ferramentas]
        return self

    def invoke(self, mensagens):  # noqa: D102
        self.chamadas.append(mensagens)
        if not self.roteiro:
            return AIMessage(content="Posso ajudar em algo mais?")
        return self.roteiro.pop(0)


def chamada(nome: str, args: dict | None = None, ident: str = "call_1") -> AIMessage:
    """Monta uma AIMessage que solicita uma ferramenta."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": nome,
                "args": args or {},
                "id": ident,
                "type": "tool_call",
            }
        ],
    )
