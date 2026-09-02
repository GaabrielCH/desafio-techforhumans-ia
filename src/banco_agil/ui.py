"""Identidade visual da interface.

A tela tem dois publicos ao mesmo tempo: o cliente, que ve uma conversa de
banco, e quem avalia, que precisa ver a maquina por tras. Em vez de esconder
essa dualidade, o design a assume - dois registros visuais no mesmo ecra:

- **Vitrine** (area principal): papel frio, tipografia humanista, balões
  arredondados. E o que o cliente veria no app do banco.
- **Retaguarda** (painel lateral): fundo petroleo, tipografia monoespacada,
  dados alinhados. E o console de quem opera o sistema.

O elemento de assinatura e o *trilho de especialidades*: quatro paradas onde
so a ativa acende. Nao e enfeite - codifica o roteamento entre agentes, que e
a tese da arquitetura, e deixa o handoff visivel para quem avalia enquanto o
chat continua costurado para o cliente.
"""

from __future__ import annotations

import html
import re

import streamlit as st

from . import config

# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
TINTA = "#08302F"       # petroleo: marca, retaguarda, fala do cliente
PAPEL = "#EDF1EF"       # papel frio: fundo da vitrine
CARTAO = "#FFFFFF"      # fala do atendente
OURO = "#E8A33D"        # acento: o "agil". So em estado ativo.
VERDE = "#0E9F6E"       # exclusivo de aprovado
RUBRO = "#C2410C"       # exclusivo de recusa / atencao
CINZA = "#5B6F6D"       # texto de apoio

_FONTES = (
    "https://fonts.googleapis.com/css2"
    "?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800"
    "&family=Instrument+Sans:wght@400;500;600"
    "&family=JetBrains+Mono:wght@400;500;700"
    "&display=swap"
)

