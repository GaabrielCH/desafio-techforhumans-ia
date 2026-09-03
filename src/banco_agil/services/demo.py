"""Restauracao dos dados de demonstracao.

Motivo de existir: na versao publicada a base e compartilhada entre todos os
visitantes e persiste enquanto o app estiver de pe. Quem rodasse o Roteiro A
do README depois de outra pessoa encontraria o limite da Ana ja em
R$ 10.000 e receberia, corretamente, "o novo limite precisa ser maior que o
atual" - comportamento certo que contradiz o roteiro que a pessoa acabou de
ler.

A semente (``data/seed/clientes.csv``) e a fonte da verdade: ela e versionada
e nunca escrita em execucao. ``data/clientes.csv`` e a copia viva.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import config
from ..erros import ErroBaseDados
from ..logging_config import obter_logger
from ..repositories.csv_base import trava_arquivo

log = obter_logger("servico.demo")

ARQUIVO_SEMENTE = config.DIR_DADOS / "seed" / "clientes.csv"


def semente_disponivel(caminho: Path | None = None) -> bool:
    """A restauracao so pode ser oferecida se houver de onde restaurar."""
    return (caminho or ARQUIVO_SEMENTE).exists()


def garantir_base(
    caminho_semente: Path | None = None, caminho_clientes: Path | None = None
) -> None:
    """Cria ``clientes.csv`` a partir da semente se ele nao existir.

    Protege o caso de alguem apagar a base viva por engano: o app volta a
    subir em vez de falhar na primeira autenticacao.
    """
    semente = caminho_semente or ARQUIVO_SEMENTE
    clientes = caminho_clientes or config.ARQUIVO_CLIENTES

    if clientes.exists() or not semente.exists():
        return

    with trava_arquivo(clientes):
        if not clientes.exists():  # outra thread pode ter criado no meio
            clientes.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(semente, clientes)
            log.info("Base de clientes recriada a partir da semente.")


def restaurar_dados_demo(
    caminho_semente: Path | None = None,
    caminho_clientes: Path | None = None,
    caminho_solicitacoes: Path | None = None,
) -> None:
    """Devolve limites, scores e solicitacoes ao estado inicial.

    Levanta ErroBaseDados se a semente nao existir ou a gravacao falhar -
    a UI traduz isso em uma mensagem, em vez de fingir que restaurou.
    """
    semente = caminho_semente or ARQUIVO_SEMENTE
    clientes = caminho_clientes or config.ARQUIVO_CLIENTES
    solicitacoes = caminho_solicitacoes or config.ARQUIVO_SOLICITACOES

    if not semente.exists():
        log.error("Semente ausente em %s.", semente)
        raise ErroBaseDados(
            "Os dados originais de demonstração não foram encontrados."
        )

    try:
        with trava_arquivo(clientes):
            clientes.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(semente, clientes)

        with trava_arquivo(solicitacoes):
            if solicitacoes.exists():
                solicitacoes.unlink()
    except OSError as exc:
        log.exception("Falha ao restaurar os dados de demonstracao.")
        raise ErroBaseDados(
            "Não foi possível restaurar os dados de demonstração."
        ) from exc

    log.info("Dados de demonstracao restaurados.")
