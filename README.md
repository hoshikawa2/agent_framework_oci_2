# Tutorial — Implementation of an Agent using `agent_template_backend`

This tutorial teaches how to implement a new agent from `agent_template_backend`, using the framework as enterprise execution engine.

The central idea is simple:

```text
Framework = reusable engine
Agent = specific business logic
MCP Server = standardized boundary with external systems
Config YAML = configurable behavior without recompiling code
IC/NOC/GRL = business traceability, operation and governance
```

![img_1.png](img_1.png)

The goal is that each new agent implements only its domain logic — prompts, business rules, tools, schemas and specific nodes — without recreating engines that already belong to the framework.

---

## 1. Overview of architecture

The template separates what is generic from what is specific.

```text
agent_template_backend/
├── app/
│   ├── main.py                    # FastAPI API, gateway, session, SSE and workflow entry
│   ├── state.py                   # LangGraph Shared Status Agreement
│   ├── workflows/
│   │   └── agent_graph.py          # Corporate workflow with router, guardrails, agents, judges and persistence
│   ├── agents/
│   │   ├── runtime.py              # Common resources for agents: MCP, RAG, cache, IC, LLM
│   │   ├── billing_agent.py        # Example of invoice agent
│   │   ├── product_agent.py        # Example of product agent
│   │   ├── orders_agent.py         # Example of application agent
│   │   └── support_agent.py        # Example of support agent
│   └── examples/                  # Examples of IC, NOC, GRL, MCP and observer
├── config/
│   ├── agents.yaml                # Registration of available agents
│   ├── routing.yaml               # Intents, keywords, fallback and route decision
│   ├── tools.yaml                 # Catalog of tools available for the backend
│   ├── mcp_servers.yaml           # Local MCP endpoints
│   ├── mcp_servers.docker.yaml    # MCP Endpoints in Docker Compose
│   ├── mcp_parameter_mapping.yaml # Mapping between canonical keys and tool parameters
│   ├── identity.yaml              # Business identity resolution
│   ├── guardrails.yaml            # Global Guardrails
│   ├── judges.yaml                # Global Judges
│   ├── prompt_policy.yaml         # Global prompt policy
│   └── agents/<agent_id>/         # Agent isolated settings
├── data/
│   └── agent_framework.db         # Local example database, where applicable
├── Dockerfile
├── requirements.txt
└── .env                           # Local Settings
```

### 1.1. What belongs to the framework

The framework should concentrate the reusable engines:

- LangGraph and workflow assembly.
- Checkpoint.
- Memory.
- Session repository.
- Channel gateway.
- Enterprise Router.
- Supervisor.
- Guardrails.
- Output Supervisor.
- Judges.
- Langfuse/OpenTelemetry Telemetry.
- IC/NOC/GRL analytics.
- MCP Tool Router.
- Cache.
- Generic RAG.

### 1.2. What belongs to the agent

The agent shall concentrate only domain customisations:

- Specific prompts.
- Business rules.
- Own schemas.
- Specific tools.
- Clients from external systems, preferably encapsulated behind MCP.
- Parameter mapping.
- Specialized nodes, if any.
- Business ICs of the journey.

When a rule only makes sense to a domain, it belongs to the agent. When a capacity must be used by several agents, it belongs to the framework.

---

## 2. Template runflow

The main flow begins at `app/main.py`, no endpoint `/gateway/message`.

```text
Channel / Frontend / API
  ↓
POST /gateway/message
  ↓
ChannelGateway.normalize()
  ↓
IdentityResolve
  ↓
SessionRepository
  ↓
MemoryRepository
  ↓
AgentWorkflow.ainvoke()
  ↓
LangGraph
  ↓
Input Guardrails
  ↓
Enterprise Router or Supervisor
  ↓
Specialized agent
  ↓
MCP Tool Router / RAG / Cache / LLM
  ↓
Output Supervisor
  ↓
Output Guardrails
  ↓
Judges
  ↓
Supervisor Review
  ↓
Persistence / Checkpoint / Memory
  ↓
Response
```

O `AgentWorkflow`in `app/workflows/agent_graph.py`, usually already contains corporate nodes as:

```text
input_guardrails
routing_decision
billing_agent
product_agent
orders_agent
support_agent
handoff
supervisor_agent
output_supervisor
output_guardrails
Judge
supervisor_review
persist
```

To create a new agent, you usually change:

```text
app/agents/<novo_agente>.py
app/workflows/agent_graph.py
app/state.py if you need new fields
config/agents. yaml
config/routing. yaml
config/tools. yaml
config/mcp_servers.yaml
config/mcp_parameter_mapping.yaml
config/identity. yaml
config/agents/<agent_id>/prompt_policy.yaml
config/agents/<agent_id>/guardrails.yaml
config/agents/<agent_id>/judges.yaml
.env
```

---

## 3. Prerequisites

### 3.1. Local requirements

- Python 3.12 or 3.13.
- `pip` or `uv`.
- Project `agent_framework` available in the same workspace if the template uses local installation.
- MCP servers, if the agent uses tools.
- Redis, Oracle Autonomous Database, MongoDB and Langfuse are optional according to configuration.

Recommended structure:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

### 3.2. Local installation

Inside directory `agent_template_backend`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `agent_framework` is in local development:

```bash
pip install -e ../agent_framework
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e ..\agent_framework
```

---

## 4. Settings `.env`

O `.env` defines which engines will be activated. It is not just a property file: it changes agent behavior at runtime.

Safe example for local development:

```env
APP_NAME=ai-agent-template
APP_ENV=local
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

LLM_PROVIDER=mock
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2048
LLM_TIMEOUT_SECONDS=120

SESSION_REPOSITORY_PROVIDER=memory
MEMORY_REPOSITORY_PROVIDER=memory
CHECKPOINT_REPOSITORY_PROVIDER=memory
USAGE_REPOSITORY_PROVIDER=memory

ENABLE_REDIS_CACHE=false
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=300

VECTOR_STORE_PROVIDER=memory
GRAPH_STORE_PROVIDER=memory
RAG_TOP_K=5
EMBEDDING_PROVIDER=mock

ENABLE_LANGFUSE=false
LANGFUSE_HOST=http://localhost:3005
ENABLE_OTEL=false
OTEL_SERVICE_NAME=ai-agent-template

ENABLE_ANALYTICS=false
ANALYTICS_PROVIDERS=noop
ENABLE_OCI_STREAMING=false
OCI_STREAM_ENDPOINT=
OCI_STREAM_OCID=
OCI_STREAM_PARTITION_KEY=agent-events

ENABLE_INPUT_GUARDRAILS=true
ENABLE_OUTPUT_GUARDRAILS=true
ENABLE_OUTPUT_SUPERVISOR=true
ENABLE_JUDGES=true
ENABLE_SUPERVISOR=true
ENABLE_PARALLEL_GUARDRAILS=true
GUARDRAILS_FAIL_FAST=true
OUTPUT_SUPERVISOR_MAX_RETRIES=3
GUARDRAILS_CONFIG_PATH=./config/guardrails.yaml
JUDGES_CONFIG_PATH=./config/judges.yaml
PROMPT_POLICY_PATH=./config/prompt_policy.yaml

ROUTING_CONFIG_PATH=./config/routing.yaml
ROUTING_MODE=router
ENABLE_LLM_ROUTER=false

ENABLE_MCP_TOOLS=true
MCP_SERVERS_CONFIG_PATH=./config/mcp_servers.yaml
TOOLS_CONFIG_PATH=./config/tools.yaml
MCP_PARAMETER_MAPPING_PATH=./config/mcp_parameter_mapping.yaml
MCP_TOOL_TIMEOUT_SECONDS=30

IDENTITY_CONFIG_PATH=./config/identity.yaml
```

### 4.1. How to reason on the `.env`

Before testing a new agent, answer:

```text
Will the LLM be mock or real?
Is the memory local or bank?
Does the checkpoint have to survive the rest?
Will MCP tools be called real or simulated?
Is routing by rule/intent or supervisor?
Guardrails, judges and supervisor should block, review or just observe?
Will Langfuse/OTEL/Streaming be used in this environment?
```

For a first test, use `LLM_PROVIDER=mock`, persistence in `memory` and MCP mock/local. Then evolve to real LLM, bank, Langfuse and real services.

To use Oracle Autonomous Database, adjust:

```env
SESSION_REPOSITORY_PROVIDER=autonomous
MEMORY_REPOSITORY_PROVIDER=autonomous
CHECKPOINT_REPOSITORY_PROVIDER=autonomous
USAGE_REPOSITORY_PROVIDER=autonomous

ADB_USER=<usuario>
ADB_PASSWORD=<senha>
ADB_DSN=<dsn>
ADB_WALLET_LOCATION=<caminho-wallet>
ADB_WALLET_PASSWORD=<senha-wallet>
ADB_TABLE_PREFIX=AGENTFW
```

