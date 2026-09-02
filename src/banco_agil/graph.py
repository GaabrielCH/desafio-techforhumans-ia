"""Grafo de atendimento (LangGraph).

Topologia:

    entrada -> [agente_atual]
    agente --(pediu ferramenta?)--> ferramentas --> [agente_atual] --> ...
    agente --(respondeu texto)-----> FIM (devolve o turno ao cliente)

Os quatro agentes sao nos irmaos, nao um supervisor com subgrafos. A troca
acontece quando uma ferramenta de handoff altera ``agente_atual`` no estado
e a aresta condicional passa a apontar para outro no. Como o historico de
mensagens e unico e compartilhado, o agente que assume ja tem todo o
contexto - e por isso a transicao e invisivel para o cliente.

Encerramento: quando ``encerrado`` vira True, o agente e chamado uma ultima
vez SEM ferramentas. Assim ele so consegue produzir a despedida em texto, o
que garante que o loop termina.
"""

from __future__ import annotations

import random
import re
import time
from typing import Any, Callable, Iterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from . import config
from .agents.prompts import montar_prompt
from .erros import ErroBancoAgil
from .logging_config import obter_logger
from .state import EstadoAtendimento, estado_inicial
from .tools import FERRAMENTAS_POR_AGENTE, TODAS_FERRAMENTAS

log = obter_logger("grafo")

NO_FERRAMENTAS = "ferramentas"
LIMITE_RECURSAO = 40

_MENSAGEM_FALHA_MODELO = (
    "Desculpe, tive uma instabilidade tecnica agora. Pode repetir, por favor?"
)
_MENSAGEM_LIMITE_TAXA = (
    "Estamos com um volume alto de atendimentos neste momento. "
    "Pode repetir a sua ultima mensagem em alguns instantes, por favor?"
)

# Retentativa do LLM. O free tier da Gemini API limita as requisicoes por
# minuto, e um unico turno do cliente pode gastar tres chamadas (agente ->
# ferramenta -> agente). Sem backoff, um pico normal de uso viraria erro na
# cara do cliente.
MAX_TENTATIVAS_MODELO = 3
ESPERA_MAXIMA_SEGUNDOS = 30.0

_PADRAO_ESPERA_SUGERIDA = re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE)


class ErroLimiteDeTaxa(Exception):
    """Todas as retentativas do provedor se esgotaram por limite de taxa."""


def _e_limite_de_taxa(excecao: BaseException) -> bool:
    """Identifica 429 / RESOURCE_EXHAUSTED sem depender do SDK do provedor."""
    texto = str(excecao)
    return (
        "429" in texto
        or "RESOURCE_EXHAUSTED" in texto
        or "rate limit" in texto.lower()
        or "quota" in texto.lower()
    )


def _espera_sugerida(excecao: BaseException, tentativa: int) -> float:
    """Usa o tempo indicado pela API; senao, backoff exponencial com jitter."""
    encontrado = _PADRAO_ESPERA_SUGERIDA.search(str(excecao))
    if encontrado:
        try:
            return min(float(encontrado.group(1)) + 1.0, ESPERA_MAXIMA_SEGUNDOS)
        except ValueError:
            pass
    return min(2.0**tentativa + random.uniform(0, 1), ESPERA_MAXIMA_SEGUNDOS)


def invocar_modelo(modelo: Any, mensagens: list[Any]) -> AIMessage:
    """Chama o LLM com retentativa para limite de taxa.

    Erros que nao sao de limite de taxa sobem na primeira ocorrencia: nao
    adianta insistir em um prompt invalido ou em uma chave errada.
    """
    ultima: BaseException | None = None

    for tentativa in range(1, MAX_TENTATIVAS_MODELO + 1):
        try:
            return modelo.invoke(mensagens)
        except Exception as exc:  # noqa: BLE001
            if not _e_limite_de_taxa(exc):
                raise
            ultima = exc
            if tentativa == MAX_TENTATIVAS_MODELO:
                break
            espera = _espera_sugerida(exc, tentativa)
            log.warning(
                "Limite de taxa do provedor (tentativa %d/%d). "
                "Aguardando %.1fs.",
                tentativa,
                MAX_TENTATIVAS_MODELO,
                espera,
            )
            time.sleep(espera)

    log.error("Limite de taxa persistente apos %d tentativas.", MAX_TENTATIVAS_MODELO)
    raise ErroLimiteDeTaxa(str(ultima))


