"""Normalizacao de entradas em texto livre."""

from __future__ import annotations

import pytest

from banco_agil.erros import ErroEntradaInvalida
from banco_agil.utils import (
    formatar_moeda,
    normalizar_cpf,
    normalizar_data,
    normalizar_inteiro_nao_negativo,
    normalizar_sim_nao,
    normalizar_tipo_emprego,
    normalizar_valor_monetario,
)


@pytest.mark.parametrize(
    "entrada",
    ["123.456.789-01", "12345678901", " 123 456 789 01 "],
)
def test_normalizar_cpf_aceita_formatos_usuais(entrada):
    assert normalizar_cpf(entrada) == "12345678901"


@pytest.mark.parametrize("entrada", ["123", "", "abcdefghijk", "123456789012"])
def test_normalizar_cpf_rejeita_invalidos(entrada):
    with pytest.raises(ErroEntradaInvalida):
        normalizar_cpf(entrada)


@pytest.mark.parametrize(
    "entrada",
    ["14/05/1990", "1990-05-14", "14-05-1990", "14.05.1990", "14051990"],
)
def test_normalizar_data_converte_para_iso(entrada):
    assert normalizar_data(entrada) == "1990-05-14"


@pytest.mark.parametrize("entrada", ["32/13/1990", "ontem", ""])
def test_normalizar_data_rejeita_invalidas(entrada):
    with pytest.raises(ErroEntradaInvalida):
        normalizar_data(entrada)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("R$ 5.000,00", 5000.0),
        ("5000", 5000.0),
        ("5000.50", 5000.5),
        ("5.000", 5000.0),
        ("1.234.567,89", 1234567.89),
        ("2,5", 2.5),
        (3000, 3000.0),
        (1500.75, 1500.75),
    ],
)
def test_normalizar_valor_monetario(entrada, esperado):
    assert normalizar_valor_monetario(entrada) == pytest.approx(esperado)


def test_normalizar_valor_monetario_rejeita_negativo():
    with pytest.raises(ErroEntradaInvalida):
        normalizar_valor_monetario(-100)


def test_normalizar_valor_monetario_rejeita_texto():
    with pytest.raises(ErroEntradaInvalida):
        normalizar_valor_monetario("bastante dinheiro")


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("0", 0),
        ("3", 3),
        ("nenhum", 0),
        ("sem dependentes", 0),
        (2, 2),
        ("tenho 4", 4),
    ],
)
def test_normalizar_inteiro_nao_negativo(entrada, esperado):
    assert normalizar_inteiro_nao_negativo(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("dois", 2),
        ("duas filhas", 2),
        ("tres", 3),
        ("um dependente", 1),
        ("zero", 0),
        ("nenhuma", 0),
    ],
)
def test_normalizar_inteiro_aceita_numero_por_extenso(entrada, esperado):
    # O cliente responde "dois filhos" com naturalidade; exigir digito
    # obrigaria o agente a refazer a pergunta sem necessidade.
    assert normalizar_inteiro_nao_negativo(entrada) == esperado


def test_normalizar_inteiro_ainda_rejeita_o_ininteligivel():
    with pytest.raises(ErroEntradaInvalida):
        normalizar_inteiro_nao_negativo("depende do mes")


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("sim", "sim"),
        ("SIM", "sim"),
        ("nao", "nao"),
        ("Não", "nao"),
        ("s", "sim"),
        ("n", "nao"),
        (True, "sim"),
        (False, "nao"),
        ("sem dividas", "nao"),
    ],
)
def test_normalizar_sim_nao(entrada, esperado):
    assert normalizar_sim_nao(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("formal", "formal"),
        ("CLT", "formal"),
        ("carteira assinada", "formal"),
        ("autonomo", "autonomo"),
        ("autônomo", "autonomo"),
        ("freelancer", "autonomo"),
        ("PJ", "autonomo"),
        ("desempregado", "desempregado"),
        ("estou desempregada", "desempregado"),
    ],
)
def test_normalizar_tipo_emprego(entrada, esperado):
    assert normalizar_tipo_emprego(entrada) == esperado


def test_normalizar_tipo_emprego_rejeita_desconhecido():
    with pytest.raises(ErroEntradaInvalida):
        normalizar_tipo_emprego("trabalho com o que aparece")


def test_formatar_moeda_usa_padrao_brasileiro():
    assert formatar_moeda(1234.5) == "R$ 1.234,50"
