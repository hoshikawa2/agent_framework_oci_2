"""Guardrails pragmáticos para o agent_framework.

A implementação combina regras determinísticas leves com metadados ricos para
observabilidade. A maior parte dos rails não bloqueia: sinaliza risco, mascara
conteúdo sensível ou suaviza a resposta para preservar utilidade do agente.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Guardrail, RailDecision


def _lower(text: str) -> str:
    return (text or "").lower()


class PiiMaskRail(Guardrail):
    """Mascara PII em mensagens de entrada.

    Mantém compatibilidade com o código anterior, mas amplia a cobertura para
    CPF, CNPJ, telefone, e-mail, cartão, CEP, RG, tokens e chaves comuns.
    """

    code = "MSK"
    stage = "input"

    PATTERNS: list[tuple[str, str]] = [
        (r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "***CPF_MASKED***"),
        (r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", "***CNPJ_MASKED***"),
        (r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "***EMAIL_MASKED***"),
        (r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[-\s]?\d{4}\b", "***PHONE_MASKED***"),
        (r"\b(?:\d[ -]*?){13,19}\b", "***CARD_MASKED***"),
        (r"\b\d{5}-?\d{3}\b", "***CEP_MASKED***"),
        (r"(?i)\bRG\s*[:#-]?\s*[0-9A-Z.\-]{5,14}\b", "***RG_MASKED***"),
        (r"(?i)\b(?:api[_-]?key|token|secret|password|senha)\s*[:=]\s*['\"]?[A-Za-z0-9_\-.=/+]{8,}", "***SECRET_MASKED***"),
    ]

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        masked = text or ""
        hits: list[str] = []
        for pattern, replacement in self.PATTERNS:
            new_value, count = re.subn(pattern, replacement, masked)
            if count:
                hits.append(replacement.strip("*"))
            masked = new_value
        return RailDecision(
            code=self.code,
            allowed=True,
            sanitized_text=masked if masked != text else None,
            metadata={"masked": bool(hits), "entities": sorted(set(hits))},
        )


class OutputPiiMaskRail(PiiMaskRail):
    """Reutiliza o mascaramento de PII para a saída do assistente."""

    code = "PII_OUT"
    stage = "output"


class ToxicityRail(Guardrail):
    """Detecta linguagem agressiva sem bloquear por padrão."""

    code = "TOX"
    stage = "input"

    TERMS = {
        "idiota",
        "burro",
        "incompetente",
        "lixo",
        "merda",
        "porcaria",
        "droga",
        "palhaço",
    }

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        lowered = _lower(text)
        hits = sorted(term for term in self.TERMS if term in lowered)
        severity = "high" if len(hits) >= 3 else "medium" if hits else "none"
        return RailDecision(
            code=self.code,
            allowed=True,
            metadata={"toxicity_detected": bool(hits), "severity": severity, "terms": hits},
        )


class PromptInjectionRail(Guardrail):
    """Sinaliza tentativas de manipular instruções internas do agente."""

    code = "PINJ"
    stage = "input"

    PATTERNS = [
        r"ignore (all )?(previous|prior) instructions",
        r"ignore todas as instru[cç][oõ]es",
        r"esque[cç]a (as|todas as) regras",
        r"reveal (the )?(system prompt|hidden prompt|instructions)",
        r"mostre (o )?(prompt|system prompt|prompt oculto|instru[cç][oõ]es internas)",
        r"developer message",
        r"system message",
        r"act as root",
        r"modo desenvolvedor",
    ]

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        hits = [p for p in self.PATTERNS if re.search(p, text or "", flags=re.IGNORECASE)]
        score = min(1.0, 0.35 * len(hits))
        return RailDecision(
            code=self.code,
            allowed=True,
            metadata={"prompt_injection_detected": bool(hits), "score": score, "matches": hits},
        )


class JailbreakRail(Guardrail):
    """Detecta jailbreak/roleplay para burlar políticas sem bloquear de imediato."""

    code = "JBRK"
    stage = "input"

    PATTERNS = [
        r"sem limites",
        r"sem restri[cç][oõ]es",
        r"finja que",
        r"vamos fazer um roleplay",
        r"modo livre",
        r"DAN\b",
        r"bypass",
        r"contorne (as )?regras",
    ]

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        hits = [p for p in self.PATTERNS if re.search(p, text or "", flags=re.IGNORECASE)]
        score = min(1.0, 0.3 * len(hits))
        return RailDecision(
            code=self.code,
            allowed=True,
            metadata={"jailbreak_detected": bool(hits), "score": score, "matches": hits},
        )


class MessageSizeRail(Guardrail):
    """Bloqueia apenas mensagens excessivamente grandes."""

    code = "MSIZE"
    stage = "input"

    def __init__(self, max_chars: int = 12_000):
        self.max_chars = max_chars

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        size = len(text or "")
        allowed = size <= self.max_chars
        return RailDecision(
            code=self.code,
            allowed=allowed,
            reason="Mensagem muito grande para processamento seguro" if not allowed else "",
            metadata={"size": size, "max_chars": self.max_chars},
        )


class OutOfScopeRail(Guardrail):
    code = "OOS"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        intents = context.get("allowed_intents", [])
        if intents and not any(i.lower() in _lower(text) for i in intents):
            return RailDecision(
                code=self.code,
                allowed=False,
                reason="Mensagem potencialmente fora do escopo configurado",
                metadata={"allowed_intents": intents},
            )
        return RailDecision(code=self.code, allowed=True)


class LoopRail(Guardrail):
    code = "VLOOP"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        normalized = _lower(text).strip()
        history = [_lower(h).strip() for h in context.get("history_texts", [])[-6:]]
        repeated = history.count(normalized) >= 2 if normalized else False
        return RailDecision(
            code=self.code,
            allowed=not repeated,
            reason="Possível loop conversacional" if repeated else "",
            metadata={"history_window": len(history), "repeated": repeated},
        )


class PrematureActionRail(Guardrail):
    """Evita afirmar que uma ação operacional ocorreu sem confirmação de tool."""

    code = "REVPREC"
    stage = "output"

    ACTION_TERMS = [
        "já cancelei",
        "já contestei",
        "ajuste realizado",
        "foi cancelado",
        "foi contestado",
        "foi ajustado",
        "foi removido",
        "reativação concluída",
        "protocolo aberto",
    ]

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        has_action_claim = any(term in _lower(text) for term in self.ACTION_TERMS)
        confirmed = bool(
            context.get("tool_action_confirmed")
            or context.get("tool_executed")
            or context.get("tool_result")
        )
        if has_action_claim and not confirmed:
            return RailDecision(
                code=self.code,
                allowed=False,
                reason="Verbalização prematura de ação operacional",
                metadata={"has_action_claim": True, "confirmed": False},
            )
        return RailDecision(code=self.code, allowed=True, metadata={"has_action_claim": has_action_claim, "confirmed": confirmed})


class ComplianceRail(Guardrail):
    """Suaviza promessas absolutas e linguagem de garantia excessiva."""

    code = "CMP"
    stage = "output"

    REPLACEMENTS = [
        (r"(?i)\bgaranto que\b", "pelas informações disponíveis,"),
        (r"(?i)\bcom certeza absoluta\b", "com alta confiança"),
        (r"(?i)\b100% garantido\b", "previsto conforme as informações disponíveis"),
        (r"(?i)\bé impossível acontecer\b", "não é esperado acontecer"),
        (r"(?i)\bnunca haverá\b", "não há indicação de que haverá"),
    ]

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        sanitized = text or ""
        changes = 0
        for pattern, replacement in self.REPLACEMENTS:
            sanitized, count = re.subn(pattern, replacement, sanitized)
            changes += count
        return RailDecision(
            code=self.code,
            allowed=True,
            sanitized_text=sanitized if sanitized != text else None,
            metadata={"softened_absolute_claims": changes},
        )


class GroundednessRail(Guardrail):
    """Sinaliza risco quando a resposta parece específica sem evidência/tool/RAG."""

    code = "GND"
    stage = "output"

    SPECIFICITY_HINTS = ["protocolo", "valor", "data", "fatura", "contrato", "cancelamento", "contestação", "rma"]

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        has_support = bool(
            context.get("evidence")
            or context.get("sources")
            or context.get("retrieval_count")
            or context.get("tool_result")
            or context.get("tool_executed")
        )
        is_specific = any(h in _lower(text) for h in self.SPECIFICITY_HINTS) or bool(re.search(r"\b\d+[,.]?\d*\b", text or ""))
        risk = "high" if is_specific and not has_support else "low"
        return RailDecision(
            code=self.code,
            allowed=True,
            metadata={"grounded": has_support or not is_specific, "risk": risk, "is_specific": is_specific},
        )


class HallucinationRiskRail(Guardrail):
    """Marca risco de alucinação para uso por judges e telemetria."""

    code = "ALUC_RISK"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        support_count = int(bool(context.get("evidence"))) + int(bool(context.get("sources"))) + int(bool(context.get("tool_result")))
        uncertainty = any(term in _lower(text) for term in ["talvez", "provavelmente", "aparentemente", "não tenho certeza"])
        risk = "medium" if uncertainty and support_count == 0 else "low"
        if context.get("hallucination_risk") == "high":
            risk = "high"
        return RailDecision(code=self.code, allowed=True, metadata={"risk": risk, "support_count": support_count})


class RetrievalRelevanceRail(Guardrail):
    """Rail opcional para uso antes de enviar chunks recuperados ao LLM."""

    code = "RET_REL"
    stage = "retrieval"

    def __init__(self, min_score: float = 0.4):
        self.min_score = min_score

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        score = context.get("score")
        allowed = score is None or float(score) >= self.min_score
        return RailDecision(
            code=self.code,
            allowed=allowed,
            reason="Chunk descartado por baixa relevância" if not allowed else "",
            metadata={"score": score, "min_score": self.min_score},
        )


class ToolValidationRail(Guardrail):
    """Rail opcional para validar chamada de ferramenta/MCP antes da execução."""

    code = "TOOL_VAL"
    stage = "tool"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        tool_name = context.get("tool_name")
        args = context.get("tool_args") or {}
        required = context.get("required_args") or []
        missing = [name for name in required if args.get(name) in (None, "")]
        invalid_numeric = [name for name, value in args.items() if isinstance(value, (int, float)) and name in {"valor", "amount", "quantity", "quantidade"} and value < 0]
        allowed_tools = context.get("allowed_tools")
        not_allowed = bool(allowed_tools and tool_name and tool_name not in allowed_tools)
        allowed = not missing and not invalid_numeric and not not_allowed
        return RailDecision(
            code=self.code,
            allowed=allowed,
            reason="Chamada de ferramenta inválida ou não permitida" if not allowed else "",
            metadata={
                "tool_name": tool_name,
                "missing_args": missing,
                "invalid_numeric_args": invalid_numeric,
                "not_allowed": not_allowed,
            },
        )
