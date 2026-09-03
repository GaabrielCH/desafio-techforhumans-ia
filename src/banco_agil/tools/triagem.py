"""Ferramenta de autenticacao do Agente de Triagem."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from .. import config
from ..erros import ErroBaseDados
from ..logging_config import obter_logger
from ..repositories import clientes as repo_clientes
from ..utils import mascarar_cpf

log = obter_logger("ferramenta.triagem")


@tool("autenticar_cliente")
def autenticar_cliente(
    cpf: str,
    data_nascimento: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Valida CPF e data de nascimento contra a base de clientes.

    Chame apenas quando tiver os DOIS dados. O controle de tentativas e
    feito aqui: apos a terceira falha consecutiva o atendimento e encerrado.

    Args:
        cpf: CPF do cliente, com ou sem pontuacao.
        data_nascimento: data de nascimento em qualquer formato usual
            (DD/MM/AAAA ou AAAA-MM-DD).
    """
    if state.get("autenticado"):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"O cliente {state.get('nome')} ja esta autenticado. "
                            "Siga para o assunto desejado."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    tentativas = int(state.get("tentativas_autenticacao", 0))

    try:
        cliente = repo_clientes.autenticar(cpf, data_nascimento)
    except ErroBaseDados as exc:
        # Falha de infraestrutura nao consome tentativa do cliente.
        log.error("Falha ao acessar a base durante a autenticacao: %s", exc)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Falha tecnica ao consultar a base de clientes. "
                            "Explique ao cliente que o sistema esta "
                            "momentaneamente indisponivel, pergunte se ele "
                            "prefere tentar de novo em instantes e NAO conte "
                            "isso como tentativa de autenticacao."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    if cliente is not None:
        log.info("Cliente autenticado: %s", mascarar_cpf(cliente.cpf))
        return Command(
            update={
                "autenticado": True,
                "cpf": cliente.cpf,
                "nome": cliente.nome,
                "tentativas_autenticacao": 0,
                "messages": [
                    ToolMessage(
                        content=(
                            f"Autenticacao aprovada. Cliente: {cliente.nome}. "
                            "Cumprimente pelo primeiro nome. "
                            "ATENCAO: se o cliente JA disse nesta conversa o "
                            "que precisa (limite, aumento, cotacao), atenda "
                            "esse assunto agora, chamando a ferramenta de "
                            "direcionamento adequada no mesmo turno. NAO "
                            "pergunte 'como posso ajudar' nem faca o cliente "
                            "repetir o que ja pediu. Só pergunte como pode "
                            "ajudar se o assunto ainda nao tiver aparecido."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    tentativas += 1
    restantes = config.MAX_TENTATIVAS_AUTENTICACAO - tentativas

    if restantes <= 0:
        log.warning("Autenticacao esgotada apos %d tentativas.", tentativas)
        return Command(
            update={
                "tentativas_autenticacao": tentativas,
                "encerrado": True,
                "messages": [
                    ToolMessage(
                        content=(
                            "Terceira falha consecutiva de autenticacao. "
                            "Informe ao cliente, de maneira agradavel e sem "
                            "culpa-lo, que nao foi possivel confirmar os dados, "
                            "oriente a procurar uma agencia ou a central "
                            "telefonica, despeca-se e encerre. Nao peca os "
                            "dados novamente."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    log.info(
        "Falha de autenticacao %d/%d.", tentativas, config.MAX_TENTATIVAS_AUTENTICACAO
    )
    return Command(
        update={
            "tentativas_autenticacao": tentativas,
            "messages": [
                ToolMessage(
                    content=(
                        f"Dados nao conferem (tentativa {tentativas} de "
                        f"{config.MAX_TENTATIVAS_AUTENTICACAO}). Informe a falha "
                        "sem revelar qual campo estava errado e peca CPF e data "
                        f"de nascimento novamente. Restam {restantes} tentativa(s)."
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
