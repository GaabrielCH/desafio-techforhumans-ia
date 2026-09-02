"""Autenticacao e leitura da base de clientes."""

from __future__ import annotations

import pytest

from banco_agil.erros import ClienteNaoEncontrado, ErroBaseDados
from banco_agil.repositories import clientes as repo


def test_autentica_com_dados_corretos(base_clientes):
    cliente = repo.autenticar("123.456.789-01", "14/05/1990", base_clientes)
    assert cliente is not None
    assert cliente.nome == "Ana Beatriz Souza"
    assert cliente.limite_credito == pytest.approx(5000.00)
    assert cliente.score == 720


def test_autentica_aceita_data_em_formato_iso(base_clientes):
    assert repo.autenticar("12345678901", "1990-05-14", base_clientes) is not None


def test_falha_quando_data_nao_confere(base_clientes):
    assert repo.autenticar("12345678901", "15/05/1990", base_clientes) is None


def test_falha_quando_cpf_nao_existe(base_clientes):
    assert repo.autenticar("00000000000", "14/05/1990", base_clientes) is None


def test_falha_quando_entrada_e_malformada_sem_estourar(base_clientes):
    # Entrada invalida e falha de autenticacao, nao excecao: o agente
    # precisa poder pedir os dados de novo.
    assert repo.autenticar("abc", "ontem", base_clientes) is None


def test_buscar_por_cpf_inexistente(base_clientes):
    with pytest.raises(ClienteNaoEncontrado):
        repo.buscar_por_cpf("00000000000", base_clientes)


def test_base_ausente_gera_erro_de_base_dados(tmp_path):
    with pytest.raises(ErroBaseDados):
        repo.listar_clientes(tmp_path / "nao_existe.csv")


def test_base_sem_colunas_esperadas(tmp_path):
    caminho = tmp_path / "clientes.csv"
    caminho.write_text("coluna_a,coluna_b\n1,2\n", encoding="utf-8")
    with pytest.raises(ErroBaseDados):
        repo.listar_clientes(caminho)


def test_linha_corrompida_nao_derruba_a_base(tmp_path):
    caminho = tmp_path / "clientes.csv"
    caminho.write_text(
        "cpf,nome,data_nascimento,limite_credito,score\n"
        "12345678901,Ana,1990-05-14,5000.00,720\n"
        "999,Linha Ruim,data-invalida,abc,xyz\n"
        "98765432100,Carlos,1985-11-02,1500.00,410\n",
        encoding="utf-8",
    )
    clientes = repo.listar_clientes(caminho)
    assert [c.nome for c in clientes] == ["Ana", "Carlos"]


def test_atualizar_score_persiste_e_trunca(base_clientes):
    atualizado = repo.atualizar_score("12345678901", 999, base_clientes)
    assert atualizado.score == 999

    # Persistiu de fato, sem perder as outras linhas.
    relido = repo.buscar_por_cpf("12345678901", base_clientes)
    assert relido.score == 999
    assert len(repo.listar_clientes(base_clientes)) == 4

    assert repo.atualizar_score("12345678901", 5000, base_clientes).score == 1000
    assert repo.atualizar_score("12345678901", -50, base_clientes).score == 0


def test_atualizar_score_de_cpf_inexistente(base_clientes):
    with pytest.raises(ClienteNaoEncontrado):
        repo.atualizar_score("00000000000", 700, base_clientes)
