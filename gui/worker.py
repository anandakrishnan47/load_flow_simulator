
"""Background worker for load-flow calculations."""

from PySide6.QtCore import QThread, Signal

from gui.controller import run_study


class LoadFlowWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        network,
        tolerance,
        max_iterations,
        enforce_q_limits,
        parent=None,
    ):
        super().__init__(parent)

        self.network = network
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.enforce_q_limits = enforce_q_limits

    def run(self):
        try:
            result = run_study(
                self.network,
                tolerance=self.tolerance,
                max_iterations=self.max_iterations,
                enforce_q_limits=self.enforce_q_limits,
            )
        except Exception as exc:
            self.failed.emit(
                f"{type(exc).__name__}: {exc}"
            )
        else:
            self.completed.emit(result)
