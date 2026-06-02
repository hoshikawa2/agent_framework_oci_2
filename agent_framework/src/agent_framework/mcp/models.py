from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

class MCPServerConfig(BaseModel):
    name: str
    transport: Literal["http"] = "http"
    endpoint: str
    enabled: bool = True
    description: str = ""

class MCPToolConfig(BaseModel):
    name: str
    description: str = ""
    mcp_server: str
    enabled: bool = True
    args_schema: dict[str, Any] = Field(default_factory=dict)

class MCPToolResult(BaseModel):
    tool_name: str
    server_name: str
    ok: bool
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
