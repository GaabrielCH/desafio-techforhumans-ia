"""Normalizacao de entradas vindas de texto livre.

O cliente digita "123.456.789-01", "14/05/1990", "R$ 5.000,00". A base de
dados guarda "12345678901", "1990-05-14", 5000.0. Estas funcoes fazem a
ponte, e falham com ErroEntradaInvalida quando o texto nao e recuperavel.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from .erros import ErroEntradaInvalida

_FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d%m%Y", "%Y/%m/%d")


def remover_acentos(texto: str) -> str:
    """Remove acentos preservando as letras ('autonomo' <- 'autonomo')."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def normalizar_texto(texto: str) -> str:
    """Minusculas, sem acentos e sem espacos nas pontas."""
    return remover_acentos(str(texto)).strip().lower()


def normalizar_cpf(cpf: str) -> str:
    """Mantem apenas digitos e valida o comprimento de 11 caracteres."""
    if cpf is None:
        raise ErroEntradaInvalida("CPF nao informado.")

    digitos = re.sub(r"\D", "", str(cpf))
    if len(digitos) != 11:
        raise ErroEntradaInvalida(
            "CPF deve conter 11 digitos. Recebido: "
            f"{len(digitos)} digito(s)."
        )
    return digitos


def normalizar_data(valor: str) -> str:
    """Converte uma data em varios formatos para ISO 'AAAA-MM-DD'."""
    if valor is None:
        raise ErroEntradaInvalida("Data de nascimento nao informada.")

    texto = str(valor).strip()
    if not texto:
        raise ErroEntradaInvalida("Data de nascimento nao informada.")

    for formato in _FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue

    # Ultimo recurso: sequencia de 8 digitos sem separador.
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) == 8:
        for formato in ("%d%m%Y", "%Y%m%d"):
            try:
                return datetime.strptime(digitos, formato).date().isoformat()
            except ValueError:
                continue

    raise ErroEntradaInvalida(
        f"Nao foi possivel interpretar a data '{valor}'. "
        "Use o formato DD/MM/AAAA."
    )


def normalizar_valor_monetario(valor: str | float | int) -> float:
    """Converte 'R$ 5.000,00', '5000.5' ou 5000 em float.

    Trata a ambiguidade ponto/virgula do padrao brasileiro: quando ha os
    dois separadores, o ultimo e o decimal.
    """
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        numero = float(valor)
        if numero < 0:
            raise ErroEntradaInvalida("O valor nao pode ser negativo.")
        return numero

    if valor is None:
        raise ErroEntradaInvalida("Valor nao informado.")

    texto = re.sub(r"[^\d,.\-]", "", str(valor)).strip()
    if not texto:
        raise ErroEntradaInvalida(f"Nao foi possivel interpretar o valor '{valor}'.")

    tem_virgula = "," in texto
    tem_ponto = "." in texto

    if tem_virgula and tem_ponto:
        # O separador decimal e o que aparece por ultimo.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif tem_virgula:
        texto = texto.replace(",", ".")
    elif tem_ponto:
        # "5.000" e milhar; "5.5" e decimal.
        partes = texto.split(".")
        if len(partes) > 2 or len(partes[-1]) == 3:
            texto = texto.replace(".", "")

    try:
        numero = float(texto)
    except ValueError as exc:
        raise ErroEntradaInvalida(
            f"Nao foi possivel interpretar o valor '{valor}'."
        ) from exc

    if numero < 0:
        raise ErroEntradaInvalida("O valor nao pode ser negativo.")
    return numero


def normalizar_inteiro_nao_negativo(valor: str | int) -> int:
    """Converte texto em inteiro >= 0 (usado para numero de dependentes)."""
    if isinstance(valor, bool):
        raise ErroEntradaInvalida("Valor invalido.")
    if isinstance(valor, int):
        numero = valor
    else:
        digitos = re.sub(r"\D", "", str(valor))
        if not digitos:
            # "nenhum", "sem dependentes" -> 0
            if any(p in normalizar_texto(valor) for p in ("nenhum", "sem", "nao")):
                return 0
            raise ErroEntradaInvalida(
                f"Nao foi possivel interpretar o numero '{valor}'."
            )
        numero = int(digitos)

    if numero < 0:
        raise ErroEntradaInvalida("O numero nao pode ser negativo.")
    return numero


def normalizar_sim_nao(valor: str | bool) -> str:
    """Converte respostas variadas em 'sim' ou 'nao'."""
    if isinstance(valor, bool):
        return "sim" if valor else "nao"

    texto = normalizar_texto(valor)
    if texto in {"sim", "s", "yes", "y", "true", "1", "possuo", "tenho", "sim tenho"}:
        return "sim"
    if texto in {"nao", "n", "no", "false", "0", "nenhuma", "nenhum", "negativo"}:
        return "nao"

    if texto.startswith("sim") or "tenho divida" in texto or "possuo divida" in texto:
        return "sim"
    if texto.startswith("nao") or "sem divida" in texto:
        return "nao"

    raise ErroEntradaInvalida(
        f"Nao foi possivel interpretar '{valor}'. Responda com 'sim' ou 'nao'."
    )


def normalizar_tipo_emprego(valor: str) -> str:
    """Mapeia a resposta do cliente para formal/autonomo/desempregado."""
    texto = normalizar_texto(valor)

    if any(p in texto for p in ("formal", "clt", "carteira", "assalariado", "efetivo",
                                "servidor", "publico", "aposentad")):
        return "formal"
    if any(p in texto for p in ("autonomo", "freelan", "pj", "conta propria",
                                "empreendedor", "mei", "informal", "liberal")):
        return "autonomo"
    if any(p in texto for p in ("desempregad", "sem emprego", "sem trabalho",
                                "nao trabalho", "desocupad")):
        return "desempregado"

    raise ErroEntradaInvalida(
        f"Nao foi possivel classificar o tipo de emprego '{valor}'. "
        "Use 'formal', 'autonomo' ou 'desempregado'."
    )


def agora_iso() -> str:
    """Timestamp local no formato ISO 8601 (usado nas solicitacoes).

    Milissegundos, e nao segundos: o timestamp e parte da chave que
    identifica um pedido no CSV, e dois pedidos do mesmo cliente no mesmo
    segundo sao um cenario real (rejeitado -> entrevista -> nova analise).
    """
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def formatar_data_br(iso: str) -> str:
    """Converte 'AAAA-MM-DD' em 'DD/MM/AAAA' para exibicao."""
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(iso)


def formatar_moeda(valor: float) -> str:
    """Formata um float como 'R$ 1.234,56'."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
