from __future__ import annotations
import logging
from typing import Any
import httpx
from .models import MCPServerConfig, MCPToolResult

logger = logging.getLogger("agent_framework.mcp.client")

class MCPHttpClient:
    """Cliente HTTP simples para MCP Server de exemplo.

    Contrato do servidor de exemplo:
    - GET  /mcp/tools/list
    - POST /mcp/tools/call  {"tool_name": "...", "arguments": {...}}

    Este contrato é propositalmente simples para facilitar testes locais. Em
    produção, substitua por client MCP oficial/streamable HTTP/SSE quando o
    padrão interno estiver definido.
    """
    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    async def list_tools(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        url = server.endpoint.rstrip("/") + "/tools/list"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("tools", data if isinstance(data, list) else [])

    async def call_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        url = server.endpoint.rstrip("/") + "/tools/call"
        payload = {"tool_name": tool_name, "arguments": arguments or {}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return MCPToolResult(
                    tool_name=tool_name,
                    server_name=server.name,
                    ok=bool(data.get("ok", True)),
                    result=data.get("result"),
                    error=data.get("error"),
                    metadata=data.get("metadata", {}),
                )
        except Exception as exc:
            logger.exception("Erro ao chamar MCP tool %s em %s", tool_name, server.endpoint)
            return MCPToolResult(
                tool_name=tool_name,
                server_name=server.name,
                ok=False,
                error=str(exc),
            )
