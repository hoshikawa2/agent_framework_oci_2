from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin

class SupportAgent(AgentRuntimeMixin):
    name = "support_agent"

    def __init__(self, llm, telemetry=None, tool_router=None, rag_service=None, cache=None, settings=None, observer=None):
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings
        self.observer = observer

    async def run(self, state):
        await self._emit_ic(
            "IC.SUPPORT_AGENT_STARTED",
            state,
            {"business_component": "suporte"},
            component="agent.support.start",
        )
        tool_context = await self._collect_tool_context(state)
        if tool_context:
            await self._emit_ic(
                "IC.SUPPORT_MCP_CONTEXT_COLLECTED",
                state,
                {"tool_result_count": len(tool_context)},
                component="agent.support.mcp",
            )
        rag_context, rag_metadata = await self._retrieve_rag_context(state)
        if rag_metadata.get("enabled"):
            await self._emit_ic(
                "IC.SUPPORT_RAG_CONTEXT_RETRIEVED",
                state,
                {
                    "document_count": rag_metadata.get("document_count"),
                    "graph_neighbors": rag_metadata.get("graph_neighbors"),
                    "latency_ms": rag_metadata.get("latency_ms"),
                },
                component="agent.support.rag",
            )
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
        result = {"answer": f"[SupportAgent] {answer}", "next_state": "SUPPORT_ACTIVE", "mcp_results": tool_context, "rag": rag_metadata}
        await self._emit_ic(
            "IC.SUPPORT_AGENT_COMPLETED",
            state,
            {
                "answer_chars": len(result.get("answer") or ""),
                "has_mcp_results": bool(tool_context),
                "rag_enabled": bool(rag_metadata.get("enabled")),
            },
            component="agent.support.completed",
        )
        return result

    async def _collect_tool_context(self, state):
        return await self._collect_mcp_context(state)
