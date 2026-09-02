# 🔁 HANDOFF — Estado do Projeto "Banco Ágil"

> Documento de contexto para retomar este projeto em outra sessão/chat.
> Última atualização: **02/09/2026**.
> Para a documentação de entrega (avaliador), leia o [README.md](README.md).
> Este arquivo é o complemento honesto: o que está pronto, o que não está,
> o que quebrou no caminho e o que ficou de dívida.

---

## 1. TL;DR do estado atual

| Item | Situação |
|---|---|
| Backend / agentes | ✅ Completo e verificado contra o Gemini real |
| **Frontend (Streamlit)** | ✅ **Feito** — `app.py`, 188 linhas, com testes de fumaça |
| CLI alternativa | ✅ Feita (`main.py`) — ⚠️ não exercitada interativamente |
| Testes | ✅ 148 passando, sem chave de API e sem rede |
| README de entrega | ✅ Completo, com todas as seções obrigatórias |
| Git | ✅ 3 commits locais |
| **Push para o GitHub** | ❌ **Não feito** — pendente, exige auth do usuário |
| **Revogar a chave de API** | ❌ **Pendente e importante** (ver §7) |

**Desafio:** sistema de atendimento bancário com 4 agentes de IA
(Triagem, Crédito, Entrevista de Crédito, Câmbio) que se revezam sem que o
cliente perceba a transição.

**Stack:** Python 3.10 · LangGraph 1.2 · langchain-core 1.6 ·
`langchain-google-genai` 4.4 · Streamlit 1.63 · Gemini · pytest.

---

## 2. Como retomar em 30 segundos

```bash
cd desafio-techforhumans-ia
.venv\Scripts\activate          # o venv já existe na máquina do usuário
pytest                          # 148 testes, ~6s, não precisa de chave
streamlit run app.py            # UI em http://localhost:8501
python main.py --debug          # CLI mostrando o agente ativo por turno
```

`.env` já existe localmente com a chave (fora do Git). O modelo padrão é
`gemini-3.1-flash-lite`.

---

## 3. Arquitetura em uma tela

Os quatro agentes são **nós irmãos de um mesmo grafo LangGraph** — não há
supervisor. Quem responde é decidido pelo campo `agente_atual` do estado,
por uma função Python determinística (sem gastar uma chamada de LLM só para
rotear).

```
START ──> {agente_atual?} ──> [triagem | credito | entrevista | cambio]
                                        │
                        pediu ferramenta?│
                          ┌──────────────┴──────────────┐
                         sim                           não
                          │                             │
                    [nó de ferramentas]              FIM (responde)
                          │
        handoff troca `agente_atual` ──> volta para {agente_atual?}
```

### Os três mecanismos que sustentam o desafio

1. **Handoff implícito.** A ferramenta de redirecionamento *só altera o
   estado* — não gera texto para o cliente. Como o histórico de mensagens é
   único e compartilhado, o agente que assume já tem todo o contexto e
   simplesmente continua falando.
2. **Escopo garantido por código.** Cada agente recebe apenas o seu conjunto
   de ferramentas (`tools/__init__.py`). Mesmo que o prompt falhe, o Agente
   de Câmbio não tem como alterar um limite de crédito.
3. **`autenticado` vive no estado, não no prompt.** As ferramentas sensíveis
   leem esse campo direto e recusam a execução se for falso — o modelo não
   consegue "alucinar" uma autenticação.

### Camadas

```
src/banco_agil/
├── config.py          # caminhos, modelo, pesos do score (tudo ajustável aqui)
├── state.py           # EstadoAtendimento (TypedDict)
├── graph.py           # grafo + retentativa + SessaoAtendimento  ← 359 linhas
├── erros.py           # exceções de domínio
├── utils.py           # normalização de CPF/data/valor em texto livre
├── agents/prompts.py  # persona única + escopo por agente
├── tools/             # ferramentas (triagem, credito, entrevista, cambio,
│                      #   handoff, comuns)
├── services/          # regra de negócio PURA — não conhece LLM nem LangGraph
└── repositories/      # CSV com escrita atômica (os.replace) + RLock por arquivo
```

