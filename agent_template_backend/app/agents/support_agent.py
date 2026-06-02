from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin

class SupportAgent(AgentRuntimeMixin):
    name = "support_agent"

    def __init__(self, llm, telemetry=None, tool_router=None, rag_service=None, cache=None, settings=None):
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings

    async def run(self, state):
        tool_context = await self._collect_tool_context(state)
        rag_context, rag_metadata = await self._retrieve_rag_context(state)
        messages = [
            {"role": "system", "content": apply_agent_profile_prompt(state, "Você é um agente de suporte de varejo para troca, devolução e garantia.")},
            {"role": "user", "content": (
                f"Mensagem: {state.get('sanitized_input') or state['user_text']}\n"
                f"Intent: {state.get('intent')}\n"
                f"Dados MCP: {tool_context}\n"
                f"Contexto RAG: {rag_context}"
            )},
        ]
        answer = await self._invoke_llm_cached(state, "SupportAgent", messages)
        return {"answer": f"[SupportAgent] {answer}", "next_state": "SUPPORT_ACTIVE", "mcp_results": tool_context, "rag": rag_metadata}

    async def _collect_tool_context(self, state):
        return await self._collect_mcp_context(state)
