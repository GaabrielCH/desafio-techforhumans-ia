"""Gera o diagrama de arquitetura a partir do grafo compilado.

    python scripts/gerar_diagrama.py

Um diagrama desenhado a mao envelhece: alguem acrescenta um no e o desenho
continua mostrando a topologia antiga. Este script pergunta ao proprio
LangGraph qual e a topologia, entao o desenho nao tem como divergir do
codigo.

Usa um duble de LLM - nao precisa de chave de API nem de rede.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from langchain_core.messages import AIMessage  # noqa: E402

from banco_agil.graph import construir_grafo  # noqa: E402

DESTINO = RAIZ / "docs" / "arquitetura.mmd"


class LLMParaDesenho:
    """So precisa existir: o grafo e montado, nunca executado."""

    def bind_tools(self, ferramentas):
        return self

    def invoke(self, mensagens):
        return AIMessage(content="")


def main() -> int:
    grafo = construir_grafo(llm=LLMParaDesenho())

    try:
        mermaid = grafo.get_graph().draw_mermaid()
    except Exception as exc:  # noqa: BLE001
        print(f"Nao foi possivel gerar o diagrama: {exc}")
        return 1

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(mermaid, encoding="utf-8")

    print(f"Diagrama gravado em {DESTINO.relative_to(RAIZ)}")
    print()
    print(mermaid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