To use Langfuse:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=<public-key>
LANGFUSE_SECRET_KEY=<secret-key>
LANGFUSE_HOST=http://localhost:3005
```


---

## 5. Creating a new agent

In this example, let's create an agent called `financeiro_agent` for generic financial assistance.

### 5.1. Before the code: what is an agent in this framework?

An agent is a domain class that receives the `state` LangGraph interprets the intention chosen by the router or supervisor, collects evidence, calls tools/RAG/LLM when necessary and returns a decision for the workflow to continue.

He must not decide alone everything the framework already decides. For example:

```text
The agent doesn't create a session.
The agent won't open SSE.
The agent doesn't compile LangGraph.
The agent doesn't create a checkpoint.
The agent does not execute global guards.
The agent does not call external system directly when there is MCP Tool Router.
```

The agent must answer questions like:

```text
What business problem am I solving?
What data do I need to respond safely?
What tools can provide this data?
What domain rules prevent or authorize action?
What answer should be returned to the user?
What IC events do I need to issue to audit the journey?
```

### 5.2. File Responsibilities `app/agents/financeiro_agent.py`

This file shall contain the specific logic of the financial agent. He must:

1. Receive `state`.
2. Issue CI at first.
3. Collect context from MCP tools if any.
4. Collect RAG context, if any.
5. Set up a domain prompt.
6. Call the LLM for the common runtime.
7. Set up a standardized response.
8. Issue CI of conclusion.
9. Return data to workflow.


### 5.2.1. Understanding `state`, `context`, `session`, `business_context` and `tool_arguments`

Before copying the agent code, the developer needs to understand where the data comes from**. In a corporate agent, the most common mistake is to take any field directly from `state` not knowing if that data came from the channel, gateway, identity solve, router or user.

O `state` It's the full envelope of LangGraph's execution. Inside it there is usually a `context`, which is the context normalized by the framework.

Inside `context`, if the project uses **Agent Gateway / Global Supervisor**, there is also a common block `session`:

```python
ctx = state.get("context") or {}
session = ctx.get("session") or {}
```

The paper of each block is different:

```text
state
  Full workingflow status current. Load text, intent, route, partial response,
  MCP results, guardrail data, checkpoint and other technical fields.

context
  Standard context of the current message. It usually comes from Channel Gateway,
  Identity Solve and Agent Gateway.

session
  Session and channel data. It helps to know who's talking, which channel,
  in which tenant, which global session is active and which backend/agent is attending.

business_context
  Business data already standardised. Example: customer_key, contract_key,
  interaction_key, session_key, protocol_id, invoice_id, order_id.

tool_arguments
  Explicit parameters already prepared for tools/MCP. When it exists, it must have
  priority on inferences made by the agent.
```

The recommended trust order is:

```text
1. explicit tool_arguments
2. business_context resolvido pelo framework
3. standard context
4. session and session.metadata, when they come from Agent Gateway
5. direct state
6. original user text, only for additional extraction
```

That order avoids two problems:

```text
Problem 1: Ignore data already solved by Gateway/Identity Solve.
Problem 2: Overwrite a canonical parameter with a raw and less reliable value.
```

Practical example: if `business_context.customer_key` already solved by the framework, the agent should not prefer a `user_id` generic session only because it exists. O `user_id` identifies the user in the channel; `customer_key` identifies the customer in the business.

Even if a simple agent doesn't use `session` directly, there is a difference between **technical session** and **business context**.

### 5.3. Create agent file

Create:

```text
app/agents/financeiro_agent.py
```

Base code commented:

```python
from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin


class FinanceiroAgent(AgentRuntimeMixin):
    # Este nome precisa bater com o nome usado no workflow e nas configurações.
    name = "financeiro_agent"

    def __init__(self, llm, telemetry=None, tool_router=None, rag_service=None, cache=None, settings=None, observer=None):
        # Estes objetos são injetados pelo workflow/framework.
        # O agente usa, mas não cria esses motores.
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings
        self.observer = observer

    async def run(self, state):
        # 1. Marca o início da jornada de negócio deste agente.
        await self._emit_ic(
            "IC.FINANCEIRO_AGENT_STARTED",
            state,
            {"business_component": "financeiro"},
            component="agent.financeiro.start",
        )

        # 2. Separa os blocos do contrato do framework.
        # O agente lê esses blocos, mas quem cria/normaliza é o framework.
        ctx = state.get("context") or {}
        session = ctx.get("session") or {}
        session_metadata = session.get("metadata") or {}
        business_context = ctx.get("business_context") or state.get("business_context") or {}
        tool_arguments = ctx.get("tool_arguments") or state.get("tool_arguments") or {}

        # 3. Interpreta a mensagem atual usando o texto já sanitizado pelos guardrails,
        # mas preserva o texto original apenas quando precisar extrair identificadores.
        user_text = state.get("sanitized_input") or state.get("user_text") or ""
        original_text = (
            ctx.get("message")
            or ctx.get("text")
            or ctx.get("query")
            or session.get("last_user_message")
            or state.get("user_text")
            or user_text
        )

        # 4. Chama tools MCP selecionadas pelo roteamento, quando configuradas.
        # O agente não precisa saber se a tool usa REST, SOAP, DB ou mock.
        tool_context = await self._collect_tool_context(state)

        if tool_context:
            await self._emit_ic(
                "IC.FINANCEIRO_MCP_CONTEXT_COLLECTED",
                state,
                {"tool_result_count": len(tool_context)},
                component="agent.financeiro.mcp",
            )

        # 5. Recupera contexto documental, se o RAG estiver habilitado.
        rag_context, rag_metadata = await self._retrieve_rag_context(state)

        # 6. Monta a mensagem para o LLM.
        # O system prompt define comportamento e limites do agente.
        # O user prompt leva dados, evidências e contexto.
        messages = [
            {
                "role": "system",
                "content": apply_agent_profile_prompt(
                    state,
                    "Você é um agente financeiro. Responda com clareza, usando dados das ferramentas quando disponíveis. Não confirme ações financeiras sem evidência e confirmação explícita."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Mensagem: {state.get('sanitized_input') or state['user_text']}\n"
                    f"Sessão: {session}\n"
                    f"Intent: {state.get('intent')}\n"
                    f"Dados MCP: {tool_context}\n"
                    f"Contexto RAG: {rag_context}"
                ),
            },
        ]

        # 7. Chama o LLM usando o runtime comum, com cache e telemetria.
        answer = await self._invoke_llm_cached(state, "FinanceiroAgent", messages)

        # 8. Retorna no contrato esperado pelo workflow.
        result = {
            "answer": f"[FinanceiroAgent] {answer}",
            "next_state": "FINANCEIRO_ACTIVE",
            "mcp_results": tool_context,
            "rag": rag_metadata,
        }

        # 9. Marca o fim da jornada de negócio.
        await self._emit_ic(
            "IC.FINANCEIRO_AGENT_COMPLETED",
            state,
            {
                "answer_chars": len(result.get("answer") or ""),
                "has_mcp_results": bool(tool_context),
                "rag_enabled": bool(rag_metadata.get("enabled")),
            },
            component="agent.financeiro.completed",
        )

        return result

    async def _collect_tool_context(self, state):
        # Este método delega para o MCP Tool Router do framework.
        # As tools chamadas dependem da intent definida em routing.yaml.
        return await self._collect_mcp_context(state)
```

### 5.3.1. How to adapt this example to a real agent

In the example above, `session`, `business_context` and `tool_arguments` appear in the prompt for didactic purposes. In production, the developer should avoid throwing huge objects directly into the prompt. The ideal is to select only the required fields.

Example of reasoning for a financial agent:

```text
session.channel → useful for adjusting language or understanding the origin of the conversation.
session.tenant_id → useful for multi-tenant isolation.
business_context.customer_key → useful to consult customer/title/payment.
business_context.contract_key → useful for consulting contract, invoice or request.
Business_context.interaction_key → useful for tracking protocol/call/interaction.
tool_arguments → useful when Gateway or Identity Solve has already prepared exact parameters.
```

A common utility function within the agent is a `pick()` with explicit precedence order:

```python
def pick(name: str, *, tool_arguments, business_context, ctx, session, session_metadata, state):
    if name in tool_arguments:
        return tool_arguments.get(name)
    if isinstance(business_context, dict) and name in business_context:
        return business_context.get(name)
    if name in ctx:
        return ctx.get(name)
    if name in session:
        return session.get(name)
    if name in session_metadata:
        return session_metadata.get(name)
    return state.get(name)
