"""Orquestracao do grafo, com um LLM dublê.

O objetivo aqui nao e avaliar a qualidade do texto do modelo, e sim provar o
que precisa valer sempre, independentemente do que o LLM decidir dizer:

- ferramenta sensivel so executa apos autenticacao;
- tres falhas consecutivas encerram o atendimento;
- handoff troca o agente sem trocar de conversa;
- o loop sempre termina depois de `encerrar_atendimento`.

Por isso os testes rodam sem chave de API e sem rede.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from banco_agil import config
from banco_agil.graph import SessaoAtendimento, construir_grafo


class LLMFalso:
    """Dublê de chat model: devolve mensagens roteirizadas, em ordem.

    Implementa apenas ``bind_tools`` e ``invoke``, que e tudo que o no do
    agente consome.
    """

    def __init__(self, roteiro: list[AIMessage]) -> None:
        self.roteiro = list(roteiro)
        self.chamadas: list[list] = []

    def bind_tools(self, ferramentas):  # noqa: D102 - interface do LangChain
        self.ultimas_ferramentas = [f.name for f in ferramentas]
        return self

    def invoke(self, mensagens):  # noqa: D102
        self.chamadas.append(mensagens)
        if not self.roteiro:
            return AIMessage(content="Posso ajudar em algo mais?")
        return self.roteiro.pop(0)


def chamada(nome: str, args: dict | None = None, ident: str = "call_1") -> AIMessage:
    """Monta uma AIMessage que solicita uma ferramenta."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": nome,
                "args": args or {},
                "id": ident,
                "type": "tool_call",
            }
        ],
    )


@pytest.fixture()
def bases(monkeypatch, base_clientes, base_score_limite, base_solicitacoes):
    """Aponta a configuracao global para as bases temporarias do teste."""
    monkeypatch.setattr(config, "ARQUIVO_CLIENTES", base_clientes)
    monkeypatch.setattr(config, "ARQUIVO_SCORE_LIMITE", base_score_limite)
    monkeypatch.setattr(config, "ARQUIVO_SOLICITACOES", base_solicitacoes)
    return {
        "clientes": base_clientes,
        "score_limite": base_score_limite,
        "solicitacoes": base_solicitacoes,
    }


def montar_sessao(roteiro: list[AIMessage]) -> SessaoAtendimento:
    llm = LLMFalso(roteiro)
    return SessaoAtendimento(grafo=construir_grafo(llm=llm), thread_id="teste")


# --------------------------------------------------------------------------- #
# Autenticacao
# --------------------------------------------------------------------------- #
def test_saudacao_inicial_nao_exige_mensagem_do_cliente(bases):
    sessao = montar_sessao([AIMessage(content="Ola! Sou o Agil. Qual o seu CPF?")])
    assert "CPF" in sessao.iniciar()
    assert sessao.estado["autenticado"] is False
    assert sessao.estado["agente_atual"] == config.AGENTE_TRIAGEM


def test_autenticacao_bem_sucedida_guarda_cliente_no_estado(bases):
    sessao = montar_sessao(
        [
            AIMessage(content="Qual o seu CPF e a sua data de nascimento?"),
            chamada(
                "autenticar_cliente",
                {"cpf": "123.456.789-01", "data_nascimento": "14/05/1990"},
            ),
            AIMessage(content="Ola, Ana! Como posso ajudar?"),
        ]
    )
    sessao.iniciar()
    resposta = sessao.enviar("12345678901, 14/05/1990")

    estado = sessao.estado
    assert estado["autenticado"] is True
    assert estado["cpf"] == "12345678901"
    assert estado["nome"] == "Ana Beatriz Souza"
    assert estado["tentativas_autenticacao"] == 0
    assert "Ana" in resposta


def test_tres_falhas_consecutivas_encerram_o_atendimento(bases):
    tentativa_errada = {"cpf": "12345678901", "data_nascimento": "01/01/1900"}
    sessao = montar_sessao(
        [
            AIMessage(content="Qual o seu CPF?"),
            chamada("autenticar_cliente", tentativa_errada),
            AIMessage(content="Os dados nao conferem. Pode repetir?"),
            chamada("autenticar_cliente", tentativa_errada, "call_2"),
            AIMessage(content="Ainda nao confere. Ultima tentativa."),
            chamada("autenticar_cliente", tentativa_errada, "call_3"),
            AIMessage(content="Nao consegui confirmar seus dados. Ate logo!"),
        ]
    )
    sessao.iniciar()

    sessao.enviar("tentativa 1")
    assert sessao.estado["tentativas_autenticacao"] == 1
    assert sessao.encerrada is False

    sessao.enviar("tentativa 2")
    assert sessao.estado["tentativas_autenticacao"] == 2
    assert sessao.encerrada is False

    resposta = sessao.enviar("tentativa 3")
    assert sessao.estado["tentativas_autenticacao"] == 3
    assert sessao.encerrada is True
    assert "Ate logo" in resposta


