from __future__ import annotations

import logging
from typing import Any

from agent_framework.analytics import AnalyticsPublisher, build_analytics_event, create_analytics_publisher

logger = logging.getLogger("agent_framework.observability.observer")


class AgentObserver:
    """Observer corporativo para eventos IC, NOC e GRL.

    Centraliza emissão de eventos estruturados. O agente chama observer.emit(...)
    e o observer decide como publicar em analytics, NOC/OTEL e EventBus interno.
    """

    def __init__(
        self,
        analytics: AnalyticsPublisher | None = None,
        *,
        event_bus: Any | None = None,
        emit_analytics: bool = True,
        emit_event_bus: bool = True,
    ):
        self.analytics = analytics or create_analytics_publisher()
        self.event_bus = event_bus
        self.emit_analytics = emit_analytics
        self.emit_event_bus = emit_event_bus

    async def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        source: str = "agent_framework",
    ) -> dict[str, Any]:
        event = build_analytics_event(event_type, payload or {}, source=source, metadata=metadata)

        if self.emit_analytics:
            await self.analytics.publish(event_type, event)

        if self.emit_event_bus and self.event_bus is not None:
            try:
                await self.event_bus.publish(event_type, event)
            except Exception:
                logger.exception("observer.event_bus_failed event_type=%s", event_type)

        return event

    async def emit_ic(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        return await self.emit(f"IC.{code}", payload, metadata=metadata)

    async def emit_noc(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        meta = dict(metadata)
        meta["noc"] = True
        return await self.emit(f"NOC.{code}", payload, metadata=meta)

    async def emit_grl(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        return await self.emit(f"GRL.{code}", payload, metadata=metadata)
