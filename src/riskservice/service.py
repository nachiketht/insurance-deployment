"""The deployable unit: wraps the unchanged Week 8 risk_scoring_agent. Identical on both targets."""

import hashlib
import time
from pathlib import Path

from underwriting.agents.risk import risk_scoring_agent
from underwriting.llm import LLMClient, LLMResponse
from underwriting.models import EnrichmentResult, IntakeResult


class _Counting:
    """Counts tokens across every model call (including the agent's one repair call)."""

    def __init__(self, inner: LLMClient):
        self.inner, self.calls = inner, []

    def complete(self, **kw) -> LLMResponse:
        r = self.inner.complete(**kw)
        self.calls.append(r)
        return r


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_risk_service(doc: dict, llm: LLMClient) -> dict:
    intake = IntakeResult.model_validate(doc["intake"])
    enrichment = EnrichmentResult.model_validate(doc["enrichment"])
    counting = _Counting(llm)
    start = time.perf_counter()
    result = risk_scoring_agent(intake, enrichment, llm=counting)
    ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "result": result.model_dump(),
        "usage": {
            "model": counting.calls[-1].model if counting.calls else None,
            "model_calls": len(counting.calls),
            "input_tokens": sum(c.input_tokens for c in counting.calls),
            "output_tokens": sum(c.output_tokens for c in counting.calls),
            "duration_ms": ms,
        },
    }
