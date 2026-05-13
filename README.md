# combine-mzml

A small tool for **synthetically reducing the scan rate** of DIA mzML files,
e.g. turning a 20 Hz acquisition into something resembling a 5 Hz one

Three reduction methods are offered:

| Method | What it does | Output scan count |
|---|---|---|
| `decimate` | Keep every Nth scan, independently per MS level | reduced ~1/N |
| `blockwise` | Merge N consecutive scans into one (per MS level): m/z-bin peaks within tolerance, sum intensities | reduced ~1/N |
| `average` | Replace each scan with a weighted average of its RT neighbours (gaussian FWHM or top-hat window) | unchanged (no scan rate reduction) |

## Installation

Pre-built binaries for Windows and Linux available [here](https://github.com/mhagar/combine-mzml/releases). Just run `combine-mzml-gui-linux` or `combine_mzml-gui-windows.exe`

To install from source, the project uses [`uv`](https://docs.astral.sh/uv/) for environment management:

```bash
git clone https://github.com/mhagar/combine-mzml.git
cd combine-mzml
uv sync

uv run combine-mzml --help        # CLI
uv run combine-mzml-gui           # GUI wizard
```

Can use `tests/data/test_file.mzML`

## CLI usage

```bash
# Decimate: keep every 4th scan per MS level
uv run combine-mzml decimate input.mzML -n 4

# Blockwise merge: sum 4 consecutive scans per MS level
uv run combine-mzml blockwise input.mzML -n 4

# RT averaging (Gaussian FWHM = 4 scans, MS1+MS2)
uv run combine-mzml average input.mzML -n 4 --type gaussian --unit scans

# Same thing with explicit seconds
uv run combine-mzml average input.mzML -n 8 --type gaussian --unit seconds

# Show the effective config as TOML (useful as a starting point for --config)
uv run combine-mzml dump-config > my_config.toml
```

Each subcommand takes `--config PATH.toml` to override the built-in defaults,
plus `-o/--output` to set the output filename and `--ms-levels 1,2` 

## Configuration

The `blockwise` and `average` methods wrap pyopenms's `SpectraMerger`, which
has ~20 tunable parameters. Common knobs are exposed as CLI flags, and everything
else is a TOML config file. `--config` overrides the built-in defaults
key-by-key (missing keys fall back to defaults), and CLI flags override the
config.

The full default config, equivalent to `combine-mzml dump-config`:

```toml
[params]
"mz_binning_width" = 5.0
"mz_binning_width_unit" = "ppm"
"sort_blocks" = "RT_ascending"

"average_gaussian:spectrum_type" = "automatic"
"average_gaussian:ms_level" = 1
"average_gaussian:rt_FWHM" = 5.0
"average_gaussian:cutoff" = 0.01
"average_gaussian:precursor_mass_tol" = 0.0
"average_gaussian:precursor_max_charge" = 1

"average_tophat:spectrum_type" = "automatic"
"average_tophat:ms_level" = 1
"average_tophat:rt_range" = 5.0
"average_tophat:rt_unit" = "scans"

"block_method:ms_levels" = [1, 2]
"block_method:rt_block_size" = 5
"block_method:rt_max_length" = 0.0

"precursor_method:mz_tolerance" = 0.0001
"precursor_method:mass_tolerance" = 0.0
"precursor_method:rt_tolerance" = 5.0
```

Key names mirror pyopenms's `SpectraMerger.getDefaults()`. See [pyopenms's spectrum-merging
docs](https://pyopenms.readthedocs.io/en/latest/user_guide/spectrum_merging.html) for what each parameter does.

A note on units for `average`: the `--factor` argument is in **scans** by
default for both Gaussian and top-hat kernels. Internally, Gaussian's FWHM
is in seconds, so when `--unit scans` (the default) the tool multiplies your
factor by the median RT delta of the relevant MS level. Pass `--unit seconds` to bypass this conversion.

## GUI

`combine-mzml-gui` opens a six-page wizard that calls the same Python functions the CLI does, so behaviour is identical.

## Building from source (binary distributions)

The Windows/Linux binaries on the Releases page are produced with PyInstaller
using the spec checked into this repo:

```bash
uv pip install pyinstaller
uv run pyinstaller combine-mzml-gui.spec --clean
# -> dist/combine-mzml-gui/combine-mzml-gui[.exe]
```

The spec bundles pyopenms's required data and the default config TOML
