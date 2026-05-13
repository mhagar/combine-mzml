"""Blockwise merging via pyopenms SpectraMerger.mergeSpectraBlockWise."""

from __future__ import annotations

from typing import Any

import pyopenms as oms

from ..config import apply_to_merger


def blockwise(exp: oms.MSExperiment, cfg: dict[str, Any]) -> oms.MSExperiment:
    """Run SpectraMerger.mergeSpectraBlockWise on a copy of `exp`."""
    out = oms.MSExperiment(exp)
    merger = oms.SpectraMerger()
    apply_to_merger(merger, cfg)
    merger.mergeSpectraBlockWise(out)
    return out
