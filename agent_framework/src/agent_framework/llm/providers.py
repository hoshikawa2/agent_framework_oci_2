from __future__ import annotations

import logging
from typing import Any

from .base import LLMProvider
from agent_framework.observability.token_cost import TokenUsageCollector
from agent_framework.billing.usage_repository import UsageRepository, UsageRecord

logger = logging.getLogger("agent_framework.llm")


class MockLLMProvider(LLMProvider):
    def __init__(self, settings=None, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.model = "mock-llm"

    async def ainvoke(self, messages, **kwargs):
        last = messages[-1].get("content", "") if messages else ""
        answer = f"[mock-llm] Resposta simulada para: {last[:300]}"
        usage = {"prompt_tokens": max(1, len(str(messages))//4), "completion_tokens": max(1, len(answer)//4), "total_tokens": max(2, (len(str(messages))+len(answer))//4), "cost_usd": 0.0, "cost_brl": 0.0}
        if self.usage_repository:
            await self.usage_repository.record(UsageRecord.from_usage("mock", self.model, "chat_completion", usage, {"provider":"mock"}))
        if self.telemetry:
            await self.telemetry.generation(
                name="mock_chat_completion",
                model=self.model,
                input=messages,
                output=answer,
                metadata={"provider": "mock", **usage},
                usage=usage,
            )
        return answer


class OCICompatibleOpenAIProvider(LLMProvider):
    """Provider principal: OCI Generative AI via endpoint OpenAI-compatible.

    Quando Langfuse está habilitado, usa `langfuse.openai.AsyncOpenAI`, que
    captura automaticamente generations da OpenAI-compatible API.
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.model = settings.OCI_GENAI_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.provider_name = "oci_openai"
        self.token_collector = TokenUsageCollector(settings)

        if not settings.OCI_GENAI_API_KEY:
            raise RuntimeError(
                "OCI_GENAI_API_KEY não configurado. "
                "Defina LLM_PROVIDER=oci_openai e OCI_GENAI_API_KEY no .env."
            )

        AsyncOpenAI = self._resolve_async_openai(settings)
        self.client = AsyncOpenAI(
            base_url=settings.OCI_GENAI_BASE_URL,
            api_key=settings.OCI_GENAI_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

        logger.info(
            "LLM provider inicializado provider=%s base_url=%s model=%s langfuse=%s",
            self.provider_name,
            settings.OCI_GENAI_BASE_URL,
            self.model,
            bool(getattr(settings, "ENABLE_LANGFUSE", False)),
        )

    def _resolve_async_openai(self, settings):
        if getattr(settings, "ENABLE_LANGFUSE", False):
            try:
                from langfuse.openai import AsyncOpenAI

                return AsyncOpenAI
            except Exception:
                logger.exception(
                    "Langfuse habilitado, mas langfuse.openai.AsyncOpenAI não pôde ser importado. "
                    "Usando openai.AsyncOpenAI sem auto-instrumentação."
                )
        from openai import AsyncOpenAI

        return AsyncOpenAI

    async def ainvoke(self, messages, **kwargs):
        async with _maybe_span(
            self.telemetry,
            "llm.oci_openai.chat_completion",
            provider=self.provider_name,
            model=self.model,
        ):
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                )
                answer = resp.choices[0].message.content or ""

                usage_metadata = self.token_collector.enrich(self.model, getattr(resp, "usage", None))
                if self.usage_repository:
                    await self.usage_repository.record(UsageRecord.from_usage(self.provider_name, self.model, "chat_completion", usage_metadata, {"provider": self.provider_name}))
                if self.telemetry:
                    await self.telemetry.generation(
                        name="oci_chat_completion",
                        model=self.model,
                        input=messages,
                        output=answer,
                        metadata={"provider": self.provider_name, **usage_metadata},
                        usage=usage_metadata,
                    )

                return answer
            except Exception as exc:
                logger.exception("Erro ao chamar OCI Generative AI OpenAI-compatible: %s", exc)
                raise

    def _using_langfuse_openai(self) -> bool:
        module = self.client.__class__.__module__
        return "langfuse" in module


class OpenAICompatibleProvider(OCICompatibleOpenAIProvider):
    """Provider genérico OpenAI-compatible.

    Reusa as variáveis OCI_GENAI_* para manter compatibilidade com o template,
    mas permite apontar para outro endpoint OpenAI-compatible.
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        super().__init__(settings, telemetry=telemetry, usage_repository=usage_repository)
        self.provider_name = "openai_compatible"


class OCISDKProvider(LLMProvider):
    """Skeleton para chamadas via OCI SDK/signer quando não quiser API key.

    Mantido explicitamente como NotImplemented para não aparentar que usa OCI
    SDK enquanto ainda não existe payload assinado implementado.
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.model = settings.OCI_GENAI_MODEL

    async def ainvoke(self, messages, **kwargs):
        raise NotImplementedError(
            "Implementar chamada OCI SDK Generative AI Inference usando OCI_CONFIG_FILE/PROFILE. "
            "Para uso imediato, configure LLM_PROVIDER=oci_openai."
        )


def create_llm(settings, telemetry=None, usage_repository: UsageRepository | None = None) -> LLMProvider:
    provider = settings.LLM_PROVIDER
    if provider == "oci_openai":
        return OCICompatibleOpenAIProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "oci_sdk":
        return OCISDKProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "mock":
        return MockLLMProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    raise ValueError(f"LLM_PROVIDER não suportado: {provider}")


class _maybe_span:
    def __init__(self, telemetry, name: str, **attrs: Any):
        self.telemetry = telemetry
        self.name = name
        self.attrs = attrs
        self.cm = None

    async def __aenter__(self):
        if not self.telemetry:
            return None
        self.cm = self.telemetry.span(self.name, **self.attrs)
        return await self.cm.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        if self.cm:
            return await self.cm.__aexit__(exc_type, exc, tb)
        return False
