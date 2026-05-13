"""Typer CLI for combine-mzml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer

from .config import dump_toml, load_config

app = typer.Typer(
    help="Synthetic scan-rate reduction for DIA mzML files.",
    no_args_is_help=True,
    add_completion=False,
)


# ---------- shared helpers ----------

def _default_output(input_path: Path, method: str, factor: int) -> Path:
    return input_path.with_name(f"{input_path.stem}_{method}_{factor}.mzML")


def _parse_ms_levels(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip()]


def _load_exp(path: Path):
    # imported lazily so `--help` is snappy even without pyopenms loaded
    import pyopenms as oms

    exp = oms.MSExperiment()
    oms.MzMLFile().load(str(path), exp)
    return exp, oms


def _store_exp(oms_mod, exp, path: Path) -> None:
    oms_mod.MzMLFile().store(str(path), exp)


def _apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> None:
    """Apply CLI overrides into cfg['params']."""
    params = cfg.setdefault("params", {})
    for k, v in overrides.items():
        if v is not None:
            params[k] = v


# ---------- subcommands ----------

@app.command()
def decimate(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    factor: int = typer.Option(..., "-n", "--factor", min=1, help="Keep every Nth scan per MS level."),
    ms_levels: str = typer.Option("1,2", "--ms-levels", help="Comma-separated MS levels to decimate; others pass through."),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output mzML path."),
) -> None:
    """Keep every Nth scan, independently per MS level (no merging)."""
    from .methods.decimate import decimate as _decimate

    out_path = output or _default_output(input, "decimate", factor)
    exp, oms = _load_exp(input)
    levels = _parse_ms_levels(ms_levels)
    before = exp.getNrSpectra()
    new_exp = _decimate(exp, factor=factor, ms_levels=levels)
    _store_exp(oms, new_exp, out_path)
    typer.echo(f"decimate: {before} -> {new_exp.getNrSpectra()} spectra  ->  {out_path}")


@app.command()
def blockwise(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    factor: Optional[int] = typer.Option(None, "-n", "--factor", min=1, help="Override block_method:rt_block_size."),
    ms_levels: Optional[str] = typer.Option(None, "--ms-levels", help="Override block_method:ms_levels (comma-separated)."),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False, readable=True),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output mzML path."),
) -> None:
    """Merge spectra using SpectraMerger.mergeSpectraBlockWise."""
    from .methods.blockwise import blockwise as _blockwise

    cfg = load_config(config)
    overrides: dict[str, Any] = {}
    if factor is not None:
        overrides["block_method:rt_block_size"] = factor
    if ms_levels is not None:
        overrides["block_method:ms_levels"] = _parse_ms_levels(ms_levels)
    _apply_overrides(cfg, overrides)

    effective_factor = cfg["params"]["block_method:rt_block_size"]
    out_path = output or _default_output(input, "blockwise", int(effective_factor))

    exp, oms = _load_exp(input)
    before = exp.getNrSpectra()
    new_exp = _blockwise(exp, cfg)
    _store_exp(oms, new_exp, out_path)
    typer.echo(f"blockwise: {before} -> {new_exp.getNrSpectra()} spectra  ->  {out_path}")


@app.command()
def average(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    factor: Optional[float] = typer.Option(None, "-n", "--factor", help="Window width: FWHM for gaussian, full range for tophat."),
    type_: str = typer.Option("gaussian", "--type", "-t", help="gaussian or tophat."),
    unit: str = typer.Option("scans", "--unit", "-u", help="Unit for --factor: 'scans' (default) or 'seconds'."),
    ms_levels: str = typer.Option("1,2", "--ms-levels", help="Comma-separated MS levels to average (looped one at a time)."),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False, readable=True),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output mzML path."),
) -> None:
    """RT-average spectra using SpectraMerger.average (gaussian or tophat)."""
    from .methods.average import average as _average

    if type_ not in ("gaussian", "tophat"):
        raise typer.BadParameter("--type must be 'gaussian' or 'tophat'")
    if unit not in ("scans", "seconds"):
        raise typer.BadParameter("--unit must be 'scans' or 'seconds'")

    cfg = load_config(config)
    levels = _parse_ms_levels(ms_levels)
    label = f"average-{type_}"
    tag_factor = int(factor) if factor is not None else 0
    out_path = output or _default_output(input, label, tag_factor)

    exp, oms = _load_exp(input)
    before = exp.getNrSpectra()
    new_exp = _average(
        exp, cfg, average_type=type_, ms_levels=levels,
        factor=factor, factor_unit=unit,
    )
    _store_exp(oms, new_exp, out_path)
    typer.echo(f"{label}: {before} -> {new_exp.getNrSpectra()} spectra  ->  {out_path}")


@app.command("dump-config")
def dump_config(
    config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False, readable=True),
) -> None:
    """Print the effective TOML config to stdout (default + optional override)."""
    cfg = load_config(config)
    typer.echo(dump_toml(cfg))


if __name__ == "__main__":
    app()
