from __future__ import annotations

import hashlib
from typing import Any


class AgentRuntimeMixin:
    """Mixin operacional para agentes.

    Integra RAG, cache, telemetria e chamadas MCP usando BusinessContext.
    Os agentes não precisam conhecer nomes reais de parâmetros do domínio
    (msisdn, invoice_id, order_id etc.); eles repassam as chaves canônicas e
    o MCPParameterMapper converte para cada tool configurada.
    """

    async def _retrieve_rag_context(self, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        rag_service = getattr(self, "rag_service", None)
        if not rag_service:
            return "", {"enabled": False}
        text = state.get("sanitized_input") or state.get("user_text") or ""
        namespace = (
            (state.get("agent_profile") or {}).get("rag_namespace")
            or state.get("agent_id")
            or state.get("route")
            or "default"
        )
        ctx = state.get("context") or {}
        business_context = ctx.get("business_context") or {}
        graph_node = (
            ctx.get("graph_node")
            or business_context.get("customer_key")
            or business_context.get("contract_key")
            or ctx.get("customer_id")
        )
        result = await rag_service.retrieve(text, namespace=namespace, graph_node=graph_node)
        context = result.as_prompt_context()
        return context, {
            "enabled": True,
            "namespace": namespace,
            "latency_ms": result.latency_ms,
            "document_count": len(result.documents),
            "graph_neighbors": len(result.graph_neighbors),
            "top_document_ids": [d.id for d in result.documents[:5]],
            "top_scores": [d.score for d in result.documents[:5]],
        }

    async def _collect_mcp_context(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if not getattr(self, "tool_router", None):
            return results
        tools = state.get("mcp_tools") or []
        ctx = state.get("context") or {}
        business_context = ctx.get("business_context") or state.get("business_context") or {}
        original_context = {
            **ctx,
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "conversation_key": state.get("conversation_key") or state.get("session_id"),
        }
        for tool in tools:
            res = await self.tool_router.call(
                tool,
                {},
                business_context=business_context,
                original_context=original_context,
            )
            results.append(res.model_dump(mode="json"))
        return results

    async def _cache_get(self, key: str):
        cache = getattr(self, "cache", None)
        if not cache:
            return None
        return await cache.get(key)

    async def _cache_set(self, key: str, value: Any, ttl_seconds: int | None = None):
        cache = getattr(self, "cache", None)
        if not cache:
            return
        await cache.set(key, value, ttl_seconds)

    def _llm_cache_key(self, state: dict[str, Any], agent_name: str, prompt_parts: list[Any]) -> str:
        business_context = (state.get("context") or {}).get("business_context") or {}
        raw = "|".join([
            agent_name,
            state.get("tenant_id") or "",
            state.get("agent_id") or "",
            state.get("intent") or "",
            business_context.get("customer_key") or "",
            business_context.get("contract_key") or "",
            business_context.get("interaction_key") or "",
            state.get("sanitized_input") or state.get("user_text") or "",
            repr(prompt_parts),
        ])
        return "llm:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _invoke_llm_cached(self, state: dict[str, Any], agent_name: str, messages: list[dict[str, str]]):
        ttl = int(getattr(getattr(self, "settings", None), "CACHE_TTL_SECONDS", 300) or 300)
        key = self._llm_cache_key(state, agent_name, messages)
        cached = await self._cache_get(key)
        if cached is not None:
            telemetry = getattr(self, "telemetry", None)
            if telemetry:
                await telemetry.event("cache.llm.hit", {"agent": agent_name, "key": key}, kind="cache")
            return cached
        telemetry = getattr(self, "telemetry", None)
        if telemetry:
            await telemetry.event("cache.llm.miss", {"agent": agent_name, "key": key}, kind="cache")
        answer = await self.llm.ainvoke(messages)
        await self._cache_set(key, answer, ttl)
        return answer