`SessaoAtendimento` (em `graph.py`) é a **única** porta de entrada: tanto a UI
quanto a CLI só falam com ela. Por isso as duas interfaces são finas e se
comportam igual.

---

## 4. Frontend — o que existe (respondendo à dúvida)

**Sim, o frontend está feito.** `app.py`, Streamlit:

- Chat com histórico (`st.chat_message` / `st.chat_input`)
- Saudação inicial disparada automaticamente ao abrir
- Barra lateral com o que o cliente **não** vê:
  - estado de autenticação (e tentativas usadas / 3)
  - **especialidade ativa** (Triagem / Crédito / Entrevista / Câmbio)
  - status do último pedido de aumento
  - tabela de clientes de teste
  - conteúdo ao vivo de `solicitacoes_aumento_limite.csv`
- Botão "Nova conversa"
- `chat_input` desabilitado quando o atendimento encerra
- Caminho de erro amigável quando falta `GOOGLE_API_KEY` (orienta o avaliador
  em vez de estourar traceback)

**Verificado com `streamlit.testing.v1.AppTest`** (5 testes), usando um LLM
dublê — servir o HTML não prova nada, porque o Streamlit devolve a casca da
página mesmo quando o script quebra.

---

## 5. Decisões técnicas e o porquê

| Decisão | Motivo |
|---|---|
| **LangGraph** em vez de CrewAI/AutoGen | O desafio é uma máquina de estados com handoffs. LangGraph modela isso direto (estado tipado + arestas condicionais + checkpointer). |
| **Agentes irmãos, sem supervisor** | Um supervisor custaria uma chamada de LLM por turno só para rotear. `agente_atual` já está no estado → roteamento é código. |
| **`gemini-3.1-flash-lite`** | Modelo mais barato que sustenta o tool calling deste fluxo. Um turno custa 2–3 chamadas, então isso importa. Validado contra `gemini-3.5-flash`: desfecho idêntico nos 4 roteiros. |
| **Cálculo de score fora do LLM** | Score é dinheiro. A fórmula vive em `services/score.py`, determinística e auditável; o LLM só coleta as respostas. |
| **AwesomeAPI para cotação** | Não exige chave — o avaliador roda sem cadastrar mais uma credencial — e devolve o par já convertido, sem precisar de LLM para interpretar busca. |
| **Escrita atômica + `RLock`** | A base é reescrita inteira quando o score muda; gravar direto perderia tudo se o processo morresse no meio. O Streamlit atende cada sessão em uma thread. |
| **Testes com LLM dublê** | 148 testes rodam sem chave e sem rede. Não se testa o texto do modelo, e sim o que precisa valer sempre: bloqueio antes da autenticação, limite de 3 tentativas, handoff, terminação do loop. |
| **Temperatura opcional** | Gemini 3.x usa amostragem fixa e emite warning se `temperature` for enviada. `BANCO_AGIL_TEMPERATURA` vazio → parâmetro omitido. |

---

## 6. Bugs reais encontrados e corrigidos

Todos foram descobertos **executando**, não lendo o código.

### 6.1 Solicitações no mesmo segundo se sobrescreviam 🔴 grave
O desafio fixa as 5 colunas do CSV, então não há `id` próprio e o pedido é
identificado por `(cpf, data_hora)`. Com timestamp em **segundos**, o fluxo
"rejeitado → entrevista → aprovado" gravava os dois pedidos com a mesma
chave, e o segundo `update` encontrava a **primeira** linha e reescrevia o
desfecho do pedido anterior. Resultado: `['aprovado','pendente']` em vez de
`['rejeitado','aprovado']`.
**Correção:** timestamp em milissegundos **+** varredura de trás para frente
no `atualizar_status` (o arquivo só cresce por append, então a linha nova é
sempre a última com aquela chave). Tem teste de regressão que força
timestamps idênticos.