```

This function makes it clear that the agent is not “guessing” where the data comes from. He's following a policy of trust.

### 5.3.2. Where does Agent Gateway enter that code?

When Agent Gateway / Global Supervisor exists, he can enrich the message before sending it to the agent's backend. Examples of data that can come in `context.session`:

```json
{
  "session": {
    "global_session_id": "s1",
    "backend_session_id": "default:financeiro_agent:s1",
    "active_backend": "financeiro",
    "channel": "web",
    "tenant_id": "default",
    "metadata": {
      "selected_backend": "financeiro",
      "last_reason": "Backend escolhido por regras: matches=['pagamento']"
    }
  }
}
```

The agent should not use this block to make final business decision. It should use it for technical context, traceability and continuity of conversation. The business decision must remain based on `business_context`MCP, RAG and domain rules.

### 5.4. How do you know the agent is well implemented?

An agent is well implemented when:

```text
He knows business rules, but he doesn't know infrastructure details.
He uses common runtime for LLM, RAG, cache, MCP and IC.
It returns a simple contract to workflow.
It doesn't duplicate guardrail, checkpoint, session, memory or telemetry.
It can be tested alone with simulated state.
```

---

## 6. Registering agent in workflow

### 6.1. Before code: what is workflow?

The workflow is the path controlled by LangGraph. It defines the execution order:

```text
entry → Guardrails → routing → agent → review → persistence → response
```

Creating the agent's class isn't enough. LangGraph only executes nodes that were registered in the graph.

The workflow record answers three questions:

```text
What class implements the agent?
What's the node name for this agent on the graph?
Where does the flow go after the agent responds?
```

### 6.2. Import agent

Edit:

```text
app/workflows/agent_graph.py
```

Add:

```python
from app.agents.financeiro_agent import FinanceiroAgent
```

### 6.3. Install agent

No `__init__` class `AgentWorkflow`After the creation of `agent_kwargs`:

```python
self.financeiro = FinanceiroAgent(llm, **agent_kwargs)
```

This line injects into the agent the same engines shared by the other agents: LLM, telemetry, MCP Tool Router, RAG, cache, settings and observerr.

### 6.4. Create LangGraph node

In `_build_graph()`:

```python
builder.add_node("financeiro_agent", self._node("financeiro_agent", self.financeiro_agent))
```

The first `financeiro_agent` is the name of the node in the graph. The second `self.financeiro_agent` is the wrapper method that will be called when the flow reaches this node.

### 6.5. Add conditional route

In the dictionary of `builder.add_conditional_edges("routing_decision",...)`, include:

```python
"financeiro_agent": "financeiro_agent",
```

Example:

```python
builder.add_conditional_edges(
    "routing_decision",
    lambda s: s.get("route", "billing_agent"),
    {
        "billing_agent": "billing_agent",
        "product_agent": "product_agent",
        "orders_agent": "orders_agent",
        "support_agent": "support_agent",
        "financeiro_agent": "financeiro_agent",
        "handoff": "handoff",
        "supervisor_agent": "supervisor_agent",
    },
)
```

This table connects the router decision with the actual node of the graph.

### 6.6. Connect the node to Output Supervisor

```python
builder.add_edge("financeiro_agent", "output_supervisor")
```

This line is important because the agent's response should not go straight to the user. It goes through supervisor output, output guardrails, judges, supervisor review and persistence.

### 6.7. Create wrapper method

In class `AgentWorkflow`:

```python
async def financeiro_agent(self, state):
    async with self.langgraph_telemetry.node("financeiro_agent", state):
        async with self.telemetry.span(
            "workflow.agent.financeiro",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input={"intent": state.get("intent")},
        ):
            return await self.financeiro.run(state)
```

The wrapper adds telemetry around the agent. Business logic continues within `FinanceiroAgent.run()`.

### 6.8. Add to supervisor mode

In the method `supervisor_agent()`, adjust the handler map:

```python
handlers = {
    "billing_agent": self.billing.run,
    "product_agent": self.product.run,
    "orders_agent": self.orders.run,
    "support_agent": self.support.run,
    "financeiro_agent": self.financeiro.run,
}
```

This allows the supervisor to call the new agent when `ROUTING_MODE=supervisor` or when there is supervised handoff.

### 6.9. Common errors in this chapter

```text
Criar a classe do agente, mas esquecer add_node.
Adicionar add_node, mas esquecer add_conditional_edges.
Adicionar rota, mas esquecer add_edge para output_supervisor.
Use different name in routing.yaml, workflow and class.
Call it self-financial. direct run without telemetry wrapper.
```

---

## 7. Adjusting agent status

### 7.1. Before the code: what is the state?

O `state` It's the object that runs between LangGraph's nodes. It works as the short-term memory of the current execution.

It is not the database, it is not the full conversational memory and should not become a giant repository of information.

Use `state` for data that need to circulate between us, for example:

```text
user text
chosen intent
route chosen
partial response
result of a tool
next state of conversation
decision flags
```

Do not use `state` for:

```text
long history of conversation
large files
complete responses from external systems without need
gross content of documents
extensive logs
```

### 7.2. When to change `app/state.py`

Edit:

```text
app/state. py
```

Only add new fields if the agent needs to share specific information with other nodes.

Example:

```python
class AgentState(TypedDict, total=False):
    # campos existentes...
    financial_context: dict[str, Any]
    financial_decision: dict[str, Any]
```

### 7.3. Decision criteria

Before you create a new field, ask:

```text
Does another knot need to read this data?
Does this data need to survive the next step of the workflow?
Is this data small and structured?
Does this help audit or decision?
```

If the answer is no, leave the local data to the agent or record in an appropriate repository.

---

## 8. Registering agent in `config/agents.yaml`

### 8.1. Before YAML: what is it for `agents.yaml`??

O `agents.yaml` is the official record of available agents. It does not run the agent alone, but informs the framework which agents exist, which isolated settings they use and which metadata describe the domain.

He says:

```text
What's Agent _id?
What friendly name appears in listings and debug?
Where are specific prompt, guardians and judges?
What domain does this agent take?
Which metadata help routing, auditing and operation?
```

### 8.2. Example of registration

Edit:

```text
config/agents. yaml
```

Add:

```yaml
agents:
  - agent_id: financeiro_agent
    name: Financeiro Agent
    description: Agente para dúvidas financeiras, pagamentos, saldos, acordos e segunda via.
    prompt_policy_path: ./config/agents/financeiro_agent/prompt_policy.yaml
    routing_config_path: ./config/routing.yaml
    guardrails_config_path: ./config/agents/financeiro_agent/guardrails.yaml
    judges_config_path: ./config/agents/financeiro_agent/judges.yaml
    mcp_servers_config_path: ./config/mcp_servers.yaml
    tools_config_path: ./config/tools.yaml
    metadata:
      domain: financeiro
      system_prefix: |
        Você está executando o financeiro_agent.
        Use somente políticas, memória, checkpoints, guardrails e judges deste agent_id.
        Não misture histórico ou decisões de outros agentes.
```

### 8.3. Care

O `agent_id` needs to be consistent with:

```text
node name in workflow
name used in roving. yaml
canonical session_id
pasta config/agents/<agent_id>/
observability metadata
```

Avoid Rename `agent_id` after the agent is already in production, because this can break history, memory, checkpoint and metrics.

---

## 9. Creating isolated agent settings

### 9.1. Before YAML: Why isolate configuration by agent?

Each agent can have his own prompt, guardrails and judges policy. A financial agent may require explicit confirmation before action. A support agent can allow more open answers. A legal agent may require documentary evidence.

So avoid putting everything in the global archive. Use global configuration for corporate rules and local configuration for domain rules.

Create:

```text
config/agents/financeiro_agent/
```

### 9.2. `prompt_policy.yaml`

This file defines the base position of the agent.

```yaml
id: financeiro_agent_prompt_policy
version: 1
description: Prompt base isolado do agente financeiro.
system_prefix: |
  Você é um agente corporativo especializado em atendimento financeiro.
  Seja claro, objetivo, auditável e não invente dados.
  Quando precisar executar uma ação, use ferramentas configuradas.
  Quando faltar informação obrigatória, peça apenas o dado necessário.
```

Use this file for persistent rules of behavior, not for temporary test rules.

### 9.3. `guardrails.yaml`

This file complements global guardrails.

```yaml
input:
  - code: MSK
    enabled: true
  - code: VLOOP
    enabled: true
  - code: PINJ
    enabled: true
output:
  - code: REVPREC
    enabled: true
  - code: CMP
    enabled: true
```

Use guardrail when the answer needs to be blocked, sanitized or revised by rule.

### 9.4. `judges.yaml`

Judges assess quality, adherence, groundedness and other criteria after the response is produced.

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
  - name: groundedness
    enabled: true
    threshold: 0.6
```

Use Judge to evaluate response. Use guardrail to block or protect. Use prompt to guide behavior.

---

## 10. Configuring routing in `config/routing.yaml`

### 10.1. Before YAML: What is routing?

Routing is the decision which agent should address the message.

In a multi-agent system, the user should not need to know which agent to call. He writes a message, and the framework decides the route.

The router usually considers:

```text
user text
current state of conversation
keywords
examples
priority
agent_id solicitado
State policies
LLM router, if enabled
```

### 10.2. When to create a new intention?

Create an intent when there is a clear category of request that should go to a specific agent.

Example of financial intent:

```yaml
intents:
  - name: financeiro_pagamentos
    domain: financeiro
    agent: financeiro_agent
    description: Dúvidas sobre pagamento, saldo, fatura, boleto, acordo, contestação e segunda via.
    priority: 15
    mcp_tools:
      - consultar_titulo_financeiro
      - consultar_pagamentos_financeiro
    keywords:
      - pagamento
      - boleto
      - saldo
      - acordo
      - financeiro
      - segunda via
      - vencimento
      - cobrança
      - contestação
    examples:
      - Quero consultar meu pagamento.
      - Preciso da segunda via do boleto.
      - Meu pagamento ainda não foi baixado.
```

### 10.3. Which means `mcp_tools` At intent?

`mcp_tools` indicates which tools should be made available/collected when this intent is chosen. Thus, the agent does not need to decide manually each call in all simple cases.

The flow is:

```text
routing.yaml chooses intent
Intent points agent
intent declara mcp_tools
AgentRuntimeMixin collects MCP context
agent uses the data in response
```

### 10.4. State Policies

If the conversation is already in a specific state, the next message may need to return to the same agent even if the text is short.

Example:

```yaml
state_policies:
  - state: WAITING_FINANCEIRO_CONFIRMATION
    agent: financeiro_agent
    description: Mantém confirmações curtas no fluxo financeiro.
```

This prevents an answer like “yes” from being routed to the wrong agent.

### 10.5. Router versus supervisor

In router mode:

```env
ROUTING_MODE=router
```

The framework chooses a route more directly, usually by rules, keywords, examples and score.

In supervisor mode:

