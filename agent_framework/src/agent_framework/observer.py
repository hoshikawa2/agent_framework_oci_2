from __future__ import annotations

"""Compatibilidade FIRST/TIM para observer.event/configure.

Este módulo expõe a API esperada por projetos legados da First/TIM:

    from agent_framework.observer import configure, event

Internamente ele usa o AgentObserver novo do framework, que pode publicar em
OCI Streaming, GCP Pub/Sub, Kafka ou Noop via AnalyticsPublisher.

A API é propositalmente síncrona e tolerante a erro para poder ser chamada por
rails, bridges e comandos de negócio sem quebrar o turno do cliente.
"""

import asyncio
import logging
import os
from threading import Lock
from typing import Any

from agent_framework.analytics.factory import create_analytics_publisher
from agent_framework.observability.observer import AgentObserver

logger = logging.getLogger("agent_framework.observer")

_GLOBAL_OBSERVER: AgentObserver | None = None
_GLOBAL_CONFIG: dict[str, Any] = {}
_LOCK = Lock()


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _apply_config_to_env(config: dict[str, Any]) -> None:
    """Traduz nomes de configuração FIRST/TIM para envs do framework.

    O projeto original costuma configurar algo como:
    {
      "publisher": {"type": "langfuse"},
      "pubsub": {"topic": "..."},
      "sampling_rate": 1.0
    }

    Para Pub/Sub, aceitamos também AGENT_PUBSUB_TOPIC no ambiente.
    """
    pubsub_cfg = config.get("pubsub") if isinstance(config.get("pubsub"), dict) else {}
    publisher_cfg = config.get("publisher") if isinstance(config.get("publisher"), dict) else {}

    topic = (
        config.get("topic_path")
        or config.get("pubsub_topic_path")
        or config.get("AGENT_PUBSUB_TOPIC")
        or pubsub_cfg.get("topic_path")
        or pubsub_cfg.get("topic")
        or publisher_cfg.get("topic_path")
        or publisher_cfg.get("topic")
    )
    if topic and not os.getenv("GCP_PUBSUB_TOPIC_PATH"):
        os.environ["GCP_PUBSUB_TOPIC_PATH"] = str(topic)

    providers = config.get("providers") or config.get("analytics_providers")
    if providers and not os.getenv("ANALYTICS_PROVIDERS"):
        if isinstance(providers, (list, tuple, set)):
            os.environ["ANALYTICS_PROVIDERS"] = ",".join(str(p) for p in providers)
        else:
            os.environ["ANALYTICS_PROVIDERS"] = str(providers)

    # Se foi informado um tópico Pub/Sub e não há providers explícitos, habilita Pub/Sub.
    if topic and not os.getenv("ANALYTICS_PROVIDERS"):
        os.environ["ANALYTICS_PROVIDERS"] = "pubsub"

    enabled = config.get("enabled")
    if enabled is None:
        enabled = config.get("enable_analytics")
    if enabled is None and topic:
        enabled = True
    if enabled is not None and not os.getenv("ENABLE_ANALYTICS"):
        os.environ["ENABLE_ANALYTICS"] = "true" if _truthy(enabled) else "false"


def configure(config: dict[str, Any] | None = None) -> None:
    """Configura o observer global.

    Pode ser chamado no startup da aplicação. Se não for chamado, o primeiro
    event() cria o observer usando settings/env atuais.
    """
    global _GLOBAL_OBSERVER, _GLOBAL_CONFIG
    config = dict(config or {})
    with _LOCK:
        _GLOBAL_CONFIG = config
        _apply_config_to_env(config)
        _GLOBAL_OBSERVER = AgentObserver(analytics=create_analytics_publisher())
    logger.info("agent_framework.observer configured providers=%s topic=%s", os.getenv("ANALYTICS_PROVIDERS"), os.getenv("GCP_PUBSUB_TOPIC_PATH"))


def get_observer() -> AgentObserver:
    global _GLOBAL_OBSERVER
    if _GLOBAL_OBSERVER is None:
        configure(_GLOBAL_CONFIG)
    assert _GLOBAL_OBSERVER is not None
    return _GLOBAL_OBSERVER


async def aevent(
    name: str,
    *,
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    event_test: bool | None = None,
) -> dict[str, Any] | None:
    """Versão async da emissão compatível com FIRST/TIM."""
    payload = dict(data or {})
    meta = dict(metadata or {})

    # O bridge legado muitas vezes manda todo o payload em metadata.
    # Mantemos ambos: payload vazio continua válido e metadata preserva noc:true.
    try:
        return await get_observer().emit(name, payload, metadata=meta)
    except Exception:
        logger.exception("agent_framework.observer.aevent failed name=%s", name)
        return None


def event(
    name: str,
    *,
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    event_test: bool | None = None,
) -> dict[str, Any] | None:
    """Emite evento de forma síncrona e tolerante a loop async.

    Retorna o envelope quando conseguiu publicar sincronicamente. Se chamado de
    dentro de um event loop ativo, agenda uma task fire-and-forget e retorna um
    status queued para não bloquear nem estourar RuntimeError.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(aevent(name, data=data, metadata=metadata, event_test=event_test))

    task = loop.create_task(aevent(name, data=data, metadata=metadata, event_test=event_test))
    task.add_done_callback(_log_task_exception)
    return {"status": "queued", "eventType": name}


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("agent_framework.observer.event task failed")
