"""Repositorio da base de clientes (clientes.csv)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import config
from ..erros import ClienteNaoEncontrado, ErroBaseDados
from ..logging_config import obter_logger
from ..utils import normalizar_cpf, normalizar_data
from .csv_base import escrever_csv, exigir_colunas, ler_csv, obter_lock

log = obter_logger("repositorio.clientes")

COLUNAS = ("cpf", "nome", "data_nascimento", "limite_credito", "score")


@dataclass(frozen=True)
class Cliente:
    """Snapshot imutavel de uma linha de clientes.csv."""

    cpf: str
    nome: str
    data_nascimento: str
    limite_credito: float
    score: int


def _converter(linha: dict[str, str]) -> Cliente:
    """Converte uma linha crua do CSV em Cliente, tolerando sujeira leve."""
    try:
        limite = float(str(linha.get("limite_credito", "0")).replace(",", "."))
    except ValueError:
        log.warning(
            "limite_credito invalido para o CPF %s; assumindo 0.0",
            linha.get("cpf"),
        )
        limite = 0.0

    try:
        score = int(float(str(linha.get("score", "0")).replace(",", ".")))
    except ValueError:
        log.warning("score invalido para o CPF %s; assumindo 0", linha.get("cpf"))
        score = 0

    return Cliente(
        cpf=normalizar_cpf(linha["cpf"]),
        nome=linha.get("nome", "").strip(),
        data_nascimento=normalizar_data(linha["data_nascimento"]),
        limite_credito=limite,
        score=max(config.SCORE_MINIMO, min(config.SCORE_MAXIMO, score)),
    )


def listar_clientes(caminho: Path | None = None) -> list[Cliente]:
    """Le todos os clientes da base."""
    caminho = caminho or config.ARQUIVO_CLIENTES
    linhas = ler_csv(caminho)
    exigir_colunas(linhas, COLUNAS, caminho.name)

    clientes: list[Cliente] = []
    for indice, linha in enumerate(linhas, start=2):  # linha 1 = cabecalho
        try:
            clientes.append(_converter(linha))
        except Exception:  # noqa: BLE001 - uma linha ruim nao invalida a base
            log.warning(
                "Linha %d de %s ignorada por formato invalido.", indice, caminho.name
            )
    return clientes


def buscar_por_cpf(cpf: str, caminho: Path | None = None) -> Cliente:
    """Retorna o cliente com o CPF informado ou levanta ClienteNaoEncontrado."""
    alvo = normalizar_cpf(cpf)
    for cliente in listar_clientes(caminho):
        if cliente.cpf == alvo:
            return cliente
    raise ClienteNaoEncontrado(f"Nenhum cliente cadastrado com o CPF {alvo}.")


def _atualizar_campo(
    cpf: str, coluna: str, valor: str, caminho: Path | None = None
) -> Cliente:
    """Reescreve um campo de um cliente, de forma atomica.

    O lock cobre leitura e escrita: sem ele, duas sessoes gravando ao mesmo
    tempo fariam a ultima sobrescrever a base lida pela primeira.
    """
    caminho = caminho or config.ARQUIVO_CLIENTES
    alvo = normalizar_cpf(cpf)

    with obter_lock(caminho):
        linhas = ler_csv(caminho)
        exigir_colunas(linhas, COLUNAS, caminho.name)

        encontrado = False
        for linha in linhas:
            try:
                if normalizar_cpf(linha.get("cpf", "")) == alvo:
                    linha[coluna] = valor
                    encontrado = True
                    break
            except Exception:  # noqa: BLE001 - linha malformada, segue adiante
                continue

        if not encontrado:
            raise ClienteNaoEncontrado(
                f"Nenhum cliente cadastrado com o CPF {alvo}."
            )

        escrever_csv(caminho, COLUNAS, linhas)

    return buscar_por_cpf(alvo, caminho)


def atualizar_score(cpf: str, novo_score: int, caminho: Path | None = None) -> Cliente:
    """Persiste o novo score do cliente (truncado em 0..1000)."""
    score_limitado = max(
        config.SCORE_MINIMO, min(config.SCORE_MAXIMO, int(novo_score))
    )
    cliente = _atualizar_campo(cpf, "score", str(score_limitado), caminho)
    log.info("Score do CPF %s atualizado para %d.", cliente.cpf, score_limitado)
    return cliente


def atualizar_limite(
    cpf: str, novo_limite: float, caminho: Path | None = None
) -> Cliente:
    """Persiste o novo limite de credito aprovado."""
    cliente = _atualizar_campo(cpf, "limite_credito", f"{float(novo_limite):.2f}", caminho)
    log.info(
        "Limite do CPF %s atualizado para %.2f.", cliente.cpf, float(novo_limite)
    )
    return cliente


def autenticar(
    cpf: str, data_nascimento: str, caminho: Path | None = None
) -> Cliente | None:
    """Confere CPF + data de nascimento.

    Retorna o Cliente quando o par confere e ``None`` quando nao confere -
    incluindo o caso de CPF inexistente, para nao revelar ao interlocutor
    qual dos dois campos estava errado.
    """
    try:
        cpf_normalizado = normalizar_cpf(cpf)
        data_normalizada = normalizar_data(data_nascimento)
    except Exception:  # noqa: BLE001 - entrada malformada = falha de autenticacao
        log.info("Tentativa de autenticacao com dados em formato invalido.")
        return None

    try:
        cliente = buscar_por_cpf(cpf_normalizado, caminho)
    except ClienteNaoEncontrado:
        log.info("Tentativa de autenticacao para CPF inexistente.")
        return None
    except ErroBaseDados:
        raise

    if cliente.data_nascimento == data_normalizada:
        log.info("Autenticacao bem-sucedida para o CPF %s.", cpf_normalizado)
        return cliente

    log.info("Data de nascimento divergente para o CPF %s.", cpf_normalizado)
    return None
