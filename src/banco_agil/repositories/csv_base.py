"""Primitivas compartilhadas de leitura/escrita de CSV.

Duas preocupacoes justificam este modulo:

1. **Atomicidade** - a base de clientes e reescrita inteira quando o score
   muda. Gravar direto no arquivo final significa perder tudo se o processo
   morrer no meio. Escrevemos em um temporario e usamos ``os.replace``, que
   e atomico no mesmo volume.
2. **Concorrencia** - o Streamlit atende cada sessao em uma thread. Um
   ``RLock`` por arquivo evita leitura suja durante uma reescrita.
"""

from __future__ import annotations

import csv
import os
import tempfile
import threading
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from ..erros import ErroBaseDados
from ..logging_config import obter_logger

log = obter_logger("repositorio")

_locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
_lock_mestre = threading.Lock()


def obter_lock(caminho: Path) -> threading.RLock:
    """Retorna (criando se preciso) o lock associado a um arquivo."""
    chave = str(caminho.resolve() if caminho.exists() else caminho)
    with _lock_mestre:
        return _locks[chave]


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    """Le um CSV inteiro como lista de dicionarios.

    Levanta ErroBaseDados em qualquer falha esperada (arquivo ausente,
    encoding invalido, cabecalho corrompido).
    """
    with obter_lock(caminho):
        if not caminho.exists():
            log.error("Arquivo nao encontrado: %s", caminho)
            raise ErroBaseDados(
                f"A base de dados '{caminho.name}' nao foi encontrada."
            )

        try:
            with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
                leitor = csv.DictReader(arquivo)
                if leitor.fieldnames is None:
                    raise ErroBaseDados(
                        f"A base '{caminho.name}' esta vazia ou sem cabecalho."
                    )
                linhas = [
                    {
                        (k or "").strip(): (v or "").strip()
                        for k, v in linha.items()
                        if k is not None
                    }
                    for linha in leitor
                ]
        except UnicodeDecodeError as exc:
            log.exception("Encoding invalido em %s", caminho)
            raise ErroBaseDados(
                f"A base '{caminho.name}' esta com codificacao invalida."
            ) from exc
        except (OSError, csv.Error) as exc:
            log.exception("Falha ao ler %s", caminho)
            raise ErroBaseDados(
                f"Nao foi possivel ler a base '{caminho.name}'."
            ) from exc

    return linhas


def escrever_csv(
    caminho: Path, colunas: Sequence[str], linhas: Iterable[dict[str, object]]
) -> None:
    """Reescreve um CSV inteiro de forma atomica."""
    with obter_lock(caminho):
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            descritor, temporario = tempfile.mkstemp(
                dir=str(caminho.parent), prefix=f".{caminho.stem}_", suffix=".tmp"
            )
            try:
                with os.fdopen(
                    descritor, "w", encoding="utf-8", newline=""
                ) as arquivo:
                    escritor = csv.DictWriter(arquivo, fieldnames=list(colunas))
                    escritor.writeheader()
                    for linha in linhas:
                        escritor.writerow(linha)
                os.replace(temporario, caminho)
            except BaseException:
                # Nao deixa lixo no diretorio de dados se algo falhar.
                if os.path.exists(temporario):
                    os.unlink(temporario)
                raise
        except (OSError, csv.Error) as exc:
            log.exception("Falha ao gravar %s", caminho)
            raise ErroBaseDados(
                f"Nao foi possivel gravar a base '{caminho.name}'."
            ) from exc


def anexar_csv(
    caminho: Path, colunas: Sequence[str], linha: dict[str, object]
) -> None:
    """Acrescenta uma linha ao final do CSV, criando cabecalho se necessario."""
    with obter_lock(caminho):
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            precisa_cabecalho = (
                not caminho.exists() or caminho.stat().st_size == 0
            )
            with caminho.open("a", encoding="utf-8", newline="") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=list(colunas))
                if precisa_cabecalho:
                    escritor.writeheader()
                escritor.writerow(linha)
        except (OSError, csv.Error) as exc:
            log.exception("Falha ao anexar em %s", caminho)
            raise ErroBaseDados(
                f"Nao foi possivel registrar os dados em '{caminho.name}'."
            ) from exc


def exigir_colunas(
    linhas: list[dict[str, str]], colunas: Sequence[str], nome_arquivo: str
) -> None:
    """Valida o cabecalho do CSV antes de confiar no seu conteudo."""
    if not linhas:
        return
    faltando = [c for c in colunas if c not in linhas[0]]
    if faltando:
        log.error("Colunas ausentes em %s: %s", nome_arquivo, faltando)
        raise ErroBaseDados(
            f"A base '{nome_arquivo}' esta com o formato inesperado "
            f"(colunas ausentes: {', '.join(faltando)})."
        )
