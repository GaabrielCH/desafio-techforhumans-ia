"""Servico de cotacao de moedas (API externa mockada)."""

from __future__ import annotations

import pytest
import requests

from banco_agil.erros import ErroEntradaInvalida, ErroServicoExterno
from banco_agil.services import cambio as servico

RESPOSTA_OK = {
    "USDBRL": {
        "code": "USD",
        "codein": "BRL",
        "name": "Dolar Americano/Real Brasileiro",
        "high": "5.4500",
        "low": "5.3800",
        "pctChange": "-0.35",
        "bid": "5.4010",
        "ask": "5.4025",
        "timestamp": "1717000000",
    }
}


class RespostaFalsa:
    def __init__(self, dados=None, status=200, quebra_json=False):
        self._dados = dados
        self.status_code = status
        self._quebra_json = quebra_json

    def json(self):
        if self._quebra_json:
            raise ValueError("nao e json")
        return self._dados


@pytest.mark.parametrize(
    ("entrada", "codigo"),
    [
        ("dolar", "USD"),
        ("Dólar", "USD"),
        ("USD", "USD"),
        ("euro", "EUR"),
        ("EUR", "EUR"),
        ("libra", "GBP"),
        ("cotacao do dolar hoje", "USD"),
        ("CHF", "CHF"),
    ],
)
def test_resolve_apelidos_de_moeda(entrada, codigo):
    assert servico.resolver_codigo_moeda(entrada) == codigo


@pytest.mark.parametrize("entrada", ["", "chocolate", "moeda do jogo"])
def test_moeda_desconhecida_gera_erro_de_entrada(entrada):
    with pytest.raises(ErroEntradaInvalida):
        servico.resolver_codigo_moeda(entrada)


def test_cotacao_bem_sucedida(monkeypatch):
    chamadas = []

    def get_falso(url, timeout):
        chamadas.append(url)
        return RespostaFalsa(RESPOSTA_OK)

    monkeypatch.setattr(requests, "get", get_falso)

    cotacao = servico.consultar_cotacao("dolar", "real")

    assert cotacao.moeda_origem == "USD"
    assert cotacao.moeda_destino == "BRL"
    assert cotacao.compra == pytest.approx(5.4010)
    assert cotacao.venda == pytest.approx(5.4025)
    assert cotacao.variacao_percentual == pytest.approx(-0.35)
    assert chamadas[0].endswith("/USD-BRL")
    assert "USD" in cotacao.resumo()


def test_mesma_moeda_de_origem_e_destino(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: pytest.fail("nao deveria chamar a API")
    )
    with pytest.raises(ErroEntradaInvalida):
        servico.consultar_cotacao("real", "BRL")


def test_api_fora_do_ar_gera_erro_de_servico(monkeypatch):
    def get_falso(url, timeout):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(requests, "get", get_falso)

    with pytest.raises(ErroServicoExterno):
        servico.consultar_cotacao("dolar")


def test_timeout_gera_erro_de_servico(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout())
    )
    with pytest.raises(ErroServicoExterno):
        servico.consultar_cotacao("dolar")


def test_par_inexistente_retorna_erro_de_entrada(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: RespostaFalsa(status=404))
    with pytest.raises(ErroEntradaInvalida):
        servico.consultar_cotacao("XYZ", "BRL")


def test_erro_5xx_e_tratado_como_servico_indisponivel(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: RespostaFalsa(status=503))
    with pytest.raises(ErroServicoExterno):
        servico.consultar_cotacao("dolar")


def test_resposta_em_formato_inesperado(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: RespostaFalsa({"USDBRL": {"foo": "bar"}})
    )
    with pytest.raises(ErroServicoExterno):
        servico.consultar_cotacao("dolar")


def test_retentativa_antes_de_desistir(monkeypatch):
    tentativas = {"n": 0}

    def get_falso(url, timeout):
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            raise requests.ConnectionError("falha transitoria")
        return RespostaFalsa(RESPOSTA_OK)

    monkeypatch.setattr(requests, "get", get_falso)

    cotacao = servico.consultar_cotacao("dolar")
    assert tentativas["n"] == 2
    assert cotacao.venda == pytest.approx(5.4025)
