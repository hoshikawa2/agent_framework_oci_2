"""
DAY ZERO TEMPLATE - OrdersAgent

Este arquivo foi copiado do agent_template_backend original.
A implementação de exemplo do agente foi comentada ao final do arquivo.

Como usar:
1. Mantenha o nome da classe se quiser reaproveitar o workflow atual sem mexer no graph.
2. Substitua o método run() pela lógica do seu agente.
3. Use AgentRuntimeMixin para reaproveitar MCP, RAG, cache e chamada LLM com telemetria.
4. Quando criar um agente real, remova o bloco "IMPLEMENTAÇÃO ORIGINAL COMENTADA" se não precisar mais da referência.
"""

from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin


class OrdersAgent(AgentRuntimeMixin):
    """Esqueleto de agente para desenvolvimento Day Zero.

    Este agente está propositalmente mínimo. O código real do exemplo original
    permanece comentado abaixo para o desenvolvedor copiar/adaptar.
    """

    name = "orders_agent"

    def __init__(self, llm, telemetry=None, tool_router=None, rag_service=None, cache=None, settings=None):
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings

    async def run(self, state):
        """Implemente aqui a regra de negócio do seu agente.

        Exemplo mínimo:
        - lê a mensagem sanitizada do usuário;
        - monta mensagens para o LLM;
        - chama _invoke_llm_cached();
        - retorna answer e next_state.
        """

        user_text = state.get("sanitized_input") or state.get("user_text", "")

        # OPCIONAL: descomente quando seu agente precisar de tools MCP.
        # tool_context = await self._collect_tool_context(state)

        # OPCIONAL: descomente quando seu agente precisar de RAG.
        # rag_context, rag_metadata = await self._retrieve_rag_context(state)

        messages = [
            {
                "role": "system",
                "content": apply_agent_profile_prompt(
                    state,
                    "Você é um agente de exemplo. Substitua este prompt pelo papel do seu agente.",
                ),
            },
            {
                "role": "user",
                "content": f"Mensagem do usuário: {user_text}",
            },
        ]

        answer = await self._invoke_llm_cached(state, "OrdersAgent", messages)

        return {
            "answer": answer,
            "next_state": "DAY_ZERO_ACTIVE",
            # "mcp_results": tool_context,
            # "rag": rag_metadata,
        }

    async def _collect_tool_context(self, state):
        """Atalho para MCP. Mantenha se seu agente for chamar tools MCP."""
        return await self._collect_mcp_context(state)


# ============================================================================
# IMPLEMENTAÇÃO ORIGINAL COMENTADA - EXEMPLO DE AGENTE DE PEDIDOS
# ============================================================================
# O bloco abaixo é o código original do template completo.
# Ele está comentado para servir de referência ao desenvolvedor.
# Copie trechos para o método run() acima quando fizer sentido.
# ============================================================================

# from app.agents.prompting import apply_agent_profile_prompt
# from app.agents.runtime import AgentRuntimeMixin
#
# class OrdersAgent(AgentRuntimeMixin):
#     name = "orders_agent"
#
#     def __init__(self, llm, telemetry=None, tool_router=None, rag_service=None, cache=None, settings=None):
#         self.llm = llm
#         self.telemetry = telemetry
#         self.tool_router = tool_router
#         self.rag_service = rag_service
#         self.cache = cache
#         self.settings = settings
#
#     async def run(self, state):
#         session = (state.get("context") or {}).get("session", {})
#         tool_context = await self._collect_tool_context(state)
#         rag_context, rag_metadata = await self._retrieve_rag_context(state)
#         messages = [
#             {"role": "system", "content": apply_agent_profile_prompt(state, "Você é um agente de pedidos de varejo. Use dados de tools quando disponíveis.")},
#             {"role": "user", "content": (
#                 f"Mensagem: {state.get('sanitized_input') or state['user_text']}\n"
#                 f"Sessão: {session}\n"
#                 f"Intent: {state.get('intent')}\n"
#                 f"Dados MCP: {tool_context}\n"
#                 f"Contexto RAG: {rag_context}"
#             )},
#         ]
#         answer = await self._invoke_llm_cached(state, "OrdersAgent", messages)
#         return {"answer": f"[OrdersAgent] {answer}", "next_state": "ORDER_ACTIVE", "mcp_results": tool_context, "rag": rag_metadata}
#
#     async def _collect_tool_context(self, state):
#         return await self._collect_mcp_context(state)
