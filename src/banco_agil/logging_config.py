"""Logging da aplicacao.

Erros esperados (CSV ilegivel, API fora do ar, entrada invalida) sao
registrados aqui para analise tecnica posterior, enquanto o cliente recebe
apenas uma mensagem amigavel.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import DIR_LOGS

_configurado = False


def configurar_logging(nivel: int = logging.INFO) -> None:
    """Configura o logger raiz uma unica vez por processo."""
    global _configurado
    if _configurado:
        return

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    raiz = logging.getLogger("banco_agil")
    raiz.setLevel(nivel)
    raiz.propagate = False

    console = logging.StreamHandler()
    console.setFormatter(formato)
    raiz.addHandler(console)

    try:
        DIR_LOGS.mkdir(parents=True, exist_ok=True)
        arquivo = RotatingFileHandler(
            DIR_LOGS / "banco_agil.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        arquivo.setFormatter(formato)
        raiz.addHandler(arquivo)
    except OSError:
        # Sem permissao de escrita: seguimos apenas com o console.
        raiz.warning("Nao foi possivel criar o arquivo de log; usando console.")

    _configurado = True


def obter_logger(nome: str) -> logging.Logger:
    """Retorna um logger filho ja configurado."""
    configurar_logging()
    return logging.getLogger(f"banco_agil.{nome}")
