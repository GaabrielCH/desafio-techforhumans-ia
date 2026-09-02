"""Politica de credito e ciclo de vida da solicitacao de aumento."""

from __future__ import annotations

import csv

import pytest

from banco_agil import config
from banco_agil.erros import ErroEntradaInvalida
from banco_agil.repositories import score_limite as repo_faixas
from banco_agil.repositories import solicitacoes as repo_solicitacoes
from banco_agil.services import credito as servico


def _linhas(caminho):
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


@pytest.mark.parametrize(
    ("score", "teto"),
    [(0, 1000.0), (299, 1000.0), (300, 3000.0), (699, 8000.0), (720, 15000.0),
     (850, 30000.0), (1000, 30000.0)],
)
def test_teto_por_faixa_de_score(score, teto, base_score_limite):
    assert repo_faixas.limite_maximo_para_score(score, base_score_limite) == teto


def test_score_fora_da_tabela_cai_na_faixa_mais_proxima(base_score_limite):
    assert repo_faixas.limite_maximo_para_score(-10, base_score_limite) == 1000.0
    assert repo_faixas.limite_maximo_para_score(5000, base_score_limite) == 30000.0


def test_aumento_aprovado_quando_cabe_no_teto(
    base_clientes, base_score_limite, base_solicitacoes
):
    # Ana: score 720 -> teto 15000; limite atual 5000.
    resultado = servico.analisar_aumento(
        "12345678901", 10000, base_clientes, base_score_limite, base_solicitacoes
    )

    assert resultado.aprovado is True
    assert resultado.status == config.STATUS_APROVADO
    assert resultado.limite_maximo_autorizado == 15000.0

    linhas = _linhas(base_solicitacoes)
    assert len(linhas) == 1
    assert linhas[0]["status_pedido"] == "aprovado"


def test_aprovacao_efetiva_o_novo_limite_na_base(
    base_clientes, base_score_limite, base_solicitacoes
):
    from banco_agil.repositories import clientes as repo_clientes

    servico.analisar_aumento(
        "12345678901", 10000, base_clientes, base_score_limite, base_solicitacoes
    )

    cliente = repo_clientes.buscar_por_cpf("12345678901", base_clientes)
    assert cliente.limite_credito == pytest.approx(10000.0)


def test_rejeicao_nao_altera_o_limite_na_base(
    base_clientes, base_score_limite, base_solicitacoes
):
    from banco_agil.repositories import clientes as repo_clientes

    servico.analisar_aumento(
        "98765432100", 9000, base_clientes, base_score_limite, base_solicitacoes
    )

    cliente = repo_clientes.buscar_por_cpf("98765432100", base_clientes)
    assert cliente.limite_credito == pytest.approx(1500.0)


def test_aumento_rejeitado_quando_estoura_o_teto(
    base_clientes, base_score_limite, base_solicitacoes
):
    # Carlos: score 410 -> teto 3000; pede 9000.
    resultado = servico.analisar_aumento(
        "98765432100", 9000, base_clientes, base_score_limite, base_solicitacoes
    )

    assert resultado.aprovado is False
    assert resultado.status == config.STATUS_REJEITADO
    assert _linhas(base_solicitacoes)[0]["status_pedido"] == "rejeitado"


def test_arquivo_de_solicitacoes_tem_as_colunas_do_desafio(
    base_clientes, base_score_limite, base_solicitacoes
):
    servico.analisar_aumento(
        "12345678901", 6000, base_clientes, base_score_limite, base_solicitacoes
    )

    with base_solicitacoes.open(encoding="utf-8", newline="") as arquivo:
        colunas = next(csv.reader(arquivo))

    assert colunas == [
        "cpf_cliente",
        "data_hora_solicitacao",
        "limite_atual",
        "novo_limite_solicitado",
        "status_pedido",
    ]

    linha = _linhas(base_solicitacoes)[0]
    assert linha["cpf_cliente"] == "12345678901"
    assert float(linha["limite_atual"]) == pytest.approx(5000.0)
    assert float(linha["novo_limite_solicitado"]) == pytest.approx(6000.0)
    # Timestamp em ISO 8601.
    from datetime import datetime

    datetime.fromisoformat(linha["data_hora_solicitacao"])


def test_pedido_e_registrado_mesmo_quando_rejeitado(
    base_clientes, base_score_limite, base_solicitacoes
):
    servico.analisar_aumento(
        "55566677788", 20000, base_clientes, base_score_limite, base_solicitacoes
    )
    assert len(_linhas(base_solicitacoes)) == 1


