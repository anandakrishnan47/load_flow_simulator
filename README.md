
# APSA Load Flow Simulator

A Python-based AC power-flow analysis application developed
for E4234 Advanced Power System Analysis.

The application implements Newton-Raphson load flow using
a sparse bus-admittance matrix and an analytical Jacobian.

It includes an interactive PySide6 GUI, single-line diagram
editor, result visualization, and engineering report exports.

## Features

- Bus, line, transformer, generator, load and shunt models
- Sparse Ybus construction
- Active and reactive power mismatch calculation
- Analytical Newton-Raphson Jacobian
- Newton-Raphson AC load-flow solver
- Generator reactive power limit enforcement
- PV-to-PQ bus switching
- Branch power flows and losses
- IEEE 14, 30, 57 and 118-bus benchmark validation
- Interactive single-line diagram
- Editable load data
- Voltage, angle, convergence and loading plots
- CSV, Excel, PDF and PNG export
- Automated pytest regression tests

## Requirements

Python 3.12 is recommended for a reproducible environment.

## Installation

Clone the repository:

```bash
git clone https://github.com/anandakrishnan47/APSA.git
cd APSA
```

Create a virtual environment:

```bash
python -m venv .venv
```

On Windows Git Bash:

```bash
source .venv/Scripts/activate
```

On Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Launch the GUI

```bash
python run_gui.py
```

## Run a Load-Flow Study

1. Select a network.
2. Click Load Network.
3. Edit Pd and Qd values if required.
4. Optionally enable generator Q-limit enforcement.
5. Click Run Load Flow.
6. Review bus voltages, branch flows and losses.
7. View voltage, convergence and loading charts.
8. Export the results.

## Interactive Diagram

The Single-Line Diagram tab supports:

- Bus movement
- Bus and branch creation
- Branch deletion
- Electrical parameter editing
- Voltage-limit visualization
- Diagram layout save/load

After changing the electrical topology, click
Apply Diagram Changes before solving.

Diagram layout JSON files store graphical positions,
not complete electrical network models.

## Benchmarks

The project includes MATPOWER-compatible IEEE
14, 30, 57 and 118-bus cases.

The independent PYPOWER validation tests compare
voltage magnitudes, phase angles and active losses.

## Testing

Run the full suite:

```bash
python -m pytest tests/ -v
```

Run the final verification:

```bash
python scripts/verify_project.py
```

## Results Export

Supported formats:

- CSV: summary, buses, branches and convergence
- Excel: formatted workbook
- PDF: multipage load-flow report
- PNG: selected result chart

## Documentation

See:

- docs/USER_GUIDE.md
- docs/ARCHITECTURE.md

## Limitations

The application performs steady-state balanced AC
load-flow analysis.

It does not implement transient stability,
short-circuit analysis, optimal power flow,
or unbalanced three-phase load flow.

The diagram editor does not yet include undo/redo
or complete electrical network serialization.

## License

See the repository's LICENSE file if present.
No license is implied by this README.
