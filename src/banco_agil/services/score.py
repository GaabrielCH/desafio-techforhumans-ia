"""Calculo do score de credito a partir da entrevista financeira.

Formula do desafio:

    score = (renda_mensal / (despesas + 1)) * peso_renda
          + peso_emprego[tipo_emprego]
          + peso_dependentes[num_dependentes]
          + peso_dividas[tem_dividas]

O resultado e truncado para a faixa 0..1000. O detalhamento de cada parcela
e devolvido junto para que o agente possa explicar o resultado ao cliente e
para que o calculo seja auditavel nos testes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import config
from ..logging_config import obter_logger
from ..utils import (
    normalizar_inteiro_nao_negativo,
    normalizar_sim_nao,
    normalizar_tipo_emprego,
    normalizar_valor_monetario,
)

log = obter_logger("servico.score")


@dataclass(frozen=True)
class DadosEntrevista:
    """Respostas normalizadas da entrevista financeira."""

    renda_mensal: float
    tipo_emprego: str
    despesas_fixas: float
    numero_dependentes: int
    tem_dividas: str


@dataclass(frozen=True)
class ResultadoScore:
    """Score calculado com a contribuicao de cada componente."""

    score: int
    score_bruto: float
    componentes: dict[str, float] = field(default_factory=dict)
    dados: DadosEntrevista | None = None


def _chave_dependentes(quantidade: int) -> str:
    """Mapeia o numero de dependentes para a chave da tabela de pesos."""
    return str(quantidade) if quantidade <= 2 else "3+"


def normalizar_entrevista(
    renda_mensal: str | float,
    tipo_emprego: str,
    despesas_fixas: str | float,
    numero_dependentes: str | int,
    tem_dividas: str | bool,
) -> DadosEntrevista:
    """Converte as respostas em texto livre para tipos confiaveis.

    Levanta ErroEntradaInvalida quando alguma resposta nao e interpretavel,
    permitindo que o agente peca de novo apenas aquele campo.
    """
    return DadosEntrevista(
        renda_mensal=normalizar_valor_monetario(renda_mensal),
        tipo_emprego=normalizar_tipo_emprego(tipo_emprego),
        despesas_fixas=normalizar_valor_monetario(despesas_fixas),
        numero_dependentes=normalizar_inteiro_nao_negativo(numero_dependentes),
        tem_dividas=normalizar_sim_nao(tem_dividas),
    )


def calcular_score(dados: DadosEntrevista) -> ResultadoScore:
    """Aplica a formula ponderada e trunca o resultado em 0..1000."""
    parcela_renda = (
        dados.renda_mensal / (dados.despesas_fixas + 1)
    ) * config.PESO_RENDA

    parcela_emprego = float(config.PESO_EMPREGO[dados.tipo_emprego])
    parcela_dependentes = float(
        config.PESO_DEPENDENTES[_chave_dependentes(dados.numero_dependentes)]
    )
    parcela_dividas = float(config.PESO_DIVIDAS[dados.tem_dividas])

    bruto = (
        parcela_renda + parcela_emprego + parcela_dependentes + parcela_dividas
    )
    score = int(
        max(config.SCORE_MINIMO, min(config.SCORE_MAXIMO, round(bruto)))
    )

    log.info(
        "Score calculado: bruto=%.2f, final=%d (renda=%.2f, emprego=%s, "
        "despesas=%.2f, dependentes=%d, dividas=%s)",
        bruto,
        score,
        dados.renda_mensal,
        dados.tipo_emprego,
        dados.despesas_fixas,
        dados.numero_dependentes,
        dados.tem_dividas,
    )

    return ResultadoScore(
        score=score,
        score_bruto=round(bruto, 2),
        componentes={
            "renda": round(parcela_renda, 2),
            "emprego": parcela_emprego,
            "dependentes": parcela_dependentes,
            "dividas": parcela_dividas,
        },
        dados=dados,
    )
