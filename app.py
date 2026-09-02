"""Interface de testes do Banco Agil (Streamlit).

    streamlit run app.py

A UI e deliberadamente fina: ela nao conhece agentes nem ferramentas, so
conversa com ``SessaoAtendimento``.

O painel lateral existe para quem avalia: mostra o que o cliente NAO ve
(especialidade ativa, estado da sessao, ferramentas acionadas no turno,
arquivos gravados) sem quebrar a ilusao de atendente unico no chat.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from banco_agil import config  # noqa: E402
from banco_agil.erros import ErroBancoAgil  # noqa: E402
from banco_agil.graph import SessaoAtendimento  # noqa: E402
from banco_agil.repositories import clientes as repo_clientes  # noqa: E402
from banco_agil.repositories.csv_base import ler_csv  # noqa: E402
from banco_agil.utils import formatar_data_br, formatar_moeda  # noqa: E402

st.set_page_config(
    page_title="Banco Agil - Atendimento",
    page_icon="🏦",
    layout="centered",
)

ROTULOS_AGENTE = {
    config.AGENTE_TRIAGEM: "Triagem",
    config.AGENTE_CREDITO: "Credito",
    config.AGENTE_ENTREVISTA: "Entrevista de Credito",
    config.AGENTE_CAMBIO: "Cambio",
}

# Nomes tecnicos das ferramentas -> descricao legivel no painel.
ROTULOS_FERRAMENTA = {
    "autenticar_cliente": "🔐 Autenticou o cliente",
    "consultar_limite_credito": "💳 Consultou limite e score",
    "solicitar_aumento_limite": "📝 Registrou e analisou o pedido",
    "realizar_entrevista_credito": "📊 Recalculou o score",
    "consultar_cotacao_moeda": "💱 Consultou a cotacao",
    "direcionar_para_credito": "➡️ Passou para Credito",
    "direcionar_para_cambio": "➡️ Passou para Cambio",
    "direcionar_para_entrevista": "➡️ Passou para Entrevista",
    "encerrar_atendimento": "👋 Encerrou o atendimento",
}


# --------------------------------------------------------------------------- #
# Sessao
# --------------------------------------------------------------------------- #
def reiniciar_sessao() -> None:
    """Descarta a conversa atual e comeca uma nova."""
    for chave in ("sessao", "historico", "erro_inicializacao", "ferramentas"):
        st.session_state.pop(chave, None)


def garantir_sessao() -> SessaoAtendimento | None:
    """Cria a sessao e a saudacao inicial uma unica vez por conversa."""
    if "sessao" in st.session_state:
        return st.session_state.sessao

    if st.session_state.get("erro_inicializacao"):
        return None

    try:
        sessao = SessaoAtendimento(thread_id=f"streamlit-{uuid.uuid4().hex[:8]}")
        with st.spinner("Conectando ao atendimento..."):
            saudacao = sessao.iniciar()
    except ErroBancoAgil as exc:
        st.session_state.erro_inicializacao = str(exc)
        return None
    except Exception as exc:  # noqa: BLE001 - erro do provedor tambem e exibido
        st.session_state.erro_inicializacao = (
            f"Nao foi possivel iniciar o atendimento: {exc}"
        )
        return None

    st.session_state.sessao = sessao
    st.session_state.historico = [{"role": "assistant", "content": saudacao}]
    st.session_state.ferramentas = []
    return sessao


# --------------------------------------------------------------------------- #
# Painel lateral (visao de quem avalia)
# --------------------------------------------------------------------------- #
def _secao_estado(estado: dict) -> None:
    st.subheader("Estado da sessao")

    if estado.get("autenticado"):
        st.success(f"Autenticado: {estado.get('nome')}")
    else:
        usadas = int(estado.get("tentativas_autenticacao", 0))
        restantes = max(config.MAX_TENTATIVAS_AUTENTICACAO - usadas, 0)
        st.warning("Nao autenticado")
        st.caption(
            f"Tentativas usadas: {usadas}/{config.MAX_TENTATIVAS_AUTENTICACAO} "
            f"({restantes} restante(s))"
        )

    st.metric(
        "Especialidade ativa",
        ROTULOS_AGENTE.get(estado.get("agente_atual", ""), "-"),
    )
    st.caption("O cliente nao ve isto: no chat a troca e implicita.")

    if estado.get("ultimo_status_solicitacao"):
        st.info(f"Ultimo pedido: **{estado['ultimo_status_solicitacao']}**")

    if estado.get("encerrado"):
        st.error("Atendimento encerrado")


def _secao_ferramentas() -> None:
    """Mostra o que aconteceu por baixo no ultimo turno."""
    ferramentas = st.session_state.get("ferramentas") or []
    if not ferramentas:
        return

    st.subheader("No ultimo turno")
    for nome in ferramentas:
        st.markdown(f"- {ROTULOS_FERRAMENTA.get(nome, f'`{nome}`')}")


def _secao_clientes_demo() -> None:
    """Lista os clientes de teste. So existe em modo demonstracao."""
    if not config.MODO_DEMO:
        st.caption(
            "Modo demonstracao desligado: a lista de clientes nao e exibida."
        )
        return

    with st.expander("👤 Clientes para teste"):
        st.caption("Dados ficticios, apenas para demonstracao.")
        try:
            for cliente in repo_clientes.listar_clientes():
                st.markdown(
                    f"**{cliente.nome}**  \n"
                    f"CPF `{cliente.cpf}` · nasc. "
                    f"`{formatar_data_br(cliente.data_nascimento)}`  \n"
                    f"{formatar_moeda(cliente.limite_credito)} · "
                    f"score **{cliente.score}**"
                )
        except ErroBancoAgil as exc:
            st.error(str(exc))


def _secao_solicitacoes() -> None:
    with st.expander("📄 Solicitacoes registradas"):
        if not config.ARQUIVO_SOLICITACOES.exists():
            st.caption("Nenhuma solicitacao registrada ainda.")
            return
        try:
            linhas = ler_csv(config.ARQUIVO_SOLICITACOES)
        except ErroBancoAgil as exc:
            st.error(str(exc))
            return
        if not linhas:
            st.caption("Nenhuma solicitacao registrada ainda.")
            return
        st.dataframe(linhas[-15:], use_container_width=True, hide_index=True)
        st.caption(f"{len(linhas)} pedido(s) no total.")


def desenhar_barra_lateral(sessao: SessaoAtendimento | None) -> None:
    with st.sidebar:
        st.header("🏦 Banco Agil")
        st.caption(f"Modelo: `{config.MODELO}`")

        if st.button("🔄 Nova conversa", use_container_width=True):
            reiniciar_sessao()
            st.rerun()

        st.divider()
        _secao_estado(sessao.estado if sessao else {})
        _secao_ferramentas()
        st.divider()
        _secao_clientes_demo()
        _secao_solicitacoes()


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #
st.title("Atendimento Banco Agil")
st.caption(
    "Assistente virtual para limite de credito, analise de score e cotacao "
    "de moedas."
)

sessao = garantir_sessao()
desenhar_barra_lateral(sessao)

if erro := st.session_state.get("erro_inicializacao"):
    st.error(erro)
    st.info(
        "Copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY` com uma "
        "chave da Gemini API (https://aistudio.google.com/apikey). "
        "Depois clique em **Nova conversa**."
    )
    st.stop()

for mensagem in st.session_state.get("historico", []):
    with st.chat_message(mensagem["role"]):
        st.markdown(mensagem["content"])

encerrada = sessao.encerrada if sessao else False

if encerrada:
    st.info("Este atendimento foi encerrado. Inicie uma nova conversa no menu.")

entrada = st.chat_input(
    "Digite sua mensagem..." if not encerrada else "Atendimento encerrado",
    disabled=encerrada,
)

if entrada:
    st.session_state.historico.append({"role": "user", "content": entrada})
    with st.chat_message("user"):
        st.markdown(entrada)

    with st.chat_message("assistant"):
        with st.spinner("Digitando..."):
            resposta = sessao.enviar(entrada)
        st.markdown(resposta)

    st.session_state.historico.append({"role": "assistant", "content": resposta})
    st.session_state.ferramentas = sessao.ferramentas_do_ultimo_turno()
    st.rerun()
