"""Retentativa do LLM diante do limite de taxa do provedor."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from banco_agil import graph


class ModeloInstavel:
    """Falha N vezes com um erro dado e depois responde."""

    def __init__(self, falhas: int, excecao: Exception) -> None:
        self.restantes = falhas
        self.excecao = excecao
        self.chamadas = 0

    def invoke(self, mensagens):
        self.chamadas += 1
        if self.restantes > 0:
            self.restantes -= 1
            raise self.excecao
        return AIMessage(content="ok")


ERRO_429 = RuntimeError(
    "429 RESOURCE_EXHAUSTED. Quota exceeded ... Please retry in 15.02s."
)


@pytest.fixture(autouse=True)
def sem_espera_real(monkeypatch):
    """Nenhum teste deve dormir de verdade."""
    esperas: list[float] = []
    monkeypatch.setattr(graph.time, "sleep", esperas.append)
    return esperas


@pytest.mark.parametrize(
    "texto",
    [
        "429 RESOURCE_EXHAUSTED",
        "Rate limit exceeded",
        "You exceeded your current quota",
    ],
)
def test_reconhece_erros_de_limite_de_taxa(texto):
    assert graph._e_limite_de_taxa(RuntimeError(texto)) is True


def test_nao_confunde_outros_erros_com_limite_de_taxa():
    assert graph._e_limite_de_taxa(RuntimeError("404 model not found")) is False


def test_reaproveita_o_tempo_sugerido_pela_api():
    # "retry in 15.02s" -> espera 16.02s (sugestao + margem).
    assert graph._espera_sugerida(ERRO_429, 1) == pytest.approx(16.02, abs=0.01)


def test_espera_respeita_o_teto():
    erro = RuntimeError("429 ... Please retry in 900s.")
    assert graph._espera_sugerida(erro, 1) == graph.ESPERA_MAXIMA_SEGUNDOS


def test_sem_sugestao_usa_backoff_exponencial():
    erro = RuntimeError("429 RESOURCE_EXHAUSTED")
    primeira = graph._espera_sugerida(erro, 1)
    terceira = graph._espera_sugerida(erro, 3)
    assert 2.0 <= primeira <= 3.0
    assert terceira > primeira


def test_retentativa_bem_sucedida(sem_espera_real):
    modelo = ModeloInstavel(falhas=2, excecao=ERRO_429)
    resposta = graph.invocar_modelo(modelo, [])

    assert resposta.content == "ok"
    assert modelo.chamadas == 3
    assert len(sem_espera_real) == 2


def test_desiste_apos_o_maximo_de_tentativas(sem_espera_real):
    modelo = ModeloInstavel(falhas=99, excecao=ERRO_429)

    with pytest.raises(graph.ErroLimiteDeTaxa):
        graph.invocar_modelo(modelo, [])

    assert modelo.chamadas == graph.MAX_TENTATIVAS_MODELO


def test_erro_que_nao_e_limite_de_taxa_sobe_na_hora(sem_espera_real):
    modelo = ModeloInstavel(falhas=99, excecao=ValueError("prompt invalido"))

    with pytest.raises(ValueError):
        graph.invocar_modelo(modelo, [])

    assert modelo.chamadas == 1
    assert sem_espera_real == []


def test_limite_de_taxa_vira_mensagem_amigavel_no_grafo(monkeypatch, tmp_path):
    """O cliente recebe um recado claro, nao um traceback."""
    from banco_agil import config
    from banco_agil.graph import SessaoAtendimento, construir_grafo

    monkeypatch.setattr(config, "ARQUIVO_CLIENTES", tmp_path / "clientes.csv")

    class SempreEstourado:
        def bind_tools(self, ferramentas):
            return self

        def invoke(self, mensagens):
            raise ERRO_429

    sessao = SessaoAtendimento(
        grafo=construir_grafo(llm=SempreEstourado()), thread_id="teste-429"
    )
    resposta = sessao.enviar("oi")

    assert "volume alto" in resposta.lower()
    assert sessao.encerrada is False
