"""Adapter for the decisions endpoints (Snap, and Jev and OpenJev through the Neon gateway)."""

from __future__ import annotations

import math
from typing import Any

from swb.clients.base import HttpEndpoint, MalformedResponse
from swb.contracts import DecisionResult, Question

SUM_TOLERANCE = 0.02


def build_payload(model_id: str, state: str, questions: dict[str, Question]) -> dict[str, Any]:
    return {
        "model": model_id,
        "state": state,
        "questions": {
            name: {
                "type": "choice",
                "instructions": question.instructions,
                "criteria": {option: None for option in question.options},
            }
            for name, question in questions.items()
        },
    }


def _read_probabilities(answer: Any, question: Question) -> dict[str, float]:
    if not isinstance(answer, dict) or not isinstance(answer.get("probabilities"), dict):
        raise MalformedResponse(f"no probabilities for {question.name}")
    given: dict[str, Any] = answer["probabilities"]
    if set(given) != set(question.options):
        raise MalformedResponse(f"options do not match for {question.name}")
    values: dict[str, float] = {}
    for option, value in given.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MalformedResponse(f"non-numeric probability for {question.name}")
        if not math.isfinite(value) or value < 0:
            raise MalformedResponse(f"invalid probability for {question.name}")
        values[option] = float(value)
    if abs(sum(values.values()) - 1.0) > SUM_TOLERANCE:
        raise MalformedResponse(f"probabilities do not sum to 1 for {question.name}")
    return values


def parse_answers(
    body: dict[str, Any], questions: dict[str, Question]
) -> tuple[dict[str, dict[str, float]], int]:
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise MalformedResponse("no answers object")
    probabilities = {
        name: _read_probabilities(answers.get(name), question)
        for name, question in questions.items()
    }
    usage = body.get("usage")
    tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise MalformedResponse("no usage.input_tokens")
    return probabilities, tokens


class DecisionApiClient:
    def __init__(self, name: str, model_id: str, window: int, endpoint: HttpEndpoint) -> None:
        self.name = name
        self.model_id = model_id
        self.window = window
        self.endpoint = endpoint

    async def decide(self, state: str, questions: dict[str, Question]) -> DecisionResult:
        payload = build_payload(self.model_id, state, questions)
        (probabilities, tokens), reply = await self.endpoint.post(
            payload, lambda body: parse_answers(body, questions)
        )
        return DecisionResult(
            probabilities=probabilities,
            input_tokens=tokens,
            latency_ms=reply.latency_ms,
            http_status=reply.status,
            billed_attempts=reply.billed_attempts,
            model_version=reply.body.get("model"),
            probabilities_source="model",
            raw=reply.body,
        )