CSS = f"""
<style>
@import url('{_FONTES}');

:root {{
  --tinta: {TINTA};
  --papel: {PAPEL};
  --cartao: {CARTAO};
  --ouro: {OURO};
  --verde: {VERDE};
  --rubro: {RUBRO};
  --cinza: {CINZA};
  --display: 'Bricolage Grotesque', 'Segoe UI', sans-serif;
  --corpo: 'Instrument Sans', 'Segoe UI', sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, 'Consolas', monospace;
}}

/* ---------- base ---------- */
html, body, [data-testid="stAppViewContainer"] {{
  background: var(--papel);
  font-family: var(--corpo);
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem; max-width: 46rem; }}
#MainMenu, footer {{ visibility: hidden; }}

/* ---------- cabecalho da vitrine ---------- */
.ag-topo {{
  display: flex; align-items: center; gap: .85rem;
  padding-bottom: 1rem; margin-bottom: 1.6rem;
  border-bottom: 1px solid rgba(8,48,47,.12);
}}
.ag-marca {{
  width: 40px; height: 40px; border-radius: 11px; flex: 0 0 auto;
  background: var(--tinta); display: grid; place-items: center;
}}
.ag-marca svg {{ display: block; }}
.ag-titulo {{ display: flex; flex-direction: column; line-height: 1.15; }}
.ag-nome {{
  font-family: var(--display); font-weight: 800; font-size: 1.24rem;
  color: var(--tinta); letter-spacing: -.02em;
}}
.ag-tagline {{
  font-family: var(--corpo); font-size: .78rem; color: var(--cinza);
}}
.ag-selo {{
  margin-left: auto; font-family: var(--corpo); font-size: .76rem;
  font-weight: 500; padding: .3rem .7rem; border-radius: 999px;
  background: rgba(14,159,110,.12); color: var(--verde);
  border: 1px solid rgba(14,159,110,.28); white-space: nowrap;
}}
.ag-selo[data-fim="1"] {{
  background: rgba(91,111,109,.12); color: var(--cinza);
  border-color: rgba(91,111,109,.28);
}}

/* ---------- falas ---------- */
.ag-fala {{ margin: 0 0 1.05rem; display: flex; flex-direction: column; }}
.ag-quem {{
  font-family: var(--corpo); font-weight: 500; font-size: .74rem;
  color: var(--cinza); margin-bottom: .32rem;
}}
.ag-balao {{
  padding: .78rem 1rem; font-size: .95rem; line-height: 1.55;
  max-width: 88%; width: fit-content;
}}
.ag-fala.agente .ag-balao {{
  background: var(--cartao); color: #10312F;
  border-radius: 4px 15px 15px 15px;
  border: 1px solid rgba(8,48,47,.10);
  box-shadow: 0 1px 2px rgba(8,48,47,.05);
}}
.ag-fala.cliente {{ align-items: flex-end; }}
.ag-fala.cliente .ag-balao {{
  background: var(--tinta); color: #EAF3F1;
  border-radius: 15px 4px 15px 15px;
}}
.ag-balao strong {{ font-weight: 600; }}
.ag-balao .ag-valor {{ font-family: var(--mono); font-weight: 500; }}

/* ---------- campo de entrada ---------- */
[data-testid="stBottomBlockContainer"] {{ background: var(--papel); }}
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stChatInputContainer"] {{
  background: var(--cartao) !important;
  border-radius: 14px;
}}
[data-testid="stChatInput"] {{ border: 1px solid rgba(8,48,47,.16); }}
[data-testid="stChatInput"] textarea {{
  font-family: var(--corpo); font-size: .95rem;
  color: #0B1F1E !important; background: transparent !important;
}}
[data-testid="stChatInput"] textarea::placeholder {{
  color: #7C918F !important; opacity: 1;
}}
[data-testid="stChatInput"] button {{ color: var(--tinta) !important; }}
[data-testid="stChatInput"] button svg {{ fill: var(--tinta); }}

/* ---------- retaguarda ---------- */
[data-testid="stSidebar"] {{ background: var(--tinta); }}
[data-testid="stSidebar"] * {{ color: #CFE0DD; }}
[data-testid="stSidebarContent"] {{ padding-top: 1.4rem; }}

.ag-console {{
  font-family: var(--display); font-weight: 600; font-size: .92rem;
  letter-spacing: -.01em; color: #EAF3F1;
  padding-bottom: .7rem; margin-bottom: 1.2rem;
  border-bottom: 1px solid rgba(207,224,221,.14);
}}
.ag-console span {{
  display: block; font-family: var(--corpo); font-weight: 400;
  font-size: .74rem; color: rgba(207,224,221,.5); margin-top: .1rem;
}}

.ag-rotulo {{
  font-family: var(--corpo); font-weight: 500; font-size: .74rem;
  color: rgba(207,224,221,.5); margin: 1.5rem 0 .6rem;
}}

/* trilho de especialidades: a assinatura */
.ag-trilho {{ list-style: none; margin: 0; padding: 0; }}
.ag-parada {{
  position: relative; padding: 0 0 .85rem 1.5rem;
  font-family: var(--corpo); font-size: .92rem; font-weight: 400;
  color: rgba(207,224,221,.45);
}}
.ag-parada::before {{           /* a parada */
  content: ""; position: absolute; left: 0; top: .38rem;
  width: 8px; height: 8px; border-radius: 50%;
  border: 1.5px solid rgba(207,224,221,.3); background: var(--tinta);
  transition: background .2s ease, box-shadow .2s ease;
}}
.ag-parada::after {{            /* o trilho que liga */
  content: ""; position: absolute; left: 3.5px; top: 1.15rem;
  width: 1.5px; height: calc(100% - 1rem);
  background: rgba(207,224,221,.14);
}}
.ag-parada:last-child {{ padding-bottom: 0; }}
.ag-parada:last-child::after {{ display: none; }}
.ag-parada[data-ativa="1"] {{ color: var(--ouro); font-weight: 600; }}
.ag-parada[data-ativa="1"]::before {{
  background: var(--ouro); border-color: var(--ouro);
  box-shadow: 0 0 0 3.5px rgba(232,163,61,.16);
}}

/* registro de ferramentas do turno */
.ag-registro {{ margin: 0; padding: 0; list-style: none; }}
.ag-registro li {{
  font-family: var(--corpo); font-size: .82rem; line-height: 1.45;
  color: rgba(207,224,221,.82);
  padding: .4rem .6rem .4rem .7rem; border-left: 2px solid var(--ouro);
  margin-bottom: .3rem; background: rgba(232,163,61,.06);
  border-radius: 0 6px 6px 0;
}}
.ag-vazio {{
  font-family: var(--corpo); font-size: .8rem;
  color: rgba(207,224,221,.35);
}}

/* ficha de sessao */
.ag-ficha {{
  border: 1px solid rgba(207,224,221,.16); border-radius: 8px;
  padding: .7rem .8rem; margin-bottom: .3rem;
}}
.ag-ficha[data-estado="autenticado"] {{
  border-color: rgba(14,159,110,.45); background: rgba(14,159,110,.09);
}}
.ag-ficha[data-estado="pendente"] {{
  border-color: rgba(232,163,61,.4); background: rgba(232,163,61,.07);
}}
.ag-ficha-quem {{
  font-family: var(--display); font-weight: 600; font-size: .95rem;
  color: #EAF3F1; letter-spacing: -.01em;
}}
.ag-ficha-nota {{
  font-family: var(--corpo); font-size: .78rem;
  color: rgba(207,224,221,.6); margin-top: .18rem;
}}

/* medidor de tentativas */
.ag-tentativas {{ display: flex; gap: 4px; margin-top: .45rem; }}
.ag-tentativas span {{
  height: 3px; flex: 1; border-radius: 2px;
  background: rgba(207,224,221,.18);
}}
.ag-tentativas span[data-usada="1"] {{ background: var(--rubro); }}

/* desfecho do pedido */
.ag-desfecho {{
  font-family: var(--corpo); font-weight: 500; font-size: .82rem;
  padding: .4rem .75rem; border-radius: 6px; display: inline-block;
}}
.ag-desfecho[data-status="aprovado"] {{
  background: rgba(14,159,110,.16); color: #6FE7BC;
}}
.ag-desfecho[data-status="rejeitado"] {{
  background: rgba(194,65,12,.18); color: #F5A97A;
}}
.ag-desfecho[data-status="pendente"] {{
  background: rgba(232,163,61,.16); color: var(--ouro);
}}

/* widgets do Streamlit dentro da retaguarda */
[data-testid="stSidebar"] [data-testid="stExpander"] details {{
  background: rgba(255,255,255,.04); border: 1px solid rgba(207,224,221,.14);
  border-radius: 8px;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{
  font-family: var(--corpo) !important; font-size: .85rem !important;
  font-weight: 500;
}}
[data-testid="stSidebar"] .stButton button {{
  background: transparent; color: var(--ouro);
  border: 1px solid rgba(232,163,61,.45); border-radius: 8px;
  font-family: var(--corpo); font-size: .85rem; font-weight: 500;
  transition: background .15s ease;
}}
[data-testid="stSidebar"] .stButton button:hover {{
  background: rgba(232,163,61,.12); border-color: var(--ouro);
  color: var(--ouro);
}}

/* acessibilidade */
:focus-visible {{ outline: 2px solid var(--ouro); outline-offset: 2px; }}
@media (prefers-reduced-motion: reduce) {{
  * {{ animation: none !important; transition: none !important; }}
}}
@media (max-width: 640px) {{
  .ag-balao {{ max-width: 100%; }}
}}
</style>
"""

