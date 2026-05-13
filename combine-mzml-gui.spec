# PyInstaller spec for the combine-mzml GUI.
#
# Build (from repo root, inside the project's venv):
#
#   pyinstaller combine-mzml-gui.spec --clean
#
# The first build can also be regenerated from scratch via:
#
#   pyinstaller --windowed --name combine-mzml-gui \
#       --additional-hooks-dir ./hooks main_gui.py --clean
#
# but the spec below is the canonical, reproducible recipe.

import importlib.util
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

# Locate the installed pyopenms package wherever the active venv put it
# (works on Linux's lib/pythonX.Y/site-packages and Windows's Lib/site-packages
# alike, without hardcoding a Python version).
_pyopenms_init = importlib.util.find_spec("pyopenms").origin
PYOPENMS_DIR = str(Path(_pyopenms_init).parent)

# Our own data file (default merger params) — must travel with the bundle.
PROJECT_DATAS = [
    ("combine_mzml/default_config.toml", "combine_mzml"),
]

# Mirror the Arslan-Siraj recipe: ship the entire pyopenms package tree
# under `pyopenms/` inside the bundle. The hook in ./hooks/ additionally
# pulls in dynamic libs and metadata.
PYOPENMS_DATAS = [
    (PYOPENMS_DIR, "pyopenms"),
] + copy_metadata("pyopenms")


block_cipher = None

a = Analysis(
    ["main_gui.py"],
    pathex=[],
    binaries=[],
    datas=PROJECT_DATAS + PYOPENMS_DATAS,
    hiddenimports=[],
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="combine-mzml-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,             # no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="combine-mzml-gui",
)
