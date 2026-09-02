"""Repositorio da tabela de politica de credito (score_limite.csv)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import config
from ..erros import ErroBaseDados
from ..logging_config import obter_logger
from .csv_base import exigir_colunas, ler_csv

log = obter_logger("repositorio.score_limite")

COLUNAS = ("score_minimo", "score_maximo", "limite_maximo")


@dataclass(frozen=True)
class FaixaScore:
    """Uma faixa de score e o limite maximo que ela autoriza."""

    score_minimo: int
    score_maximo: int
    limite_maximo: float

    def contem(self, score: int) -> bool:
        return self.score_minimo <= score <= self.score_maximo


def listar_faixas(caminho: Path | None = None) -> list[FaixaScore]:
    """Le a tabela de faixas, ordenada por score minimo."""
    caminho = caminho or config.ARQUIVO_SCORE_LIMITE
    linhas = ler_csv(caminho)
    exigir_colunas(linhas, COLUNAS, caminho.name)

    faixas: list[FaixaScore] = []
    for indice, linha in enumerate(linhas, start=2):
        try:
            faixas.append(
                FaixaScore(
                    score_minimo=int(float(linha["score_minimo"])),
                    score_maximo=int(float(linha["score_maximo"])),
                    limite_maximo=float(
                        str(linha["limite_maximo"]).replace(",", ".")
                    ),
                )
            )
        except (ValueError, KeyError):
            log.warning(
                "Linha %d de %s ignorada por formato invalido.", indice, caminho.name
            )

    if not faixas:
        raise ErroBaseDados(
            f"A tabela de politica de credito '{caminho.name}' esta vazia."
        )

    return sorted(faixas, key=lambda f: f.score_minimo)


def limite_maximo_para_score(score: int, caminho: Path | None = None) -> float:
    """Retorna o teto de credito autorizado para um score.

    Scores fora de qualquer faixa caem na faixa mais proxima (piso da
    primeira ou teto da ultima), em vez de derrubar o atendimento.
    """
    faixas = listar_faixas(caminho)

    for faixa in faixas:
        if faixa.contem(score):
            return faixa.limite_maximo

    if score < faixas[0].score_minimo:
        log.warning("Score %d abaixo da tabela; usando a menor faixa.", score)
        return faixas[0].limite_maximo

    log.warning("Score %d acima da tabela; usando a maior faixa.", score)
    return faixas[-1].limite_maximo
