from __future__ import annotations

import logging
from typing import Any

import httpx

from .models import MCPServerConfig, MCPToolResult

logger = logging.getLogger("agent_framework.mcp.client")


class MCPHttpClient:
    """MCP client with two compatible modes.

    - transport=http keeps the framework's legacy simple contract:
      GET  <endpoint>/tools/list
      POST <endpoint>/tools/call {"tool_name": "...", "arguments": {...}}

    - transport=fastmcp|streamable_http|sse uses the official MCP Python client
      and can call FastMCP servers directly.
    """

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    async def list_tools(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        if server.transport in {"fastmcp", "streamable_http", "sse"}:
            return await self._list_fastmcp_tools(server)
        return await self._list_legacy_http_tools(server)

    async def call_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        if server.transport in {"fastmcp", "streamable_http", "sse"}:
            return await self._call_fastmcp_tool(server, tool_name, arguments or {})
        return await self._call_legacy_http_tool(server, tool_name, arguments or {})

    async def _list_legacy_http_tools(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        url = server.endpoint.rstrip("/") + "/tools/list"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("tools", data if isinstance(data, list) else [])

    async def _call_legacy_http_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
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
                    metadata={"transport": server.transport, **(data.get("metadata", {}) or {})},
                )
        except Exception as exc:
            logger.exception("Erro ao chamar MCP tool %s em %s", tool_name, server.endpoint)
            return MCPToolResult(
                tool_name=tool_name,
                server_name=server.name,
                ok=False,
                error=str(exc),
                metadata={"transport": server.transport},
            )

    async def _open_fastmcp_session(self, server: MCPServerConfig):
        """Return an async context manager yielding an initialized MCP session."""
        try:
            from mcp import ClientSession
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            raise RuntimeError(
                "FastMCP transport requires the optional package 'mcp'. "
                "Install with: pip install 'mcp>=1.9.0'"
            ) from exc

        if server.transport == "sse":
            try:
                from mcp.client.sse import sse_client
            except Exception as exc:  # pragma: no cover
                raise RuntimeError("MCP SSE client is unavailable in the installed mcp package") from exc

            class _SSESessionCM:
                async def __aenter__(self_inner):
                    self_inner.stream_cm = sse_client(server.endpoint, timeout=self.timeout_seconds)
                    read, write = await self_inner.stream_cm.__aenter__()
                    self_inner.session = ClientSession(read, write)
                    await self_inner.session.__aenter__()
                    await self_inner.session.initialize()
                    return self_inner.session

                async def __aexit__(self_inner, exc_type, exc, tb):
                    await self_inner.session.__aexit__(exc_type, exc, tb)
                    await self_inner.stream_cm.__aexit__(exc_type, exc, tb)

            return _SSESessionCM()

        try:
            from mcp.client.streamable_http import streamablehttp_client
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("MCP streamable HTTP client is unavailable in the installed mcp package") from exc

        class _StreamableHTTPSessionCM:
            async def __aenter__(self_inner):
                self_inner.stream_cm = streamablehttp_client(server.endpoint, timeout=self.timeout_seconds)
                streams = await self_inner.stream_cm.__aenter__()
                # Newer mcp returns (read, write, get_session_id); older returns (read, write).
                read, write = streams[0], streams[1]
                self_inner.session = ClientSession(read, write)
                await self_inner.session.__aenter__()
                await self_inner.session.initialize()
                return self_inner.session

            async def __aexit__(self_inner, exc_type, exc, tb):
                await self_inner.session.__aexit__(exc_type, exc, tb)
                await self_inner.stream_cm.__aexit__(exc_type, exc, tb)

        return _StreamableHTTPSessionCM()

    @staticmethod
    def _content_to_python(content: Any) -> Any:
        if content is None:
            return None
        if not isinstance(content, list):
            return content
        out: list[Any] = []
        for item in content:
            if hasattr(item, "model_dump"):
                dumped = item.model_dump(exclude_none=True)
                if dumped.get("type") == "text" and "text" in dumped:
                    out.append(dumped["text"])
                else:
                    out.append(dumped)
            elif hasattr(item, "text"):
                out.append(getattr(item, "text"))
            else:
                out.append(item)
        if len(out) == 1:
            return out[0]
        return out

    async def _list_fastmcp_tools(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        cm = await self._open_fastmcp_session(server)
        async with cm as session:
            response = await session.list_tools()
            tools = getattr(response, "tools", response)
            result = []
            for tool in tools or []:
                if hasattr(tool, "model_dump"):
                    data = tool.model_dump(exclude_none=True)
                else:
                    data = dict(tool)
                result.append({
                    "name": data.get("name"),
                    "description": data.get("description", ""),
                    "input_schema": data.get("inputSchema") or data.get("input_schema") or {},
                })
            return result

    async def _call_fastmcp_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        try:
            cm = await self._open_fastmcp_session(server)
            async with cm as session:
                response = await session.call_tool(tool_name, arguments=arguments or {})
                is_error = bool(getattr(response, "isError", False) or getattr(response, "is_error", False))
                content = self._content_to_python(getattr(response, "content", response))
                return MCPToolResult(
                    tool_name=tool_name,
                    server_name=server.name,
                    ok=not is_error,
                    result=content,
                    error=str(content) if is_error else None,
                    metadata={"transport": server.transport, "endpoint": server.endpoint},
                )
        except Exception as exc:
            logger.exception("Erro ao chamar FastMCP tool %s em %s", tool_name, server.endpoint)
            return MCPToolResult(
                tool_name=tool_name,
                server_name=server.name,
                ok=False,
                error=str(exc),
                metadata={"transport": server.transport, "endpoint": server.endpoint},
            )
