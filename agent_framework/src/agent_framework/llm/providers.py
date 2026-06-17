from __future__ import annotations

import logging
import os
from typing import Any

from .base import LLMProvider
from .profile_resolver import LLMProfileResolver
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
        profile_name = kwargs.get("profile_name", "default")
        component_name = kwargs.get("component_name") or kwargs.get("component") or profile_name or "default"
        generation_name = kwargs.get("generation_name") or f"llm.{component_name}"
        model = kwargs.get("model") or self.model
        profile_source = kwargs.get("profile_source")
        profile_found = kwargs.get("profile_found")
        profiles_enabled = kwargs.get("profiles_enabled")
        profiles_path = kwargs.get("profiles_path")
        last = messages[-1].get("content", "") if messages else ""
        answer = f"[mock-llm] Resposta simulada para: {last[:300]}"
        usage = {"prompt_tokens": max(1, len(str(messages))//4), "completion_tokens": max(1, len(answer)//4), "total_tokens": max(2, (len(str(messages))+len(answer))//4), "cost_usd": 0.0, "cost_brl": 0.0}
        if self.usage_repository:
            await self.usage_repository.record(UsageRecord.from_usage("mock", model, generation_name, usage, {"provider":"mock", "profile_name": profile_name, "component": component_name, "model": model, "profile_source": profile_source, "profile_found": profile_found, "profiles_enabled": profiles_enabled, "profiles_path": profiles_path}))
        if self.telemetry:
            await self.telemetry.generation(
                name=generation_name,
                model=model,
                input=messages,
                output=answer,
                metadata={"provider": "mock", "profile_name": profile_name, "component": component_name, "model": model, "profile_source": profile_source, "profile_found": profile_found, "profiles_enabled": profiles_enabled, "profiles_path": profiles_path, **usage},
                usage=usage,
            )
        return answer


class OCICompatibleOpenAIProvider(LLMProvider):
    """Provider principal: OCI Generative AI via endpoint OpenAI-compatible.

    Also supports optional dynamic per-inference profiles from llm_profiles.yaml.
    If the YAML file does not exist, behavior remains .env based as before.
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.profile_resolver = LLMProfileResolver.from_settings(settings)
        self.provider_name = getattr(settings, "LLM_PROVIDER", "oci_openai")
        self.model = settings.OCI_GENAI_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.token_collector = TokenUsageCollector(settings)
        self._clients: dict[tuple[str | None, str | None, float | int | None, bool], Any] = {}

        if not settings.OCI_GENAI_API_KEY and self.provider_name not in ("mock",):
            raise RuntimeError(
                "OCI_GENAI_API_KEY não configurado. "
                "Defina LLM_PROVIDER=oci_openai e OCI_GENAI_API_KEY no .env."
            )

        # Eagerly create the env/default client to preserve current startup behavior
        # for real OpenAI-compatible providers. In mock mode, do not require any API key.
        self.client = None
        if self.provider_name != 'mock':
            self.client = self._get_client(
                base_url=settings.OCI_GENAI_BASE_URL,
                api_key=settings.OCI_GENAI_API_KEY,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )

        logger.info(
            "LLM provider inicializado provider=%s base_url=%s model=%s langfuse=%s profiles_enabled=%s",
            self.provider_name,
            settings.OCI_GENAI_BASE_URL,
            self.model,
            bool(getattr(settings, "ENABLE_LANGFUSE", False)),
            self.profile_resolver.enabled,
        )

    def _resolve_async_openai(self, settings):
        # The framework records LLM calls through Telemetry.generation(...), where
        # we can inject the request trace_context. The langfuse.openai wrapper is
        # useful in simple apps, but in this framework it may create one top-level
        # Langfuse trace per OpenAI call when no parent observation is active in
        # the SDK context. Keep it opt-in to avoid noisy trace lists.
        use_langfuse_wrapper = str(
            getattr(settings, "ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION", None)
            or os.getenv("ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION", "false")
        ).strip().lower() in {"1", "true", "yes", "on", "y"}
        if getattr(settings, "ENABLE_LANGFUSE", False) and use_langfuse_wrapper:
            try:
                from langfuse.openai import AsyncOpenAI
                return AsyncOpenAI
            except Exception:
                logger.exception(
                    "Langfuse OpenAI auto-instrumentation habilitada, mas langfuse.openai.AsyncOpenAI "
                    "não pôde ser importado. Usando openai.AsyncOpenAI sem auto-instrumentação."
                )
        from openai import AsyncOpenAI
        return AsyncOpenAI

    def _get_client(self, *, base_url: str | None, api_key: str | None, timeout: float | int | None):
        key = (base_url, api_key, timeout, bool(getattr(self.settings, "ENABLE_LANGFUSE", False)))
        if key not in self._clients:
            AsyncOpenAI = self._resolve_async_openai(self.settings)
            self._clients[key] = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        return self._clients[key]

    async def ainvoke(self, messages, **kwargs):
        profile_name = kwargs.pop("profile_name", None)
        component_name = kwargs.pop("component_name", None) or kwargs.pop("component", None) or profile_name or "default"
        generation_name = kwargs.pop("generation_name", None) or f"llm.{component_name}"
        effective = self.profile_resolver.resolve(profile_name, **kwargs)
        provider = str(effective.get("provider") or self.provider_name)
        model = str(effective.get("model") or self.model)
        temperature = effective.get("temperature", self.temperature)
        max_tokens = effective.get("max_tokens", self.max_tokens)
        timeout = effective.get("timeout_seconds", getattr(self.settings, "LLM_TIMEOUT_SECONDS", 120))
        base_url = effective.get("base_url") or getattr(self.settings, "OCI_GENAI_BASE_URL", None)
        api_key = effective.get("api_key") or getattr(self.settings, "OCI_GENAI_API_KEY", None)
        resolved_profile_name = effective.get("profile_name") or profile_name or "default"
        requested_profile_name = effective.get("requested_profile_name") or profile_name or "default"
        profile_source = effective.get("profile_source") or ("yaml" if effective.get("profiles_enabled") else "env")
        profile_found = bool(effective.get("profile_found"))
        component_name = str(component_name or resolved_profile_name)

        if provider == "mock":
            mock = MockLLMProvider(self.settings, telemetry=self.telemetry, usage_repository=self.usage_repository)
            return await mock.ainvoke(
                messages,
                model=model,
                profile_name=resolved_profile_name,
                component_name=component_name,
                generation_name=generation_name,
                profile_source=profile_source,
                profile_found=profile_found,
                profiles_enabled=bool(effective.get("profiles_enabled")),
                profiles_path=effective.get("profiles_path"),
            )

        if provider == "oci_sdk":
            sdk = OCISDKProvider(self.settings, telemetry=self.telemetry, usage_repository=self.usage_repository)
            return await sdk.ainvoke(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout,
                compartment_id=effective.get("compartment_id") or effective.get("project_ocid"),
                profile_name=resolved_profile_name,
                requested_profile_name=requested_profile_name,
                profile_source=profile_source,
                profile_found=profile_found,
                profiles_enabled=bool(effective.get("profiles_enabled")),
                profiles_path=effective.get("profiles_path"),
                component_name=component_name,
                generation_name=generation_name,
            )

        if provider not in ("oci_openai", "openai_compatible"):
            raise ValueError(f"LLM provider não suportado no profile {resolved_profile_name}: {provider}")

        if not api_key:
            raise RuntimeError(
                f"API key ausente para o profile LLM {resolved_profile_name!r}. "
                "Configure api_key no llm_profiles.yaml ou OCI_GENAI_API_KEY no .env."
            )

        client = self._get_client(base_url=base_url, api_key=api_key, timeout=timeout)

        request_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Optional OpenAI-compatible params. Only send when explicitly configured.
        for optional_key in ("top_p", "frequency_penalty", "presence_penalty"):
            if effective.get(optional_key) is not None:
                request_kwargs[optional_key] = effective[optional_key]

        async with _maybe_span(
            self.telemetry,
            "llm.chat_completion",
            provider=provider,
            model=model,
            profile_name=resolved_profile_name,
            requested_profile_name=requested_profile_name,
            profile_source=profile_source,
            profile_found=profile_found,
            component=component_name,
            temperature=temperature,
            max_tokens=max_tokens,
            profiles_enabled=bool(effective.get("profiles_enabled")),
        ):
            try:
                resp = await client.chat.completions.create(**request_kwargs)
                answer = resp.choices[0].message.content or ""

                usage_metadata = self.token_collector.enrich(model, getattr(resp, "usage", None))
                usage_metadata.update({
                    "profile_name": resolved_profile_name,
                    "requested_profile_name": requested_profile_name,
                    "profile_source": profile_source,
                    "profile_found": profile_found,
                    "component": component_name,
                    "model": model,
                    "provider": provider,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                })
                llm_metadata = {
                    "provider": provider,
                    "model": model,
                    "component": component_name,
                    "profile_name": resolved_profile_name,
                    "requested_profile_name": requested_profile_name,
                    "profile_source": profile_source,
                    "profile_found": profile_found,
                    "profiles_enabled": bool(effective.get("profiles_enabled")),
                    "profiles_path": effective.get("profiles_path"),
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if self.usage_repository:
                    await self.usage_repository.record(
                        UsageRecord.from_usage(provider, model, generation_name, usage_metadata, llm_metadata)
                    )
                if self.telemetry:
                    await self.telemetry.generation(
                        name=generation_name,
                        model=model,
                        input=messages,
                        output=answer,
                        metadata={**llm_metadata, **usage_metadata},
                        usage=usage_metadata,
                    )

                return answer
            except Exception as exc:
                logger.exception(
                    "Erro ao chamar LLM provider=%s component=%s profile=%s model=%s: %s",
                    provider,
                    component_name,
                    resolved_profile_name,
                    model,
                    exc,
                )
                raise

    def _using_langfuse_openai(self) -> bool:
        if self.client is None:
            return False
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
    """OCI Generative AI via OCI Python SDK.

    This provider supports API-key config files for local development and
    instance/resource principals for OCI runtimes through OCI_AUTH_MODE.
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.model = settings.OCI_GENAI_MODEL
        self.token_collector = TokenUsageCollector(settings)
        self._client = None

    @staticmethod
    def _resolve_endpoint(settings, endpoint: str | None = None) -> str:
        if endpoint:
            return endpoint
        configured = getattr(settings, "OCI_GENAI_ENDPOINT", None)
        if configured:
            return configured
        region = getattr(settings, "OCI_REGION", "sa-saopaulo-1")
        return f"https://inference.generativeai.{region}.oci.oraclecloud.com"

    def _get_client(self, endpoint: str | None = None):
        if self._client is None:
            from oci.generative_ai_inference import GenerativeAiInferenceClient
            from agent_framework.oci.auth import get_oci_config_and_signer

            config, signer = get_oci_config_and_signer(self.settings)
            kwargs = {"config": config, "service_endpoint": self._resolve_endpoint(self.settings, endpoint)}
            if signer is not None:
                kwargs["signer"] = signer
            self._client = GenerativeAiInferenceClient(**kwargs)
        return self._client

    @staticmethod
    def _to_prompt(messages) -> str:
        parts: list[str] = []
        for m in messages or []:
            role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "user")) or "user"
            content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def _build_chat_details(self, *, messages, model: str, compartment_id: str, temperature: float, max_tokens: int):
        from oci.generative_ai_inference import models

        serving_mode = models.OnDemandServingMode(model_id=model)

        # Prefer GenericChatRequest when available in the installed OCI SDK.
        if hasattr(models, "GenericChatRequest") and hasattr(models, "UserMessage"):
            oci_messages = []
            for m in messages or []:
                role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "user")) or "user"
                content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
                text_content = models.TextContent(text=str(content)) if hasattr(models, "TextContent") else str(content)
                content_list = [text_content] if not isinstance(text_content, str) else str(content)
                if role == "system" and hasattr(models, "SystemMessage"):
                    oci_messages.append(models.SystemMessage(content=content_list))
                elif role == "assistant" and hasattr(models, "AssistantMessage"):
                    oci_messages.append(models.AssistantMessage(content=content_list))
                else:
                    oci_messages.append(models.UserMessage(content=content_list))
            chat_request = models.GenericChatRequest(
                messages=oci_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return models.ChatDetails(
                compartment_id=compartment_id,
                serving_mode=serving_mode,
                chat_request=chat_request,
            )

        # Fallback for older SDKs / Cohere-style requests.
        prompt = self._to_prompt(messages)
        chat_request = models.CohereChatRequest(
            message=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return models.ChatDetails(
            compartment_id=compartment_id,
            serving_mode=serving_mode,
            chat_request=chat_request,
        )

    @staticmethod
    def _extract_answer(response) -> str:
        data = getattr(response, "data", response)
        chat_response = getattr(data, "chat_response", None) or data
        for attr in ("text", "message", "output_text"):
            value = getattr(chat_response, attr, None)
            if value:
                return str(value)
        choices = getattr(chat_response, "choices", None) or []
        if choices:
            first = choices[0]
            msg = getattr(first, "message", None)
            content = getattr(msg, "content", None) if msg is not None else getattr(first, "text", None)
            if isinstance(content, list):
                chunks = []
                for item in content:
                    chunks.append(str(getattr(item, "text", item)))
                return "".join(chunks)
            if content:
                return str(content)
        return str(chat_response)

    async def ainvoke(self, messages, **kwargs):
        import asyncio

        model = kwargs.get("model") or self.model
        temperature = kwargs.get("temperature", getattr(self.settings, "LLM_TEMPERATURE", 0.2))
        max_tokens = kwargs.get("max_tokens", getattr(self.settings, "LLM_MAX_TOKENS", 2048))
        compartment_id = kwargs.get("compartment_id") or getattr(self.settings, "OCI_COMPARTMENT_ID", None) or getattr(self.settings, "OCI_GENAI_PROJECT_OCID", None)
        profile_name = kwargs.get("profile_name", "default")
        component_name = kwargs.get("component_name") or kwargs.get("component") or profile_name
        generation_name = kwargs.get("generation_name") or f"llm.{component_name}"

        if not compartment_id:
            raise RuntimeError("OCI_COMPARTMENT_ID or OCI_GENAI_PROJECT_OCID is required for LLM_PROVIDER=oci_sdk")

        async with _maybe_span(
            self.telemetry,
            "llm.chat_completion",
            provider="oci_sdk",
            model=model,
            profile_name=profile_name,
            component=component_name,
            auth_mode=getattr(self.settings, "OCI_AUTH_MODE", "config_file"),
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            client = self._get_client(kwargs.get("endpoint"))
            details = self._build_chat_details(
                messages=messages,
                model=model,
                compartment_id=compartment_id,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response = await asyncio.to_thread(client.chat, details)
            answer = self._extract_answer(response)

            usage_metadata = {
                "prompt_tokens": max(1, len(str(messages)) // 4),
                "completion_tokens": max(1, len(answer) // 4),
                "total_tokens": max(2, (len(str(messages)) + len(answer)) // 4),
                "cost_usd": 0.0,
                "cost_brl": 0.0,
                "estimated_usage": True,
                "provider": "oci_sdk",
                "model": model,
                "component": component_name,
                "profile_name": profile_name,
                "auth_mode": getattr(self.settings, "OCI_AUTH_MODE", "config_file"),
            }
            llm_metadata = dict(usage_metadata)
            if self.usage_repository:
                await self.usage_repository.record(
                    UsageRecord.from_usage("oci_sdk", model, generation_name, usage_metadata, llm_metadata)
                )
            if self.telemetry:
                await self.telemetry.generation(
                    name=generation_name,
                    model=model,
                    input=messages,
                    output=answer,
                    metadata=llm_metadata,
                    usage=usage_metadata,
                )
            return answer


def create_llm(settings, telemetry=None, usage_repository: UsageRepository | None = None) -> LLMProvider:
    provider = settings.LLM_PROVIDER
    if provider == "oci_openai":
        return OCICompatibleOpenAIProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "oci_sdk":
        return OCISDKProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "mock":
        # When llm_profiles.yaml exists, even an env mock backend may route specific
        # inference points to real providers. Use the dynamic provider in that case;
        # otherwise preserve the old lightweight mock behavior.
        resolver = LLMProfileResolver.from_settings(settings)
        if resolver.enabled:
            return OCICompatibleOpenAIProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
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
