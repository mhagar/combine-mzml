"""RT averaging via pyopenms SpectraMerger.average.

`SpectraMerger.average` operates on a single MS level per call (set via
`average_<type>:ms_level`). For DIA we loop over the requested MS levels,
overriding that key each pass so MS1 and MS2 are both averaged.

Unit handling: pyopenms's `average_tophat` has a native `rt_unit` knob, but
`average_gaussian:rt_FWHM` is always in **seconds** with no unit toggle.
We make both kernels feel the same to the caller by interpreting `factor`
in **scans** by default; pass `factor_unit="seconds"` to skip conversion.
For gaussian + scans, the conversion uses each MS level's median dt, so
MS1 and MS2 are sized correctly even if their sampling rates differ.
"""

from __future__ import annotations

import copy
from statistics import median
from typing import Any, Iterable

import pyopenms as oms

from ..config import apply_to_merger


def _median_dt(exp: oms.MSExperiment, ms_level: int) -> float:
    """Median RT delta between consecutive scans of the given MS level."""
    rts = [s.getRT() for s in exp.getSpectra() if s.getMSLevel() == ms_level]
    if len(rts) < 2:
        return 0.0
    return median(rts[i + 1] - rts[i] for i in range(len(rts) - 1))


def average(
    exp: oms.MSExperiment,
    cfg: dict[str, Any],
    average_type: str,
    ms_levels: Iterable[int],
    factor: float | None = None,
    factor_unit: str = "scans",
) -> oms.MSExperiment:
    """Run SpectraMerger.average once per MS level on a copy of `exp`.

    Parameters
    ----------
    factor:
        Window width. For gaussian → FWHM; for tophat → full range.
        If None, the value already in `cfg` (or pyopenms's default) is used.
    factor_unit:
        "scans" (default) or "seconds". Gaussian's underlying param is in
        seconds, so when `factor_unit == "scans"` we multiply by each MS
        level's median dt. Tophat passes the unit through to pyopenms via
        `average_tophat:rt_unit`.
    """
    if average_type not in ("gaussian", "tophat"):
        raise ValueError(f"average_type must be 'gaussian' or 'tophat', got {average_type!r}")
    if factor_unit not in ("scans", "seconds"):
        raise ValueError(f"factor_unit must be 'scans' or 'seconds', got {factor_unit!r}")

    ms_level_key = f"average_{average_type}:ms_level"
    out = oms.MSExperiment(exp)

    for lvl in ms_levels:
        per_pass = copy.deepcopy(cfg)
        params = per_pass.setdefault("params", {})
        params[ms_level_key] = int(lvl)

        if factor is not None:
            if average_type == "tophat":
                params["average_tophat:rt_range"] = float(factor)
                params["average_tophat:rt_unit"] = factor_unit
            else:  # gaussian
                if factor_unit == "scans":
                    dt = _median_dt(exp, lvl)
                    params["average_gaussian:rt_FWHM"] = float(factor) * dt
                else:
                    params["average_gaussian:rt_FWHM"] = float(factor)

        merger = oms.SpectraMerger()
        apply_to_merger(merger, per_pass)
        merger.average(out, average_type)

    return out
