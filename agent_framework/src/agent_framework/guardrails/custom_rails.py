from __future__ import annotations

from typing import Any

from .pipeline import GuardrailPipeline
from .rails import (
    ComplianceRail,
    MessageSizeRail,
    OutputPiiMaskRail,
    PiiMaskRail,
    PrematureActionRail,
    PromptInjectionRail,
    ToxicityRail,
)


class CustomRails:
    """Ponto de extensão para agentes TIM.

    Subclasses implementam configure() e registram rails específicos com add().
    O bundle mínimo é carregado por padrão para manter piso de segurança.
    """

    def __init__(self, *, skip_default_bundle: bool = False):
        self.input_rails: list[Any] = []
        self.output_rails: list[Any] = []
        if not skip_default_bundle:
            self._load_default_bundle()
        self.configure()

    def _load_default_bundle(self) -> None:
        self.input_rails.extend([MessageSizeRail(), PiiMaskRail(), PromptInjectionRail()])
        self.output_rails.extend([OutputPiiMaskRail(), ToxicityRail(), ComplianceRail(), PrematureActionRail()])

    def configure(self) -> None:
        """Override em subclasses."""

    def add(self, rail: Any, *, stage: str | None = None) -> None:
        target_stage = stage or getattr(rail, "stage", "input")
        if target_stage == "output":
            self.output_rails.append(rail)
        else:
            self.input_rails.append(rail)

    def as_pipeline(self) -> GuardrailPipeline:
        return GuardrailPipeline(input_rails=self.input_rails, output_rails=self.output_rails)

    async def apply_input(self, user_message: str, **ctx: Any):
        return await self.as_pipeline().run_input(user_message, ctx)

    async def apply_output(self, candidate_response: str, **ctx: Any):
        return await self.as_pipeline().run_output(candidate_response, ctx)
