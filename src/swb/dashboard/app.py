"""Serves web/dist at / and the precomputed JSON at /data, with link previews for shared pages."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

DEFAULT_DATA_DIR = "web/public/data"
DEFAULT_DIST_DIR = "web/dist"
_SITE_TITLE = "Does the Sheep Remember the Wolf?"
_SITE_DESCRIPTION = (
    "An AI reads a sheep's diary and must pick the safe field. "
    "A benchmark of how far back decision models really remember."
)
_OG_BLOCK = re.compile(r"<!-- og:start -->.*?<!-- og:end -->", re.DOTALL)
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _public_base(request: Request) -> str:
    """X needs absolute image URLs, and Fly terminates TLS in front of the app."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}"


def _meta_tags(title: str, description: str, image_url: str, page_url: str) -> str:
    fields = {
        "title": html.escape(title, quote=True),
        "description": html.escape(description, quote=True),
        "image": html.escape(image_url, quote=True),
        "url": html.escape(page_url, quote=True),
    }
    return (
        f'<meta property="og:type" content="website" />\n'
        f'    <meta property="og:title" content="{fields["title"]}" />\n'
        f'    <meta property="og:description" content="{fields["description"]}" />\n'
        f'    <meta property="og:image" content="{fields["image"]}" />\n'
        f'    <meta property="og:url" content="{fields["url"]}" />\n'
        f'    <meta name="twitter:card" content="summary_large_image" />\n'
        f'    <meta name="twitter:title" content="{fields["title"]}" />\n'
        f'    <meta name="twitter:description" content="{fields["description"]}" />\n'
        f'    <meta name="twitter:image" content="{fields["image"]}" />'
    )


def _flock_text(card: dict[str, object]) -> str:
    flock = card.get("flock_score")
    return f"Flock score {flock:.0f}/100" if isinstance(flock, (int, float)) else "Not testable"


def _model_preview(card: dict[str, object]) -> tuple[str, str]:
    demo = "DEMO DATA, NOT A MODEL RESULT. " if card.get("is_demo") else ""
    title = f"{demo}{card.get('display', 'Model')}: {_flock_text(card)}"
    return title, str(card.get("verdict_line", _SITE_DESCRIPTION))


def create_app(data_dir: Path, dist_dir: Path) -> FastAPI:
    api = FastAPI(title=_SITE_TITLE, docs_url=None, redoc_url=None)
    index_html = dist_dir / "index.html"

    def page(request: Request, title: str, description: str, image: str, path: str) -> HTMLResponse:
        base = _public_base(request)
        tags = _meta_tags(title, description, f"{base}{image}", f"{base}{path}")
        return HTMLResponse(_OG_BLOCK.sub(lambda _: tags, index_html.read_text(encoding="utf-8")))

    @api.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {
            "ok": True,
            "site": index_html.is_file(),
            "data": (data_dir / "index.json").is_file(),
        }

    if index_html.is_file():

        @api.get("/", response_class=HTMLResponse)
        def home(request: Request) -> HTMLResponse:
            return page(request, _SITE_TITLE, _SITE_DESCRIPTION, "/data/og/site.png", "/")

        @api.get("/model/{model_id}", response_class=HTMLResponse)
        def model(request: Request, model_id: str) -> HTMLResponse:
            card_path = data_dir / "models" / f"{model_id}.json"
            if not _MODEL_ID.fullmatch(model_id) or not card_path.is_file():
                raise HTTPException(status_code=404)
            title, description = _model_preview(json.loads(card_path.read_text(encoding="utf-8")))
            image = (
                f"/data/og/{model_id}.png"
                if (data_dir / "og" / f"{model_id}.png").is_file()
                else "/data/og/site.png"
            )
            return page(request, title, description, image, f"/model/{model_id}")

    # Starlette fails the request on a missing folder, so an absent one is simply not mounted.
    if data_dir.is_dir():
        api.mount("/data", StaticFiles(directory=data_dir), name="data")
    if dist_dir.is_dir():
        api.mount("/", StaticFiles(directory=dist_dir, html=True), name="site")
    return api


app = create_app(
    Path(os.environ.get("SWB_DATA_DIR", DEFAULT_DATA_DIR)),
    Path(os.environ.get("SWB_WEB_DIST", DEFAULT_DIST_DIR)),
)
