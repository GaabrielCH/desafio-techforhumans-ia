"""Ferramenta do Agente de Entrevista de Credito.

A entrevista em si (as perguntas, uma de cada vez) e conduzida pelo LLM. A
ferramenta so entra quando as cinco respostas ja foram coletadas: ela
normaliza, calcula o score e persiste. Isso mantem o calculo deterministico
e testavel, fora do alcance do modelo.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ..erros import ClienteNaoEncontrado, ErroBaseDados, ErroEntradaInvalida
from ..logging_config import obter_logger
from ..repositories import clientes as repo_clientes
from ..repositories import score_limite as repo_score_limite
from ..services import score as servico_score
from ..utils import formatar_moeda

log = obter_logger("ferramenta.entrevista")


@tool("realizar_entrevista_credito")
def realizar_entrevista_credito(
    renda_mensal: float,
    tipo_emprego: str,
    despesas_fixas: float,
    numero_dependentes: int,
    tem_dividas: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Calcula e grava o novo score de credito a partir da entrevista.

    Chame somente depois de ter coletado as CINCO respostas na conversa.

    Args:
        renda_mensal: renda mensal do cliente em reais.
        tipo_emprego: 'formal', 'autonomo' ou 'desempregado'.
        despesas_fixas: despesas fixas mensais em reais.
        numero_dependentes: quantidade de dependentes (0 ou mais).
        tem_dividas: 'sim' ou 'nao' para dividas ativas.
    """
    if not state.get("autenticado") or not state.get("cpf"):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Bloqueado: cliente nao autenticado. Peca CPF e "
                            "data de nascimento."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    def _erro(texto: str) -> Command:
        return Command(
            update={
                "messages": [ToolMessage(content=texto, tool_call_id=tool_call_id)]
            }
        )

    try:
        dados = servico_score.normalizar_entrevista(
            renda_mensal=renda_mensal,
            tipo_emprego=tipo_emprego,
            despesas_fixas=despesas_fixas,
            numero_dependentes=numero_dependentes,
            tem_dividas=tem_dividas,
        )
    except ErroEntradaInvalida as exc:
        log.info("Resposta de entrevista invalida: %s", exc)
        return _erro(
            f"Resposta invalida: {exc} Refaca apenas essa pergunta ao cliente e "
            "chame a ferramenta de novo com as cinco respostas."
        )

    resultado = servico_score.calcular_score(dados)

    try:
        cliente = repo_clientes.atualizar_score(state["cpf"], resultado.score)
        teto = repo_score_limite.limite_maximo_para_score(cliente.score)
    except ClienteNaoEncontrado:
        log.error("CPF autenticado %s sumiu da base.", state.get("cpf"))
        return _erro(
            "Erro: cadastro do cliente nao localizado. Peca desculpas e oriente "
            "a procurar uma agencia."
        )
    except ErroBaseDados as exc:
        log.error("Falha ao gravar o novo score: %s", exc)
        return _erro(
            f"O score foi recalculado para {resultado.score}, mas nao foi "
            "possivel grava-lo agora. Informe o cliente de que houve uma falha "
            "no registro e que ele pode tentar novamente mais tarde."
        )

    log.info(
        "Score do CPF %s atualizado para %d (bruto %.2f).",
        cliente.cpf,
        cliente.score,
        resultado.score_bruto,
    )

    return Command(
        update={
            "ultimo_status_solicitacao": None,
            "messages": [
                ToolMessage(
                    content=(
                        f"Entrevista concluida. Novo score: {cliente.score} "
                        f"(anteriormente informado ao cliente pode ter mudado). "
                        f"Base de clientes atualizada. Com esse score o teto "
                        f"autorizado passa a ser {formatar_moeda(teto)}. "
                        f"Limite atual do cliente: "
                        f"{formatar_moeda(cliente.limite_credito)}. "
                        "Informe o novo score ao cliente e, em seguida, chame "
                        "direcionar_para_credito para refazer a analise do "
                        "pedido de aumento."
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