### 6.2 Aprovação que não se sustentava 🟠
O agente dizia "seu novo limite é R$ 10.000,00" mas `clientes.csv` continuava
com R$ 5.000,00 — uma segunda consulta na mesma conversa se contradiria.
**Correção:** aprovar passou a efetivar o limite na base. O desafio não pede
isso explicitamente; sem isso o sistema mente para o cliente.

### 6.3 Saudação inicial quebrava a API 🟠
`ValueError: contents are required` ao abrir o chat — a saudação acontece
antes de o cliente digitar, e o Gemini recusa requisição só com mensagem de
sistema.
**Correção:** o nó injeta uma deixa sintética (`"(o cliente acabou de abrir o
chat)"`) **apenas na chamada ao modelo**; não entra no estado nem na conversa.

### 6.4 Rate limit do free tier 🟡
Um turno custa 2–3 chamadas. Sem backoff, conversa longa entregava erro na
cara do cliente.
**Correção:** retentativa que **lê o tempo sugerido pela própria API**
(`"Please retry in 15.02s"`), teto de 30s, jitter, 3 tentativas. Erros que
não são de limite de taxa sobem na primeira ocorrência.

### 6.5 Modelo vazava rubrica 🟡
No fluxo de 3 falhas de autenticação o modelo assinava
`"(Encerrando atendimento)"` ao final — mecânica interna vazando pro cliente.
**Correção:** regra 9 no prompt base proibindo rubrica/narração.

### 6.6 `gemini-2.5-flash` aposentado 🟡
Retorna 404 para contas novas. Migrado para a família Gemini 3.

---

## 7. ⚠️ Ressalvas e pendências

### 7.1 A chave de API precisa ser revogada — **prioridade**
A chave foi colada em texto plano no chat de desenvolvimento. Está em `.env`
(fora do Git; confirmado zero ocorrências nos commits), **mas deve ser
revogada e regerada** em https://aistudio.google.com/apikey antes de tornar
o repositório público.

### 7.2 Push para o GitHub não foi feito
3 commits locais. Para publicar:
```bash
gh repo create desafio-techforhumans-ia --public --source=. --push
```

### 7.3 CLI não exercitada interativamente
`main.py` roda o mesmo `SessaoAtendimento` que a UI e os testes cobrem, mas
o loop interativo em si não foi rodado ponta a ponta. Risco baixo, mas é uma
verificação que falta.

### 7.4 Free tier é apertado para conversas longas
O limite de requisições por minuto é **por modelo**. Na medição do
desenvolvimento, `gemini-3.6-flash` cortava em 20/min. Uma conversa de 12
turnos chegou a levar ~40 min por causa dos backoffs acumulados. Para uma
demo ao vivo, convém ter uma chave com billing ativo ou usar roteiros curtos.

### 7.5 Autenticação não é segurança real
CPF + data de nascimento é o que o enunciado pede. Não há hash, rate limiting
por CPF, nem proteção contra enumeração. Adequado ao escopo do desafio,
inadequado para produção.

### 7.6 Estado em memória
Usa `MemorySaver`. Reiniciar o processo perde as conversas em andamento
(os CSVs persistem). Para produção: `SqliteSaver` ou `PostgresSaver`.

### 7.7 Concorrência entre processos
O `RLock` protege threads **do mesmo processo**. Duas instâncias do Streamlit
sobre os mesmos CSVs ainda podem se atropelar. Precisaria de lock de arquivo
no SO (`portalocker`) ou de um banco de verdade.

### 7.8 Números por extenso não são convertidos
`normalizar_inteiro_nao_negativo("dois")` falha de propósito — a conversão
fica a cargo do LLM, que normalmente já manda `2`. Se aparecer na prática,
o agente refaz a pergunta em vez de errar silenciosamente. Documentado em
teste.

---

## 8. Ideias de próximos passos (nenhuma é bloqueante)

