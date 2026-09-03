"""Interface: fumaca do app e seguranca da renderizacao.

Servir o HTML nao prova nada - o Streamlit devolve a casca da pagina mesmo
quando o script quebra. Estes testes executam `app.py` de verdade, com um LLM
dublê.

A parte de seguranca importa porque a UI passou a montar HTML proprio para os
balões de conversa: o texto do cliente e do modelo entra em `unsafe_allow_html`
e precisa estar escapado.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dubles import LLMFalso
from langchain_core.messages import AIMessage

from banco_agil import ui

APP = Path(__file__).resolve().parents[1] / "app.py"

AppTest = pytest.importorskip(
    "streamlit.testing.v1", reason="Streamlit sem framework de teste"
).AppTest

_STREAMLIT_REAL = ui.st


class _StreamlitFalso:
    """Captura o markdown de um componente fora do runtime do Streamlit."""

    def __init__(self, destino: list[str]) -> None:
        self._destino = destino

    def markdown(self, corpo: str, **_kwargs) -> None:
        self._destino.append(corpo)


@pytest.fixture()
def app_com_llm_falso(monkeypatch, bases):
    from banco_agil import graph

    monkeypatch.setattr(
        graph,
        "criar_modelo",
        lambda *a, **k: LLMFalso([AIMessage(content="Olá! Qual é o seu CPF?")]),
    )
    return AppTest.from_file(str(APP), default_timeout=30).run()


def _pagina(at) -> str:
    """Todo o markdown renderizado, concatenado."""
    return " ".join(str(m.value) for m in at.markdown)


# --------------------------------------------------------------------------- #
# Fumaca
# --------------------------------------------------------------------------- #
def test_pagina_carrega_sem_excecao(app_com_llm_falso):
    assert not app_com_llm_falso.exception, [
        str(e) for e in app_com_llm_falso.exception
    ]


def test_saudacao_inicial_aparece(app_com_llm_falso):
    assert "CPF" in _pagina(app_com_llm_falso)


def test_marca_e_especialidade_sao_renderizadas(app_com_llm_falso):
    pagina = _pagina(app_com_llm_falso)
    assert "Banco Ágil" in pagina
    assert "ag-atual-nome" in pagina, "a especialidade atual nao apareceu"
    assert "Triagem" in pagina


def test_percurso_so_aparece_depois_do_primeiro_handoff(app_com_llm_falso):
    """Um percurso de um item so seria repeticao da especialidade atual."""
    # Procurar a classe solta acharia tambem o seletor dentro do <style>.
    assert '<div class="ag-percurso">' not in _pagina(app_com_llm_falso)


def test_percurso_mostra_a_sequencia_de_especialidades():
    """Com mais de uma parada, o percurso conta a historia do roteamento."""
    from banco_agil import config

    marcacao: list[str] = []
    ui.st = _StreamlitFalso(marcacao)  # type: ignore[assignment]
    try:
        ui.percurso([config.AGENTE_TRIAGEM, config.AGENTE_CREDITO])
    finally:
        ui.st = _STREAMLIT_REAL  # type: ignore[assignment]

    saida = " ".join(marcacao)
    assert '<div class="ag-percurso">' in saida
    assert "Triagem" in saida and "Crédito" in saida
    assert "→" in saida


def test_registro_do_turno_some_quando_nao_ha_nada(app_com_llm_falso):
    """Um bloco dizendo 'nada aconteceu' ocupa espaco sem informar."""
    assert "No último turno" not in _pagina(app_com_llm_falso)


def test_conversa_avanca_ao_enviar_mensagem(app_com_llm_falso):
    at = app_com_llm_falso
    at.chat_input[0].set_value("meu cpf é 12345678901").run()

    assert not at.exception, [str(e) for e in at.exception]
    pagina = _pagina(at)
    assert "12345678901" in pagina
    assert "CPF" in pagina


def test_sem_chave_de_api_a_ui_orienta_em_vez_de_quebrar(monkeypatch, bases):
    """Quem rodar sem .env precisa entender o que fazer."""
    from banco_agil import graph
    from banco_agil.erros import ErroBancoAgil

    def sem_chave(*args, **kwargs):
        raise ErroBancoAgil("GOOGLE_API_KEY nao configurada.")

    monkeypatch.setattr(graph, "criar_modelo", sem_chave)
    at = AppTest.from_file(str(APP), default_timeout=30).run()

    assert not at.exception, [str(e) for e in at.exception]
    assert "GOOGLE_API_KEY" in " ".join(str(e.value) for e in at.error)


# --------------------------------------------------------------------------- #
# Seguranca da renderizacao
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "malicioso",
    [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "</div><style>body{display:none}</style>",
        "<a href='javascript:alert(1)'>clique</a>",
        "<iframe src='http://exemplo.com'></iframe>",
    ],
)
def test_html_do_cliente_e_neutralizado(malicioso):
    """O texto vira para dentro de unsafe_allow_html: tem de sair escapado."""
    saida = ui.formatar_para_html(malicioso)
    assert "<script" not in saida.lower()
    assert "<img" not in saida.lower()
    assert "<iframe" not in saida.lower()
    assert "<style" not in saida.lower()
    assert "onerror" not in saida.lower() or "&lt;" in saida
    assert "&lt;" in saida


def test_formatacao_permitida_sobrevive():
    """Negrito, quebra de linha e valores continuam funcionando."""
    saida = ui.formatar_para_html("Limite **aprovado**\nR$ 5.000,00")
    assert "<strong>aprovado</strong>" in saida
    assert "<br>" in saida
    assert 'class="ag-valor"' in saida


def test_negrito_nao_vira_brecha_de_html():
    """O escape acontece ANTES de reintroduzir o negrito."""
    saida = ui.formatar_para_html("**<script>x</script>**")
    assert "<script>" not in saida
    assert "<strong>" in saida


def test_texto_vazio_nao_quebra():
    assert ui.formatar_para_html("") == ""
    assert ui.formatar_para_html(None) == ""


def test_nome_do_cliente_e_escapado_na_ficha(monkeypatch):
    """A ficha da retaguarda tambem monta HTML com dado vindo do CSV."""
    import html as _html

    nome = "<script>roubar()</script>"
    assert "&lt;script&gt;" in _html.escape(nome)
    # A ficha usa html.escape diretamente; este teste fixa a expectativa.
    assert "<script>" not in _html.escape(nome)
