"""Restauracao dos dados de demonstracao."""

from __future__ import annotations

import csv

import pytest

from banco_agil.erros import ErroBaseDados
from banco_agil.repositories import clientes as repo_clientes
from banco_agil.repositories import solicitacoes as repo_solicitacoes
from banco_agil.services import demo


@pytest.fixture()
def semente(tmp_path, base_clientes):
    """Copia intocada da base, como a versionada em data/seed/."""
    caminho = tmp_path / "seed" / "clientes.csv"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(base_clientes.read_text(encoding="utf-8"), encoding="utf-8")
    return caminho


def test_restaura_limite_e_score_alterados(
    semente, base_clientes, base_solicitacoes
):
    repo_clientes.atualizar_limite("12345678901", 99000, base_clientes)
    repo_clientes.atualizar_score("12345678901", 1000, base_clientes)

    demo.restaurar_dados_demo(semente, base_clientes, base_solicitacoes)

    cliente = repo_clientes.buscar_por_cpf("12345678901", base_clientes)
    assert cliente.limite_credito == pytest.approx(5000.0)
    assert cliente.score == 720


def test_restaura_todos_os_clientes(semente, base_clientes, base_solicitacoes):
    repo_clientes.atualizar_score("98765432100", 999, base_clientes)
    repo_clientes.atualizar_score("55566677788", 999, base_clientes)

    demo.restaurar_dados_demo(semente, base_clientes, base_solicitacoes)

    scores = {c.cpf: c.score for c in repo_clientes.listar_clientes(base_clientes)}
    assert scores["98765432100"] == 410
    assert scores["55566677788"] == 250
    assert len(scores) == 4


def test_apaga_as_solicitacoes(semente, base_clientes, base_solicitacoes):
    repo_solicitacoes.registrar(
        "12345678901", 5000, 9000, caminho=base_solicitacoes
    )
    assert base_solicitacoes.exists()

    demo.restaurar_dados_demo(semente, base_clientes, base_solicitacoes)
    assert not base_solicitacoes.exists()


def test_restaurar_sem_solicitacoes_nao_quebra(
    semente, base_clientes, base_solicitacoes
):
    assert not base_solicitacoes.exists()
    demo.restaurar_dados_demo(semente, base_clientes, base_solicitacoes)


def test_semente_ausente_vira_erro_de_dominio(tmp_path, base_clientes):
    """A UI precisa avisar, nao fingir que restaurou."""
    with pytest.raises(ErroBaseDados):
        demo.restaurar_dados_demo(
            tmp_path / "nao_existe.csv", base_clientes, tmp_path / "s.csv"
        )


def test_semente_nunca_e_alterada(semente, base_clientes, base_solicitacoes):
    """A semente e a fonte da verdade: restaurar nao pode toca-la."""
    antes = semente.read_text(encoding="utf-8")
    repo_clientes.atualizar_score("12345678901", 100, base_clientes)
    demo.restaurar_dados_demo(semente, base_clientes, base_solicitacoes)
    assert semente.read_text(encoding="utf-8") == antes


def test_garantir_base_recria_quando_apagada(
    semente, base_clientes, base_solicitacoes
):
    base_clientes.unlink()
    demo.garantir_base(semente, base_clientes)

    assert base_clientes.exists()
    assert len(repo_clientes.listar_clientes(base_clientes)) == 4


def test_garantir_base_nao_sobrescreve_a_existente(semente, base_clientes):
    repo_clientes.atualizar_score("12345678901", 333, base_clientes)
    demo.garantir_base(semente, base_clientes)
    assert repo_clientes.buscar_por_cpf("12345678901", base_clientes).score == 333


def test_semente_do_repositorio_bate_com_a_base_viva():
    """Regressao: a semente versionada nao pode divergir de clientes.csv.

    Se alguem editar a base e esquecer a semente, o botao de restaurar
    passaria a introduzir dados diferentes dos documentados no README.
    """
    from banco_agil import config

    semente = config.DIR_DADOS / "seed" / "clientes.csv"
    if not semente.exists():
        pytest.skip("semente nao versionada neste checkout")

    def linhas(caminho):
        with caminho.open(encoding="utf-8-sig", newline="") as f:
            return sorted(tuple(sorted(l.items())) for l in csv.DictReader(f))

    assert linhas(semente) == linhas(config.ARQUIVO_CLIENTES), (
        "data/seed/clientes.csv divergiu de data/clientes.csv"
    )
