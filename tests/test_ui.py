"""Fumaca da interface Streamlit.

Servir o HTML nao prova nada: o Streamlit devolve a casca da pagina mesmo
quando o script quebra. Estes testes executam `app.py` de verdade, com um
LLM dublê, e conferem que nenhuma excecao escapou.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

APP = Path(__file__).resolve().parents[1] / "app.py"

AppTest = pytest.importorskip(
    "streamlit.testing.v1", reason="Streamlit sem framework de teste"
).AppTest


class LLMFalso:
    """Responde sempre a mesma coisa; ferramentas nunca sao chamadas."""

    def __init__(self, texto: str = "Ola! Sou o Agil. Qual o seu CPF?") -> None:
        self.texto = texto

    def bind_tools(self, ferramentas):
        return self

    def invoke(self, mensagens):
        return AIMessage(content=self.texto)


@pytest.fixture()
def app_com_llm_falso(monkeypatch, base_clientes, base_score_limite):
    from banco_agil import config, graph

    monkeypatch.setattr(config, "ARQUIVO_CLIENTES", base_clientes)
    monkeypatch.setattr(config, "ARQUIVO_SCORE_LIMITE", base_score_limite)
    monkeypatch.setattr(graph, "criar_modelo", lambda *a, **k: LLMFalso())

    return AppTest.from_file(str(APP), default_timeout=30).run()


def test_pagina_carrega_sem_excecao(app_com_llm_falso):
    at = app_com_llm_falso
    assert not at.exception, [str(e) for e in at.exception]


def _textos(at) -> str:
    """Todo o markdown renderizado na pagina, concatenado."""
    return " ".join(str(m.value) for m in at.markdown)


def test_saudacao_inicial_aparece_no_chat(app_com_llm_falso):
    assert app_com_llm_falso.chat_message, "nenhuma mensagem renderizada"
    assert "CPF" in _textos(app_com_llm_falso)


def test_barra_lateral_mostra_estado_nao_autenticado(app_com_llm_falso):
    textos = " ".join(str(w.value) for w in app_com_llm_falso.sidebar.warning)
    assert "Nao autenticado" in textos


def test_conversa_avanca_ao_enviar_mensagem(app_com_llm_falso):
    at = app_com_llm_falso
    at.chat_input[0].set_value("meu cpf e 12345678901").run()

    assert not at.exception, [str(e) for e in at.exception]
    # A mensagem do cliente e a resposta do agente estao ambas na pagina.
    conteudo = _textos(at)
    assert "12345678901" in conteudo
    assert "CPF" in conteudo


def test_sem_chave_de_api_a_ui_orienta_em_vez_de_quebrar(
    monkeypatch, base_clientes
):
    """O avaliador que rodar sem .env precisa entender o que fazer."""
    from banco_agil import config, graph
    from banco_agil.erros import ErroBancoAgil

    monkeypatch.setattr(config, "ARQUIVO_CLIENTES", base_clientes)

    def sem_chave(*args, **kwargs):
        raise ErroBancoAgil("GOOGLE_API_KEY nao configurada.")

    monkeypatch.setattr(graph, "criar_modelo", sem_chave)

    at = AppTest.from_file(str(APP), default_timeout=30).run()

    assert not at.exception, [str(e) for e in at.exception]
    erros = " ".join(str(e.value) for e in at.error)
    assert "GOOGLE_API_KEY" in erros
