"""Formula de score da entrevista de credito."""

from __future__ import annotations

import pytest

from banco_agil import config
from banco_agil.erros import ErroEntradaInvalida
from banco_agil.services import score as servico


def _entrevista(**kwargs):
    padrao = {
        "renda_mensal": 5000,
        "tipo_emprego": "formal",
        "despesas_fixas": 2000,
        "numero_dependentes": 0,
        "tem_dividas": "nao",
    }
    padrao.update(kwargs)
    return servico.normalizar_entrevista(**padrao)


def test_formula_segue_o_enunciado():
    dados = _entrevista()
    resultado = servico.calcular_score(dados)

    # (5000 / 2001) * 30 + 300 (formal) + 100 (0 dependentes) + 100 (sem dividas)
    esperado = (5000 / 2001) * 30 + 300 + 100 + 100
    assert resultado.score_bruto == pytest.approx(round(esperado, 2))
    assert resultado.score == round(esperado)


def test_componentes_sao_detalhados():
    resultado = servico.calcular_score(_entrevista())
    assert resultado.componentes["emprego"] == 300
    assert resultado.componentes["dependentes"] == 100
    assert resultado.componentes["dividas"] == 100
    assert resultado.componentes["renda"] > 0


@pytest.mark.parametrize(
    ("tipo", "peso"), [("formal", 300), ("autonomo", 200), ("desempregado", 0)]
)
def test_peso_de_emprego(tipo, peso):
    assert servico.calcular_score(_entrevista(tipo_emprego=tipo)).componentes[
        "emprego"
    ] == peso


@pytest.mark.parametrize(
    ("dependentes", "peso"), [(0, 100), (1, 80), (2, 60), (3, 30), (7, 30)]
)
def test_peso_de_dependentes_agrupa_tres_ou_mais(dependentes, peso):
    resultado = servico.calcular_score(_entrevista(numero_dependentes=dependentes))
    assert resultado.componentes["dependentes"] == peso


@pytest.mark.parametrize(("dividas", "peso"), [("sim", -100), ("nao", 100)])
def test_peso_de_dividas(dividas, peso):
    assert servico.calcular_score(_entrevista(tem_dividas=dividas)).componentes[
        "dividas"
    ] == peso


def test_score_nunca_passa_de_1000():
    # Renda altissima com despesa zero explodiria a formula sem o teto.
    resultado = servico.calcular_score(
        _entrevista(renda_mensal=1_000_000, despesas_fixas=0)
    )
    assert resultado.score == config.SCORE_MAXIMO
    assert resultado.score_bruto > config.SCORE_MAXIMO


def test_score_nunca_fica_abaixo_de_zero():
    resultado = servico.calcular_score(
        _entrevista(
            renda_mensal=0,
            tipo_emprego="desempregado",
            despesas_fixas=3000,
            numero_dependentes=5,
            tem_dividas="sim",
        )
    )
    assert resultado.score == config.SCORE_MINIMO


def test_despesa_zero_nao_divide_por_zero():
    resultado = servico.calcular_score(
        _entrevista(renda_mensal=1000, despesas_fixas=0)
    )
    # (1000 / 1) * 30 = 30000 -> truncado
    assert resultado.score == config.SCORE_MAXIMO


def test_normalizacao_aceita_texto_livre():
    dados = servico.normalizar_entrevista(
        renda_mensal="R$ 4.500,00",
        tipo_emprego="Carteira assinada",
        despesas_fixas="1.200,50",
        numero_dependentes="2",
        tem_dividas="Não",
    )
    assert dados.renda_mensal == pytest.approx(4500.0)
    assert dados.tipo_emprego == "formal"
    assert dados.despesas_fixas == pytest.approx(1200.50)
    assert dados.numero_dependentes == 2
    assert dados.tem_dividas == "nao"


def test_normalizacao_rejeita_resposta_ininteligivel():
    with pytest.raises(ErroEntradaInvalida):
        servico.normalizar_entrevista(
            renda_mensal="depende do mes",
            tipo_emprego="formal",
            despesas_fixas=1000,
            numero_dependentes=0,
            tem_dividas="nao",
        )
