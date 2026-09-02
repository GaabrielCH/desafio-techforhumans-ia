"""Excecoes de dominio.

Toda falha esperada vira uma destas, para que a camada de ferramentas
consiga traduzi-la em uma mensagem clara ao cliente em vez de estourar
um traceback no meio da conversa.
"""

from __future__ import annotations


class ErroBancoAgil(Exception):
    """Erro base da aplicacao."""


class ErroBaseDados(ErroBancoAgil):
    """Falha ao ler ou gravar um arquivo CSV."""


class ClienteNaoEncontrado(ErroBancoAgil):
    """CPF nao existe na base de clientes."""


class ErroEntradaInvalida(ErroBancoAgil):
    """Dado informado pelo cliente nao pode ser interpretado."""


class ErroServicoExterno(ErroBancoAgil):
    """API externa indisponivel ou com resposta inesperada."""
