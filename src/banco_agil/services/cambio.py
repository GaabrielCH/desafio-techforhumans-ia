"""Consulta de cotacao de moedas via API externa (AwesomeAPI).

Escolhi a AwesomeAPI porque ela nao exige chave de API - o avaliador do
desafio consegue rodar o projeto sem cadastrar uma credencial a mais - e
devolve o par de moedas ja convertido, sem precisar de um LLM para
interpretar resultado de busca.

Endpoint: https://economia.awesomeapi.com.br/json/last/USD-BRL
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests

from .. import config
from ..erros import ErroEntradaInvalida, ErroServicoExterno
from ..logging_config import obter_logger
from ..utils import normalizar_texto

log = obter_logger("servico.cambio")

# Apelidos que o cliente costuma usar -> codigo ISO 4217.
APELIDOS_MOEDA: dict[str, str] = {
    "dolar": "USD",
    "dolar americano": "USD",
    "dolares": "USD",
    "usd": "USD",
    "us$": "USD",
    "euro": "EUR",
    "euros": "EUR",
    "eur": "EUR",
    "libra": "GBP",
    "libra esterlina": "GBP",
    "gbp": "GBP",
    "iene": "JPY",
    "iene japones": "JPY",
    "jpy": "JPY",
    "peso argentino": "ARS",
    "ars": "ARS",
    "franco suico": "CHF",
    "chf": "CHF",
    "dolar canadense": "CAD",
    "cad": "CAD",
    "dolar australiano": "AUD",
    "aud": "AUD",
    "yuan": "CNY",
    "cny": "CNY",
    "bitcoin": "BTC",
    "btc": "BTC",
    "real": "BRL",
    "reais": "BRL",
    "brl": "BRL",
    "r$": "BRL",
}

NOMES_MOEDA: dict[str, str] = {
    "USD": "dolar americano",
    "EUR": "euro",
    "GBP": "libra esterlina",
    "JPY": "iene japones",
    "ARS": "peso argentino",
    "CHF": "franco suico",
    "CAD": "dolar canadense",
    "AUD": "dolar australiano",
    "CNY": "yuan chines",
    "BTC": "bitcoin",
    "BRL": "real brasileiro",
}


@dataclass(frozen=True)
class Cotacao:
    """Cotacao de um par de moedas em um instante."""

    moeda_origem: str
    moeda_destino: str
    nome: str
    compra: float
    venda: float
    maxima: float
    minima: float
    variacao_percentual: float
    atualizado_em: str

    def resumo(self) -> str:
        """Frase pronta para o agente repassar ao cliente."""
        return (
            f"1 {self.moeda_origem} = {self.venda:.4f} {self.moeda_destino} "
            f"(compra {self.compra:.4f}, variacao {self.variacao_percentual:+.2f}% "
            f"no dia). Atualizado em {self.atualizado_em}."
        )


def resolver_codigo_moeda(moeda: str) -> str:
    """Converte 'dolar', 'USD' ou 'us$' no codigo ISO da moeda."""
    if not moeda or not str(moeda).strip():
        raise ErroEntradaInvalida("Nenhuma moeda foi informada.")

    texto = normalizar_texto(moeda)
    if texto in APELIDOS_MOEDA:
        return APELIDOS_MOEDA[texto]

    # Tenta casar por prefixo ("dolar canadense hoje").
    for apelido, codigo in APELIDOS_MOEDA.items():
        if apelido in texto:
            return codigo

    candidato = texto.upper().strip()
    if len(candidato) == 3 and candidato.isalpha():
        return candidato

    raise ErroEntradaInvalida(
        f"Nao reconheci a moeda '{moeda}'. "
        "Tente por exemplo dolar, euro, libra ou o codigo de 3 letras."
    )


def _formatar_timestamp(bruto: str) -> str:
    """Converte o epoch da API para 'DD/MM/AAAA HH:MM'."""
    try:
        return datetime.fromtimestamp(int(bruto)).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError, OSError):
        return "agora"


def _float_seguro(valor: object, padrao: float = 0.0) -> float:
    try:
        return float(str(valor))
    except (TypeError, ValueError):
        return padrao


def consultar_cotacao(
    moeda_origem: str = "USD",
    moeda_destino: str = "BRL",
    tentativas: int = 2,
) -> Cotacao:
    """Busca a cotacao atual de um par de moedas.

    Levanta ErroEntradaInvalida (moeda desconhecida / par invalido) ou
    ErroServicoExterno (API fora do ar ou resposta inesperada).
    """
    origem = resolver_codigo_moeda(moeda_origem)
    destino = resolver_codigo_moeda(moeda_destino) if moeda_destino else "BRL"

    if origem == destino:
        raise ErroEntradaInvalida(
            "As moedas de origem e destino sao a mesma; nao ha cotacao."
        )

    par = f"{origem}-{destino}"
    url = f"{config.API_CAMBIO.rstrip('/')}/{par}"

    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(url, timeout=config.TIMEOUT_API_CAMBIO)
        except requests.RequestException as exc:
            ultimo_erro = exc
            log.warning(
                "Tentativa %d/%d falhou ao consultar %s: %s",
                tentativa,
                tentativas,
                par,
                exc,
            )
            continue

        if resposta.status_code == 404:
            log.info("Par de moedas nao suportado pela API: %s", par)
            raise ErroEntradaInvalida(
                f"O par {origem}/{destino} nao esta disponivel para cotacao."
            )

        if resposta.status_code >= 400:
            ultimo_erro = ErroServicoExterno(
                f"HTTP {resposta.status_code} ao consultar {par}."
            )
            log.warning(
                "Tentativa %d/%d retornou HTTP %d para %s.",
                tentativa,
                tentativas,
                resposta.status_code,
                par,
            )
            continue

        try:
            dados = resposta.json()
        except ValueError as exc:
            ultimo_erro = exc
            log.warning("Resposta nao-JSON da API de cambio para %s.", par)
            continue

        chave = f"{origem}{destino}"
        bloco = dados.get(chave) or next(
            (v for v in dados.values() if isinstance(v, dict)), None
        )
        if not isinstance(bloco, dict) or "bid" not in bloco:
            log.error("Formato inesperado da API de cambio para %s: %s", par, dados)
            raise ErroServicoExterno(
                "A cotacao veio em um formato inesperado do provedor."
            )

        cotacao = Cotacao(
            moeda_origem=origem,
            moeda_destino=destino,
            nome=bloco.get("name") or (
                f"{NOMES_MOEDA.get(origem, origem)}/"
                f"{NOMES_MOEDA.get(destino, destino)}"
            ),
            compra=_float_seguro(bloco.get("bid")),
            venda=_float_seguro(bloco.get("ask"), _float_seguro(bloco.get("bid"))),
            maxima=_float_seguro(bloco.get("high")),
            minima=_float_seguro(bloco.get("low")),
            variacao_percentual=_float_seguro(bloco.get("pctChange")),
            atualizado_em=_formatar_timestamp(bloco.get("timestamp", "")),
        )
        log.info("Cotacao obtida para %s: %.4f", par, cotacao.venda)
        return cotacao

    log.error("API de cambio indisponivel para %s: %s", par, ultimo_erro)
    raise ErroServicoExterno(
        "O servico de cotacao esta indisponivel no momento."
    ) from ultimo_erro
