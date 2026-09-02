"""Repositorio das solicitacoes de aumento de limite.

Colunas exigidas pelo desafio, nesta ordem:
cpf_cliente, data_hora_solicitacao, limite_atual, novo_limite_solicitado,
status_pedido.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import config
from ..logging_config import obter_logger
from ..utils import agora_iso, mascarar_cpf, normalizar_cpf
from .csv_base import anexar_csv, escrever_csv, ler_csv, trava_arquivo

log = obter_logger("repositorio.solicitacoes")

COLUNAS = (
    "cpf_cliente",
    "data_hora_solicitacao",
    "limite_atual",
    "novo_limite_solicitado",
    "status_pedido",
)


@dataclass(frozen=True)
class Solicitacao:
    """Pedido formal de aumento de limite."""

    cpf_cliente: str
    data_hora_solicitacao: str
    limite_atual: float
    novo_limite_solicitado: float
    status_pedido: str

    def para_linha(self) -> dict[str, object]:
        return {
            "cpf_cliente": self.cpf_cliente,
            "data_hora_solicitacao": self.data_hora_solicitacao,
            "limite_atual": f"{self.limite_atual:.2f}",
            "novo_limite_solicitado": f"{self.novo_limite_solicitado:.2f}",
            "status_pedido": self.status_pedido,
        }


def registrar(
    cpf: str,
    limite_atual: float,
    novo_limite: float,
    status: str = config.STATUS_PENDENTE,
    caminho: Path | None = None,
) -> Solicitacao:
    """Grava um pedido novo (por padrao 'pendente') e o devolve."""
    caminho = caminho or config.ARQUIVO_SOLICITACOES
    solicitacao = Solicitacao(
        cpf_cliente=normalizar_cpf(cpf),
        data_hora_solicitacao=agora_iso(),
        limite_atual=float(limite_atual),
        novo_limite_solicitado=float(novo_limite),
        status_pedido=status,
    )
    anexar_csv(caminho, COLUNAS, solicitacao.para_linha())
    log.info(
        "Solicitacao registrada: CPF %s, %.2f -> %.2f, status '%s'.",
        mascarar_cpf(solicitacao.cpf_cliente),
        solicitacao.limite_atual,
        solicitacao.novo_limite_solicitado,
        solicitacao.status_pedido,
    )
    return solicitacao


def atualizar_status(
    cpf: str,
    data_hora: str,
    novo_status: str,
    caminho: Path | None = None,
) -> bool:
    """Muda o status de um pedido ja gravado (pendente -> aprovado/rejeitado).

    O par (cpf, data_hora) identifica o pedido. Retorna True se encontrou.

    A varredura e de tras para frente de proposito: o desafio fixa as cinco
    colunas do CSV, entao nao ha um id proprio e a chave pode repetir se dois
    pedidos cairem no mesmo instante. Como o arquivo so cresce por append, a
    linha recem-criada e sempre a ultima com aquela chave - atualizar a
    primeira sobrescreveria o desfecho de um pedido anterior.
    """
    caminho = caminho or config.ARQUIVO_SOLICITACOES
    alvo = normalizar_cpf(cpf)

    with trava_arquivo(caminho):
        linhas = ler_csv(caminho)
        atualizado = False
        for linha in reversed(linhas):
            mesmo_cpf = (
                "".join(ch for ch in linha.get("cpf_cliente", "") if ch.isdigit())
                == alvo
            )
            if mesmo_cpf and linha.get("data_hora_solicitacao") == data_hora:
                linha["status_pedido"] = novo_status
                atualizado = True
                break

        if atualizado:
            escrever_csv(caminho, COLUNAS, linhas)
            log.info(
                "Solicitacao de %s em %s atualizada para '%s'.",
                mascarar_cpf(alvo),
                data_hora,
                novo_status,
            )
        else:
            log.warning(
                "Solicitacao de %s em %s nao encontrada para atualizacao.",
                mascarar_cpf(alvo),
                data_hora,
            )

    return atualizado


def listar_por_cpf(cpf: str, caminho: Path | None = None) -> list[Solicitacao]:
    """Historico de pedidos de um cliente (mais antigo primeiro)."""
    caminho = caminho or config.ARQUIVO_SOLICITACOES
    if not caminho.exists():
        return []

    solicitacoes: list[Solicitacao] = []
    alvo = normalizar_cpf(cpf)
    for linha in ler_csv(caminho):
        digitos = "".join(ch for ch in linha.get("cpf_cliente", "") if ch.isdigit())
        if digitos != alvo:
            continue
        try:
            solicitacoes.append(
                Solicitacao(
                    cpf_cliente=digitos,
                    data_hora_solicitacao=linha.get("data_hora_solicitacao", ""),
                    limite_atual=float(linha.get("limite_atual", "0") or 0),
                    novo_limite_solicitado=float(
                        linha.get("novo_limite_solicitado", "0") or 0
                    ),
                    status_pedido=linha.get("status_pedido", ""),
                )
            )
        except ValueError:
            log.warning(
                "Solicitacao com valores invalidos ignorada (CPF %s).",
                mascarar_cpf(alvo),
            )

    return solicitacoes
