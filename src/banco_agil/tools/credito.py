"""Ferramentas do Agente de Credito."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ..erros import ClienteNaoEncontrado, ErroBaseDados, ErroEntradaInvalida
from ..logging_config import obter_logger
from ..repositories import score_limite as repo_score_limite
from ..services import credito as servico_credito
from ..utils import formatar_moeda, mascarar_cpf, normalizar_valor_monetario

log = obter_logger("ferramenta.credito")

_NAO_AUTENTICADO = (
    "Bloqueado: o cliente ainda nao foi autenticado. Peca CPF e data de "
    "nascimento antes de qualquer consulta."
)


@tool("consultar_limite_credito")
def consultar_limite_credito(
    state: Annotated[dict, InjectedState],
) -> str:
    """Consulta o limite de credito disponivel e o score do cliente logado.

    Nao recebe parametros: usa o CPF ja autenticado na sessao.
    """
    if not state.get("autenticado") or not state.get("cpf"):
        return _NAO_AUTENTICADO

    try:
        cliente = servico_credito.consultar_limite(state["cpf"])
        teto = repo_score_limite.limite_maximo_para_score(cliente.score)
    except ClienteNaoEncontrado:
        log.error(
            "CPF autenticado %s sumiu da base.",
            mascarar_cpf(state.get("cpf", "")),
        )
        return (
            "Erro: o cadastro do cliente nao foi localizado. Peca desculpas e "
            "oriente a procurar uma agencia."
        )
    except ErroBaseDados as exc:
        log.error("Falha ao consultar limite: %s", exc)
        return (
            "Falha tecnica ao consultar o cadastro. Avise o cliente que a "
            "consulta esta indisponivel agora e ofereca tentar novamente ou "
            "tratar outro assunto."
        )

    return (
        f"Limite de credito atual: {formatar_moeda(cliente.limite_credito)}. "
        f"Score de credito: {cliente.score}. "
        f"Teto autorizado para esse score: {formatar_moeda(teto)}. "
        "Informe o limite e o score ao cliente de forma objetiva."
    )


@tool("solicitar_aumento_limite")
def solicitar_aumento_limite(
    novo_limite: float,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Registra e analisa um pedido de aumento de limite de credito.

    Grava o pedido em solicitacoes_aumento_limite.csv, compara o valor
    pedido com o teto autorizado pelo score do cliente e conclui o pedido
    como 'aprovado' ou 'rejeitado'.

    Args:
        novo_limite: novo limite de credito desejado pelo cliente, em reais.
    """
    if not state.get("autenticado") or not state.get("cpf"):
        return Command(
            update={
                "messages": [
                    ToolMessage(content=_NAO_AUTENTICADO, tool_call_id=tool_call_id)
                ]
            }
        )

    def _erro(texto: str) -> Command:
        """Devolve a falha ao agente sem alterar o status do pedido."""
        return Command(
            update={
                "messages": [ToolMessage(content=texto, tool_call_id=tool_call_id)]
            }
        )

    try:
        valor = normalizar_valor_monetario(novo_limite)
    except ErroEntradaInvalida as exc:
        return _erro(
            f"Valor invalido ({exc}). Peca ao cliente que informe o novo "
            "limite desejado em reais."
        )

    try:
        resultado = servico_credito.analisar_aumento(state["cpf"], valor)
    except ErroEntradaInvalida as exc:
        return _erro(
            f"Pedido nao pode ser registrado: {exc} Explique isso ao cliente e "
            "pergunte qual valor ele deseja."
        )
    except ClienteNaoEncontrado:
        log.error(
            "CPF autenticado %s sumiu da base.",
            mascarar_cpf(state.get("cpf", "")),
        )
        return _erro(
            "Erro: cadastro do cliente nao localizado. Peca desculpas e "
            "oriente a procurar uma agencia."
        )
    except ErroBaseDados as exc:
        log.error("Falha ao registrar solicitacao: %s", exc)
        return _erro(
            "Falha tecnica ao registrar a solicitacao. Avise o cliente que o "
            "pedido nao pode ser registrado agora e ofereca tentar mais tarde."
        )

    if resultado.aprovado:
        conteudo = (
            f"Solicitacao APROVADA e registrada com status '{resultado.status}'. "
            f"Limite anterior: {formatar_moeda(resultado.limite_atual)}. "
            f"Novo limite: {formatar_moeda(resultado.novo_limite_solicitado)}. "
            f"{resultado.motivo} "
            "Comunique a aprovacao ao cliente e pergunte se precisa de mais algo."
        )
    else:
        conteudo = (
            f"Solicitacao REJEITADA e registrada com status '{resultado.status}'. "
            f"{resultado.motivo} "
            "Comunique a recusa com empatia, sem repetir numeros em excesso, e "
            "OFERECA uma entrevista financeira rapida que pode reajustar o "
            "score e viabilizar o pedido. Se o cliente aceitar, chame "
            "direcionar_para_entrevista. Se recusar, ofereca outro assunto ou "
            "encerre com encerrar_atendimento."
        )

    return Command(
        update={
            "ultimo_status_solicitacao": resultado.status,
            "messages": [ToolMessage(content=conteudo, tool_call_id=tool_call_id)],
        }
    )