```env
ROUTING_MODE=supervisor
```

A supervisor may decide the sequence of agents, handoff or combination of responses.

Use router when the domain is well mapped. Use supervisor when the conversation requires decomposition, multiple agents or more flexible decision.

---

## 11. Configuring tools in `config/tools.yaml`

### 11.1. Before YAML: What is a tool?

A tool is an external capability that the agent can use to get data or perform an action.

Examples:

```text
see invoice
see payment
open protocol
fetch request
cancel service
consult knowledge base
```

The tool is not necessarily the real system. She's the contract the backend knows. The real system is behind MCP Server.

### 11.2. Declaring tools

Edit:

```text
config/tools. yaml
```

Add:

```yaml
tools:
  consultar_titulo_financeiro:
    description: Consulta um título financeiro por cliente e contrato.
    mcp_server: financeiro
    enabled: true
    args_schema:
      customer_id: string
      contract_id: string

  consultar_pagamentos_financeiro:
    description: Consulta pagamentos financeiros por cliente.
    mcp_server: financeiro
    enabled: true
    args_schema:
      customer_id: string
```

### 11.3. How to think about a tool

Before declaring a tool, define:

```text
What business question does she answer?
Does she just consult or execute an action?
Which parameters are mandatory?
What parameters come from canonical identity?
Which MCP Server implements tool?
Which timeout and fallback are acceptable?
Does the result have sensitive data that needs to be masked?
```

The backend should not call directly HTTP/SOAP/DB business systems when this call can be standardized via MCP Tool Router.

---

## 12. Configuring servers MCP

### 12.1. Before YAML: What is MCP Server?

MCP Server is the adapter between the agent world and the real systems. It allows the backend to talk with tools in a standardized way, without knowing details of REST, SOAP, bench, queues or mocks.

The drawing is:

```text
Officer
  ↓
MCP Tool Router Framework
  ↓
MCP Domain Server
  ↓
Real system, mock, bank, REST, SOAP or internal service
```

### 12.2. Local Settings

Edit:

```text
config/mcp_servers.yaml
```

Example:

```yaml
servers:
  financeiro:
    transport: http
    endpoint: http://localhost:8300/mcp
    enabled: true
    description: MCP Server Financeiro local.
```

### 12.3. Docker Settings Compose

Edit:

```text
config/mcp_servers.docker.yaml
```

Example:

```yaml
servers:
  financeiro:
    transport: http
    endpoint: http://financeiro-mcp:8300/mcp
    enabled: true
    description: MCP Server Financeiro em Docker.
```

### 12.4. How to avoid common endpoint error

Locally, `localhost` works because backend and MCP run on the same machine.

Inside Docker Compose, `localhost` inside the backend container points to the backend container itself, not to the MCP container. So in Docker, use the name of the service:

```text
http://financeiro-mcp:8300/mcp
```

---

## 13. Setting parameter mapping MCP

### 13.1. Before YAML: Why is there mapping?

The framework works with canonical keys not to depend on the specific names of each system.

Example:

```text
customer_key = canonical client in the framework
contract_key = contract/invoice/request/canonical title
interaction_key = external interaction
session_key = technical session
```

But each tool can expect different names:

```text
customer_id
cpf
msisdn
clientCode
contract_id
invoice_id
order_id
```

O `mcp_parameter_mapping.yaml` does this translation without forcing the agent to know the internal names of each MCP.

### 13.2. Example

Edit:

```text
config/mcp_parameter_mapping.yaml
```

```yaml
mcp_parameter_mapping:
  defaults:
    use_mock: true
  tools:
    consultar_titulo_financeiro:
      map:
        customer_key: customer_id
        contract_key: contract_id
        interaction_key: interaction_id
        session_key: session_id
    consultar_pagamentos_financeiro:
      map:
        customer_key: customer_id
        session_key: session_id
```

Interpretation:

```text
customer_key -> canonical key in the framework
customer_id -> parameter expected by MCP tool
```

### 13.3. How to validate mapping

If the tool gets the wrong parameter, investigate in this order:

```text
payload sent to /gateway/message
config/identity. yaml
business_context resolvido
config/mcp_parameter_mapping.yaml
args_schema da tool
Real signature on MCP Server
```

---

## 14. Configuring business identity

### 14.1. Before YAML: What is business identity?

Business identity is the normalization of the keys representing the client, contract, request, protocol, session or interaction.

Without this layer, each channel sends a different name and each tool expects another name. The result is parameter error, tool without mandatory data or wrong customer query.

O `identity.yaml` responds:

```text
Where can I extract customer_key from?
Where can I extract contract_key from?
Where can I extract interaction_key from?
Where can I extract session_key?
Which keys are mandatory?
```

### 14.2. Example

Edit:

```text
config/identity. yaml
```

```yaml
identity:
  version: "2"
  required:
    - session_key
  keys:
    customer_key:
      description: Cliente canônico.
      sources:
        - business_context.customer_key
        - context.business_context.customer_key
        - context.session.metadata.customer_key
        - customer_key
        - customer_id
        - cpf
        - cnpj
        - user_id
    contract_key:
      description: Contrato, pedido, fatura ou título principal.
      sources:
        - business_context.contract_key
        - context.business_context.contract_key
        - context.session.metadata.contract_key
        - contract_key
        - contract_id
        - invoice_id
        - order_id
    interaction_key:
      description: Chave externa da interação.
      sources:
        - business_context.interaction_key
        - context.business_context.interaction_key
        - context.session.metadata.interaction_key
        - interaction_key
        - call_id
        - message_id
        - protocol_id
    session_key:
      description: Sessão técnica estável.
      sources:
        - business_context.session_key
        - context.business_context.session_key
        - context.session.backend_session_id
        - context.session.global_session_id
        - context.session.metadata.session_key
        - session_key
        - conversation_key
        - session_id
```

### 14.3. How to think about identity

Use the minimum necessary. Don't make it all mandatory. For a generic question, maybe just `session_key` Be enough. To consult a financial title, perhaps `customer_key` and `contract_key` be mandatory.

The resolved identity appears in `business_context` within the `state` and is used by `MCP Tool Router`.

### 14.4. Relationship between SessionContext and BusinessContext

When Agent Gateway is present, it can create or transport session data. These data are important, but they do not replace business identity.

```text
SessionContext responde:
  Who is this?
  Which channel?
  Which global session is active?
  What backend are you answering?
  What was the reason for the last route decision?

BusinessContext responde:
  Which customer should be consulted?
  What contract/invoice/request is under discussion?
  Which protocol/call/interaction identifies the case?
  Which key should be sent to MCP tool?
```

Practical rule:

```text
Use session for continuity, traceability and channel.
Use business_context to consult systems, call MCP and make business decision.
Use tool_arguments when parameters are already explicitly prepared.
```

Common error example:

```text
Usar session.user_id como customer_key sem validar identity.yaml.
```

The right thing is to leave the `IdentityResolver` transform `user_id`, `cpf`, `msisdn`, `customer_id` or another identifier in a canonical key like `customer_key`.

---

## 15. Implementing or connecting an MCP Server

### 15.1. Before the code: What is the role of MCP Server?

MCP Server is where integration with external systems or domain mocks is located. It allows the agent to use a tool without knowing technical implementation.

The backend can call:

```text
consultar_titulo_financeiro(customer_id, contract_id)
```

But you don't know, and you shouldn't know if this appointment uses:

```text
REST
SOAP
Oracle bank
mock file
legacy service
queue
internal system
```

### 15.2. Conceptual tool contract

Conceptual example:

```python
async def consultar_titulo_financeiro(customer_id: str, contract_id: str, session_id: str | None = None):
    return {
        "customer_id": customer_id,
        "contract_id": contract_id,
        "status": "ABERTO",
        "valor": 129.90,
        "vencimento": "2026-06-20",
    }


async def consultar_pagamentos_financeiro(customer_id: str, session_id: str | None = None):
    return {
        "customer_id": customer_id,
        "pagamentos": [
            {"data": "2026-06-01", "valor": 129.90, "status": "COMPENSADO"}
        ],
    }
```

### 15.3. Criteria for mock versus real

Use mock when:

```text
real system is not available
You're testing routing and contract
you want to validate frontend/backend without relying on VPN
you want to mount automated deterministic tests
```

Use real integration when:

```text
the contract has already been validated
the parameters are correct
timeout and fallback were defined
there is observability for success and failure
there are safe data for testing
```

For development, you can use `use_mock: true` in `mcp_parameter_mapping.yaml` or implement an MCP Local server with simulated answers.

---

## 16. CI, NOC and GRL on the new agent

### 16.1. Before events: why do they exist?

CI, NOC and GRL are not common logs. They exist to track the execution in a corporate way.

```text
CI = business event or agent journey
NOC = operational event, error, unavailability, timeout or degradation
GRL = governance event, guardrail, blockade, review or sanitization
```

Use `logger.info()` for simple diagnosis. Use IC/NOC/GRL when the event needs to appear in audit, observability or operational analysis.

### 16.2. IC — business events

Use ICs inside the agent to record relevant journey steps.

Example:

```python
await self._emit_ic(
    "IC.FINANCEIRO_AGENT_STARTED",
    state,
    {"business_component": "financeiro"},
    component="agent.financeiro.start",
)
```

Minimum suggestion per agent:

