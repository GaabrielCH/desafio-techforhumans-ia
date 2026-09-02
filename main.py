"""Atendimento do Banco Agil pelo terminal.

Util para testar o fluxo sem subir o Streamlit:

    python main.py
    python main.py --debug     # mostra o agente ativo a cada turno
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from banco_agil.erros import ErroBancoAgil  # noqa: E402
from banco_agil.graph import SessaoAtendimento  # noqa: E402

DESPEDIDAS = {"sair", "exit", "quit", ":q"}


def _imprimir(rotulo: str, texto: str) -> None:
    print(f"\n{rotulo}: {texto}\n")


def main() -> int:
    analisador = argparse.ArgumentParser(description="Banco Agil - atendimento CLI")
    analisador.add_argument(
        "--debug",
        action="store_true",
        help="mostra o agente ativo e o estado a cada turno",
    )
    argumentos = analisador.parse_args()

    try:
        sessao = SessaoAtendimento(thread_id="cli")
    except ErroBancoAgil as exc:
        print(f"Erro de configuracao: {exc}")
        return 1

    print("=" * 68)
    print("Banco Agil - atendimento virtual (digite 'sair' para encerrar)")
    print("=" * 68)

    _imprimir("Agil", sessao.iniciar())

    while not sessao.encerrada:
        try:
            entrada = input("Voce: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAtendimento interrompido.")
            return 0

        if not entrada:
            continue

        if entrada.lower() in DESPEDIDAS:
            _imprimir("Agil", sessao.enviar("Quero encerrar o atendimento, obrigado."))
            break

        _imprimir("Agil", sessao.enviar(entrada))

        if argumentos.debug:
            estado = sessao.estado
            print(
                f"  [debug] agente={estado.get('agente_atual')} "
                f"autenticado={estado.get('autenticado')} "
                f"tentativas={estado.get('tentativas_autenticacao')} "
                f"ultimo_pedido={estado.get('ultimo_status_solicitacao')}"
            )

    print("Atendimento finalizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
