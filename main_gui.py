# Frozen-app entry point.
#
# PyInstaller analyses the imports of *this* script to decide what to bundle.
# Keep it as thin as possible so the dependency graph is unambiguous, and
# place it at the repo root so all relative data paths in the spec stay tidy.

from combine_mzml.gui import main


if __name__ == "__main__":
    raise SystemExit(main())
