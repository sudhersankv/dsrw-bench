"""The dashboard serves the built site and the data folder, and stays up without them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from swb.dashboard.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>site</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("run()", encoding="utf-8")
    data = tmp_path / "data"
    (data / "models").mkdir(parents=True)
    (data / "index.json").write_text('{"is_demo": true}', encoding="utf-8")
    (data / "models" / "a.json").write_text('{"model_id": "a"}', encoding="utf-8")
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    return TestClient(create_app(data, dist))


def test_healthz_reports_site_and_data(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "site": True, "data": True}


def test_root_serves_the_built_site(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>site</title>" in response.text
    assert client.get("/assets/app.js").text == "run()"


def test_data_comes_from_the_data_dir(client: TestClient) -> None:
    assert client.get("/data/index.json").json() == {"is_demo": True}
    assert client.get("/data/models/a.json").json() == {"model_id": "a"}
    assert client.get("/data/models/missing.json").status_code == 404


def test_data_route_does_not_escape_its_folder(client: TestClient) -> None:
    assert client.get("/data/%2e%2e/secret.txt").status_code == 404


@pytest.fixture
def share_client(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        '<head><!-- og:start --><meta property="og:image" content="/x" /><!-- og:end --></head>',
        encoding="utf-8",
    )
    data = tmp_path / "data"
    (data / "models").mkdir(parents=True)
    (data / "og").mkdir()
    (data / "og" / "a.png").write_bytes(b"png")
    card = {"display": 'A <"model">', "flock_score": 66.4, "verdict_line": "Good.", "is_demo": True}
    (data / "models" / "a.json").write_text(json.dumps(card), encoding="utf-8")
    return TestClient(create_app(data, dist))


def test_home_has_absolute_preview_tags(share_client: TestClient) -> None:
    text = share_client.get("/", headers={"x-forwarded-proto": "https", "host": "x.dev"}).text
    assert 'content="https://x.dev/data/og/site.png"' in text
    assert "summary_large_image" in text


def test_model_path_has_its_own_escaped_preview(share_client: TestClient) -> None:
    text = share_client.get("/model/a", headers={"host": "x.dev"}).text
    assert "/data/og/a.png" in text
    assert "Flock score 66/100" in text
    assert "DEMO DATA" in text
    assert 'A <"model">' not in text


def test_unknown_or_unsafe_model_paths_are_404(share_client: TestClient) -> None:
    assert share_client.get("/model/nope").status_code == 404
    assert share_client.get("/model/%2e%2e").status_code == 404


def test_app_boots_and_reports_when_folders_are_missing(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "no-data", tmp_path / "no-dist"))
    assert client.get("/healthz").json() == {"ok": True, "site": False, "data": False}
    assert client.get("/data/index.json").status_code == 404
