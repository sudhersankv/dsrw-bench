"""Adapter for chat-completions models. They name one option per question, so scores are top-1."""

from __future__ import annotations

import json
from typing import Any

from swb.clients.base import HttpEndpoint, MalformedResponse
from swb.contracts import DecisionResult, Question

SYSTEM_PROMPT = (
    "You answer questions about the text the user gives you. "
    "Reply with one JSON object and nothing else. "
    "Each key is a question name and each value is exactly one of that question's options."
)


def _question_block(name: str, question: Question) -> str:
    options = ", ".join(json.dumps(option) for option in question.options)
    return f"{json.dumps(name)}: {question.instructions}\nOptions: {options}"


def build_payload(model_id: str, state: str, questions: dict[str, Question]) -> dict[str, Any]:
    blocks = "\n\n".join(_question_block(name, q) for name, q in questions.items())
    return {
        "model": model_id,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{state}\n\nQuestions:\n\n{blocks}"},
        ],
    }


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0]
    return stripped


def _message_content(body: dict[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MalformedResponse("no message content") from exc
    if not isinstance(content, str):
        raise MalformedResponse("message content is not text")
    return content


def _one_hot(chosen: Any, question: Question) -> dict[str, float]:
    if chosen not in question.options:
        raise MalformedResponse(f"{chosen!r} is not an option of {question.name}")
    return {option: float(option == chosen) for option in question.options}


def parse_answers(
    body: dict[str, Any], questions: dict[str, Question]
) -> tuple[dict[str, dict[str, float]], int]:
    try:
        decoded = json.loads(_strip_fences(_message_content(body)))
    except json.JSONDecodeError as exc:
        raise MalformedResponse("message content is not JSON") from exc
    if not isinstance(decoded, dict):
        raise MalformedResponse("message content is not an object")
    probabilities = {
        name: _one_hot(decoded.get(name), question) for name, question in questions.items()
    }
    usage = body.get("usage")
    tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise MalformedResponse("no usage.prompt_tokens")
    return probabilities, tokens


class OpenAIChatClient:
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
            probabilities_source="verbalized",
            raw=reply.body,
        )