def texto_da_mensagem(mensagem: Any) -> str:
    """Extrai o texto de uma mensagem.

    No langchain-core 1.x o ``content`` pode vir como lista de blocos; a
    propriedade ``text`` concatena so as partes textuais. Mantemos o
    fallback para ``content`` porque dublês de teste usam string simples.
    """
    texto = getattr(mensagem, "text", None)
    # A ordem importa: em langchain-core 1.x `text` e uma propriedade que
    # devolve uma str ainda invocavel por compatibilidade, e chama-la emite
    # DeprecationWarning. Testamos str antes de testar callable.
    if isinstance(texto, str):
        return texto.strip()
    if callable(texto):  # versoes antigas em que text() era metodo
        try:
            return str(texto()).strip()
        except Exception:  # noqa: BLE001
            pass

    conteudo = getattr(mensagem, "content", "")
    if isinstance(conteudo, str):
        return conteudo.strip()
    if isinstance(conteudo, list):
        partes = [
            bloco.get("text", "")
            for bloco in conteudo
            if isinstance(bloco, dict) and bloco.get("type") == "text"
        ]
        return "".join(partes).strip()
    return str(conteudo).strip()


def criar_modelo(
    modelo: str | None = None, temperatura: float | None = None
) -> BaseChatModel:
    """Instancia o LLM do Google Gemini.

    Importacao tardia para que os testes de regra de negocio nao dependam
    do pacote do provedor nem de uma chave de API valida.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not config.GOOGLE_API_KEY:
        raise ErroBancoAgil(
            "GOOGLE_API_KEY nao configurada. Copie .env.example para .env e "
            "preencha a chave da Gemini API."
        )

    escolhida = config.TEMPERATURA if temperatura is None else temperatura
    extras = {} if escolhida is None else {"temperature": escolhida}

    return ChatGoogleGenerativeAI(
        model=modelo or config.MODELO,
        google_api_key=config.GOOGLE_API_KEY,
        **extras,
    )


def _criar_no_agente(nome: str, llm: BaseChatModel) -> Callable[[dict], dict]:
    """Cria o no de um agente com o seu proprio prompt e conjunto de tools."""
    ferramentas = FERRAMENTAS_POR_AGENTE[nome]
    llm_com_ferramentas = llm.bind_tools(ferramentas)

    def no(estado: EstadoAtendimento) -> dict[str, Any]:
        # No turno de despedida o agente perde as ferramentas: sobra apenas
        # produzir texto, e o grafo necessariamente termina.
        modelo = llm if estado.get("encerrado") else llm_com_ferramentas

        historico = list(estado.get("messages", []))

        # A saudacao inicial acontece antes de o cliente digitar qualquer
        # coisa, e a API do Gemini recusa uma requisicao sem nenhum turno de
        # usuario ("contents are required"). Esta deixa e so para o modelo:
        # nao entra no estado nem aparece na conversa.
        if not historico:
            historico = [HumanMessage(content="(o cliente acabou de abrir o chat)")]

        mensagens = [
            SystemMessage(content=montar_prompt(nome, dict(estado))),
            *historico,
        ]

        try:
            resposta = invocar_modelo(modelo, mensagens)
        except ErroLimiteDeTaxa:
            log.error("Agente '%s' sem resposta por limite de taxa.", nome)
            resposta = AIMessage(content=_MENSAGEM_LIMITE_TAXA)
        except Exception:  # noqa: BLE001 - falha do provedor nao derruba a UI
            log.exception("Falha ao invocar o modelo no agente '%s'.", nome)
            resposta = AIMessage(content=_MENSAGEM_FALHA_MODELO)

        return {"messages": [resposta], "agente_atual": nome}

    return no


def _rotear_do_agente(estado: EstadoAtendimento) -> str:
    """Se o agente pediu ferramentas, executa-as; senao devolve o turno."""
    mensagens = estado.get("messages", [])
    ultima = mensagens[-1] if mensagens else None
    if isinstance(ultima, AIMessage) and getattr(ultima, "tool_calls", None):
        return NO_FERRAMENTAS
    return END


def _rotear_para_agente(estado: EstadoAtendimento) -> str:
    """Aponta para o agente que estiver no comando do estado."""
    agente = estado.get("agente_atual") or config.AGENTE_TRIAGEM
    if agente not in config.AGENTES:
        log.warning("Agente desconhecido '%s'; voltando para triagem.", agente)
        return config.AGENTE_TRIAGEM
    return agente


def construir_grafo(
    llm: BaseChatModel | None = None,
    checkpointer: Any | None = None,
):
    """Monta e compila o grafo de atendimento."""
    llm = llm or criar_modelo()

    construtor = StateGraph(EstadoAtendimento)

    for agente in config.AGENTES:
        construtor.add_node(agente, _criar_no_agente(agente, llm))

    construtor.add_node(NO_FERRAMENTAS, ToolNode(TODAS_FERRAMENTAS))

    destinos_agentes = {a: a for a in config.AGENTES}

    construtor.add_conditional_edges(START, _rotear_para_agente, destinos_agentes)

    for agente in config.AGENTES:
        construtor.add_conditional_edges(
            agente,
            _rotear_do_agente,
            {NO_FERRAMENTAS: NO_FERRAMENTAS, END: END},
        )

    construtor.add_conditional_edges(
        NO_FERRAMENTAS, _rotear_para_agente, destinos_agentes
    )

    return construtor.compile(checkpointer=checkpointer or MemorySaver())


class SessaoAtendimento:
    """Uma conversa: encapsula grafo, thread e estado.

    Tanto a UI do Streamlit quanto o modo CLI conversam apenas com esta
    classe, o que mantem as interfaces finas e o comportamento identico
    nas duas.
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        thread_id: str = "sessao-local",
        grafo: Any | None = None,
    ) -> None:
        self.grafo = grafo or construir_grafo(llm)
        self.thread_id = thread_id
        self._iniciada = False

    @property
    def _config(self) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": LIMITE_RECURSAO,
        }

    def _entrada(self, texto: str | None) -> dict[str, Any]:
        """Primeira chamada leva o estado inicial; as seguintes, so a mensagem."""
        mensagens = [HumanMessage(content=texto)] if texto else []

        if not self._iniciada:
            self._iniciada = True
            estado = estado_inicial()
            estado["messages"] = mensagens
            return estado

        return {"messages": mensagens}

    def iniciar(self) -> str:
        """Dispara a saudacao inicial, sem nenhuma mensagem do cliente."""
        return self.enviar(None)

    def enviar(self, texto: str | None) -> str:
        """Processa um turno e devolve a resposta em texto ao cliente."""
        try:
            resultado = self.grafo.invoke(self._entrada(texto), self._config)
        except Exception:  # noqa: BLE001 - a UI nunca deve quebrar
            log.exception("Falha ao processar o turno do atendimento.")
            return _MENSAGEM_FALHA_MODELO

        return self._texto_final(resultado)

    def transmitir(self, texto: str | None) -> Iterator[str]:
        """Versao incremental de ``enviar``, para UIs que mostram progresso."""
        try:
            for evento in self.grafo.stream(
                self._entrada(texto), self._config, stream_mode="values"
            ):
                mensagens = evento.get("messages", [])
                if not mensagens:
                    continue
                ultima = mensagens[-1]
                if isinstance(ultima, AIMessage) and not getattr(
                    ultima, "tool_calls", None
                ):
                    conteudo = texto_da_mensagem(ultima)
                    if conteudo:
                        yield conteudo
        except Exception:  # noqa: BLE001
            log.exception("Falha ao transmitir o turno do atendimento.")
            yield _MENSAGEM_FALHA_MODELO

    @staticmethod
    def _texto_final(resultado: dict[str, Any]) -> str:
        """Extrai a ultima fala do agente, ignorando chamadas de ferramenta."""
        for mensagem in reversed(resultado.get("messages", [])):
            if isinstance(mensagem, AIMessage):
                conteudo = texto_da_mensagem(mensagem)
                if conteudo:
                    return conteudo
        return _MENSAGEM_FALHA_MODELO

    def ferramentas_do_ultimo_turno(self) -> list[str]:
        """Ferramentas acionadas desde a ultima fala do cliente.

        Existe para a UI de avaliacao: permite ver o handoff acontecendo no
        painel lateral enquanto o chat continua costurado, sem nenhuma pista
        da transicao. E leitura do estado, nao instrumentacao do fluxo.
        """
        mensagens = self.estado.get("messages", [])

        inicio = 0
        for indice in range(len(mensagens) - 1, -1, -1):
            if isinstance(mensagens[indice], HumanMessage):
                inicio = indice
                break

        nomes: list[str] = []
        for mensagem in mensagens[inicio:]:
            for chamada in getattr(mensagem, "tool_calls", None) or []:
                nome = chamada.get("name") if isinstance(chamada, dict) else None
                if nome:
                    nomes.append(nome)
        return nomes

    @property
    def estado(self) -> dict[str, Any]:
        """Estado atual persistido no checkpointer."""
        try:
            snapshot = self.grafo.get_state(self._config)
            return dict(snapshot.values or {})
        except Exception:  # noqa: BLE001
            log.exception("Falha ao ler o estado da sessao.")
            return {}

    @property
    def encerrada(self) -> bool:
        return bool(self.estado.get("encerrado"))