# Marca: dupla seta para a frente - "agil". Geometrica, sem gradiente.
_MARCA_SVG = f"""
<svg width="21" height="21" viewBox="0 0 24 24" fill="none"
     aria-hidden="true">
  <path d="M4 5.5 L11 12 L4 18.5" stroke="{OURO}" stroke-width="2.6"
        stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M13 5.5 L20 12 L13 18.5" stroke="#EAF3F1" stroke-width="2.6"
        stroke-linecap="round" stroke-linejoin="round" opacity=".55"/>
</svg>
"""

ORDEM_ESPECIALIDADES = (
    (config.AGENTE_TRIAGEM, "Triagem"),
    (config.AGENTE_CREDITO, "Crédito"),
    (config.AGENTE_ENTREVISTA, "Entrevista"),
    (config.AGENTE_CAMBIO, "Câmbio"),
)

ROTULOS_FERRAMENTA = {
    "autenticar_cliente": "autenticou o cliente",
    "consultar_limite_credito": "consultou limite e score",
    "solicitar_aumento_limite": "registrou e analisou o pedido",
    "realizar_entrevista_credito": "recalculou o score",
    "consultar_cotacao_moeda": "consultou a cotação",
    "direcionar_para_credito": "→ passou para Crédito",
    "direcionar_para_cambio": "→ passou para Câmbio",
    "direcionar_para_entrevista": "→ passou para Entrevista",
    "encerrar_atendimento": "encerrou o atendimento",
}


# --------------------------------------------------------------------------- #
# Renderizacao
# --------------------------------------------------------------------------- #
def aplicar_estilo() -> None:
    """Injeta a folha de estilo uma vez por execucao do script."""
    st.markdown(CSS, unsafe_allow_html=True)


