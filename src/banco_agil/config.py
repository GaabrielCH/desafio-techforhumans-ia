"""Configuracao central: caminhos, parametros do modelo e pesos do score.

Tudo que e "ajustavel" no desafio mora aqui, para nao ficar espalhado em
regra de negocio ou em prompt.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
DIR_DADOS = Path(os.getenv("BANCO_AGIL_DIR_DADOS", RAIZ_PROJETO / "data"))
DIR_LOGS = Path(os.getenv("BANCO_AGIL_DIR_LOGS", RAIZ_PROJETO / "logs"))

ARQUIVO_CLIENTES = DIR_DADOS / "clientes.csv"
ARQUIVO_SCORE_LIMITE = DIR_DADOS / "score_limite.csv"
ARQUIVO_SOLICITACOES = DIR_DADOS / "solicitacoes_aumento_limite.csv"

# --------------------------------------------------------------------------- #
# Modelo (LLM)
# --------------------------------------------------------------------------- #
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
MODELO = os.getenv("BANCO_AGIL_MODELO", "gemini-3.6-flash")

# Deixada em branco por padrao: os modelos Gemini 3.x usam amostragem fixa e
# emitem aviso quando `temperature` e enviada. Preencha apenas se estiver
# usando um modelo que aceite o parametro (ex.: gemini-2.5-flash).
_temperatura_bruta = os.getenv("BANCO_AGIL_TEMPERATURA", "").strip()
TEMPERATURA: float | None = (
    float(_temperatura_bruta) if _temperatura_bruta else None
)

# --------------------------------------------------------------------------- #
# Autenticacao
# --------------------------------------------------------------------------- #
# 1 tentativa inicial + 2 novas tentativas = 3 no total (regra do desafio).
MAX_TENTATIVAS_AUTENTICACAO = 3

# --------------------------------------------------------------------------- #
# Cambio
# --------------------------------------------------------------------------- #
API_CAMBIO = os.getenv(
    "BANCO_AGIL_API_CAMBIO", "https://economia.awesomeapi.com.br/json/last"
)
TIMEOUT_API_CAMBIO = float(os.getenv("BANCO_AGIL_TIMEOUT_CAMBIO", "10"))

# --------------------------------------------------------------------------- #
# Pesos da formula de score (valores sugeridos pelo desafio)
# --------------------------------------------------------------------------- #
PESO_RENDA = 30

PESO_EMPREGO: dict[str, int] = {
    "formal": 300,
    "autonomo": 200,
    "desempregado": 0,
}

PESO_DEPENDENTES: dict[str, int] = {
    "0": 100,
    "1": 80,
    "2": 60,
    "3+": 30,
}

PESO_DIVIDAS: dict[str, int] = {
    "sim": -100,
    "nao": 100,
}

SCORE_MINIMO = 0
SCORE_MAXIMO = 1000

# --------------------------------------------------------------------------- #
# Status possiveis de uma solicitacao de aumento de limite
# --------------------------------------------------------------------------- #
STATUS_PENDENTE = "pendente"
STATUS_APROVADO = "aprovado"
STATUS_REJEITADO = "rejeitado"

# --------------------------------------------------------------------------- #
# Agentes
# --------------------------------------------------------------------------- #
AGENTE_TRIAGEM = "triagem"
AGENTE_CREDITO = "credito"
AGENTE_ENTREVISTA = "entrevista"
AGENTE_CAMBIO = "cambio"

AGENTES = (AGENTE_TRIAGEM, AGENTE_CREDITO, AGENTE_ENTREVISTA, AGENTE_CAMBIO)