```text
IC.<AGENTE>_AGENT_STARTED
IC.<AGENTE>_MCP_CONTEXT_COLLECTED
IC.<AGENTE>_RAG_CONTEXT_RETRIEVED
IC.<AGENTE>_AGENT_COMPLETED
IC.<AGENTE>_BUSINESS_DECISION
IC.<AGENTE>_ACTION_REQUESTED
IC.<AGENTE>_ACTION_COMPLETED
```

### 16.3. NOC — operational events

NOC should be used for technical health, unavailability, error, timeout, fallback and degradation.

Example:

```python
await self.observer.emit_noc(
    "NOC.FINANCEIRO_TOOL_TIMEOUT",
    {
        "session_id": state.get("conversation_key") or state.get("session_id"),
        "tenant_id": state.get("tenant_id"),
        "agent_id": state.get("agent_id"),
        "tool": "consultar_titulo_financeiro",
    },
    component="agent.financeiro.tool",
)
```

### 16.4. GRL — Guardrails

Most GRLs are already issued by workflow at:

```text
input_guardrails
output_supervisor
output_guardrails
```

Only implement GRL within the agent when there is a specific domain validation that does not fit the global guards.

### 16.5. When not creating new event

Do not create IC/NOC/GRL for each line of code. Create events for important decisions:

```text
validated entry
MCP context collected
business decision made
External action requested
external action completed
technical fallback triggered
blocked or revised response
workflow completed
```

---

## 17. Build and local execution

### 17.1. Before commands: what does starting the backend mean?

starting the backend means starting the API that receives messages, normalizing channel, solving identity, signing in, running workflow and returning response.

It can start even without real MCP, provided the configuration is in mock or that tools are not required for testing.

### 17.2. Rotate local backend

Inside `agent_template_backend`:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 17.3. Immediate validations

Check health:

```bash
curl http://localhost:8000/health
```

List agents:

```bash
curl http://localhost:8000/agents
```

List known MCP tools:

```bash
curl http://localhost:8000/debug/mcp/tools
```

### 17.4. How to interpret the result

```text
/health ok         → API subiu.
/agents lista      → agents.yaml foi carregado.
/debug/mcp/tools   → tools.yaml e mcp_servers.yaml foram carregados.
```

If `/health` works but `/agents` The problem is probably in `config/agents.yaml`. If `/debug/mcp/tools` does not show the tool, the problem is probably in `tools.yaml` or `mcp_servers.yaml`.

---

## 18. Up MCP Servers

### 18.1. Before commands: When do I need to start MCP?

You need to start MCP when the chosen intent uses `mcp_tools` And the agent depends on those tools to answer.

You do not need to start MCP to test only:

```text
health check
register of agents
basic routing
mock LLM without tools
simple conversational flow without external consultation
```

### 18.2. initiate MCP Local server

If MCPs Servers are Processes Separate Python, climb each on a distinct port.

Example:

```bash
cd ../mcp_servers/financeiro_mcp_server
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8300 --reload
```

Then confirm that the endpoint configured under `config/mcp_servers.yaml` is correct:

```yaml
servers:
  financeiro:
    endpoint: http://localhost:8300/mcp
```

### 18.3. Test tool for backend

Test by backend, not directly by MCP. So you validate the complete path:

```text
backend → MCP Tool Router → MCP Server → response
```

```bash
curl -X POST http://localhost:8000/debug/mcp/call/consultar_titulo_financeiro \
  -H "Content-Type: application/json" \
  -d '{
    "business_context": {
      "customer_key": "12345",
      "contract_key": "ABC-999",
      "session_key": "sessao-teste"
    },
    "original_context": {
      "session_id": "sessao-teste"
    }
  }'
```

### 18.4. How to interpret MCP errors

```text
Tool not found → tools.yaml or wrong tool name.
Server not found → mcp_servers. yaml does not have mcp_server indicated by tool.
Connection refused → MCP Server's not running or wrong door.
Absent mandatory parameter → identity. yaml or mcp_tometer_mapping.yaml incorrect.
Timeout → Slow MCP, wrong endpoint, VPN, DNS or real system unavailable.
```

---

## 19. Build with Docker

Template Dockerfile expects to copy `agent_framework` and `agent_template_backend`. Therefore, turn the build from the parent directory containing both.

Expected structure:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

Build:

```bash
cd workspace
docker build -t agent-template-backend:local -f agent_template_backend/Dockerfile .
```

Run:

```bash
docker run --rm -p 8000:8000 \
  --env-file agent_template_backend/.env \
  agent-template-backend:local
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## 20. Suggested Docker Compose

Create a `docker-compose.yaml` in parent directory, if you want to start backend, Redis, Langfuse and MCP Servers together.

Simplified example:

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: agent_template_backend/Dockerfile
    env_file:
      - agent_template_backend/.env
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - financeiro-mcp

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  financeiro-mcp:
    build:
      context: ./mcp_servers/financeiro_mcp_server
    ports:
      - "8300:8300"
```

When you're in Docker, use `config/mcp_servers.docker.yaml` and adjust `.env`:

```env
MCP_SERVERS_CONFIG_PATH=./config/mcp_servers.docker.yaml
```

---

## 21. Testing the agent for Gateway.

### 21.1. Simple test

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "agent_id": "financeiro_agent",
    "tenant_id": "default",
    "payload": {
      "text": "Quero consultar meu pagamento",
      "session_id": "teste-financeiro-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999",
      "message_id": "msg-001"
    }
  }'
```

The answer shall contain metadata such as:

```json
{
  "channel": "web",
  "session_id": "default:financeiro_agent:teste-financeiro-001",
  "text": "...",
  "metadata": {
    "route": "financeiro_agent",
    "intent": "financeiro_pagamentos",
    "mcp_results": [],
    "business_context": {
      "customer_key": "12345",
      "contract_key": "ABC-999"
    }
  }
}
```

### 21.2. Routing test without fixing `agent_id`

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "payload": {
      "text": "Meu pagamento ainda não foi baixado",
      "session_id": "teste-router-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999"
    }
  }'
```

### 21.3. SSE test

Send a message with SSE:

```bash
curl -X POST http://localhost:8000/gateway/message/sse \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "agent_id": "financeiro_agent",
    "tenant_id": "default",
    "payload": {
      "text": "Preciso da segunda via do boleto",
      "session_id": "teste-sse-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999"
    }
  }'
```

Open stream:

```bash
curl -N http://localhost:8000/gateway/events/default:financeiro_agent:teste-sse-001
```

Expected events:

```text
connected
flow.start
session.upserted
message. received
workflow.started
workflow. completed
message. respond
flow.end
```

---

## 22. Testing debug endpoints

### 22.1. Route

```bash
curl -X POST http://localhost:8000/debug/route \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Quero consultar meu pagamento",
    "context": {
      "agent_id": "financeiro_agent",
      "tenant_id": "default"
    }
  }'
```

### 22.2. Identity

```bash
curl -X POST http://localhost:8000/debug/identity \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "teste-id-001",
    "customer_id": "12345",
    "contract_id": "ABC-999",
    "message_id": "msg-001"
  }'
```

### 22.3. Session messages

```bash
curl http://localhost:8000/sessions/default:financeiro_agent:teste-financeiro-001/messages
```

### 22.4. Checkpoint

```bash
curl http://localhost:8000/sessions/default:financeiro_agent:teste-financeiro-001/checkpoint
```

### 22.5. Use/cost

```bash
curl http://localhost:8000/debug/usage
```

---

## 23. Functional validation checklist

Use this checklist before considering the agent ready.

### 23.1. Settings

- [ ] `.env` with no real versioned credentials.
- [ ] `LLM_PROVIDER` Correct.
- [ ] `ROUTING_MODE` defined: `router` or `supervisor`.
- [ ] `ENABLE_MCP_TOOLS` adjusted as needed.
- [ ] `MCP_SERVERS_CONFIG_PATH` points to the correct YAML.
- [ ] `IDENTITY_CONFIG_PATH` points to `config/identity.yaml`.
- [ ] Local or Autonomous persistence configured.

### 23.2. Officer

- [ ] File created in `app/agents/<agent>.py`.
- [ ] Class implement `async def run(self, state)`.
- [ ] Agent inherits `AgentRuntimeMixin`.
- [ ] Agent separates `context`, `session`, `business_context` and `tool_arguments` before making decisions.
- [ ] Agent uses `business_context` for business decisions and `session` for continuity/traceability.
- [ ] Specific prompts apply `apply_agent_profile_prompt()`.
- [ ] Tools are called via `_collect_mcp_context()`.
- [ ] RAG is called via `_retrieve_rag_context()`, if applicable.
- [ ] LLM is called via `_invoke_llm_cached()`.
- [ ] Return contains `answer`, `next_state`, `mcp_results` and, if applicable, `rag`.

### 23.3. Workflow

- [ ] Imported agent in `agent_graph.py`.
- [ ] Agent instantiate in `__init__`.
- [ ] We added in `StateGraph`.
- [ ] Route added in `add_conditional_edges`.
- [ ] Edge created for `output_supervisor`.
- [ ] Handler added in supervisor mode if necessary.

### 23.4. Route

- [ ] Intent added in `config/routing.yaml`.
- [ ] Enough keywords.
- Consistent examples.
- [ ] `agent` Intent matches the workflow node name.
- [ ] `mcp_tools` Intent exist in `config/tools.yaml`.

### 23.5. MCP

- [ ] Tool declared as `config/tools.yaml`.
- [ ] MCP Server declared on `config/mcp_servers.yaml`.
- [ ] Mapping declared on `config/mcp_parameter_mapping.yaml`.
- [ ] Tool tested via `/debug/mcp/call/{tool_name}`.
- [ ] Timeout and fallback set.