- [ ] Rodar `main.py` interativamente para fechar a lacuna de §7.3
- [ ] `SqliteSaver` no lugar do `MemorySaver` (persistir conversas)
- [ ] Streaming token a token na UI — `SessaoAtendimento.transmitir()` **já
      existe**, a UI só não usa
- [ ] Histórico de solicitações do cliente exposto como ferramenta
      ("já pedi aumento antes?") — o repositório já tem `listar_por_cpf`
- [ ] Métricas de atendimento (tempo por turno, taxa de aprovação)
- [ ] Dockerfile

---

## 9. Mapa de testes (148)

| Arquivo | Testes | Cobre |
|---|---|---|
| `test_utils.py` | 52 | Normalização de CPF, data, valor monetário BR, sim/não, emprego |
| `test_credito.py` | 21 | Política de score→limite, ciclo do pedido, colunas do CSV, regressão do §6.1 |
| `test_cambio.py` | 19 | API mockada: sucesso, 404, 5xx, timeout, retentativa, formato inesperado |
| `test_score.py` | 17 | Fórmula, pesos, truncamento 0–1000, divisão por zero |
| `test_grafo.py` | 12 | Autenticação, 3 tentativas, bloqueio pré-auth, handoff, encerramento, resiliência |
| `test_autenticacao.py` | 11 | Base ausente/corrompida, linha ruim não derruba a base |
| `test_retentativa.py` | 11 | Backoff, teto, tempo sugerido pela API, erro não-429 sobe na hora |
| `test_ui.py` | 5 | Streamlit `AppTest`: página carrega, saudação, sidebar, envio, sem-chave |

Nenhum precisa de chave de API ou rede.

---

## 10. Verificação feita contra o Gemini real

Os 4 roteiros do README foram executados de verdade (não só mockados), sobre
**cópias** dos CSVs (via `BANCO_AGIL_DIR_DADOS`), para não sujar a base:

| Roteiro | Resultado |
|---|---|
| **A** — consulta + aumento aprovado | ✅ Handoff invisível: autenticou e informou o limite **na mesma resposta** |
| **B** — rejeitado → entrevista → aprovado | ✅ 2 linhas no CSV (`rejeitado`, `aprovado`), score 250→680, limite efetivado |
| **C** — 3 falhas de autenticação | ✅ Encerrou cordialmente, sem revelar qual campo errou |
| **D** — câmbio + fora de escopo | ✅ Bloqueou antes da auth, cotou euro ao vivo, recusou Pix |

O roteiro B foi validado em **dois modelos** (`gemini-3.5-flash` e
`gemini-3.1-flash-lite`) com desfecho idêntico.

---

## 11. Armadilhas do ambiente (Windows / PowerShell 5.1)

- **`Get-Content | Set-Content` corrompe arquivos UTF-8 sem BOM.** Sem
  `-Encoding utf8` na leitura, o PS assume ANSI e `á` vira `Ã¡`. Isso
  **corrompeu o README** durante o desenvolvimento (recuperado com
  `git checkout -- README.md`). Para editar texto: use a ferramenta de edição,
  ou `[System.IO.File]::ReadAllText/WriteAllText` com encoding explícito.
- **Aspas somem em `python -c` via PowerShell.** Escreva um `.py` temporário
  em vez de passar código inline.
- **Heredoc (`<<'EOF'`) não existe no PowerShell.** Para mensagem de commit
  multilinha, use `git commit -F arquivo.txt`.
- `Select-Object -First N` no fim de um pipe longo gera **exit code 255**
  (broken pipe) — não é falha real do comando.

---

## 12. Prompt sugerido para retomar em outro chat

```
Estou retomando o projeto "Banco Ágil" (desafio técnico de agentes de IA),
em c:\Users\gabri\.vscode\desafio-techforhumans-ia.

Leia HANDOFF.md e README.md antes de qualquer coisa.

Estado: backend, frontend Streamlit e 148 testes prontos e verificados
contra o Gemini real. 3 commits locais, sem push.

O que eu quero fazer agora: <descreva a tarefa>
```
