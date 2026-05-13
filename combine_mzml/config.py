"""TOML config loading and merging for combine-mzml.

Defaults live in `default_config.toml`. A user-supplied TOML can override any
subset; CLI flags then override values from the merged TOML.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).parent / "default_config.toml"


def load_default() -> dict[str, Any]:
    with _DEFAULT_PATH.open("rb") as f:
        return tomllib.load(f)


def load_config(path: Path | None) -> dict[str, Any]:
    """Load defaults and overlay user TOML if provided.

    Both `params` and `descriptions` tables are merged shallowly so partial
    overrides only touch the keys the user specified.
    """
    cfg = load_default()
    if path is None:
        return cfg
    with Path(path).open("rb") as f:
        user = tomllib.load(f)
    for section in ("params", "descriptions"):
        if section in user:
            cfg.setdefault(section, {}).update(user[section])
    return cfg


def build_param_tuples(cfg: dict[str, Any]) -> list[tuple[str, Any, str]]:
    """Build the (key, value, description) list (kept for introspection)."""
    params: dict[str, Any] = cfg.get("params", {})
    descs: dict[str, str] = cfg.get("descriptions", {})
    return [(k, v, descs.get(k, "")) for k, v in params.items()]


def apply_to_merger(merger, cfg: dict[str, Any]) -> None:
    """Populate a SpectraMerger's params from `cfg['params']`.

    pyopenms's SpectraMerger.setParameters expects a `Param` object — not a
    list of tuples (despite what example.py implied). We start from the
    merger's own defaults and override each key the user supplied.
    """
    p = merger.getDefaults()
    for k, v in cfg.get("params", {}).items():
        # pyopenms Param.setValue is strict about types; coerce a few common
        # cases (TOML ints -> floats where the default is float, etc.).
        existing = p.getValue(k)
        if isinstance(existing, float) and isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        p.setValue(k, v)
    merger.setParameters(p)


def dump_toml(cfg: dict[str, Any]) -> str:
    """Serialize the effective config back to TOML (manual, stdlib-only)."""
    lines: list[str] = []
    for section in ("params", "descriptions"):
        if section not in cfg:
            continue
        lines.append(f"[{section}]")
        for k, v in cfg[section].items():
            lines.append(f'"{k}" = {_to_toml_value(v)}')
        lines.append("")
    return "\n".join(lines)


def _to_toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        # ensure a decimal point so it round-trips as float
        s = repr(v)
        return s if ("." in s or "e" in s or "E" in s) else f"{s}.0"
    if isinstance(v, str):
        # escape backslashes and quotes
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    if isinstance(v, list):
        return "[" + ", ".join(_to_toml_value(x) for x in v) + "]"
    raise TypeError(f"Cannot serialize {type(v).__name__} to TOML: {v!r}")
