"""Fixtures compartilhadas.

Todo teste que toca CSV trabalha sobre copias em ``tmp_path``: a base do
repositorio nunca e alterada por uma rodada de testes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

CLIENTES_CSV = """\
cpf,nome,data_nascimento,limite_credito,score
12345678901,Ana Beatriz Souza,1990-05-14,5000.00,720
98765432100,Carlos Eduardo Lima,1985-11-02,1500.00,410
55566677788,Rafael Nogueira Pinto,1979-08-09,800.00,250
11122233344,Mariana Duarte Alves,1998-03-27,12000.00,880
"""

SCORE_LIMITE_CSV = """\
score_minimo,score_maximo,limite_maximo
0,299,1000.00
300,499,3000.00
500,699,8000.00
700,849,15000.00
850,1000,30000.00
"""


@pytest.fixture()
def base_clientes(tmp_path: Path) -> Path:
    caminho = tmp_path / "clientes.csv"
    caminho.write_text(CLIENTES_CSV, encoding="utf-8")
    return caminho


@pytest.fixture()
def base_score_limite(tmp_path: Path) -> Path:
    caminho = tmp_path / "score_limite.csv"
    caminho.write_text(SCORE_LIMITE_CSV, encoding="utf-8")
    return caminho


@pytest.fixture()
def base_solicitacoes(tmp_path: Path) -> Path:
    """Caminho de saida; o arquivo e criado pelo proprio repositorio."""
    return tmp_path / "solicitacoes_aumento_limite.csv"


@pytest.fixture()
def bases(
    monkeypatch, base_clientes: Path, base_score_limite: Path,
    base_solicitacoes: Path,
) -> dict[str, Path]:
    """Aponta a configuracao global para as bases temporarias do teste.

    Necessario para os testes que exercitam o grafo inteiro, porque as
    ferramentas leem os caminhos de ``config`` em tempo de chamada.
    """
    from banco_agil import config

    monkeypatch.setattr(config, "ARQUIVO_CLIENTES", base_clientes)
    monkeypatch.setattr(config, "ARQUIVO_SCORE_LIMITE", base_score_limite)
    monkeypatch.setattr(config, "ARQUIVO_SOLICITACOES", base_solicitacoes)
    return {
        "clientes": base_clientes,
        "score_limite": base_score_limite,
        "solicitacoes": base_solicitacoes,
    }
