"""O diagrama versionado nao pode divergir do grafo real.

Diagrama de arquitetura desenhado a mao envelhece em silencio: alguem
acrescenta um no e o desenho segue mostrando a topologia antiga. Aqui o
desenho e gerado do proprio grafo compilado, e este teste falha se o arquivo
versionado ficar para tras.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from banco_agil import config
from banco_agil.graph import construir_grafo

RAIZ = Path(__file__).resolve().parents[1]
DIAGRAMA = RAIZ / "docs" / "arquitetura.mmd"
SCRIPT = RAIZ / "scripts" / "gerar_diagrama.py"


class LLMParaDesenho:
    def bind_tools(self, ferramentas):
        return self

    def invoke(self, mensagens):
        return AIMessage(content="")


@pytest.fixture()
def topologia() -> str:
    return construir_grafo(llm=LLMParaDesenho()).get_graph().draw_mermaid()


def test_diagrama_versionado_esta_atualizado(topologia):
    if not DIAGRAMA.exists():
        pytest.skip("diagrama nao versionado neste checkout")

    gravado = DIAGRAMA.read_text(encoding="utf-8").strip()
    assert gravado == topologia.strip(), (
        "docs/arquitetura.mmd ficou para tras. "
        "Rode: python scripts/gerar_diagrama.py"
    )


def test_todos_os_agentes_estao_no_grafo(topologia):
    for agente in config.AGENTES:
        assert agente in topologia, f"agente '{agente}' ausente do grafo"


def test_no_de_ferramentas_alcanca_todos_os_agentes(topologia):
    """E isso que torna o handoff possivel entre quaisquer especialidades."""
    for agente in config.AGENTES:
        assert f"ferramentas -.-> {agente}" in topologia, (
            f"o no de ferramentas nao volta para '{agente}'"
        )


def test_todo_agente_pode_encerrar_o_turno(topologia):
    """Sem aresta para o fim, o grafo nunca devolveria a palavra ao cliente."""
    for agente in config.AGENTES:
        assert f"{agente} -.-> __end__" in topologia


def test_script_de_geracao_roda(tmp_path):
    """O script precisa funcionar sem chave de API e sem rede."""
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(RAIZ),
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "Diagrama gravado" in resultado.stdout