### 23.6. Observeability

- [ ] Start and end CIs issued.
- [ ] MCP/RAG collection CIs issued where applicable.
- [ ] NOCs issued in relevant technical errors.
- [ ] Global GRLs appear in input/output.
- Langfuse or other provider receives strokes if enabled.

### 23.7. Tests

- [ ] `/health` returns `status=ok`.
- [ ] `/agents` List the new agent.
- [ ] `/debug/route` Pick the right agent.
- [ ] `/debug/identity` Solve the expected keys.
- [ ] `/gateway/message` returns correct answer.
- [ ] `/gateway/message/sse` publishes events.
- [ ] `/sessions/{session_id}/messages` historical display.
- [ ] `/sessions/{session_id}/checkpoint` shows checkpoint.

---

## 24. Good customisation practices

### Do it.

- Put business rule on the agent, not the framework.
- Use MCP to access external systems.
- Use `identity.yaml` to normalize business keys.
- Use `mcp_parameter_mapping.yaml` to adapt parameter names.
- Use IC for business events.
- Use NOC for technical failures.
- Use GRL for security/validation decisions.
- Keep prompts per agent on `config/agents/<agent_id>/prompt_policy.yaml`.
- Keep guardrails and judges isolated when the agent has his own rules.

### Avoid

- Create another workflow outside `AgentWorkflow` No need.
- Call REST/DB directly inside the agent when the call should be MCP tool.
- Create your own checkpointer.
- Create parallel memory outside the framework.
- Issue telemetry in format incompatible with `AgentObserver`.
- Place specific agent rule within the framework.
- Mix history of different agents in the same session.

---

## 25. Troubleshooting

### 25.1. `/gateway/message` returns wrong route

Check:

```bash
curl -X POST http://localhost:8000/debug/route \
  -H "Content-Type: application/json" \
  -d '{"text":"sua frase de teste","context":{"agent_id":"financeiro_agent"}}'
```

Then review:

```text
config/routing. yaml
keywords
examples
priority
ROUTING_MODE
ENABLE_LLM_ROUTER
```

### 25.2. MCP Tool is not called

Check:

```text
A intent em routing.yaml possui mcp_tools.
The tool exists in tools.yaml.
MCP Server is in mcp_servers.yaml.
ENABLE_MCP_TOOLS=true.
O mapeamento existe em mcp_parameter_mapping.yaml.
Identity has the necessary keys.
```

### 25.3. Tool gets wrong parameter

Review:

```text
config/identity. yaml
config/mcp_parameter_mapping.yaml
payload sent to /gateway/message
```

Use:

```bash
curl -X POST http://localhost:8000/debug/identity \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","customer_id":"123","contract_id":"C1"}'
```

### 25.4. This gives MIME type incorrect

The correct endpoint is:

```text
GET /gateway/events/{session_id}
```

O `session_id` must be the complete canonical key returned by the gateway:

```text
tenant_id:agent_id:session_id_original
```

Example:

```text
default:financeiro_agent:teste-sse-001
```

### 25.5. Langfuse does not show traces

Check:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=<public-key>
LANGFUSE_SECRET_KEY=<secret-key>
LANGFUSE_HOST=http://localhost:3005
```

And check it out:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/debug/env
```

### 25.6. Autonomous Bank does not connect

For development, simplify first:

```env
SESSION_REPOSITORY_PROVIDER=memory
MEMORY_REPOSITORY_PROVIDER=memory
CHECKPOINT_REPOSITORY_PROVIDER=memory
USAGE_REPOSITORY_PROVIDER=memory
```

Then go back to `autonomous` when wallet, DSN and variables are correct.

---

## 26. Minimum delivery model for a new agent

Upon completion of an implementation, the minimum delivery shall contain:

```text
app/agents/<agent_name>.py
config/agents. yaml
config/routing. yaml
config/tools. yaml
config/mcp_servers.yaml
config/mcp_parameter_mapping.yaml
config/identity. yaml
config/agents/<agent_id>/prompt_policy.yaml
config/agents/<agent_id>/guardrails.yaml
config/agents/<agent_id>/judges.yaml
app/workflows/agent_graph.py
app/state.py, if necessary
.env.example or variable documentation
README.md with curl tests
```

---

## 27. Full test example

```bash
# 1. Health
curl http://localhost:8000/health

# 2. Agentes
curl http://localhost:8000/agents

# 3. Tools MCP
curl http://localhost:8000/debug/mcp/tools

# 4. Roteamento
curl -X POST http://localhost:8000/debug/route \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Quero consultar meu pagamento",
    "context": {"agent_id": "financeiro_agent", "tenant_id": "default"}
  }'

# 5. Identidade
curl -X POST http://localhost:8000/debug/identity \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "teste-final-001",
    "customer_id": "12345",
    "contract_id": "ABC-999"
  }'

# 6. Mensagem real
curl -X POST http://localhost:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "agent_id": "financeiro_agent",
    "tenant_id": "default",
    "payload": {
      "text": "Quero consultar meu pagamento",
      "session_id": "teste-final-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999",
      "message_id": "msg-final-001"
    }
  }'

# 7. Histórico
curl http://localhost:8000/sessions/default:financeiro_agent:teste-final-001/messages

# 8. Checkpoint
curl http://localhost:8000/sessions/default:financeiro_agent:teste-final-001/checkpoint
```

---

## 28. Agent Gateway / Global Supervisor

This chapter is a treatative apart. In an architecture with multiple agents, it is not enough to build an isolated agent backend. At some point the frontend receives a message from the user and needs to decide which agent backend should treat that conversation**.

This decision should not be spread on the frontend, nor duplicated within each agent. For this there is the **Agent Gateway**, also called here the **Global Supervisor**.

### 28.1. Before the code: What problem does Agent Gateway solve?

Imagine that the company has three independent backends:

```text
Backend Accounts
  resolve invoice, payment, consumption, duplicate, contestation

Backend Offers
  resolve plans, hiring, upgrade, retention, discount

Backend Support
  solves slow internet, signal, network, modem, technical failure
```

Without a global gateway, the frontend would have to know rules like:

```text
If the message has "invoice", call Accounts.
If the message has a plan, call Offers.
If the message has slow Internet, call Support.
```

This seems simple at first, but becomes trouble when:

- there are many agents;
- a conversation starts in Accounts and then changes to Offers;
- a message is ambiguous, like “I want to cancel”;
- each channel, Web, WhatsApp and Voice, begins to implement its own rule;
- the developer needs to keep routing, session and handoff in various places.

The **Agent Gateway** centralizes this decision.

It receives the normalized message from the channel, discovers the correct backend and forwards the request to the chosen backend.

```text
User
  ↓
Frontend / Canal
  ↓
Agent Gateway / Global Supervisor
  ↓
Backend Accounts 
```

The Gateway does not replace the agent**. It should not contain billing, offer or support business rule. He only decides who should receive the message**.

### 28.2. Difference between Agent Supervisor and Global Supervisor

Inside an agent backend, you can have a local supervisor. This supervisor decides between his own internal paths.

Example within Account Agent:

```text
Mensagem: "Minha fatura veio alta"

Supervisor local do Backend Contas decide:
  - explain invoice
  - consult payments
  - open dispute
  - call human.
```

* Global Supervisor** decides at a level above:

```text
Message: "My internet is slow"

Global Supervisor decide:
  - That's not accounts.
  - this should go to Support
```

The correct separation is:

```text
Global Supervisor / Agent Gateway
  decides the backend

Local backend supervisor
  decides the internal flow of the agent

Specialized agent
  executes business logic
```

This separation prevents the framework or gateway from being contaminated with specific details of a domain.

### 28.3. What belongs to Agent Gateway

Gateway must take care of cross-cutting responsibilities between backends:

```text
agent_gateway/
  app/main.py
    expõe /gateway/message, /gateway/events/{session_id}, /debug/route,
    /backends, /backends/health e /health

  app/settings. py
    read global gateway environment variables

  config/backends. yaml
    declares which backends exist, their URLs, domains, keywords and priority

  . env.example
    documents the routing mode, session TTL, timeout and provide LLM
```

Gateway can use framework engines to:

- global routing;
- general meeting;
- HTTP client for backends;
- supervisor LLM;
- observability;
- publication of events;
- SSE proxy.

File `agent_gateway/app/main.py`, gateway uses framework components like:

```python
from agent_framework.global_supervisor import (
    BackendClient,
    BackendRegistry,
    GlobalRouteRequest,
    GlobalSupervisorRouter,
    InMemoryGlobalSessionStore,
)
```

This means that the gateway is not creating a parallel routing mechanism. He's using his own framework layer to rule multiple backends.

### 28.4. Which doesn't belong to Agent Gateway.

Gateway should not implement specific rules such as:

```text
consultar_fatura
consultar_pagamentos
abrir_contestacao
consultar_imdb
buscar_speech_analytics
abrir_sr_siebel
calcular_pro_rata
resolver_ean
```

These features belong to specialized backends or MCP servers.

A practical rule:

```text
If logic depends on the business of a specific agent, she shouldn't stay at Gateway.
If logic decides which backend should treat the conversation, she can stay at Gateway.
```

### 28.5. Project structure `agent_gateway`

The minimum structure observed in the project is:

```text
agent_gateway/
  app/
    main.py
    settings.py
  config/
    backends.yaml
  docs/
    ARQUITETURA_GLOBAL_SUPERVISOR.md
  . env.example
  Dockerfile
  README.md
  requirements.txt
```

Each file has a clear responsibility:

| File | Responsibility |
|---|---|
| `app/main.py` | displays HTTP endpoints, calls the global router, forwards messages to backends and makes SSE proxy |
| `app/settings.py` | centralizes global gateway variables |
| `config/backends.yaml` | backends and domain/keyword routing rules available |
| `.env.example` | documents how to turn on/off routing modes and providers |
| `Dockerfile` | package gateway as separate service |
| `docs/ARQUITETURA_GLOBAL_SUPERVISOR.md` | explains the conceptual architecture |

### 28.6. As the developer must think before setting up Gateway

Before editing `config/backends.yaml`, the developer must answer four questions:

```text
1. What agent backends are there?
2. What is the responsibility domain of each backend?
3. What words or examples indicate each domain?
4. What should happen when the message is ambiguous?
```

Example:

```text
Mensagem: "Quero cancelar"
```

This message could mean:

```text
Cancel individual service → maybe Accounts or Offers
Cancel whole plan → maybe Offers or Retention
Cancel by network problem → maybe Support
```

In this case, the keyword router may not be enough. The mode `hybrid` can keep the backend active if the conversation already has context, or call the LLM supervisor if there is conflict.

### 28.7. Configuring backends in `config/backends.yaml`

The main Gateway configuration file is:

```text
agent_gateway/config/backends.yaml
```

Example:

```yaml
default_backend: contas

backends:
  contas:
    url: http://localhost:8001
    description: Backend responsável por faturas, contas, pagamentos, consumo, segunda via e contestação.
    domains: [contas, fatura, pagamento, consumo, contestacao]
    keywords: [fatura, conta, boleto, pagamento, consumo, segunda via, contestar, contestação, valor, cobrança]
    examples:
      - Quero consultar minha fatura
      - Minha conta veio alta
      - Preciso da segunda via do boleto
    priority: 10
    default_agent_id: telecom_contas

  ofertas:
    url: http://localhost:8002
    description: Backend responsável por ofertas, planos, upgrades, retenção e contratação.
    domains: [ofertas, planos, retenção, contratação]
    keywords: [oferta, plano, contratar, upgrade, desconto, promoção, pacote, retenção, cancelar serviço]
    examples:
      - Quero trocar meu plano
      - Tem alguma oferta para mim?
      - Quero cancelar um serviço
    priority: 20
    default_agent_id: telecom_ofertas

  suporte:
    url: http://localhost:8003
    description: Backend responsável por suporte técnico, falhas, rede, internet e atendimento operacional.
    domains: [suporte, técnico, rede, internet]
    keywords: [internet, sinal, rede, suporte, técnico, problema, falha, sem conexão, modem]
    examples:
      - Minha internet está lenta
      - Estou sem sinal
      - Preciso de suporte técnico
    priority: 30
    default_agent_id: telecom_suporte
```

The developer must not fill this YAML as a random list of words. He must think of ** families of intent**.

Correct example:

```text
Família: contas
  matters: invoice, payment, consumption, duplicate, contestation
```

Bad example:

```text
Family: anything that has "value"
```

The word “value” can appear in invoice, offer, discount, contestation or collection. Generic words should be used carefully.

### 28.8. Choosing global routing mode

O `.env` gateway has variable:

```env
GLOBAL_ROUTING_MODE=hybrid
```

Possible modes are:

| Mode | How do you decide? | When to use |
|---|---|---|
| `router` | uses rules, keywords, domains and priority | local development, deterministic tests, environments with low ambiguity |
| `supervisor` | uses LLM to choose backend | very similar domains or very open messages |
| `hybrid` | keeps backend active, uses rule and calls LLM in conflict | recommended for initial production |

The practical decision is:

```text
If you want full predictability, use the router.
If you want strong semantic interpretation, use supervisor.
If you want context balance, rule and LLM, use hybrid.
```

For most corporate projects, start with:

```env
GLOBAL_ROUTING_MODE=hybrid
GLOBAL_KEEP_ACTIVE_BACKEND=true
GLOBAL_USE_SUPERVISOR_ON_CONFLICT=true
GLOBAL_MIN_ROUTER_CONFIDENCE=0.55
```

### 28.9. Understanding global session and backend session

Gateway maintains a global session, for example:

```text
global_session_id = s1
```

The backend can hold another internal session, for example:

```text
backend_session_id = default:telecom_contas:s1
```

Gateway code adjusts the answer to keep both identifiers in `metadata`:

```json
{
  "session_id": "s1",
  "metadata": {
    "global_session_id": "s1",
    "backend_session_id": "default:telecom_contas:s1",
    "selected_backend": "contas"
  }
}
```

This separation is important because the user talks to a global session, but each backend may need its own internal key for memory, checkpoint and history.

### 28.9.1. How Gateway should deliver session to the backend

In order for the agent to understand where the conversation came from, Gateway must forward the session within `context.session` or in an equivalent structure normalized by the framework.

Example of conceptual payload that reaches the backend:

```json
{
  "channel": "web",
  "tenant_id": "default",
  "agent_id": "financeiro_agent",
  "payload": {
    "text": "Quero consultar meu pagamento",
    "session_id": "s1",
    "customer_id": "12345"
  },
  "context": {
    "session": {
      "global_session_id": "s1",
      "backend_session_id": "default:financeiro_agent:s1",
      "active_backend": "financeiro",
      "channel": "web",
      "tenant_id": "default",
      "metadata": {
        "selected_backend": "financeiro",
        "route_confidence": 0.82
      }
    },
    "business_context": {
      "customer_key": "12345",
      "session_key": "default:financeiro_agent:s1"
    }
  }
}
```

The developer of the agent must understand that `context.session` is not “another place to look for any parameter”. He's the continuity contract for conversation. For MCP calls, always prefer `business_context` and `tool_arguments`.

### 28.10. Up the Agent Gateway locally

Enter the gateway directory:

```bash
cd agent_gateway
```

Copy environment file:

```bash
cp .env.example .env
```

Configure `PYTHONPATH` to see the framework:

```bash
export PYTHONPATH=../agent_framework/src:.
```

Raise the service:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

Validate the health:

```bash
curl http://localhost:8010/health
```

Expected response:

```json
{
  "status": "ok",
  "app": "agent-gateway-global-supervisor",
  "routing_mode": "hybrid",
  "backends": ["contas", "ofertas", "suporte"],
  "llm_provider": "mock"
}
```

If that endpoint doesn't answer, the problem is still in the gateway, not the backends.

### 28.11. Up Agent Backends

Gateway only routes correctly if the backends configured in `backends.yaml` On your feet.

Local example:

```text
Gateway        http://localhost:8010
Contas         http://localhost:8001
Ofertas        http://localhost:8002
Suporte        http://localhost:8003
Frontend       http://localhost:5173
```

Each backend must display at least:

```text
GET  /health
POST /gateway/message
GET  /gateway/events/{session_id}
```

The endpoint `/backends/health` Gateway checks the health of backends:

```bash
curl http://localhost:8010/backends/health
```

Use this test before you blame the routing. If the backend is off the air, Gateway can even choose correctly, but will fail in forwarding.

### 28.12. Testing only the route decision

Before sending a real message to the backend, test the decision:

```bash
curl -X POST http://localhost:8010/debug/route \
  -H 'content-type: application/json' \
  -d '{
    "channel": "web",
    "payload": {
      "text": "Minha fatura veio alta",
      "session_id": "s1"
    }
  }'
```

Expected result:

```json
{
  "backend_id": "contas",
  "confidence": 0.8,
  "reason": "Backend escolhido por regras: matches=['fatura']"
}
```

The developer must interpret the result as follows:

```text
backend_id → to which backend the gateway would send the message
confidence → how strong the decision was
reason → why the decision was made
```

If the chosen backend is wrong, adjust `domains`, `keywords`, `examples`, `priority` or the routing mode.

### 28.13. Sending real message through Gateway

Once the route decision is correct, send the actual message:

```bash
curl -X POST http://localhost:8010/gateway/message \
  -H 'content-type: application/json' \
  -d '{
    "channel": "web",
    "payload": {
      "text": "Minha fatura veio alta",
      "session_id": "s1",
      "msisdn": "11999999999"
    }
  }'
```

The Gateway will do:

```text
1. Get the message.
2. Emitir IC.GLOBAL_GATEWAY_RECEIVED.
3. Create a GlobalRouteRequest.
4. Call Global SupervisorRouter.
5. Choose the backend.
6. Emitir IC.GLOBAL_BACKEND_SELECTED.
7. Forward to /gateway/message of the backend.
8. Save session active_backend.
9. Add route metadata in response.
10. Emitir IC.GLOBAL_GATEWAY_COMPLETED.
```

### 28.14. Handoff between backends

Handoff happens when a backend realizes that the conversation should change domain.

Example:

```text
User started in Accounts:
  "My invoice came high"

Depois perguntou:
  "Do you have a better plan to reduce that value?"
```

The Account backend can answer with metadata asking for exchange:

```json
{
  "metadata": {
    "handover_backend": "ofertas"
  }
}
```

Gateway detects this field and automatically calls the new backend.

The developer needs to understand that handoff is not an error. It is a controlled transition between domains.

### 28.15. Proxy SSE by Gateway

Gateway also has an endpoint:

