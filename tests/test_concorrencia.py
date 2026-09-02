"""Concorrencia: entre threads e entre processos.

Estes testes exercitam a trava de verdade (threads reais, processos reais),
porque o modo de falha aqui é silencioso: sem exclusao mutua, o arquivo
simplesmente perde escritas e ninguem levanta excecao.
"""

from __future__ import annotations

import csv
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from banco_agil.erros import ErroBaseDados
from banco_agil.repositories import solicitacoes as repo_solicitacoes
from banco_agil.repositories.csv_base import (
    _chave,
    _sanitizar_celula,
    escrever_csv,
    ler_csv,
    trava_arquivo,
)

RAIZ = Path(__file__).resolve().parents[1]


def _linhas(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


# --------------------------------------------------------------------------- #
# Identidade da trava
# --------------------------------------------------------------------------- #
def test_chave_e_estavel_antes_e_depois_de_o_arquivo_existir(tmp_path):
    """Regressao: a trava trocava de identidade quando o arquivo nascia.

    O CSV de solicitacoes so e criado na primeira gravacao. Se a chave da
    trava mudasse nesse momento, duas rotinas passariam a segurar travas
    diferentes para o mesmo arquivo - sem nenhum sintoma visivel.
    """
    alvo = tmp_path / "novo.csv"
    antes = _chave(alvo)
    alvo.write_text("a,b\n1,2\n", encoding="utf-8")
    assert _chave(alvo) == antes


def test_chave_e_a_mesma_para_caminho_relativo_e_absoluto(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _chave(Path("dados.csv")) == _chave(tmp_path / "dados.csv")


def test_trava_e_reentrante_na_mesma_thread(tmp_path):
    """analisar_aumento aninha travas; sem reentrancia isso seria deadlock."""
    alvo = tmp_path / "reentrante.csv"
    alvo.write_text("a\n1\n", encoding="utf-8")

    with trava_arquivo(alvo):
        with trava_arquivo(alvo):
            linhas = ler_csv(alvo)  # ler_csv trava de novo, terceiro nivel

    assert linhas == [{"a": "1"}]


# --------------------------------------------------------------------------- #
# Threads
# --------------------------------------------------------------------------- #
def test_gravacoes_concorrentes_de_threads_nao_se_perdem(base_solicitacoes):
    """20 threads gravando: todas as linhas precisam sobreviver."""
    total = 20
    erros: list[BaseException] = []

    def grava(indice: int) -> None:
        try:
            repo_solicitacoes.registrar(
                cpf="12345678901",
                limite_atual=1000,
                novo_limite=2000 + indice,
                caminho=base_solicitacoes,
            )
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [threading.Thread(target=grava, args=(i,)) for i in range(total)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not erros, erros
    linhas = _linhas(base_solicitacoes)
    assert len(linhas) == total
    # Cabecalho gravado uma unica vez.
    assert base_solicitacoes.read_text(encoding="utf-8").count("cpf_cliente") == 1


def test_leitura_concorrente_nunca_ve_arquivo_pela_metade(tmp_path):
    """A reescrita e atomica: quem le pega a versao antiga ou a nova."""
    alvo = tmp_path / "clientes.csv"
    colunas = ("cpf", "valor")
    escrever_csv(alvo, colunas, [{"cpf": "1", "valor": "0"}])

    parar = threading.Event()
    tamanhos: set[int] = set()
    falhas: list[BaseException] = []

    def escritor() -> None:
        try:
            for i in range(60):
                escrever_csv(
                    alvo,
                    colunas,
                    [{"cpf": str(n), "valor": str(i)} for n in range(50)],
                )
        except BaseException as exc:  # noqa: BLE001
            falhas.append(exc)
        finally:
            parar.set()

    def leitor() -> None:
        try:
            while not parar.is_set():
                tamanhos.add(len(ler_csv(alvo)))
        except BaseException as exc:  # noqa: BLE001
            falhas.append(exc)

    t1, t2 = threading.Thread(target=escritor), threading.Thread(target=leitor)
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    assert not falhas, falhas
    # Só existem dois estados válidos: a base inicial (1) ou a completa (50).
    assert tamanhos <= {1, 50}, f"leitura parcial observada: {tamanhos}"


# --------------------------------------------------------------------------- #
# Processos
# --------------------------------------------------------------------------- #
_SCRIPT_FILHO = """
import sys
sys.path.insert(0, {raiz!r})
from pathlib import Path
from banco_agil.repositories import solicitacoes as repo

alvo = Path({alvo!r})
for i in range({n}):
    repo.registrar(cpf="12345678901", limite_atual=1000,
                   novo_limite=2000 + i, caminho=alvo)
"""


@pytest.mark.slow
def test_processos_simultaneos_nao_corrompem_o_csv(base_solicitacoes, tmp_path):
    """Dois processos gravando ao mesmo tempo no mesmo CSV.

    Este é o cenario que o RLock sozinho NAO cobre: um lock de processo nao
    atravessa a fronteira do SO. Sem a trava de arquivo, o resultado sao
    linhas truncadas ou cabecalho duplicado no meio do arquivo.
    """
    por_processo = 15
    script = tmp_path / "filho.py"
    script.write_text(
        textwrap.dedent(
            _SCRIPT_FILHO.format(
                raiz=str(RAIZ / "src"),
                alvo=str(base_solicitacoes),
                n=por_processo,
            )
        ),
        encoding="utf-8",
    )

    processos = [
        subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    saidas = [p.communicate(timeout=120) for p in processos]

    for processo, (_, erro) in zip(processos, saidas):
        assert processo.returncode == 0, erro.decode("utf-8", "replace")

    conteudo = base_solicitacoes.read_text(encoding="utf-8")
    # Cabecalho exatamente uma vez, nenhuma linha perdida ou truncada.
    assert conteudo.count("cpf_cliente") == 1
    linhas = _linhas(base_solicitacoes)
    assert len(linhas) == 2 * por_processo
    assert all(l["status_pedido"] == "pendente" for l in linhas)
    assert all(l["cpf_cliente"] == "12345678901" for l in linhas)


# --------------------------------------------------------------------------- #
# Injecao de formula em CSV
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "perigoso",
    ["=1+1", "+SOMA(A1)", "-2+3", "@SUM(A1)", "=HYPERLINK(\"http://x\")"],
)
def test_celula_perigosa_e_neutralizada(perigoso):
    assert _sanitizar_celula(perigoso).startswith("'")


@pytest.mark.parametrize("inofensivo", ["12345678901", "5000.00", "aprovado", ""])
def test_celula_normal_nao_e_alterada(inofensivo):
    assert _sanitizar_celula(inofensivo) == inofensivo


def test_gravacao_neutraliza_formula(tmp_path):
    alvo = tmp_path / "saida.csv"
    escrever_csv(alvo, ("nome",), [{"nome": "=1+1"}])
    assert _linhas(alvo)[0]["nome"] == "'=1+1"


def test_base_ocupada_vira_erro_de_dominio(tmp_path, monkeypatch):
    """Timeout de trava precisa virar ErroBaseDados, nao travar a UI."""
    from banco_agil.repositories import csv_base

    alvo = tmp_path / "ocupado.csv"
    alvo.write_text("a\n1\n", encoding="utf-8")

    monkeypatch.setattr(csv_base, "TIMEOUT_LOCK_SEGUNDOS", 0.1)
    monkeypatch.setattr(csv_base, "_travar_no_so", lambda handle: False)

    if csv_base._BACKEND_LOCK == "nenhum":
        pytest.skip("plataforma sem lock de arquivo")

    with pytest.raises(ErroBaseDados):
        with trava_arquivo(alvo):
            pass
