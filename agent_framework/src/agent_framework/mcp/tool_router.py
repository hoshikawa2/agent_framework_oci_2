from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent_framework.identity import MCPParameterMapper

from .registry import MCPRegistry
from .client import MCPHttpClient
from .models import MCPToolResult

logger = logging.getLogger("agent_framework.mcp.tool_router")


_EMPTY_VALUES = (None, "", {}, [])


class MCPToolRouter:
    """Roteia chamadas de tools para MCP Servers configurados.

    Também aplica, de forma centralizada, o mapper de chaves canônicas do
    framework para parâmetros reais do MCP Server. Assim os agentes podem
    trabalhar com customer_key/contract_key/etc. e o domínio TIM recebe
    msisdn/invoice_id/customer_id conforme YAML.

    Além disso, suporta extração de argumentos adicionais por tool, configurada
    no mcp_parameter_mapping.yaml. Extrações determinísticas ficam no mapper;
    extrações LLM são executadas aqui, imediatamente antes da chamada MCP.
    """

    def __init__(self, settings, telemetry=None, llm=None):
        self.settings = settings
        self.telemetry = telemetry
        self.llm = llm
        self.enabled = bool(getattr(settings, "ENABLE_MCP_TOOLS", True))
        self.registry = MCPRegistry(
            settings.MCP_SERVERS_CONFIG_PATH,
            settings.TOOLS_CONFIG_PATH,
        )
        self.client = MCPHttpClient(timeout_seconds=settings.MCP_TOOL_TIMEOUT_SECONDS)
        self.parameter_mapper = MCPParameterMapper.from_yaml(
            getattr(settings, "MCP_PARAMETER_MAPPING_PATH", "./config/mcp_parameter_mapping.yaml")
        )
        logger.info(
            "MCPToolRouter carregado enabled=%s servers=%s tools=%s mapper=%s llm_extract=%s",
            self.enabled,
            list(self.registry.servers.keys()),
            list(self.registry.tools.keys()),
            getattr(settings, "MCP_PARAMETER_MAPPING_PATH", None),
            bool(self.llm),
        )

    def describe_tools(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        return self.registry.describe_tools(tool_names)

    @staticmethod
    def _is_present(value: Any) -> bool:
        return value not in _EMPTY_VALUES

    @staticmethod
    def _json_from_text(text: str) -> dict[str, Any]:
        """Extrai um objeto JSON de uma resposta LLM."""
        if not text:
            return {}
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            pass
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        try:
            obj = json.loads(match.group(0))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _coerce_value(value: Any, value_type: str | None) -> Any:
        if value in _EMPTY_VALUES:
            return None
        typ = str(value_type or "").strip().lower()
        if typ == "int":
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        if typ in {"str", "string"}:
            return str(value)
        if typ in {"float", "number"}:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        if typ in {"bool", "boolean"}:
            if isinstance(value, bool):
                return value
            normalized = str(value).strip().lower()
            if normalized in {"true", "sim", "yes", "1"}:
                return True
            if normalized in {"false", "nao", "não", "no", "0"}:
                return False
            return None
        return value

    @staticmethod
    def _is_llm_extractor(spec: Any) -> bool:
        if isinstance(spec, str):
            return spec.strip().lower() in {"llm", "llm_json", "semantic", "llm_entity"}
        if not isinstance(spec, dict):
            return False
        strategy = str(spec.get("strategy") or spec.get("extractor") or "").strip().lower()
        return (
            strategy in {"llm", "llm_json", "semantic", "llm_entity"}
            or bool(spec.get("llm"))
            or bool(spec.get("use_llm"))
        )

    def _ensure_llm(self) -> Any:
        """Garante um LLM disponível para extractors declarados no YAML.

        A extração só acontece quando a tool escolhida possui `extract` em
        mcp_parameter_mapping.yaml e o extractor está configurado para LLM
        (`strategy: llm`, `llm_json`, `semantic` ou `use_llm: true`).
        Não há fallback hardcoded por campo ou por domínio.
        """
        if self.llm:
            return self.llm
        try:
            from agent_framework.llm.providers import create_llm

            self.llm = create_llm(self.settings, telemetry=self.telemetry)
            logger.info("mcp.parameter.llm_provider.lazy_loaded provider=%s", type(self.llm).__name__)
        except Exception as exc:
            logger.warning("mcp.parameter.llm_provider.unavailable error=%r", exc)
            self.llm = None
        return self.llm

    async def _apply_llm_extractors(
        self,
        tool_name: str,
        mapped_arguments: dict[str, Any],
        *,
        original_context: dict[str, Any],
    ) -> None:
        """Executa extractors declarativos da tool já selecionada.

        Fluxo desejado:
          1. Router escolhe a tool MCP.
          2. MCPParameterMapper aplica `map`/defaults.
          3. Se a tool possuir `extract` no YAML, executa as extrações LLM.
          4. Injeta os campos extraídos em `mapped_arguments` antes da chamada MCP.

        Este método não possui regra específica de mês, fatura ou domínio. A
        semântica do campo vem exclusivamente de `mcp_parameter_mapping.yaml`.
        """
        extractors = self.parameter_mapper.get_extractors(tool_name)
        if not extractors:
            return

        llm_extractors = {
            field_name: spec
            for field_name, spec in extractors.items()
            if self._is_llm_extractor(spec)
        }
        if not llm_extractors:
            return

        llm = self._ensure_llm()
        if not llm:
            logger.warning(
                "mcp.parameter.llm_extract_skipped tool=%s reason=llm_unavailable fields=%s",
                tool_name,
                sorted(llm_extractors.keys()),
            )
            return

        for field_name, spec in llm_extractors.items():
            spec_dict = spec if isinstance(spec, dict) else {"strategy": spec}
            target_field = str(spec_dict.get("target") or field_name)
            override = bool(spec_dict.get("override", False))
            if not override and self._is_present(mapped_arguments.get(target_field)):
                continue

            source = spec_dict.get("from") or spec_dict.get("source") or "message"
            text = self.parameter_mapper.resolve_source_text(
                source,
                args=mapped_arguments,
                original_context=original_context,
            )
            if not text:
                logger.info(
                    "mcp.parameter.llm_extract_skipped tool=%s field=%s reason=empty_source",
                    tool_name,
                    target_field,
                )
                continue

            description = spec_dict.get("description") or spec_dict.get("prompt") or ""
            allowed_values = spec_dict.get("allowed_values") or spec_dict.get("enum")
            value_type = str(spec_dict.get("type") or "").strip() or "string"
            system_prompt = (
                "Você é um extrator de parâmetros para chamada de ferramenta MCP. "
                "Use exclusivamente a definição do campo fornecida pelo YAML. "
                "Responda somente JSON válido, sem markdown. "
                "Se o valor não estiver presente no texto, use null."
            )
            user_prompt = {
                "tool_name": tool_name,
                "field": target_field,
                "type": value_type,
                "description": description,
                "allowed_values": allowed_values,
                "text": text,
                "expected_output": {target_field: "value_or_null"},
            }
            try:
                raw = await llm.ainvoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                    ],
                    profile_name=spec_dict.get("profile_name") or "router",
                    component_name="mcp_parameter_extractor",
                    generation_name=f"llm.mcp_parameter_extractor.{tool_name}.{target_field}",
                    temperature=0,
                )
                parsed = self._json_from_text(str(raw))
                value = self._coerce_value(parsed.get(target_field), value_type)
                if self._is_present(value):
                    mapped_arguments[target_field] = value
                    logger.info(
                        "mcp.parameter.llm_extracted tool=%s field=%s value=%s",
                        tool_name,
                        target_field,
                        value,
                    )
                else:
                    logger.info(
                        "mcp.parameter.llm_extracted_null tool=%s field=%s",
                        tool_name,
                        target_field,
                    )
            except Exception as exc:
                logger.warning(
                    "mcp.parameter.llm_extract_failed tool=%s field=%s error=%r",
                    tool_name,
                    target_field,
                    exc,
                )

    def _mapped_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        business_context: dict[str, Any] | None = None,
        original_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        args = dict(arguments or {})
        ctx = business_context or args.get("business_context") or args.get("identity") or {}
        original = dict(original_context or {})

        # Preserva também o que veio junto dos argumentos, pois em alguns fluxos
        # o business_context vem dentro de arguments.
        for k, v in args.items():
            original.setdefault(k, v)

        mapped = self.parameter_mapper.map(
            tool_name,
            ctx,
            original_context=original,
            extra_args=args,
        )
        mapped.pop("business_context", None)
        mapped.pop("identity", None)
        return mapped

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        business_context: dict[str, Any] | None = None,
        original_context: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        if not self.enabled:
            return MCPToolResult(tool_name=tool_name, server_name="disabled", ok=False, error="MCP tools disabled")

        server = self.registry.get_server_for_tool(tool_name)
        if not server:
            return MCPToolResult(tool_name=tool_name, server_name="unknown", ok=False, error="Tool/server not configured")

        mapped_arguments = self._mapped_arguments(
            tool_name,
            arguments,
            business_context=business_context,
            original_context=original_context,
        )

        # Extrações LLM são executadas depois do mapeamento determinístico e antes
        # da chamada MCP, quando a tool já foi escolhida pelo router.
        original_for_extract = dict(original_context or {})
        original_for_extract.update(arguments or {})
        await self._apply_llm_extractors(
            tool_name,
            mapped_arguments,
            original_context=original_for_extract,
        )

        logger.info(
            "mcp.tool.mapped tool=%s server=%s keys=%s has_msisdn=%s has_invoice_id=%s",
            tool_name,
            server.name,
            sorted(mapped_arguments.keys()),
            bool(mapped_arguments.get("msisdn")),
            bool(mapped_arguments.get("invoice_id") or mapped_arguments.get("current_invoice_number")),
        )

        if self.telemetry:
            async with self.telemetry.span(
                "mcp.tool_call",
                tool_name=tool_name,
                mcp_server=server.name,
                input=mapped_arguments,
                tags=["mcp", "tool"],
            ):
                result = await self.client.call_tool(server, tool_name, mapped_arguments)
                await self.telemetry.event(
                    "mcp.tool_call.completed",
                    {
                        "tool_name": tool_name,
                        "server": server.name,
                        "ok": result.ok,
                        "error": result.error,
                    },
                )
                return result

        return await self.client.call_tool(server, tool_name, mapped_arguments)


def create_mcp_tool_router(settings, telemetry=None, llm=None) -> MCPToolRouter:
    return MCPToolRouter(settings, telemetry=telemetry, llm=llm)