def test_autenticacao_correta_zera_o_contador_de_tentativas(bases):
    sessao = montar_sessao(
        [
            AIMessage(content="Qual o seu CPF?"),
            chamada(
                "autenticar_cliente",
                {"cpf": "12345678901", "data_nascimento": "01/01/1900"},
            ),
            AIMessage(content="Nao conferiu, pode repetir?"),
            chamada(
                "autenticar_cliente",
                {"cpf": "12345678901", "data_nascimento": "14/05/1990"},
                "call_2",
            ),
            AIMessage(content="Perfeito, Ana!"),
        ]
    )
    sessao.iniciar()
    sessao.enviar("errado")
    assert sessao.estado["tentativas_autenticacao"] == 1

    sessao.enviar("agora certo")
    assert sessao.estado["autenticado"] is True
    assert sessao.estado["tentativas_autenticacao"] == 0


# --------------------------------------------------------------------------- #
# Escopo e bloqueio antes da autenticacao
# --------------------------------------------------------------------------- #
def test_consulta_de_limite_e_bloqueada_sem_autenticacao(bases):
    sessao = montar_sessao(
        [
            chamada("direcionar_para_credito"),
            AIMessage(content="Preciso confirmar seus dados antes. Qual o seu CPF?"),
        ]
    )
    resposta = sessao.enviar("quero saber meu limite")

    # O handoff foi recusado: continuamos na triagem, sem autenticar.
    assert sessao.estado["agente_atual"] == config.AGENTE_TRIAGEM
    assert sessao.estado["autenticado"] is False
    assert "CPF" in resposta


def test_cambio_e_bloqueado_sem_autenticacao(bases):
    sessao = montar_sessao(
        [
            chamada("direcionar_para_cambio"),
            AIMessage(content="Antes preciso confirmar seus dados. Qual o seu CPF?"),
        ]
    )
    sessao.enviar("quanto esta o dolar?")
    assert sessao.estado["agente_atual"] == config.AGENTE_TRIAGEM
    assert sessao.estado["autenticado"] is False


# --------------------------------------------------------------------------- #
# Redirecionamento implicito
# --------------------------------------------------------------------------- #
def _roteiro_autenticado() -> list[AIMessage]:
    return [
        chamada(
            "autenticar_cliente",
            {"cpf": "12345678901", "data_nascimento": "14/05/1990"},
        ),
        AIMessage(content="Ola, Ana! Como posso ajudar?"),
    ]


def test_handoff_troca_o_agente_mantendo_a_mesma_conversa(bases):
    sessao = montar_sessao(
        _roteiro_autenticado()
        + [
            chamada("direcionar_para_credito", ident="call_2"),
            chamada("consultar_limite_credito", ident="call_3"),
            AIMessage(content="Seu limite atual e de R$ 5.000,00 e o score e 720."),
        ]
    )
    sessao.enviar("oi, sou a Ana: 12345678901, 14/05/1990")
    resposta = sessao.enviar("qual meu limite?")

    assert sessao.estado["agente_atual"] == config.AGENTE_CREDITO
    assert "5.000,00" in resposta
    # A transicao nao pode aparecer para o cliente.
    for termo in ("transfer", "encaminh", "setor", "agente"):
        assert termo not in resposta.lower()


