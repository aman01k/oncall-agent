"""Shared, validated incident and evidence contracts."""
from typing import Literal
import json
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(StrictModel):
    tool_call_id: str
    quote: str = Field(min_length=4, max_length=240, description="Copy one short contiguous substring from an actual tool result. Prefer a string value, such as summary, exception or code diff. Never concatenate JSON fields or paraphrase.")


class Action(StrictModel):
    kind: Literal["restart", "rollback"]
    target: str | None = None
    reason: str = Field(min_length=5)


class TimelineEvent(StrictModel):
    ts: str
    description: str


class Report(StrictModel):
    summary: str = Field(max_length=600)
    failure_type: Literal["bad_deploy", "db_pool_exhaustion", "memory_leak", "unknown"] = Field(
        description="bad_deploy means request logic/schema exceptions such as KeyError. db_pool_exhaustion means connection contention/timeouts. memory_leak means unbounded retained allocations/cache growth, even when introduced by a deployment. Use the specific resource fault rather than the generic deployment label.")
    culprit: str
    confidence: Literal["low", "medium", "high"]
    timeline: list[TimelineEvent] = Field(max_length=6)
    evidence: list[Citation] = Field(min_length=1, max_length=5)
    next_steps: list[str] = Field(min_length=1, max_length=5)
    proposed_actions: list[Action] = Field(default_factory=list, max_length=2)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def verify_evidence(report, outputs):
    errors = []
    for citation in report.evidence:
        value = outputs.get(citation.tool_call_id)
        if value is None or not any(citation.quote in text for text in [json.dumps(value), *strings(value)]):
            errors.append(f"Unverified quote for {citation.tool_call_id}: {citation.quote[:60]}")
    return errors
