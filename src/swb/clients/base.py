"""HTTP plumbing shared by the adapters: retries, error classes, latency measurement."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from swb.runner.backoff import Backoff

DAILY_LIMIT_CODE = "REQUEST_LIMIT_EXCEEDED"
TIMEOUT_S = 300.0

Sleep = Callable[[float], Awaitable[None]]


class MalformedResponse(Exception):
    """The body could not be read as a valid answer."""


class CallFailed(Exception):
    """One job failed after retries. The run continues; the job stays undone for resume."""

    def __init__(self, message: str, billed_attempts: int = 0) -> None:
        super().__init__(message)
        self.billed_attempts = billed_attempts

    @property
    def maybe_billed(self) -> bool:
        return self.billed_attempts > 0


class StopModel(Exception):
    """No further calls to this model in this run (for example, the daily spend cap)."""


class StopRun(Exception):
    """No further calls at all: credits exhausted (402) or credentials refused (401, 403)."""


@dataclass(frozen=True)
class HttpReply:
    body: dict[str, Any]
    status: int
    latency_ms: int
    billed_attempts: int = 1


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _is_retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _raise_for_terminal(response: httpx.Response, model: str) -> None:
    status = response.status_code
    if status == 402:
        raise StopRun(f"{model}: HTTP 402, credits exhausted")
    if status in (401, 403):
        raise StopRun(f"{model}: HTTP {status}, credentials refused")
    if status != 200 and not _is_retryable(status):
        raise CallFailed(f"{model}: HTTP {status}")


class HttpEndpoint:
    """POSTs JSON and returns a parsed reply, retrying what the spec says to retry."""

    def __init__(
        self,
        model: str,
        url: str,
        api_key: str | None,
        backoff: Backoff,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.model = model
        self.url = url
        self.backoff = backoff
        self.sleep = sleep
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(headers=headers, timeout=TIMEOUT_S)

    async def post(self, payload: dict[str, Any], parse: Callable[[dict[str, Any]], Any]) -> Any:
        """Returns (parse(body), HttpReply). Raises CallFailed, StopModel or StopRun."""
        attempts = self.backoff.config.max_attempts
        billed_attempts = 0
        last_error = "no attempts made"
        limited = False
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                response = await self._http.post(self.url, json=payload)
            except httpx.TransportError as exc:
                last_error = f"transport error: {exc!r}"
                await self._wait(attempt, attempts, None)
                continue
            latency_ms = int((time.perf_counter() - started) * 1000)
            _raise_for_terminal(response, self.model)
            if response.status_code != 200:
                last_error = f"HTTP {response.status_code}"
                limited = response.status_code == 429 and DAILY_LIMIT_CODE in response.text
                await self._wait(attempt, attempts, _retry_after(response))
                continue
            billed_attempts += 1
            try:
                body = response.json()
                if not isinstance(body, dict):
                    raise MalformedResponse("body is not an object")
                reply = HttpReply(body, response.status_code, latency_ms, billed_attempts)
                return parse(body), reply
            except (MalformedResponse, ValueError) as exc:
                last_error = f"malformed response: {exc}"
                await self._wait(attempt, attempts, None)
        if limited:
            # The gateway uses this code for short bursts too, so only a limit that outlasts every
            # retry is treated as the daily spend cap.
            raise StopModel(f"{self.model}: limit outlasted retries ({DAILY_LIMIT_CODE})")
        raise CallFailed(f"{self.model}: {last_error}", billed_attempts=billed_attempts)

    async def _wait(self, attempt: int, attempts: int, retry_after: float | None) -> None:
        if attempt + 1 < attempts:
            await self.sleep(self.backoff.delay(attempt, retry_after))

    async def aclose(self) -> None:
        await self._http.aclose()
