"""Ferramentas disponiveis para cada agente.

Cada agente enxerga apenas o seu conjunto - e isso que garante, no nivel do
codigo e nao apenas do prompt, que "nenhum agente pode atuar fora do seu
escopo definido".
"""

from __future__ import annotations

from .. import config
from .cambio import consultar_cotacao_moeda
from .comuns import encerrar_atendimento
from .credito import consultar_limite_credito, solicitar_aumento_limite
from .entrevista import realizar_entrevista_credito
from .handoff import (
    direcionar_para_cambio,
    direcionar_para_credito,
    direcionar_para_entrevista,
)
from .triagem import autenticar_cliente

FERRAMENTAS_TRIAGEM = [
    autenticar_cliente,
    direcionar_para_credito,
    direcionar_para_cambio,
    encerrar_atendimento,
]

FERRAMENTAS_CREDITO = [
    consultar_limite_credito,
    solicitar_aumento_limite,
    direcionar_para_entrevista,
    direcionar_para_cambio,
    encerrar_atendimento,
]

FERRAMENTAS_ENTREVISTA = [
    realizar_entrevista_credito,
    direcionar_para_credito,
    encerrar_atendimento,
]

FERRAMENTAS_CAMBIO = [
    consultar_cotacao_moeda,
    direcionar_para_credito,
    encerrar_atendimento,
]

FERRAMENTAS_POR_AGENTE = {
    config.AGENTE_TRIAGEM: FERRAMENTAS_TRIAGEM,
    config.AGENTE_CREDITO: FERRAMENTAS_CREDITO,
    config.AGENTE_ENTREVISTA: FERRAMENTAS_ENTREVISTA,
    config.AGENTE_CAMBIO: FERRAMENTAS_CAMBIO,
}

# Uniao sem duplicatas, para montar um unico no de ferramentas no grafo.
TODAS_FERRAMENTAS = list(
    {f.name: f for lista in FERRAMENTAS_POR_AGENTE.values() for f in lista}.values()
)

__all__ = [
    "FERRAMENTAS_POR_AGENTE",
    "FERRAMENTAS_TRIAGEM",
    "FERRAMENTAS_CREDITO",
    "FERRAMENTAS_ENTREVISTA",
    "FERRAMENTAS_CAMBIO",
    "TODAS_FERRAMENTAS",
]
