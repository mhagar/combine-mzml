"""Decimation: keep every Nth scan, independently per MS level.

This preserves the MS1/MS2 ratio of an interleaved DIA acquisition: striding
naively over the raw scan list would skew the ratio if MS1 and MS2 counts are
not identical, and would couple the reduction factor to the interleaving
period. Doing it per-MS-level mirrors what a slower instrument would actually
produce.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import pyopenms as oms


def decimate(
    exp: oms.MSExperiment, factor: int, ms_levels: Iterable[int] | None = None
) -> oms.MSExperiment:
    """Return a new MSExperiment keeping every Nth scan per MS level.

    Scans whose MS level is not in `ms_levels` (or all levels, if None) pass
    through unchanged. Original acquisition order is preserved.
    """
    if factor < 1:
        raise ValueError("factor must be >= 1")
    spectra = exp.getSpectra()
    levels_filter = set(ms_levels) if ms_levels is not None else None

    # Walk once, counting per-level index, and keep when index % factor == 0.
    counters: dict[int, int] = defaultdict(int)
    kept: list[oms.MSSpectrum] = []
    for spec in spectra:
        lvl = spec.getMSLevel()
        if levels_filter is not None and lvl not in levels_filter:
            kept.append(spec)
            continue
        idx = counters[lvl]
        counters[lvl] += 1
        if idx % factor == 0:
            kept.append(spec)

    out = oms.MSExperiment(exp)  # copy header/metadata
    out.setSpectra(kept)
    return out
