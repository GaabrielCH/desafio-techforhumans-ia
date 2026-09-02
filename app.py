"""Interface do Banco Agil (Streamlit).

    streamlit run app.py

A UI e fina de proposito: nao conhece agentes nem ferramentas, so conversa
com ``SessaoAtendimento``. Todo o visual mora em ``banco_agil.ui``.

A tela serve dois publicos ao mesmo tempo - o cliente, que ve um atendente
so, e quem avalia, que precisa ver o roteamento acontecendo. Dai a divisao
entre vitrine (area principal) e retaguarda (painel lateral).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from banco_agil import config, ui  # noqa: E402
from banco_agil.erros import ErroBancoAgil  # noqa: E402
from banco_agil.graph import SessaoAtendimento  # noqa: E402
from banco_agil.repositories import clientes as repo_clientes  # noqa: E402
from banco_agil.repositories.csv_base import ler_csv  # noqa: E402
from banco_agil.utils import formatar_data_br, formatar_moeda  # noqa: E402

st.set_page_config(
    page_title="Banco Ágil",
    page_icon="◈",
    layout="centered",
    initial_sidebar_state="expanded",
)

ui.aplicar_estilo()


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
        with st.spinner("Abrindo o atendimento..."):
            saudacao = sessao.iniciar()
    except ErroBancoAgil as exc:
        st.session_state.erro_inicializacao = str(exc)
        return None
    except Exception as exc:  # noqa: BLE001 - erro do provedor tambem e exibido
        st.session_state.erro_inicializacao = (
            f"Não foi possível abrir o atendimento: {exc}"
        )
        return None

    st.session_state.sessao = sessao
    st.session_state.historico = [{"papel": "agente", "texto": saudacao}]
    st.session_state.ferramentas = []
    return sessao


# --------------------------------------------------------------------------- #
# Retaguarda
# --------------------------------------------------------------------------- #
def _clientes_de_teste() -> None:
    """Credenciais de demonstracao. Some quando o modo demo e desligado."""
    if not config.MODO_DEMO:
        return

    with st.expander("Clientes para teste"):
        st.caption("Dados fictícios, apenas para demonstração.")
        try:
            for cliente in repo_clientes.listar_clientes():
                st.markdown(
                    f"**{cliente.nome}**  \n"
                    f"`{cliente.cpf}` · "
                    f"`{formatar_data_br(cliente.data_nascimento)}`  \n"
                    f"{formatar_moeda(cliente.limite_credito)} · "
                    f"score {cliente.score}"
                )
        except ErroBancoAgil as exc:
            st.error(str(exc))


def _solicitacoes_gravadas() -> None:
    with st.expander("Solicitações gravadas"):
        if not config.ARQUIVO_SOLICITACOES.exists():
            st.caption("Nenhum pedido registrado ainda.")
            return
        try:
            linhas = ler_csv(config.ARQUIVO_SOLICITACOES)
        except ErroBancoAgil as exc:
            st.error(str(exc))
            return
        if not linhas:
            st.caption("Nenhum pedido registrado ainda.")
            return
        st.dataframe(linhas[-12:], use_container_width=True, hide_index=True)
        st.caption(f"{len(linhas)} pedido(s) no arquivo.")


def desenhar_retaguarda(sessao: SessaoAtendimento | None) -> None:
    estado = sessao.estado if sessao else {}

    with st.sidebar:
        ui.marca_console()
        ui.ficha_de_sessao(estado)
        ui.trilho_de_especialidades(estado.get("agente_atual", ""))
        ui.registro_do_turno(st.session_state.get("ferramentas") or [])

        if estado.get("ultimo_status_solicitacao"):
            ui.desfecho_do_pedido(estado["ultimo_status_solicitacao"])

        st.markdown('<div class="ag-rotulo">Dados</div>', unsafe_allow_html=True)
        _clientes_de_teste()
        _solicitacoes_gravadas()

        st.markdown("<div style='height:.9rem'></div>", unsafe_allow_html=True)
        if st.button("Iniciar nova conversa", use_container_width=True):
            reiniciar_sessao()
            st.rerun()


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #
sessao = garantir_sessao()
encerrada = sessao.encerrada if sessao else False

ui.cabecalho(encerrada)
desenhar_retaguarda(sessao)

if erro := st.session_state.get("erro_inicializacao"):
    st.error(erro)
    st.info(
        "Preencha `GOOGLE_API_KEY` no arquivo `.env` com uma chave da Gemini "
        "API (aistudio.google.com/apikey) e clique em **Iniciar nova "
        "conversa**."
    )
    st.stop()

for mensagem in st.session_state.get("historico", []):
    ui.fala(mensagem["papel"], mensagem["texto"])

if encerrada:
    st.info("Atendimento encerrado. Inicie uma nova conversa no painel.")

entrada = st.chat_input(
    "Escreva sua mensagem" if not encerrada else "Atendimento encerrado",
    disabled=encerrada,
)

if entrada:
    st.session_state.historico.append({"papel": "cliente", "texto": entrada})
    ui.fala("cliente", entrada)

    with st.spinner("Consultando..."):
        resposta = sessao.enviar(entrada)

    st.session_state.historico.append({"papel": "agente", "texto": resposta})
    st.session_state.ferramentas = sessao.ferramentas_do_ultimo_turno()
    st.rerun()
