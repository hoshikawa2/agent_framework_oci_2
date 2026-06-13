from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any

from agent_framework.analytics.publisher import AnalyticsPublisher

logger = logging.getLogger("agent_framework.analytics.langfuse")


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _safe_metadata(value: Any) -> Any:
    """Remove/mascara segredos antes de enviar metadata para Langfuse."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lk = str(key).lower()
            if any(token in lk for token in ("password", "secret", "token", "api_key", "authorization")):
                out[key] = "***"
            else:
                out[key] = _safe_metadata(item)
        return out
    if isinstance(value, list):
        return [_safe_metadata(item) for item in value]
    return value


_LANGFUSE_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _raw_correlation_id(metadata: dict[str, Any]) -> str | None:
    value = (
        metadata.get("traceId")
        or metadata.get("trace_id")
        or metadata.get("requestId")
        or metadata.get("request_id")
        or metadata.get("transactionId")
        or metadata.get("transaction_id")
        or metadata.get("sessionId")
        or metadata.get("session_id")
    )
    return str(value) if value else None


def _langfuse_trace_id(value: Any) -> str | None:
    """Normalize framework/business ids to Langfuse's 32 lowercase hex id."""
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    compact = raw.replace("-", "")
    if _LANGFUSE_TRACE_ID_RE.match(compact):
        return compact
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _correlation_trace_id(metadata: dict[str, Any]) -> str | None:
    """Stable Langfuse-safe trace id used to group IC/NOC/GRL events."""
    return _langfuse_trace_id(_raw_correlation_id(metadata))