```text
GET /gateway/events/{session_id}
```

This endpoint makes SSE proxy of the active backend.

Flow:

```text
Frontend Opens EventSource on Gateway
  ↓
Gateway Expects Global Session
  ↓
Gateway descobre active_backend
  ↓
Gateway mounts backend URL SSE
  ↓
Gateway passes the text/event-stream events to the frontend
```

Test:

```bash
curl -N http://localhost:8010/gateway/events/s1
```

Events expected at the beginning:

```text
event: connected
data: {"session_id":"s1","component":"agent_gateway"}

```

After a message is sent to `/gateway/message`The Gateway must send something like:

```text
event: backend.selected
data: {"session_id":"s1","backend_id":"contas","backend_session_id":"s1"}
```

If MIME type error appears, the active backend is probably not returning `text/event-stream` ed `/gateway/events/{session_id}`.

### 28.16. Agent Gateway CI and NOC

Gateway must issue its own events, different from the agents' internal events.

Events found in the project:

| Event | Meaning |
|---|---|
| `IC.GLOBAL_GATEWAY_RECEIVED` | Gateway received message from the channel |
| `IC.GLOBAL_BACKEND_SELECTED` | Gateway picked a backend |
| `IC.GLOBAL_BACKEND_HANDOVER` | There was a change of backend during the conversation. |
| `IC.GLOBAL_GATEWAY_COMPLETED` | Gateway completed the referral |
| `NOC.005` | Gateway operational failure or backend call |
| `NOC.006` | HTTP conclusion observed by middleware |

These events do not replace the backend CI/NOC/GRL. They complement the point-to-point view.

In a complete traceability, you should be able to see:

```text
IC.GLOBAL_GATEWAY_RECEIVED
IC.GLOBAL_BACKEND_SELECTED
IC.BACKEND_WORKFLOW_STARTED
IC.TOOL_CALLED
GRL.INPUT_STARTED
GRL.OUTPUT_COMPLETED
IC.BACKEND_WORKFLOW_COMPLETED
IC.GLOBAL_GATEWAY_COMPLETED
```

### 28.17. How to integrate the frontend with Agent Gateway

The frontend should not directly call each agent backend.

Instead, he should point to:

```text
POST http://localhost:8010/gateway/message
GET  http://localhost:8010/gateway/events/{session_id}
```

The frontend continues to send a standard message:

```json
{
  "channel": "web",
  "payload": {
    "text": "Minha fatura veio alta",
    "session_id": "s1"
  }
}
```

The frontend does not need to know if the message went to Accounts, Offers or Support. This information may appear in `metadata.selected_backend`But it shouldn't become a business rule on the frontend.

### 28:18. Gateway Build with Docker

Gateway Dockerfile uses:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY agent_framework /agent_framework
COPY agent_gateway /app
RUN pip install --no-cache-dir -e /agent_framework -r requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

This presupposes that, in the build context, there are directories:

```text
agent_framework/
agent_gateway/
```

Build:

```bash
docker build -t agent-gateway:local -f agent_gateway/Dockerfile .
```

Run:

```bash
docker run --rm -p 8010:8010 \
  --env-file agent_gateway/.env \
  agent-gateway:local
```

### 28.19. Agent Gateway implementation checklist

Before you consider Gateway ready, validate:

```text
[ ] /health responde.
[ ] /backends lista todos os backends esperados.
[ ] /backends/health consegue chamar cada backend.
[ ] /debug/route chooses the correct backend for obvious messages.
[ ] /debug/route explains the reason for the decision.
[ ] /gateway/message encaminha para o backend escolhido.
[ ] response.metadata.selected_backend aparece na resposta.
[ ] response.metadata.global_route_decision aparece na resposta.
[ ] /debug/sessions shows active_backend after first message.
[ ] /gateway/events/{session_id} retorna text/event-stream.
[ ] handoff_backend funciona quando um backend solicita troca.
[ ] IC.GLOBAL * appears in observability.
[ ] NOC.005 aparece em falhas reais de backend.
```

### 28.20. Common Agent Gateway Errors

#### Error 1: Gateway chooses wrong backend

Common causes:

```text
too generic keywords
priority misdefined
insufficient examples
GLOBAL_MIN_ROUTER_CONFIDENCE muito baixo
router mode used for ambiguous domain
```

Correction:

```text
1. Test /debug/route.
2. Read the Reason field.
3. Adjust domains, keywords and examples.
4. If you remain ambiguous, use hybrid or supervisor.
```

#### Error 2: Gateway chooses right, but returns 502

This usually means that the chosen backend is off-air or does not expose `/gateway/message`.

Test:

```bash
curl http://localhost:8001/health
curl -X POST http://localhost:8001/gateway/message \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","session_id":"s1"}}'
```

#### Error 3: SSE returns `application/json` instead of `text/event-stream`

The active backend needs to expose SSE correctly.

Direct test on the backend:

```bash
curl -i -N http://localhost:8001/gateway/events/s1
```

The expected header is:

```text
content-type: text/event-stream
```

#### Error 4: Global session exists, but active backend does not appear

Check:

```bash
curl http://localhost:8010/debug/sessions
```

Then send a message by `/gateway/message`. O `active_backend` is only set after Gateway route a message successfully.

### 28.21. How to explain this architecture to a new developer

A simple way to teach is:

```text
The agent's backend can solve some kind of problem.
Gateway knows how to choose which backend to solve the problem.
The framework provides reusable engines for both.
```

Therefore, when implementing a new agent, the developer must make two integrations:

```text
1. Criar o backend especializado usando agent_template_backend.
2. Registrar esse backend no agent_gateway/config/backends.yaml.
```

He should not alter the frontend for each new agent. You shouldn't put the new agent's business rule inside Gateway either.


---

## 29. Conclusion

O `agent_template_backend` provides the corporate backbone to new agents. The implementation of a new agent should be limited to the domain: prompts, rules, tools, clients, schemas and specific decisions.

The correct pattern is:

```text
Framework = reusable engine
Agent = Business customization
MCP = standardized boundary with external systems
Config YAML = configurable behavior without touching the engine
CI/NOC/GRL = corporate traceability
```

A developer should not only copy files. He must understand that each change represents an architectural decision:

```text
Create Agent → defines domain logic.
Register workflow → makes the agent executable by LangGraph.
Adjust state → shares data between us.
Configure agents → declares the agent for the framework.
Configure routing → teaches the framework when calling the agent.
Configure tools → declares external capabilities.
Configure MCP → connects tools to systems or mocks.
Configure identity→ normalizes business keys.
Issue IC/NOC/GRL → makes execution auditable.
Test gateway → validates the end real flow in order.
```

Following this model, new agents can be created with simpler standardization, scalability, traceability and maintenance.


## 30. Final delivery with Agent Gateway

At the end of the implementation, the recommended delivery must contain four clearly separated projects or directories:

```text
agent_framework/
  reusable library with workflow engines, routing, guardrails,
  judges, supervisor, memory, checkpoint, observability and MCP tool router

agent_template_backend/
  specialized backend of an agent, with domain, prompts, tools,
  state, workflow and own settings

agent_gateway/
  global supervisor routing conversations between multiple agent backends

agent_frontend/
  Web interface, WhatsApp or Voice chatting with Agent Gateway
```

The correct relationship is:

```text
Frontend
  Call Agent Gateway

Agent Gateway
  choose backend

Agent Backend
  performs the specialized workflow

MCP Server
  executes or simulates business tools

Framework
  provides reusable engines for gateway and backends
```

### 30.1. Local startup end sequence

A complete local sequence can be:

```bash
# 1. Subir MCP do agente, se existir
cd mcp_servers/meu_agente_mcp
uvicorn app.main:app --host 0.0.0.0 --port 9001 --reload

# 2. Subir backend do agente Contas
cd agent_template_backend
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# 3. Subir Agent Gateway
cd agent_gateway
cp .env.example .env
export PYTHONPATH=../agent_framework/src:.
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# 4. Subir frontend
cd agent_frontend
npm install
npm run dev
```

### 30.2. Final test sequence

```bash
# Gateway vivo
curl http://localhost:8010/health

# Backends registrados
curl http://localhost:8010/backends

# Saúde dos backends
curl http://localhost:8010/backends/health

# Decisão de rota
curl -X POST http://localhost:8010/debug/route \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"Minha fatura veio alta","session_id":"s1"}}'

# Mensagem real ponta a ponta
curl -X POST http://localhost:8010/gateway/message \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"Minha fatura veio alta","session_id":"s1","msisdn":"11999999999"}}'

# Sessões globais
curl http://localhost:8010/debug/sessions

# SSE pelo Gateway
curl -N http://localhost:8010/gateway/events/s1
```

### 30.3. Architecture Acceptance Criteria

The implementation is architecturally correct when:

```text
[ ] the frontend does not know individual URLs of agent backends;
[ ] Gateway does not contain specific business rule of invoice, offer or support;
[ ] each backend remains independent;
[ ] each backend uses the framework engines;
[ ] Gateway uses the Global SupervisorRouter framework;
[ ] the overall routing is observable;
[ ] each backend exchange generates metadata and handoff event;
[ ] MCP servers remain plugable by backend/agent;
[ ] the global session and the backend session are preserved in the metadata;
[ ] the developer can test route before testing actual execution.
```

With this drawing, adding a new agent does not require rewriting the frontend or copying logic between backends. The developer creates the specialized backend, registers with Agent Gateway and lets the framework handle the transverse engines.
