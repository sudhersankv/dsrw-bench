"""Reads configs/models.yaml and builds a client for each entry."""

from __future__ import annotations

import os
import zlib
from pathlib import Path
from typing import cast

import yaml

from swb.clients.base import HttpEndpoint
from swb.clients.decision_api import DecisionApiClient
from swb.clients.openai_chat import OpenAIChatClient
from swb.contracts import DecisionClient, ModelEntry
from swb.runner.backoff import Backoff, BackoffConfig

DEFAULT_CHAT_PATH = "/v1/chat/completions"
DEFAULT_BACKOFF = BackoffConfig()


class ConfigError(Exception):
    """A model entry cannot be turned into a client."""


def load_models(path: str | Path) -> list[ModelEntry]:
    with Path(path).open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    return [ModelEntry.model_validate(item) for item in document["models"]]


def _env(name: str, entry_id: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"model {entry_id}: environment variable {name} is not set")
    return value


def _base_url(entry: ModelEntry) -> str:
    if entry.base_url:
        return entry.base_url.rstrip("/")
    if entry.base_url_env:
        return _env(entry.base_url_env, entry.id).rstrip("/")
    raise ConfigError(f"model {entry.id}: set base_url or base_url_env")


def _endpoint(entry: ModelEntry, path: str, backoff_config: BackoffConfig) -> HttpEndpoint:
    api_key = _env(entry.api_key_env, entry.id) if entry.api_key_env else None
    backoff = Backoff(backoff_config, seed=zlib.crc32(entry.id.encode()))
    return HttpEndpoint(entry.id, f"{_base_url(entry)}{path}", api_key, backoff)


def _parse_mock_spec(model_id: str) -> dict[str, str]:
    """A mock's model_id is a spec: `kind=window,horizon=1000,noise=0.05,seed=1,ladder_gain=1`."""
    try:
        return dict(pair.split("=", 1) for pair in model_id.split(","))
    except ValueError as exc:
        raise ConfigError(f"bad mock spec {model_id!r}") from exc


def _mock_client(entry: ModelEntry) -> DecisionClient:
    from swb.baselines.mock_readers import MockReader  # module B is optional at import time

    spec = _parse_mock_spec(entry.model_id)
    reader = MockReader(
        entry.id,
        spec["kind"],
        float(spec.get("horizon", "1000")),
        float(spec.get("noise", "0")),
        int(spec.get("seed", "0")),
        ladder_gain=float(spec.get("ladder_gain", "1")),
        window=entry.window,
    )
    return cast(DecisionClient, reader)


def get_client(
    entry: ModelEntry, backoff_config: BackoffConfig = DEFAULT_BACKOFF
) -> DecisionClient:
    if entry.adapter == "mock":
        return _mock_client(entry)
    if entry.adapter == "decision_api":
        endpoint = _endpoint(entry, entry.path or "", backoff_config)
        return DecisionApiClient(entry.id, entry.model_id, entry.window, endpoint)
    endpoint = _endpoint(entry, entry.path or DEFAULT_CHAT_PATH, backoff_config)
    return OpenAIChatClient(entry.id, entry.model_id, entry.window, endpoint)


async def close_clients(clients: dict[str, DecisionClient]) -> None:
    for client in clients.values():
        endpoint = getattr(client, "endpoint", None)
        if isinstance(endpoint, HttpEndpoint):
            await endpoint.aclose()
