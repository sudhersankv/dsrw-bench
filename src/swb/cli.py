"""The `swb` command line."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from dotenv import load_dotenv

from swb.clients.registry import close_clients, get_client, load_models
from swb.config import RunConfig, budget_cap_usd, load_run_config
from swb.contracts import Job, ModelEntry
from swb.runner import tokens
from swb.runner.jobs import ModelEstimate, estimate, expand_config
from swb.runner.queue import RunSummary, run_jobs
from swb.store.base import ResultStore
from swb.store.db import PostgresStore
from swb.store.jsonl import JsonlStore

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_MODELS = Path("configs/models.yaml")
DEFAULT_STORE = "jsonl:out/results.jsonl"
DEMO_PATH = Path("out/demo.jsonl")
PILOT_CONFIG = Path("configs/pilot.yaml")
CALIBRATION_FILE = Path("configs/token_calibration.json")

ModelsFile = Annotated[Path, typer.Option("--models-file", help="Model registry YAML.")]
StoreOption = Annotated[str, typer.Option("--store", help="jsonl:PATH, postgres, or postgres:URL.")]
CalibrationFile = Annotated[Path, typer.Option("--calibration", help="`swb calibrate` output.")]


def open_store(spec: str) -> ResultStore:
    if spec.startswith("jsonl:"):
        return JsonlStore(spec.removeprefix("jsonl:"))
    if spec == "postgres":
        url = os.environ.get("DATABASE_URL", "").strip()
        if not url:
            raise typer.BadParameter("DATABASE_URL is not set")
        return PostgresStore(url)
    if spec.startswith("postgres:"):
        return PostgresStore(spec.removeprefix("postgres:"))
    raise typer.BadParameter(f"unknown store {spec!r}; use jsonl:PATH or postgres")


def _select(models: list[ModelEntry], wanted: str | None) -> list[ModelEntry]:
    if not wanted:
        return models
    ids = [item.strip() for item in wanted.split(",") if item.strip()]
    unknown = sorted(set(ids) - {entry.id for entry in models})
    if unknown:
        raise typer.BadParameter(f"unknown models: {', '.join(unknown)}")
    return [entry for entry in models if entry.id in ids]


def _print_estimates(rows: list[ModelEstimate]) -> None:
    header = f"{'run':<14}{'model':<20}{'calls':>9}{'tokens':>16}{'dollars':>11}{'Neon hours':>12}"
    typer.echo(header)
    for row in rows:
        hours = f"{row.hours_at_limit:.2f}" if row.hours_at_limit is not None else "-"
        typer.echo(
            f"{row.run_id:<14}{row.model:<20}{row.calls:>9,}{row.tokens:>16,}"
            f"{row.usd:>11.2f}{hours:>12}"
        )


def _print_totals(rows: list[ModelEstimate]) -> None:
    typer.echo("")
    for model in sorted({row.model for row in rows}):
        own = [row for row in rows if row.model == model]
        hours = sum(row.hours_at_limit or 0.0 for row in own)
        typer.echo(
            f"total {model:<20}{sum(r.calls for r in own):>9,}{sum(r.tokens for r in own):>16,}"
            f"{sum(r.usd for r in own):>11.2f}{hours:>12.2f}"
        )


@app.command("dry-run")
def dry_run(
    configs: Annotated[list[Path], typer.Argument(help="One or more run configs.")],
    models_file: ModelsFile = DEFAULT_MODELS,
) -> None:
    """Print calls, tokens, dollars and Neon hours per model and run. Calls nothing."""
    models = load_models(models_file)
    rows: list[ModelEstimate] = []
    for path in configs:
        config = load_run_config(path)
        rows.extend(estimate(config, expand_config(config, models), models))
    _print_estimates(rows)
    _print_totals(rows)


def _execute(
    jobs: list[Job],
    config: RunConfig,
    models: list[ModelEntry],
    store: ResultStore,
    calibration: tokens.Calibration | None = None,
) -> RunSummary:
    async def main() -> RunSummary:
        clients = {entry.id: get_client(entry) for entry in models}
        try:
            return await run_jobs(
                jobs,
                clients,
                store,
                entries=models,
                cap_usd=budget_cap_usd(),
                concurrency=config.concurrency,
                rate_limits=config.rate_limits,
                calibration=calibration,
            )
        finally:
            await close_clients(clients)

    return asyncio.run(main())


def _report(summary: RunSummary) -> None:
    typer.echo(
        f"completed {summary.completed}, skipped {summary.skipped}, "
        f"failed {len(summary.failed)}, refused {len(summary.refused)}, "
        f"token check {len(summary.token_problems)}"
    )
    for model, reason in summary.stopped_models.items():
        typer.echo(f"stopped {model}: {reason}")
    if summary.stopped_run:
        typer.echo(f"run stopped: {summary.stopped_run}")


def _required_calibration(
    config: RunConfig, models: list[ModelEntry], path: Path
) -> tokens.Calibration | None:
    """The measured rates this config will be checked against. Refuses to spend without them."""
    paid = [entry for entry in models if entry.adapter != "mock"]
    if not config.requires_calibration or not paid:
        return None
    calibration = tokens.load(path)
    problems = tokens.calibration_problems(calibration, config, paid)
    if problems:
        for problem in problems:
            typer.echo(f"token check: {problem}", err=True)
        raise typer.Exit(code=2)
    return calibration


def _run_config(
    config_path: Path,
    models_file: Path,
    wanted: str | None,
    store_spec: str,
    yes: bool,
    calibration_path: Path = CALIBRATION_FILE,
) -> None:
    all_models = load_models(models_file)
    if any(entry.adapter != "mock" for entry in all_models):
        load_dotenv()
    models = _select(all_models, wanted)
    config = load_run_config(config_path)
    calibration = _required_calibration(config, models, calibration_path)
    jobs = expand_config(config, models)
    _print_estimates(estimate(config, jobs, models))
    paid = any(entry.adapter != "mock" for entry in models)
    if paid and not yes:
        typer.confirm("Make these calls?", abort=True)
    store = open_store(store_spec)
    summary = _execute(jobs, config, models, store, calibration)
    _report(summary)
    if not summary.clean:
        raise typer.Exit(code=1)


@app.command()
def run(
    config: Annotated[Path, typer.Argument(help="A run config in configs/.")],
    models: Annotated[str | None, typer.Option("--models", help="Comma-separated ids.")] = None,
    store: StoreOption = DEFAULT_STORE,
    models_file: ModelsFile = DEFAULT_MODELS,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation.")] = False,
    calibration: CalibrationFile = CALIBRATION_FILE,
) -> None:
    """Run one config. Resumes by job id if the store already has results."""
    _run_config(config, models_file, models, store, yes, calibration)


@app.command()
def pilot(
    models: Annotated[str | None, typer.Option("--models", help="Comma-separated ids.")] = None,
    store: StoreOption = DEFAULT_STORE,
    models_file: ModelsFile = DEFAULT_MODELS,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation.")] = False,
) -> None:
    """Run the pilot and format checks on reserved seeds."""
    _run_config(PILOT_CONFIG, models_file, models, store, yes)


@app.command()
def demo(
    out: Annotated[Path, typer.Option("--out", help="JSONL results path.")] = DEMO_PATH,
    data: Annotated[Path, typer.Option("--data", help="Site data folder.")] = Path(
        "web/public/data"
    ),
    analyze_after: Annotated[bool, typer.Option("--analyze/--no-analyze")] = True,
) -> None:
    """Run fake mock readers through the whole pipeline. These results are not findings."""
    from swb.runner.demo import demo_config, demo_models

    for stale in (out, out.with_name(out.name + ".budget")):
        stale.unlink(missing_ok=True)
    config = demo_config()
    models = demo_models()
    store = JsonlStore(out)
    jobs = expand_config(config, models)
    typer.echo(f"demo: {len(jobs)} jobs, {len(models)} fake models; results are not findings")
    summary = _execute(jobs, config, models, store)
    _report(summary)
    if not summary.clean:
        raise typer.Exit(code=1)
    if analyze_after:
        _build_site(store, data)


@app.command()
def calibrate(
    store: StoreOption = DEFAULT_STORE,
    out: CalibrationFile = CALIBRATION_FILE,
) -> None:
    """Measure tokens per day per model and world from stored pilot calls."""
    calibration = tokens.measure(open_store(store).rows())
    if not calibration:
        typer.echo("no pilot calls to measure; run `swb pilot` first", err=True)
        raise typer.Exit(code=2)
    tokens.save(calibration, out)
    for model, rates in sorted(calibration.items()):
        for world, rate in sorted(rates.items()):
            typer.echo(f"{model:<20}{world:<10}{rate.tokens_per_day:>8.2f} tokens per day")
    typer.echo(f"wrote {out}")


def _build_site(store: ResultStore, out: Path, models_file: Path = DEFAULT_MODELS) -> None:
    from swb.analysis.cards import build_site
    from swb.runner.demo import demo_models

    rows = store.rows()
    registry = load_models(models_file) if models_file.exists() else []
    build_site(
        rows,
        out,
        is_demo=any(row.is_mock for row in rows),
        models=[*registry, *demo_models()],
    )
    typer.echo(f"wrote site data to {out}")


@app.command()
def worker(
    configs: Annotated[
        str,
        typer.Option(
            "--configs", envvar="SWB_WORKER_CONFIGS", help="Comma-separated run configs, in order."
        ),
    ] = "",
    models: Annotated[
        str | None,
        typer.Option("--models", envvar="SWB_WORKER_MODELS", help="Comma-separated ids."),
    ] = None,
    store: StoreOption = "postgres",
    models_file: ModelsFile = DEFAULT_MODELS,
) -> None:
    """Run the named configs without prompting, then exit. With none named, do nothing."""
    # A first `fly deploy` boots every process group, so an unconfigured runner must not spend.
    paths = [Path(item.strip()) for item in configs.split(",") if item.strip()]
    if not paths:
        typer.echo("SWB_WORKER_CONFIGS is not set; nothing to run")
        return
    for path in paths:
        typer.echo(f"worker: running {path}")
        _run_config(path, models_file, models, store, yes=True)


@app.command()
def analyze(
    store: StoreOption = DEFAULT_STORE,
    out: Annotated[Path, typer.Option("--out", help="Site data folder.")] = Path("web/public/data"),
) -> None:
    """Build the site JSON from stored results."""
    _build_site(open_store(store), out)


@app.command()
def gates() -> None:
    """Run the validation gates. They live in the test suite and make no network calls."""
    if not Path("tests").is_dir():
        typer.echo("gates need the tests folder; run them from a checkout, not the Fly image")
        raise typer.Exit(code=2)
    result = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], check=False)
    raise typer.Exit(code=result.returncode)


@app.command()
def export(
    store: StoreOption = DEFAULT_STORE,
    out: Annotated[Path, typer.Option("--out", help="Parquet path.")] = Path("out/results.parquet"),
) -> None:
    """Export stored results to parquet. Nested fields become JSON text."""
    rows = [_flat(row.model_dump()) for row in open_store(store).rows()]
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(out)
    typer.echo(f"wrote {len(rows)} rows to {out}")


def _flat(row: dict[str, object]) -> dict[str, object]:
    return {
        key: json.dumps(value) if isinstance(value, (dict, list)) else value
        for key, value in row.items()
    }
