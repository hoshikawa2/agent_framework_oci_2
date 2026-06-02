from __future__ import annotations

from typing import Any

from .base import RailDecision
from .rails import (
    ComplianceRail,
    GroundednessRail,
    HallucinationRiskRail,
    JailbreakRail,
    LoopRail,
    MessageSizeRail,
    OutOfScopeRail,
    OutputPiiMaskRail,
    PiiMaskRail,
    PrematureActionRail,
    PromptInjectionRail,
    RetrievalRelevanceRail,
    ToolValidationRail,
    ToxicityRail,
)


class GuardrailPipeline:
    """Pipeline default de rails.

    Os rails de input/output são executados em sequência. Rails com
    sanitized_text alteram o texto corrente; rails não bloqueantes retornam
    allowed=True com metadata para auditoria. Os rails de retrieval/tool ficam
    disponíveis por métodos dedicados, sem quebrar compatibilidade com o fluxo
    LangGraph atual.
    """

    def __init__(self, input_rails=None, output_rails=None, retrieval_rails=None, tool_rails=None):
        self.input_rails = input_rails or [
            MessageSizeRail(),
            PiiMaskRail(),
            ToxicityRail(),
            PromptInjectionRail(),
            JailbreakRail(),
            LoopRail(),
        ]
        self.output_rails = output_rails or [
            OutputPiiMaskRail(),
            ComplianceRail(),
            PrematureActionRail(),
            GroundednessRail(),
            HallucinationRiskRail(),
        ]
        self.retrieval_rails = retrieval_rails or [RetrievalRelevanceRail(), PiiMaskRail()]
        self.tool_rails = tool_rails or [ToolValidationRail()]

    async def _run(self, text: str, context: dict[str, Any], rails: list) -> tuple[str, list[RailDecision]]:
        current = text
        decisions: list[RailDecision] = []
        for rail in rails:
            decision = await rail.evaluate(current, context)
            decisions.append(decision)
            if decision.sanitized_text is not None:
                current = decision.sanitized_text
            if not decision.allowed:
                return current, decisions
        return current, decisions

    async def run_input(self, text, context):
        return await self._run(text, context or {}, self.input_rails)

    async def run_output(self, text, context):
        current, decisions = await self._run(text, context or {}, self.output_rails)
        if any((not decision.allowed and decision.code == "REVPREC") for decision in decisions):
            return (
                "Não posso confirmar essa ação sem validação operacional. Posso explicar o próximo passo.",
                decisions,
            )
        return current, decisions

    async def run_retrieval(self, chunk_text: str, context: dict[str, Any] | None = None):
        return await self._run(chunk_text, context or {}, self.retrieval_rails)

    async def run_tool(self, tool_name: str, tool_args: dict[str, Any], context: dict[str, Any] | None = None):
        ctx = dict(context or {})
        ctx.setdefault("tool_name", tool_name)
        ctx.setdefault("tool_args", tool_args or {})
        return await self._run(tool_name, ctx, self.tool_rails)
