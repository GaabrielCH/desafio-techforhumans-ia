"""Primitivas compartilhadas de leitura/escrita de CSV.

Quatro preocupacoes justificam este modulo:

1. **Atomicidade** - a base de clientes e reescrita inteira quando o score
   muda. Gravar direto no arquivo final significa perder tudo se o processo
   morrer no meio. Escrevemos em um temporario e usamos ``os.replace``, que
   e atomico no mesmo volume.
2. **Concorrencia entre threads** - o Streamlit atende cada sessao em uma
   thread. Um ``RLock`` por arquivo evita leitura suja durante uma reescrita.
3. **Concorrencia entre processos** - duas instancias do app (ou o app e a
   CLI) sobre os mesmos CSVs se atropelariam, porque um lock de processo nao
   atravessa a fronteira do SO. Usamos um lock de arquivo do proprio sistema
   operacional (``msvcrt`` no Windows, ``fcntl`` no POSIX) sobre um arquivo
   sentinela ``.lock``.
4. **Injecao de formula em CSV** - uma celula iniciada por ``=``, ``+``,
   ``-`` ou ``@`` vira formula ao abrir o arquivo no Excel. Como estes CSVs
   sao a saida "oficial" do sistema e podem ser abertos por um analista,
   prefixamos essas celulas com apostrofo na gravacao.
"""

from __future__ import annotations

import csv
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from ..erros import ErroBaseDados
from ..logging_config import obter_logger

log = obter_logger("repositorio")

# Backend de lock do SO. Ausente em plataformas exoticas: seguimos apenas
# com exclusao entre threads e avisamos uma unica vez.
try:  # pragma: no cover - depende da plataforma
    import msvcrt

    _BACKEND_LOCK = "msvcrt"
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]
    try:
        import fcntl

        _BACKEND_LOCK = "fcntl"
    except ImportError:
        fcntl = None  # type: ignore[assignment]
        _BACKEND_LOCK = "nenhum"

TIMEOUT_LOCK_SEGUNDOS = 15.0
INTERVALO_TENTATIVA_LOCK = 0.05

_CARACTERES_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")


@dataclass
class _EstadoTrava:
    """Trava de um arquivo: entre threads e entre processos."""

    lock: threading.RLock = field(default_factory=threading.RLock)
    profundidade: int = 0
    handle: object | None = None


_travas: dict[str, _EstadoTrava] = {}
_lock_registro = threading.Lock()
_avisou_sem_backend = False


def _chave(caminho: Path) -> str:
    """Identidade estavel de um arquivo.

    ``resolve()`` e usado sempre, inclusive quando o arquivo ainda nao
    existe (caso do CSV de solicitacoes, criado na primeira gravacao).
    Sem isso, o mesmo arquivo receberia travas diferentes antes e depois de
    ser criado, ou conforme fosse referenciado por caminho relativo ou
    absoluto - e a exclusao mutua deixaria de valer sem nenhum sintoma.
    """
    return str(Path(caminho).resolve())


def _estado_trava(caminho: Path) -> _EstadoTrava:
    chave = _chave(caminho)
    with _lock_registro:
        estado = _travas.get(chave)
        if estado is None:
            estado = _EstadoTrava()
            _travas[chave] = estado
        return estado


def _travar_no_so(handle) -> bool:
    """Tenta adquirir o lock exclusivo do SO. Retorna False se ocupado."""
    try:
        if _BACKEND_LOCK == "msvcrt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        elif _BACKEND_LOCK == "fcntl":
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            return True
    except OSError:
        return False
    return True


def _destravar_no_so(handle) -> None:
    try:
        if _BACKEND_LOCK == "msvcrt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        elif _BACKEND_LOCK == "fcntl":
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        log.warning("Falha ao liberar o lock de arquivo; seguindo.")


def _abrir_trava_de_processo(caminho: Path):
    """Abre o arquivo sentinela e aguarda o lock exclusivo do SO."""
    global _avisou_sem_backend

    if _BACKEND_LOCK == "nenhum":
        if not _avisou_sem_backend:
            log.warning(
                "Plataforma sem lock de arquivo; a protecao vale apenas "
                "entre threads deste processo."
            )
            _avisou_sem_backend = True
        return None

    sentinela = Path(str(caminho) + ".lock")
    try:
        sentinela.parent.mkdir(parents=True, exist_ok=True)
        handle = open(sentinela, "a+b")
    except OSError:
        log.warning(
            "Nao foi possivel criar o arquivo de trava %s; seguindo apenas "
            "com exclusao entre threads.",
            sentinela.name,
        )
        return None

    handle.seek(0)
    limite = time.monotonic() + TIMEOUT_LOCK_SEGUNDOS
    while True:
        if _travar_no_so(handle):
            return handle
        if time.monotonic() >= limite:
            handle.close()
            log.error(
                "Timeout de %.0fs esperando a trava de '%s'.",
                TIMEOUT_LOCK_SEGUNDOS,
                caminho.name,
            )
            raise ErroBaseDados(
                f"A base '{caminho.name}' esta ocupada por outro processo. "
                "Tente novamente em instantes."
            )
        time.sleep(INTERVALO_TENTATIVA_LOCK)


@contextmanager
def trava_arquivo(caminho: Path) -> Iterator[None]:
    """Acesso exclusivo a um arquivo, entre threads e entre processos.

    Reentrante: aninhar o mesmo caminho na mesma thread nao trava, e o lock
    do SO so e liberado quando a chamada mais externa termina. E isso que
    permite a ``analisar_aumento`` gravar o pedido e concluir o status sem
    que outro processo se intrometa no meio.
    """
    estado = _estado_trava(caminho)
    with estado.lock:
        estado.profundidade += 1
        try:
            if estado.profundidade == 1:
                estado.handle = _abrir_trava_de_processo(caminho)
            yield
        finally:
            estado.profundidade -= 1
            if estado.profundidade == 0 and estado.handle is not None:
                _destravar_no_so(estado.handle)
                try:
                    estado.handle.close()
                except OSError:
                    pass
                estado.handle = None


def _sanitizar_celula(valor: object) -> str:
    """Neutraliza injecao de formula antes de gravar."""
    texto = "" if valor is None else str(valor)
    if texto[:1] in _CARACTERES_PERIGOSOS:
        return "'" + texto
    return texto


def _sanitizar_linha(linha: dict[str, object]) -> dict[str, str]:
    return {chave: _sanitizar_celula(valor) for chave, valor in linha.items()}


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    """Le um CSV inteiro como lista de dicionarios.

    Levanta ErroBaseDados em qualquer falha esperada (arquivo ausente,
    encoding invalido, cabecalho corrompido).
    """
    with trava_arquivo(caminho):
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
    with trava_arquivo(caminho):
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
                        escritor.writerow(_sanitizar_linha(linha))
                    arquivo.flush()
                    os.fsync(arquivo.fileno())
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
    with trava_arquivo(caminho):
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            precisa_cabecalho = (
                not caminho.exists() or caminho.stat().st_size == 0
            )
            with caminho.open("a", encoding="utf-8", newline="") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=list(colunas))
                if precisa_cabecalho:
                    escritor.writeheader()
                escritor.writerow(_sanitizar_linha(linha))
                arquivo.flush()
                os.fsync(arquivo.fileno())
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
