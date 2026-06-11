from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import BusinessContext


class MCPParameterMapper:
    """Mapeia BusinessContext para parâmetros reais de cada tool MCP.

    Responsabilidade deste mapper:
    - converter chaves canônicas do framework para nomes esperados pela tool MCP;
    - aplicar defaults declarados em mcp_parameter_mapping.yaml;
    - expor metadados de extractors declarativos para o MCPToolRouter.

    Este componente NÃO conhece semântica de campos específicos.
    Qualquer extração de parâmetro adicional deve ser declarada no YAML da tool
    e executada por um mecanismo genérico, normalmente LLM, no MCPToolRouter.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        root = self.config.get("mcp_parameter_mapping") or self.config
        self.tools = root.get("tools") or {}
        self.defaults = root.get("defaults") or {}
        self.global_extract = root.get("extract") or root.get("entity_map") or {}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MCPParameterMapper":
        p = Path(path)
        if not p.exists():
            return cls({})
        return cls(yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    @staticmethod
    def _is_present(value: Any) -> bool:
        return value not in (None, "", {}, [])

    def _resolve_source_text(
        self,
        source: str | list[str] | tuple[str, ...] | None,
        *,
        args: dict[str, Any],
        original_context: dict[str, Any],
    ) -> str:
        """Obtém o texto-fonte para extrações declarativas.

        `from: message` procura pelos nomes comuns usados pelo framework para a
        mensagem original, sem interpretar o conteúdo semanticamente.
        """
        if source in (None, "", "message"):
            candidates = ["message", "query", "operator_instructions", "text", "user_text"]
        elif isinstance(source, (list, tuple)):
            candidates = list(source)
        else:
            candidates = [str(source)]

        for key in candidates:
            value = original_context.get(key)
            if not self._is_present(value):
                value = args.get(key)
            if self._is_present(value):
                return str(value)
        return ""

    def get_extractors(self, tool_name: str) -> dict[str, Any]:
        """Retorna extractors declarados para a tool.

        O mapper apenas lê a configuração. A execução das extrações ocorre no
        MCPToolRouter, depois que a tool já foi escolhida e antes da chamada MCP.
        """
        rule = self.tools.get(tool_name) or {}
        extractors: dict[str, Any] = {}
        extractors.update(self.global_extract or {})
        extractors.update(rule.get("extract") or {})
        extractors.update(rule.get("entity_map") or {})
        return extractors

    def resolve_source_text(
        self,
        source: str | list[str] | tuple[str, ...] | None,
        *,
        args: dict[str, Any],
        original_context: dict[str, Any],
    ) -> str:
        """API pública usada pelo MCPToolRouter para extrações genéricas."""
        return self._resolve_source_text(source, args=args, original_context=original_context)

    def map(
        self,
        tool_name: str,
        business_context: BusinessContext | dict[str, Any] | None,
        *,
        original_context: dict[str, Any] | None = None,
        extra_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = business_context if isinstance(business_context, BusinessContext) else BusinessContext.from_mapping(business_context or {})
        original_context = dict(original_context or {})
        args = {k: v for k, v in (extra_args or {}).items() if self._is_present(v)}
        rule = self.tools.get(tool_name) or {}
        mappings = dict(rule.get("map") or {})

        # Também aceita formato simples: customer_key: msisdn
        for src_key, target in rule.items():
            if src_key in {"map", "defaults", "required", "extract", "entity_map"}:
                continue
            mappings.setdefault(src_key, target)

        for canonical_key, target_field in mappings.items():
            value = getattr(ctx, canonical_key, None)
            if self._is_present(value):
                args[str(target_field)] = value

        for key, value in {**self.defaults, **(rule.get("defaults") or {})}.items():
            args.setdefault(key, value)

        # Preserva parâmetros específicos já capturados no canal, sem o framework
        # conhecer seus nomes ou interpretar seus valores.
        for key, value in original_context.items():
            if key not in args and self._is_present(value):
                args[key] = value
        return args