def test_solicitacoes_acumulam_no_mesmo_arquivo(
    base_clientes, base_score_limite, base_solicitacoes
):
    servico.analisar_aumento(
        "12345678901", 6000, base_clientes, base_score_limite, base_solicitacoes
    )
    servico.analisar_aumento(
        "98765432100", 2000, base_clientes, base_score_limite, base_solicitacoes
    )
    linhas = _linhas(base_solicitacoes)
    assert len(linhas) == 2
    assert {l["cpf_cliente"] for l in linhas} == {"12345678901", "98765432100"}


def test_limite_menor_ou_igual_ao_atual_e_recusado_antes_de_gravar(
    base_clientes, base_score_limite, base_solicitacoes
):
    with pytest.raises(ErroEntradaInvalida):
        servico.analisar_aumento(
            "12345678901", 3000, base_clientes, base_score_limite, base_solicitacoes
        )
    assert not base_solicitacoes.exists()


def test_limite_zero_ou_negativo_e_recusado(
    base_clientes, base_score_limite, base_solicitacoes
):
    for valor in (0, -100):
        with pytest.raises(ErroEntradaInvalida):
            servico.analisar_aumento(
                "12345678901",
                valor,
                base_clientes,
                base_score_limite,
                base_solicitacoes,
            )


def test_valor_exatamente_no_teto_e_aprovado(
    base_clientes, base_score_limite, base_solicitacoes
):
    # Ana: teto 15000 -> pedir exatamente 15000 deve passar.
    resultado = servico.analisar_aumento(
        "12345678901", 15000, base_clientes, base_score_limite, base_solicitacoes
    )
    assert resultado.aprovado is True


def test_historico_por_cpf(base_clientes, base_score_limite, base_solicitacoes):
    servico.analisar_aumento(
        "12345678901", 6000, base_clientes, base_score_limite, base_solicitacoes
    )
    servico.analisar_aumento(
        "12345678901", 20000, base_clientes, base_score_limite, base_solicitacoes
    )

    historico = repo_solicitacoes.listar_por_cpf("12345678901", base_solicitacoes)
    assert [s.status_pedido for s in historico] == ["aprovado", "rejeitado"]


def test_dois_pedidos_no_mesmo_instante_nao_se_sobrescrevem(
    base_solicitacoes, monkeypatch
):
    """Regressao: com timestamps iguais, o update ia parar na linha errada.

    Sem id proprio no CSV, a chave (cpf, data_hora) pode repetir. O update
    precisa alcancar a ultima linha com aquela chave, nunca a primeira.
    """
    from banco_agil import utils

    monkeypatch.setattr(utils, "agora_iso", lambda: "2026-09-02T18:00:00.000-03:00")
    monkeypatch.setattr(repo_solicitacoes, "agora_iso", utils.agora_iso)

    primeira = repo_solicitacoes.registrar(
        "12345678901", 1000, 5000, caminho=base_solicitacoes
    )
    repo_solicitacoes.atualizar_status(
        "12345678901", primeira.data_hora_solicitacao, "rejeitado", base_solicitacoes
    )

    segunda = repo_solicitacoes.registrar(
        "12345678901", 1000, 5000, caminho=base_solicitacoes
    )
    assert segunda.data_hora_solicitacao == primeira.data_hora_solicitacao

    repo_solicitacoes.atualizar_status(
        "12345678901", segunda.data_hora_solicitacao, "aprovado", base_solicitacoes
    )

    assert [l["status_pedido"] for l in _linhas(base_solicitacoes)] == [
        "rejeitado",
        "aprovado",
    ]


def test_entrevista_muda_o_desfecho_da_mesma_solicitacao(
    base_clientes, base_score_limite, base_solicitacoes
):
    """Fluxo completo do desafio: rejeitado -> entrevista -> aprovado."""
    from banco_agil.repositories import clientes as repo_clientes

    # Rafael: score 250 -> teto 1000. Pede 5000 e e rejeitado.
    primeira = servico.analisar_aumento(
        "55566677788", 5000, base_clientes, base_score_limite, base_solicitacoes
    )
    assert primeira.status == config.STATUS_REJEITADO

    # Entrevista eleva o score para 720 -> teto 15000.
    repo_clientes.atualizar_score("55566677788", 720, base_clientes)

    segunda = servico.analisar_aumento(
        "55566677788", 5000, base_clientes, base_score_limite, base_solicitacoes
    )
    assert segunda.status == config.STATUS_APROVADO

    linhas = _linhas(base_solicitacoes)
    assert [l["status_pedido"] for l in linhas] == ["rejeitado", "aprovado"]
