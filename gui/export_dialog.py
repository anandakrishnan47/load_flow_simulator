
"""Module 11: GUI controls for result exports."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton,
    QFileDialog, QMessageBox,
)

from loadflow.results_export import (
    export_csv,
    export_excel,
    export_pdf,
)


class ExportPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.study = None

        layout = QHBoxLayout(self)

        self.csv_button = QPushButton("Export CSV")
        self.excel_button = QPushButton("Export Excel")
        self.pdf_button = QPushButton("Export PDF")

        for button in (
            self.csv_button,
            self.excel_button,
            self.pdf_button,
        ):
            layout.addWidget(button)

        self.csv_button.clicked.connect(
            self.export_csv_dialog
        )
        self.excel_button.clicked.connect(
            self.export_excel_dialog
        )
        self.pdf_button.clicked.connect(
            self.export_pdf_dialog
        )

        self.set_study(None)

    def set_study(self, study):
        self.study = study

        enabled = study is not None

        self.csv_button.setEnabled(enabled)
        self.excel_button.setEnabled(enabled)
        self.pdf_button.setEnabled(enabled)

    def _notify(self, path):
        QMessageBox.information(
            self,
            "Export Complete",
            f"Results exported to:\n{path}",
        )

    def _error(self, exc):
        QMessageBox.critical(
            self,
            "Export Failed",
            str(exc),
        )

    def export_csv_dialog(self):
        if self.study is None:
            return

        directory = QFileDialog.getExistingDirectory(
            self, "Select CSV Output Folder"
        )

        if directory:
            try:
                paths = export_csv(
                    self.study, directory
                )
                self._notify(
                    "\n".join(map(str, paths))
                )
            except Exception as exc:
                self._error(exc)

    def export_excel_dialog(self):
        if self.study is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Excel",
            "loadflow_results.xlsx",
            "Excel Workbook (*.xlsx)",
        )

        if path:
            try:
                result = export_excel(
                    self.study, path
                )
                self._notify(result)
            except Exception as exc:
                self._error(exc)

    def export_pdf_dialog(self):
        if self.study is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            "loadflow_report.pdf",
            "PDF Documents (*.pdf)",
        )

        if path:
            try:
                result = export_pdf(
                    self.study, path
                )
                self._notify(result)
            except Exception as exc:
                self._error(exc)