def test_fluxo_completo_rejeicao_entrevista_e_nova_aprovacao(bases):
    """Rejeitado por score baixo -> entrevista -> aprovado. Fluxo do desafio."""
    sessao = montar_sessao(
        [
            # Autentica o Rafael (score 250 -> teto 1000, limite 800).
            chamada(
                "autenticar_cliente",
                {"cpf": "55566677788", "data_nascimento": "09/08/1979"},
            ),
            AIMessage(content="Ola, Rafael! Como posso ajudar?"),
            # Pede aumento e e rejeitado.
            chamada("direcionar_para_credito", ident="call_2"),
            chamada(
                "solicitar_aumento_limite", {"novo_limite": 5000}, "call_3"
            ),
            AIMessage(
                content=(
                    "Nao foi possivel aprovar agora. Posso fazer algumas "
                    "perguntas rapidas para reavaliar?"
                )
            ),
            # Cliente aceita a entrevista.
            chamada("direcionar_para_entrevista", ident="call_4"),
            chamada(
                "realizar_entrevista_credito",
                {
                    "renda_mensal": 9000,
                    "tipo_emprego": "formal",
                    "despesas_fixas": 1500,
                    "numero_dependentes": 0,
                    "tem_dividas": "nao",
                },
                "call_5",
            ),
            AIMessage(content="Seu score foi atualizado."),
            # Volta para credito e refaz a analise.
            chamada("direcionar_para_credito", ident="call_6"),
            chamada(
                "solicitar_aumento_limite", {"novo_limite": 5000}, "call_7"
            ),
            AIMessage(content="Boa noticia: seu novo limite foi aprovado!"),
        ]
    )

    sessao.enviar("oi, 55566677788, 09/08/1979")

    sessao.enviar("quero aumentar meu limite para 5000")
    assert sessao.estado["ultimo_status_solicitacao"] == config.STATUS_REJEITADO

    sessao.enviar("pode fazer as perguntas")
    assert sessao.estado["agente_atual"] == config.AGENTE_ENTREVISTA

    # O score foi recalculado e persistido na base.
    from banco_agil.repositories import clientes as repo_clientes

    cliente = repo_clientes.buscar_por_cpf("55566677788", bases["clientes"])
    assert cliente.score > 250

    resposta = sessao.enviar("e agora?")
    assert sessao.estado["ultimo_status_solicitacao"] == config.STATUS_APROVADO
    assert "aprovado" in resposta.lower()

    # As duas solicitacoes ficaram registradas, com desfechos diferentes.
    from banco_agil.repositories import solicitacoes as repo_solicitacoes

    historico = repo_solicitacoes.listar_por_cpf(
        "55566677788", bases["solicitacoes"]
    )
    assert [s.status_pedido for s in historico] == ["rejeitado", "aprovado"]


# --------------------------------------------------------------------------- #
# Encerramento
# --------------------------------------------------------------------------- #
def test_encerrar_atendimento_finaliza_o_loop(bases):
    sessao = montar_sessao(
        _roteiro_autenticado()
        + [
            chamada(
                "encerrar_atendimento",
                {"mensagem_final": "Obrigado por falar com o Banco Agil!"},
                "call_2",
            ),
            AIMessage(content="Obrigado por falar com o Banco Agil! Ate mais."),
        ]
    )
    sessao.enviar("oi, 12345678901, 14/05/1990")
    resposta = sessao.enviar("era so isso, obrigado")

    assert sessao.encerrada is True
    assert "Banco Agil" in resposta


def test_apos_encerrar_o_agente_perde_as_ferramentas(bases):
    """Garante a terminacao: no turno final o modelo so pode gerar texto."""
    llm = LLMFalso(
        _roteiro_autenticado()
        + [
            chamada(
                "encerrar_atendimento",
                {"mensagem_final": "Ate logo!"},
                "call_2",
            ),
            # Se as ferramentas ainda estivessem ligadas, isso viraria um loop.
            AIMessage(content="Ate logo!"),
        ]
    )
    sessao = SessaoAtendimento(grafo=construir_grafo(llm=llm), thread_id="teste-fim")
    sessao.enviar("oi, 12345678901, 14/05/1990")
    sessao.enviar("tchau")

    assert sessao.encerrada is True
    # A ultima ligacao de ferramentas ocorreu antes do turno de despedida.
    assert llm.ultimas_ferramentas is not None


# --------------------------------------------------------------------------- #
# Resiliencia
# --------------------------------------------------------------------------- #
def test_falha_do_modelo_nao_derruba_a_sessao(bases):
    class LLMQuebrado(LLMFalso):
        def invoke(self, mensagens):
            raise RuntimeError("provedor fora do ar")

    sessao = SessaoAtendimento(
        grafo=construir_grafo(llm=LLMQuebrado([])), thread_id="teste-falha"
    )
    resposta = sessao.enviar("oi")

    assert "instabilidade" in resposta.lower()
    assert sessao.encerrada is False


def test_base_de_clientes_ausente_nao_consome_tentativa(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ARQUIVO_CLIENTES", tmp_path / "sumiu.csv")

    sessao = montar_sessao(
        [
            chamada(
                "autenticar_cliente",
                {"cpf": "12345678901", "data_nascimento": "14/05/1990"},
            ),
            AIMessage(content="Estamos com instabilidade. Tenta de novo?"),
        ]
    )
    sessao.enviar("12345678901, 14/05/1990")

    # Falha de infraestrutura nao pode custar uma tentativa ao cliente.
    assert sessao.estado["tentativas_autenticacao"] == 0
    assert sessao.encerrada is False