def _with_trace_context(kwargs: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    raw_id = _raw_correlation_id(metadata)
    trace_id = _langfuse_trace_id(raw_id)
    if trace_id and "trace_context" not in kwargs:
        kwargs["trace_context"] = {"trace_id": trace_id}
        meta = kwargs.setdefault("metadata", {})
        if isinstance(meta, dict):
            meta.setdefault("framework_trace_id", raw_id)
            meta.setdefault("langfuse_trace_id", trace_id)
    return kwargs


class LangfuseAnalyticsPublisher(AnalyticsPublisher):
    """Publica eventos IC/NOC/GRL do observer como observations/spans no Langfuse.

    Esta classe é a versão nativa, dentro do framework, do comportamento que
    projetos legados faziam com `ics_collector.py`: qualquer chamada para
    `agent_framework.observer.event("AGA.001"|"NOC.001"|"GRL.001", ...)`
    passa a aparecer no Langfuse como uma observation/span com o próprio código
    como nome.

    O publisher é tolerante a versões diferentes do SDK Langfuse:
    - SDK v3: usa `start_as_current_observation(as_type="span", ...)`;
    - SDK antigo: tenta `event(...)` ou `span(...)` como fallback.
    """

    def __init__(self, settings: Any | None = None, langfuse: Any | None = None):
        self.settings = settings
        self.langfuse = langfuse
        self.enabled = True

        if self.langfuse is not None:
            return

        if settings is None:
            from agent_framework.config.settings import settings as default_settings
            settings = default_settings
            self.settings = settings

        public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None) or os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None) or os.getenv("LANGFUSE_SECRET_KEY")
        host = getattr(settings, "LANGFUSE_HOST", None) or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"

        if not public_key or not secret_key:
            self.enabled = False
            logger.warning("LangfuseAnalyticsPublisher desabilitado: LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY ausentes")
            return

        try:
            from langfuse import Langfuse  # type: ignore
            self.langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
            logger.info("LangfuseAnalyticsPublisher habilitado host=%s", host)
        except Exception:
            self.enabled = False
            self.langfuse = None
            logger.exception("Falha ao inicializar LangfuseAnalyticsPublisher")

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.enabled or self.langfuse is None:
            return

        event_type = str(event_type)
        envelope = dict(payload or {})
        body = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), dict) else {}
        source = envelope.get("source") or "agent_framework"
        event_date = envelope.get("eventDate")

        # Metadata fica rica, mas o input mantém o envelope para auditoria.
        langfuse_metadata = _safe_metadata({
            "eventType": event_type,
            "source": source,
            "eventDate": event_date,
            "payload": body,
            "metadata": metadata,
            "ic": _is_ic(event_type, metadata),
            "noc": _is_noc(event_type, metadata),
            "grl": _is_grl(event_type, metadata),
            "tag": body.get("tag") or metadata.get("tag") or event_type,
            "request_id": body.get("request_id") or metadata.get("request_id") or body.get("requestId") or metadata.get("requestId"),
            "trace_id": body.get("trace_id") or metadata.get("trace_id") or body.get("traceId") or metadata.get("traceId"),
            "transaction_id": body.get("transaction_id") or metadata.get("transaction_id") or body.get("transactionId") or metadata.get("transactionId"),
            "sessionId": body.get("sessionId") or metadata.get("sessionId") or body.get("session_id") or metadata.get("session_id"),
            "messageId": body.get("messageId") or metadata.get("messageId") or body.get("message_id") or metadata.get("message_id"),
            "agentId": body.get("agentId") or metadata.get("agentId") or body.get("agent_id") or metadata.get("agent_id"),
            "channelId": body.get("channelId") or metadata.get("channelId") or body.get("channel") or metadata.get("channel"),
        })

        # Atualiza trace corrente quando houver dados suficientes, mas não falha
        # se o SDK/contexto não suportar essa operação.
        self._update_current_trace(langfuse_metadata)

        # Preferência: observation/span nomeada pelo próprio código. Isso replica
        # a experiência visual do backoffice original no Langfuse.
        try:
            if hasattr(self.langfuse, "start_as_current_observation"):
                kwargs = _with_trace_context({
                    "name": event_type,
                    "as_type": "span",
                    "input": envelope,
                    "metadata": langfuse_metadata,
                }, langfuse_metadata)
                try:
                    cm = self.langfuse.start_as_current_observation(**kwargs)
                except (TypeError, ValueError):
                    kwargs.pop("trace_context", None)
                    cm = self.langfuse.start_as_current_observation(**kwargs)
                with cm as observation:
                    _update_observation(observation, output={"published": True})
                return
        except Exception:
            logger.debug("Falha ao publicar Langfuse observation para %s", event_type, exc_info=True)

        # Avoid raw langfuse.event(...) because older SDKs create a new trace row
        # for every analytics event. Prefer attaching spans to the deterministic
        # request trace when legacy trace/span APIs are available.
        try:
            trace_id = _correlation_trace_id(langfuse_metadata)
            if trace_id and hasattr(self.langfuse, "trace"):
                trace = self.langfuse.trace(
                    id=str(trace_id),
                    name=str(langfuse_metadata.get("request_id") or langfuse_metadata.get("sessionId") or "agent_framework.request"),
                    session_id=langfuse_metadata.get("sessionId"),
                    user_id=langfuse_metadata.get("user_id") or langfuse_metadata.get("userId"),
                    metadata={k: v for k, v in langfuse_metadata.items() if v is not None},
                )
                if hasattr(trace, "span"):
                    span = trace.span(name=event_type, input=envelope, metadata=langfuse_metadata)
                    if hasattr(span, "end"):
                        span.end(output={"published": True})
                    return
        except Exception:
            logger.debug("Falha ao publicar Langfuse span correlacionado para %s", event_type, exc_info=True)

        try:
            if hasattr(self.langfuse, "span"):
                span = self.langfuse.span(name=event_type, input=envelope, metadata=langfuse_metadata)
                if hasattr(span, "end"):
                    span.end(output={"published": True})
                return
        except Exception:
            logger.debug("Falha ao publicar Langfuse span legado para %s", event_type, exc_info=True)

    def _update_current_trace(self, metadata: dict[str, Any]) -> None:
        try:
            kwargs: dict[str, Any] = {
                "metadata": {k: v for k, v in metadata.items() if v is not None},
                "tags": [tag for tag, enabled in (
                    ("ic", metadata.get("ic")),
                    ("noc", metadata.get("noc")),
                    ("grl", metadata.get("grl")),
                    (str(metadata.get("tag")), metadata.get("tag")),
                ) if enabled],
            }
            session_id = metadata.get("sessionId")
            if session_id:
                kwargs["session_id"] = str(session_id)
            if hasattr(self.langfuse, "update_current_trace"):
                self.langfuse.update_current_trace(**kwargs)
        except Exception:
            logger.debug("Langfuse update_current_trace ignorado", exc_info=True)


def _update_observation(observation: Any, **kwargs: Any) -> None:
    if observation is None:
        return
    try:
        if hasattr(observation, "update"):
            observation.update(**{k: v for k, v in kwargs.items() if v is not None})
    except Exception:
        logger.debug("Langfuse observation update ignorado", exc_info=True)


def _is_noc(event_type: str, metadata: dict[str, Any]) -> bool:
    return event_type.startswith("NOC.") or _truthy(metadata.get("noc"))


def _is_grl(event_type: str, metadata: dict[str, Any]) -> bool:
    return event_type.startswith("GRL.") or _truthy(metadata.get("grl"))


def _is_ic(event_type: str, metadata: dict[str, Any]) -> bool:
    return event_type.startswith(("IC.", "AGA.")) or _truthy(metadata.get("ic"))
