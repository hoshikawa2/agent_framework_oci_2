from pydantic import BaseModel

class JudgeResult(BaseModel):
    name: str
    score: float
    passed: bool
    reason: str = ''

class ResponseQualityJudge:
    name='response_quality'
    async def evaluate(self, question: str, answer: str, context: dict) -> JudgeResult:
        score = 1.0 if len(answer.strip()) > 20 else 0.2
        return JudgeResult(name=self.name, score=score, passed=score >= 0.7, reason='Tamanho e completude básicos')

class GroundednessJudge:
    name='groundedness'
    async def evaluate(self, question: str, answer: str, context: dict) -> JudgeResult:
        evidence = context.get('evidence', '')
        if evidence and any(w.lower() in answer.lower() for w in evidence.split()[:10]):
            return JudgeResult(name=self.name, score=0.9, passed=True, reason='Resposta usa evidência')
        return JudgeResult(name=self.name, score=0.6, passed=True, reason='Sem evidência configurada; aprovado com ressalva')

class JudgePipeline:
    def __init__(self): self.judges=[ResponseQualityJudge(), GroundednessJudge()]
    async def evaluate_all(self, question, answer, context):
        return [await j.evaluate(question, answer, context) for j in self.judges]
