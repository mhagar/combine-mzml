"""PyQt5 wizard GUI for combine-mzml.

Wraps the same `combine_mzml.methods.*` functions the CLI uses, imported
those directly (no subprocess) so the app freezes cleanly with PyInstaller
on Windows.

Pages:
    0. Intro
    1. Pick input mzML files (one or many; batch processing)
    2. Pick method (decimate / blockwise / average-gaussian / average-tophat)
    3. Method parameters (factor, MS levels, optional config TOML)
    4. Output directory
    5. Run page: kicks off a QThread worker, streams log + progress
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

from PyQt5 import QtCore, QtWidgets

from .config import load_config

# ---------- field keys (registered on wizard pages) ----------
F_INPUTS = "inputs"
F_METHOD = "method"
F_FACTOR = "factor"
F_MS1 = "ms1"
F_MS2 = "ms2"
F_CONFIG = "configPath"
F_OUTDIR = "outDir"
F_UNIT = "factorUnit"

METHODS = [
    ("decimate", "Decimate: keep every Nth scan (per MS level)"),
    ("blockwise", "Blockwise merge: sum N consecutive scans per MS level"),
    ("average-gaussian", "Average (gaussian): RT-smooth with Gaussian window"),
    ("average-tophat", "Average (tophat): RT-smooth with uniform window"),
]


# ===================== worker =====================


class Worker(QtCore.QObject):
    """
    Runs the actual mzML processing off the UI thread
    """

    progress = QtCore.pyqtSignal(int, int)  # (done, total)
    log = QtCore.pyqtSignal(str)
    file_done = QtCore.pyqtSignal(str, str)  # (input_path, output_path)
    finished = QtCore.pyqtSignal(bool, str)  # (ok, message)

    def __init__(
        self,
        inputs: list[Path],
        method: str,
        factor: int,
        ms_levels: list[int],
        out_dir: Path,
        config_path: Path | None,
        factor_unit: str = "scans",
    ) -> None:
        super().__init__()
        self.inputs = inputs
        self.method = method
        self.factor = factor
        self.ms_levels = ms_levels
        self.out_dir = out_dir
        self.config_path = config_path
        self.factor_unit = factor_unit
        self._cancel = False

    @QtCore.pyqtSlot()
    def cancel(self) -> None:
        self._cancel = True

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            # Import pyopenms + methods lazily so the GUI opens fast
            import pyopenms as oms

            from .methods.decimate import decimate as m_decimate
            from .methods.blockwise import blockwise as m_blockwise
            from .methods.average import average as m_average

            total = len(self.inputs)
            self.progress.emit(0, total)

            for i, in_path in enumerate(self.inputs):
                if self._cancel:
                    self.finished.emit(False, "Cancelled.")
                    return

                self.log.emit(f"[{i + 1}/{total}] Loading {in_path.name} ...")
                exp = oms.MSExperiment()
                oms.MzMLFile().load(str(in_path), exp)
                before = exp.getNrSpectra()
                self.log.emit(f"    {before} spectra loaded")

                if self.method == "decimate":
                    new_exp = m_decimate(
                        exp, factor=self.factor, ms_levels=self.ms_levels
                    )
                    out_tag = f"decimate_{self.factor}"
                elif self.method == "blockwise":
                    cfg = load_config(self.config_path)
                    cfg.setdefault("params", {})["block_method:rt_block_size"] = (
                        self.factor
                    )
                    cfg["params"]["block_method:ms_levels"] = list(self.ms_levels)
                    new_exp = m_blockwise(exp, cfg)
                    out_tag = f"blockwise_{self.factor}"
                elif self.method in ("average-gaussian", "average-tophat"):
                    kind = "gaussian" if self.method.endswith("gaussian") else "tophat"
                    cfg = load_config(self.config_path)
                    new_exp = m_average(
                        exp,
                        cfg,
                        average_type=kind,
                        ms_levels=self.ms_levels,
                        factor=float(self.factor),
                        factor_unit=self.factor_unit,
                    )
                    unit_tag = "s" if self.factor_unit == "seconds" else "scans"
                    out_tag = f"average-{kind}_{self.factor}{unit_tag}"
                else:
                    raise ValueError(f"Unknown method: {self.method}")

                out_path = self.out_dir / f"{in_path.stem}_{out_tag}.mzML"
                self.log.emit(
                    f"    writing {out_path.name} ({new_exp.getNrSpectra()} spectra) ..."
                )
                oms.MzMLFile().store(str(out_path), new_exp)

                self.file_done.emit(str(in_path), str(out_path))
                self.progress.emit(i + 1, total)

            self.finished.emit(True, f"Done. Processed {total} file(s).")
        except Exception as exc:  # surface to the UI rather than crashing
            tb = traceback.format_exc()
            self.log.emit(tb)
            self.finished.emit(False, f"Error: {exc}")


# ===================== wizard pages =====================


class IntroPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("combine-mzml")
        self.setSubTitle("Synthetically reduce scan rate of DIA mzML files.")
        lay = QtWidgets.QVBoxLayout(self)
        lbl = QtWidgets.QLabel(
            "This tool produces a slower-scan-rate copy of one or more mzML "
            "files using one of three methods:\n\n"
            "  • Decimate: keep every Nth scan (per MS level)\n"
            "  • Blockwise merge: combine consecutive scans (per MS level) - sum intensity, average m/z values\n"
            "  • RT averaging: Gaussian or top-hat smoothing\n\n"
            "Click Next to begin."
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)


class InputsPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Input files")
        self.setSubTitle("Select one or more mzML files to process.")

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        btn_add = QtWidgets.QPushButton("Add files...")
        btn_remove = QtWidgets.QPushButton("Remove selected...")
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_add.clicked.connect(self._on_add)
        btn_remove.clicked.connect(self._on_remove)
        btn_clear.clicked.connect(self._on_clear)

        side = QtWidgets.QVBoxLayout()
        for b in (btn_add, btn_remove, btn_clear):
            side.addWidget(b)
        side.addStretch(1)

        row = QtWidgets.QHBoxLayout(self)
        row.addWidget(self.listw, 1)
        row.addLayout(side)

        # Hidden field to back isComplete; we update it from the list.
        self._hidden = QtWidgets.QLineEdit()
        self._hidden.setVisible(False)
        row.addWidget(self._hidden)
        self.registerField(f"{F_INPUTS}*", self._hidden)

    def _refresh_field(self) -> None:
        paths = [self.listw.item(i).text() for i in range(self.listw.count())]
        self._hidden.setText(";".join(paths))
        self.completeChanged.emit()

    def _on_add(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select mzML files", "", "mzML files (*.mzML *.mzml);;All files (*)"
        )
        for p in paths:
            if not self._already_added(p):
                self.listw.addItem(p)
        self._refresh_field()

    def _on_remove(self) -> None:
        for item in self.listw.selectedItems():
            self.listw.takeItem(self.listw.row(item))
        self._refresh_field()

    def _on_clear(self) -> None:
        self.listw.clear()
        self._refresh_field()

    def _already_added(self, p: str) -> bool:
        return any(self.listw.item(i).text() == p for i in range(self.listw.count()))

    def isComplete(self) -> bool:
        return self.listw.count() > 0


class MethodPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Method")
        self.setSubTitle("Choose how to reduce the scan rate.")

        self.group = QtWidgets.QButtonGroup(self)
        lay = QtWidgets.QVBoxLayout(self)
        self._buttons: dict[str, QtWidgets.QRadioButton] = {}
        for i, (key, label) in enumerate(METHODS):
            rb = QtWidgets.QRadioButton(label)
            if i == 0:
                rb.setChecked(True)
            self.group.addButton(rb)
            lay.addWidget(rb)
            self._buttons[key] = rb
        lay.addStretch(1)

        # Hidden field for the chosen key.
        self._hidden = QtWidgets.QLineEdit("decimate")
        self._hidden.setVisible(False)
        lay.addWidget(self._hidden)
        self.registerField(F_METHOD, self._hidden)

        for key, rb in self._buttons.items():
            rb.toggled.connect(
                lambda checked, k=key: checked and self._hidden.setText(k)
            )


class ParamsPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Parameters")
        self.setSubTitle("Reduction factor and MS levels.")

        form = QtWidgets.QFormLayout(self)

        self.factor = QtWidgets.QSpinBox()
        self.factor.setRange(1, 1000)
        self.factor.setValue(4)
        self.factor.setToolTip(
            "For decimate: keep every Nth scan.\n"
            "For blockwise: number of scans summed per output spectrum.\n"
            "For average: width of the RT window (FWHM for gaussian, range for tophat)."
        )
        form.addRow("Reduction factor (Nth scan):", self.factor)

        # Unit selector — only meaningful for the averaging methods. We show
        # the row always but disable it for decimate/blockwise so its state
        # is obvious rather than mysteriously absent.
        self.unit = QtWidgets.QComboBox()
        self.unit.addItems(["scans", "seconds"])
        self.unit.setToolTip(
            "Averaging only: interpret the factor as a number of scans "
            "(default) or as seconds of RT. For gaussian the scan-based "
            "value is converted to seconds per MS level using each level's "
            "median dt."
        )
        self._unit_row_label = QtWidgets.QLabel("Factor unit:")
        form.addRow(self._unit_row_label, self.unit)

        self.ms1 = QtWidgets.QCheckBox("MS1")
        self.ms1.setChecked(True)
        self.ms2 = QtWidgets.QCheckBox("MS2")
        self.ms2.setChecked(True)
        ms_row = QtWidgets.QHBoxLayout()
        ms_row.addWidget(self.ms1)
        ms_row.addWidget(self.ms2)
        ms_row.addStretch(1)
        ms_w = QtWidgets.QWidget()
        ms_w.setLayout(ms_row)
        form.addRow("MS levels to process:", ms_w)

        self.config_edit = QtWidgets.QLineEdit()
        self.config_edit.setPlaceholderText(
            "(optional) uses built-in defaults if blank"
        )
        btn_browse = QtWidgets.QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_config)
        cfg_row = QtWidgets.QHBoxLayout()
        cfg_row.addWidget(self.config_edit, 1)
        cfg_row.addWidget(btn_browse)
        cfg_w = QtWidgets.QWidget()
        cfg_w.setLayout(cfg_row)
        form.addRow("Config TOML:", cfg_w)

        # Register all fields.
        self.registerField(F_FACTOR, self.factor)
        self.registerField(F_MS1, self.ms1)
        self.registerField(F_MS2, self.ms2)
        self.registerField(F_CONFIG, self.config_edit)
        # PyQt5's registerField wants the actual signal object for changedSignal,
        # not a string name (PyQt6 accepts the string form). Pass the bound
        # signal directly so the wizard tracks combo changes correctly.
        self.registerField(
            F_UNIT, self.unit, "currentText", self.unit.currentTextChanged
        )
        self.ms1.toggled.connect(lambda _: self.completeChanged.emit())
        self.ms2.toggled.connect(lambda _: self.completeChanged.emit())

    def initializePage(self) -> None:
        # Grey out the unit selector when the chosen method doesn't use it.
        method = str(self.wizard().field(F_METHOD) or "")
        is_avg = method.startswith("average-")
        self.unit.setEnabled(is_avg)
        self._unit_row_label.setEnabled(is_avg)

    def _browse_config(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select config TOML", "", "TOML files (*.toml);;All files (*)"
        )
        if path:
            self.config_edit.setText(path)

    def isComplete(self) -> bool:
        return self.ms1.isChecked() or self.ms2.isChecked()


class OutputPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Output")
        self.setSubTitle("Where should the processed files be written?")

        self.out_edit = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.out_edit, 1)
        row.addWidget(btn_browse)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Output directory:"))
        lay.addLayout(row)
        lay.addStretch(1)

        self.registerField(f"{F_OUTDIR}*", self.out_edit)

    def _browse(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select output directory"
        )
        if path:
            self.out_edit.setText(path)

    def initializePage(self) -> None:
        # Default to the directory of the first input file.
        if not self.out_edit.text():
            raw = self.wizard().field(F_INPUTS) or ""
            paths = [p for p in str(raw).split(";") if p]
            if paths:
                self.out_edit.setText(str(Path(paths[0]).parent))


class RunPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Run")
        self.setSubTitle("Processing files…")
        self.setCommitPage(True)
        self.setButtonText(QtWidgets.QWizard.CommitButton, "Start")

        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 1)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QtWidgets.QApplication.instance().font())
        self.status = QtWidgets.QLabel("Click Start to begin.")

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.status)
        lay.addWidget(self.bar)
        lay.addWidget(self.log, 1)

        self._done = False
        self._thread: QtCore.QThread | None = None
        self._worker: Worker | None = None

    def isComplete(self) -> bool:
        return self._done

    def initializePage(self) -> None:
        self._done = False
        self.completeChanged.emit()
        QtCore.QTimer.singleShot(0, self._start)

    def _start(self) -> None:
        w = self.wizard()
        raw_inputs = str(w.field(F_INPUTS) or "")
        inputs = [Path(p) for p in raw_inputs.split(";") if p]
        method = str(w.field(F_METHOD) or "decimate")
        factor = int(w.field(F_FACTOR) or 4)
        ms_levels: list[int] = []
        if w.field(F_MS1):
            ms_levels.append(1)
        if w.field(F_MS2):
            ms_levels.append(2)
        out_dir = Path(str(w.field(F_OUTDIR) or "."))
        cfg_raw = str(w.field(F_CONFIG) or "").strip()
        config_path = Path(cfg_raw) if cfg_raw else None
        unit = str(w.field(F_UNIT) or "scans")

        self.log.appendPlainText(
            f"Method: {method}\nFactor: {factor} {unit if method.startswith('average-') else '(scans)'}\n"
            f"MS levels: {ms_levels}\n"
            f"Output dir: {out_dir}\nConfig: {config_path or '(defaults)'}\n"
            f"Files: {len(inputs)}\n"
        )

        self.bar.setRange(0, len(inputs))
        self.bar.setValue(0)

        self._thread = QtCore.QThread(self)
        self._worker = Worker(
            inputs, method, factor, ms_levels, out_dir, config_path, factor_unit=unit
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self.log.appendPlainText)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    @QtCore.pyqtSlot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.status.setText(f"{done} / {total} files processed")

    @QtCore.pyqtSlot(str, str)
    def _on_file_done(self, in_path: str, out_path: str) -> None:
        self.log.appendPlainText(f"  DONE: {Path(out_path).name}")

    @QtCore.pyqtSlot(bool, str)
    def _on_finished(self, ok: bool, message: str) -> None:
        self.status.setText(message)
        self.log.appendPlainText("\n" + message)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._done = True
        self.completeChanged.emit()


# ===================== wizard =====================


class CombineMzMLWizard(QtWidgets.QWizard):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("combine-mzml")
        self.setWizardStyle(QtWidgets.QWizard.ModernStyle)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)
        self.addPage(IntroPage())
        self.addPage(InputsPage())
        self.addPage(MethodPage())
        self.addPage(ParamsPage())
        self.addPage(OutputPage())
        self.addPage(RunPage())
        self.resize(720, 560)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    w = CombineMzMLWizard()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
