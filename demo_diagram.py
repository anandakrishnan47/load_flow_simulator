
"""
Module 10 demonstration:
Interactive single-line diagram editor.
"""

import sys

from PySide6.QtWidgets import QApplication

from gui.controller import (
    load_network,
    run_study,
)
from gui.diagram_editor import DiagramEditor


def main():
    app = QApplication(sys.argv)

    network = load_network("3-Bus Example")

    editor = DiagramEditor(network)
    editor.setWindowTitle(
        "APSA | Interactive Single-Line Diagram"
    )
    editor.resize(1100, 700)

    # Solve the original network.
    study = run_study(network)

    # Display solved voltage magnitudes and angles.
    editor.apply_solution(study.solution)

    print("=" * 60)
    print("APSA MODULE 10: SINGLE-LINE DIAGRAM")
    print("=" * 60)

    print("Buses:", len(network.buses))
    print("Lines:", len(network.lines))
    print("Transformers:", len(network.transformers))

    print("Converged:", study.solution.converged)

    print(
        "Active power loss:",
        f"{study.flows.total_p_loss:.6f} MW"
    )

    print("\nDrag the busbars to change their positions.")
    print("Use the toolbar to edit the diagram.")

    editor.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