def formatar_para_html(texto: str) -> str:
    """Escapa o texto e devolve so a formatacao que decidimos permitir.

    O conteudo vem do cliente e do modelo, e vai para dentro de HTML: escapar
    e obrigatorio. Depois de escapado, reintroduzimos apenas negrito e quebra
    de linha - qualquer marcacao que o modelo tenha escrito ja virou texto
    inofensivo nesse ponto.
    """
    seguro = html.escape(str(texto or ""))
    seguro = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", seguro)
    seguro = re.sub(
        r"(R\$\s?[\d.,]+)", r'<span class="ag-valor">\1</span>', seguro
    )
    return seguro.replace("\n", "<br>")


def cabecalho(encerrado: bool) -> None:
    """Marca do banco e situacao do atendimento."""
    selo = "atendimento encerrado" if encerrado else "atendimento aberto"
    st.markdown(
        f"""
        <div class="ag-topo">
          <div class="ag-marca">{_MARCA_SVG}</div>
          <div class="ag-titulo">
            <span class="ag-nome">Banco Ágil</span>
            <span class="ag-tagline">Atendimento digital</span>
          </div>
          <span class="ag-selo" data-fim="{int(encerrado)}">{selo}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fala(papel: str, texto: str) -> None:
    """Uma fala do chat. `papel` e 'agente' ou 'cliente'."""
    quem = "Ágil" if papel == "agente" else "Você"
    st.markdown(
        f'<div class="ag-fala {papel}">'
        f'<span class="ag-quem">{quem}</span>'
        f'<div class="ag-balao">{formatar_para_html(texto)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def marca_console() -> None:
    st.markdown(
        '<div class="ag-console">Painel do atendimento'
        "<span>o que o cliente não vê</span></div>",
        unsafe_allow_html=True,
    )


def ficha_de_sessao(estado: dict) -> None:
    """Quem esta do outro lado e quantas tentativas restam."""
    if estado.get("autenticado"):
        st.markdown(
            f'<div class="ag-ficha" data-estado="autenticado">'
            f'<div class="ag-ficha-quem">{html.escape(str(estado.get("nome") or ""))}</div>'
            f'<div class="ag-ficha-nota">identidade confirmada</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    usadas = int(estado.get("tentativas_autenticacao", 0))
    total = config.MAX_TENTATIVAS_AUTENTICACAO
    marcas = "".join(
        f'<span data-usada="{int(i < usadas)}"></span>' for i in range(total)
    )
    st.markdown(
        f'<div class="ag-ficha" data-estado="pendente">'
        f'<div class="ag-ficha-quem">Não identificado</div>'
        f'<div class="ag-ficha-nota">tentativas {usadas} de {total}</div>'
        f'<div class="ag-tentativas">{marcas}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def trilho_de_especialidades(agente_atual: str) -> None:
    """A assinatura: as quatro paradas, com a ativa acesa."""
    st.markdown('<div class="ag-rotulo">Especialidade ativa</div>',
                unsafe_allow_html=True)
    paradas = "".join(
        f'<li class="ag-parada" data-ativa="{int(chave == agente_atual)}">'
        f"{rotulo}</li>"
        for chave, rotulo in ORDEM_ESPECIALIDADES
    )
    st.markdown(f'<ul class="ag-trilho">{paradas}</ul>', unsafe_allow_html=True)


def registro_do_turno(ferramentas: list[str]) -> None:
    """O que o sistema fez desde a ultima mensagem do cliente."""
    st.markdown('<div class="ag-rotulo">No último turno</div>',
                unsafe_allow_html=True)

    if not ferramentas:
        st.markdown(
            '<div class="ag-vazio">nenhuma ferramenta acionada</div>',
            unsafe_allow_html=True,
        )
        return

    itens = "".join(
        f"<li>{html.escape(ROTULOS_FERRAMENTA.get(nome, nome))}</li>"
        for nome in ferramentas
    )
    st.markdown(f'<ul class="ag-registro">{itens}</ul>', unsafe_allow_html=True)


def desfecho_do_pedido(status: str) -> None:
    st.markdown('<div class="ag-rotulo">Último pedido</div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<span class="ag-desfecho" data-status="{html.escape(status)}">'
        f"{html.escape(status)}</span>",
        unsafe_allow_html=True,
    )
