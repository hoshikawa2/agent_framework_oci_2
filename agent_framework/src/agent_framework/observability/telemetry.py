"""Observabilidade central do framework no padrão FIRST.

Recursos incluídos:
- ContextVar para correlation ids assíncronos;
- Langfuse com trace/span/event/generation e fallback por versão de SDK;
- OpenTelemetry opcional via OTLP;
- Event bus interno para plugar logs, SSE, OCI Streaming, Elastic, Phoenix etc.;
- spans de workflow, guardrail, judge, RAG, MCP, cache, checkpoint e LLM;
- token/cost metadata quando informado pelos providers.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from .context import context_metadata, get_observability_context, set_observability_context
from .event_bus import TelemetryEventBus
from .otel import OpenTelemetryProvider

logger = logging.getLogger("agent_framework.telemetry")

_LANGFUSE_OBSERVATION_TYPES = {"span", "generation", "agent", "tool", "chain", "retriever", "embedding", "evaluator", "guardrail"}

def _langfuse_type(kind: str | None) -> str:
    # Langfuse SDKs do not accept arbitrary event types such as "event"; FIRST pattern
    # stores those as spans with rich metadata to avoid noisy warnings.
    if kind in _LANGFUSE_OBSERVATION_TYPES:
        return kind
    return "span"

class Telemetry:
    def __init__(self, settings):
        self.settings = settings
        self.langfuse = None
        self.enabled = bool(getattr(settings, "ENABLE_LANGFUSE", False))
        self.event_bus = TelemetryEventBus()
        self.otel = OpenTelemetryProvider(settings)
        if getattr(settings, "ENABLE_OCI_STREAMING", False):
            try:
                from .streaming_exporter import OCIStreamingTelemetryExporter
                self.event_bus.subscribe(OCIStreamingTelemetryExporter(settings))
                logger.info("OCI Streaming telemetry exporter habilitado")
            except Exception:
                logger.exception("Falha ao inicializar exporter OCI Streaming")

        if not self.enabled:
            logger.info("Langfuse desabilitado")
            return

        public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None)
        secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None)
        host = getattr(settings, "LANGFUSE_HOST", None)
        if not public_key or not secret_key:
            logger.warning("ENABLE_LANGFUSE=true, mas LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY não foram configuradas")
            self.enabled = False
            return
        try:
            from langfuse import Langfuse
            self.langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
            logger.info("Langfuse habilitado host=%s", host)
        except Exception as exc:
            logger.exception("Falha ao inicializar Langfuse: %s", exc)
            self.enabled = False
            self.langfuse = None

    def is_enabled(self) -> bool:
        return bool(self.enabled and self.langfuse)

    def bind_context(self, **kwargs: Any):
        return set_observability_context(**kwargs)

    def context(self) -> dict[str, Any]:
        return get_observability_context().clean()

    @asynccontextmanager
    async def span(self, name: str, **attrs):
        """Cria span correlacionado em logs, Langfuse e OpenTelemetry."""
        start = time.time()
        attrs = context_metadata(attrs)
        if not attrs.get("request_id"):
            attrs["request_id"] = str(uuid4())
            set_observability_context(request_id=attrs["request_id"])
        observation_cm = None
        observation = None
        logger.info("span.start %s %s", name, _safe(attrs))
        await self.event_bus.publish(f"{name}.started", attrs, kind="span")

        otel_cm = self.otel.span(name, attrs)
        otel_span = otel_cm.__enter__()
        if self.is_enabled():
            observation_cm = self._start_observation(
                name=name,
                as_type="span",
                input=attrs.get("input"),
                metadata={k: v for k, v in attrs.items() if k != "input"},
            )
        try:
            if observation_cm is not None:
                observation = observation_cm.__enter__()
                self._update_trace_from_attrs(observation, attrs)
            yield observation
            duration_ms = int((time.time() - start) * 1000)
            out = {"status": "ok", "duration_ms": duration_ms}
            self._update_observation(observation, output=out, metadata={"duration_ms": duration_ms})
            if otel_span is not None:
                otel_span.set_attribute("duration_ms", duration_ms)
            await self.event_bus.publish(f"{name}.completed", {**attrs, **out}, kind="span")
            logger.info("span.end %s duration_ms=%s", name, duration_ms)
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            out = {"status": "error", "error": str(exc), "duration_ms": duration_ms}
            self._update_observation(observation, level="ERROR", status_message=str(exc), output=out, metadata={"duration_ms": duration_ms})
            if otel_span is not None:
                try:
                    otel_span.record_exception(exc)
                    otel_span.set_attribute("error", True)
                except Exception:
                    pass
            await self.event_bus.publish(f"{name}.failed", {**attrs, **out}, kind="span")
            logger.exception("span.error %s %s", name, exc)
            raise
        finally:
            if observation_cm is not None:
                try: observation_cm.__exit__(None, None, None)
                except Exception: logger.exception("Falha ao finalizar span Langfuse %s", name)
            try: otel_cm.__exit__(None, None, None)
            except Exception: logger.debug("Falha ao fechar span OTEL", exc_info=True)

    async def event(self, name: str, payload: dict[str, Any] | None = None, *, kind: str = "event"):
        payload = context_metadata(payload or {})
        logger.info("event %s %s", name, _safe(payload))
        await self.event_bus.publish(name, payload, kind=kind)
        if not self.is_enabled():
            return
        try:
            if hasattr(self.langfuse, "event"):
                self.langfuse.event(name=name, metadata=payload)
                return
        except Exception:
            logger.exception("Falha ao enviar event via Langfuse.event")
        try:
            cm = self._start_observation(name=name, as_type=_langfuse_type(kind), metadata={**payload, "event_kind": kind})
            if cm is not None:
                with cm: pass
        except Exception:
            logger.exception("Falha ao enviar event via observation")

    async def generation(self, name: str, model: str, input: list | dict | str, output: str,
                         metadata: dict[str, Any] | None = None, usage: dict[str, Any] | None = None):
        metadata = context_metadata(metadata or {})
        # Keep the actual LLM model visible both in Langfuse's generation.model field
        # and in metadata for filtering/debugging across SDK versions.
        metadata.setdefault("model", model)
        metadata.setdefault("llm_model", model)
        metadata.setdefault("component", metadata.get("profile_name") or name)
        if usage:
            metadata["usage"] = usage
        logger.info("generation %s model=%s component=%s profile=%s metadata=%s", name, model, metadata.get("component"), metadata.get("profile_name"), _safe(metadata))
        await self.event_bus.publish(name, {"model": model, "llm_model": model, "output_chars": len(output or ""), **metadata}, kind="generation")
        if not self.is_enabled():
            return
        try:
            kwargs = dict(name=name, as_type="generation", input=input, output=output, model=model, metadata=metadata)
            if usage:
                kwargs["usage"] = usage
                kwargs["usage_details"] = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "reasoning_tokens") if k in usage}

            # Prefer explicit generation APIs when available because they expose the
            # model column more reliably in Langfuse than a generic observation.
            if hasattr(self.langfuse, "generation"):
                gen = self.langfuse.generation(**{k: v for k, v in kwargs.items() if k != "as_type" and v is not None})
                if hasattr(gen, "end"):
                    gen.end(output=output, metadata=metadata)
                return
            if hasattr(self.langfuse, "start_as_current_generation"):
                with self.langfuse.start_as_current_generation(**{k: v for k, v in kwargs.items() if k != "as_type" and v is not None}) as obs:
                    self._update_observation(obs, output=output, model=model, metadata=metadata)
                return

            cm = self._start_observation(**kwargs)
            if cm is not None:
                with cm as obs:
                    self._update_observation(obs, output=output, model=model, metadata=metadata)
        except Exception:
            logger.exception("Falha ao registrar generation no Langfuse")

    async def rag_event(self, name: str, query: str, results_count: int, metadata: dict[str, Any] | None = None):
        await self.event(f"rag.{name}", {"query": query, "results_count": results_count, **(metadata or {})}, kind="rag")

    async def cache_event(self, name: str, key: str, hit: bool | None = None, metadata: dict[str, Any] | None = None):
        await self.event(f"cache.{name}", {"key": key, "hit": hit, **(metadata or {})}, kind="cache")

    async def checkpoint_event(self, name: str, thread_id: str, metadata: dict[str, Any] | None = None):
        await self.event(f"checkpoint.{name}", {"thread_id": thread_id, **(metadata or {})}, kind="checkpoint")

    async def score(self, name: str, value: float, *, comment: str | None = None, metadata: dict[str, Any] | None = None):
        metadata = context_metadata(metadata or {})
        logger.info("score %s value=%s metadata=%s", name, value, _safe(metadata))
        await self.event_bus.publish(f"score.{name}", {"value": value, "comment": comment, **metadata}, kind="score")
        if not self.is_enabled():
            return
        try:
            if hasattr(self.langfuse, "score_current_trace"):
                self.langfuse.score_current_trace(name=name, value=value, comment=comment, metadata=metadata)
            elif hasattr(self.langfuse, "score"):
                self.langfuse.score(name=name, value=value, comment=comment, metadata=metadata)
        except Exception:
            logger.exception("Falha ao registrar score Langfuse")

    def flush(self):
        if not self.is_enabled(): return
        try:
            if hasattr(self.langfuse, "flush"):
                self.langfuse.flush(); logger.info("Langfuse flush executado")
        except Exception: logger.exception("Falha no Langfuse flush")

    def shutdown(self):
        if not self.is_enabled(): return
        try:
            if hasattr(self.langfuse, "shutdown"):
                self.langfuse.shutdown(); logger.info("Langfuse shutdown executado"); return
            self.flush()
        except Exception: logger.exception("Falha no Langfuse shutdown")

    def _start_observation(self, **kwargs):
        if not self.is_enabled(): return None
        if hasattr(self.langfuse, "start_as_current_observation"):
            clean = {k: v for k, v in kwargs.items() if v is not None}
            if "as_type" in clean:
                clean["as_type"] = _langfuse_type(clean.get("as_type"))
            try: return self.langfuse.start_as_current_observation(**clean)
            except TypeError:
                return self.langfuse.start_as_current_observation(name=kwargs["name"], as_type=kwargs.get("as_type", "span"))
        if hasattr(self.langfuse, "span"):
            legacy_metadata = dict(kwargs.get("metadata") or {})
            if kwargs.get("model") is not None:
                legacy_metadata.setdefault("model", kwargs.get("model"))
                legacy_metadata.setdefault("llm_model", kwargs.get("model"))
            span = self.langfuse.span(name=kwargs["name"], input=kwargs.get("input"), output=kwargs.get("output"), metadata=legacy_metadata)
            return _LegacyObservationContext(span)
        return None

    def _update_observation(self, observation, **kwargs):
        if observation is None: return
        clean = {k: v for k, v in kwargs.items() if v is not None}
        try:
            if hasattr(observation, "update"): observation.update(**clean)
        except Exception: logger.debug("Observation update não suportado", exc_info=True)

    def _update_trace_from_attrs(self, observation, attrs: dict[str, Any]):
        if observation is None: return
        trace_attrs = {}
        for key in ("session_id", "user_id"):
            if attrs.get(key): trace_attrs[key] = attrs[key]
        if attrs.get("input"): trace_attrs["input"] = attrs["input"]
        if attrs.get("tags"): trace_attrs["tags"] = attrs["tags"]
        if attrs.get("request_id") or attrs.get("agent_id") or attrs.get("tenant_id"):
            trace_attrs["metadata"] = {k: attrs.get(k) for k in ("request_id", "agent_id", "tenant_id", "channel", "message_id", "ura_call_id") if attrs.get(k)}
        if not trace_attrs: return
        try:
            if hasattr(observation, "update_trace"): observation.update_trace(**trace_attrs)
        except Exception: logger.debug("Trace update não suportado", exc_info=True)

class _LegacyObservationContext:
    def __init__(self, observation): self.observation = observation
    def __enter__(self): return self.observation
    def __exit__(self, exc_type, exc, tb):
        try:
            if hasattr(self.observation, "end"):
                if exc: self.observation.end(level="ERROR", status_message=str(exc))
                else: self.observation.end()
        except Exception: logger.debug("Falha ao encerrar observation legada", exc_info=True)
        return False

def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        masked = {}
        for k, v in value.items():
            lk = str(k).lower()
            if "key" in lk or "secret" in lk or "password" in lk or "token" in lk:
                masked[k] = "***"
            else: masked[k] = _safe(v)
        return masked
    if isinstance(value, list): return [_safe(v) for v in value]
    return value
