# E4234 APSA — AC Load Flow Simulator

A Python-based **AC power-flow analysis and network visualization application** developed for **E4234 Advanced Power System Analysis (APSA)**. The project implements a Newton–Raphson load-flow solver, IEEE benchmark case support, and a PySide6 graphical interface for creating, editing, solving, and inspecting electrical networks.

## Features

### Power-system modeling
- Bus types: **Slack, PV, and PQ**
- Transmission lines and off-nominal/phase-shifting transformers
- Generators, loads, shunts, and external-grid connections
- Constant-power, constant-impedance, and ZIP load models
- Network admittance matrix (**Y-bus**) construction

### Load-flow calculation
- Newton–Raphson solution using an analytical Jacobian
- Sparse linear-system support
- Flat, model-based, and warm-start initialization options
- Optional generator reactive-power limit enforcement and PV–PQ switching
- Bus voltage magnitudes and phase angles
- Sending- and receiving-end branch active/reactive powers
- Branch active losses, net reactive absorption, and power-balance checks
- Convergence history and mismatch reporting

### Graphical interface
- PySide6 desktop application
- Editable single-line diagram (SLD)
- Bus, line, transformer, generator, and load components
- Network parameter editing and bus-type changes
- Diagram navigation and layout tools
- New project, project opening, and saving workflows
- Bus results, branch results, convergence, and voltage-profile charts
- Results export capabilities including tabular and PDF outputs

> **Note:** Available controls can depend on the checked-out project revision. Confirm the specific GUI actions against the installed version before demonstration.

## IEEE benchmark networks

The project supports the following cases:

| Case | Buses |
| --- | ---: |
| IEEE 14-bus | 14 |
| IEEE 30-bus | 30 |
| IEEE 57-bus | 57 |
| IEEE 118-bus | 118 |

Benchmark data are read from MATPOWER-format `.m` case files stored under `data/ieee/`. If these files are missing, run the repository's case download script as described below.

### Branch-rating interpretation

In the restored compatibility implementation, a MATPOWER branch with an unspecified thermal rating may be assigned a large numeric placeholder (`1e12 MVA`) so the existing network model continues to require positive ratings. Consequently, a reported loading value near **0%** for such a branch **does not represent a verified thermal utilization**. Branch power flows and losses are calculated separately from this reporting placeholder. Do not use those near-zero percentages for overload assessment.

## Requirements

- Python with a compatible version of the packages used by the project
- `numpy`, `scipy`, `pandas`
- `PySide6`, `matplotlib`
- `pytest`, `pytest-qt`
- `pypower` for IEEE reference validation
- Export-related dependencies used by the installed revision (for example `openpyxl`, `reportlab`, `pypdf`)

Use the project's existing `requirements.txt` if present; it is the preferred dependency specification.

## Installation

Clone the repository:

```bash
git clone https://github.com/anandakrishnan47/load_flow_simulator.git
cd load_flow_simulator
```

Create a virtual environment:

**Windows (PowerShell):**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**

```bash
python -m venv .venv
source .venv/Scripts/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `requirements.txt` is not available or is incomplete, install the relevant packages explicitly:

```bash
python -m pip install numpy scipy pandas PySide6 matplotlib pytest pytest-qt pypower openpyxl reportlab pypdf
```

If IEEE case files are missing and the download script is present:

```bash
python download_ieee_cases.py
```

## Running the application

From the repository root, with the virtual environment activated:

```bash
python run_gui.py
```

If your checked-out revision uses a different entry point, inspect the repository's root launcher scripts. Do not assume `python -m gui.app` exists.

### Typical workflow

1. Launch the GUI and select an IEEE benchmark network, or create a new project.
2. Inspect or edit bus types, generator settings, load demands, and branch parameters.
3. For a new network, include an appropriate Slack bus and connect the network components.
4. Configure the solver tolerance, iteration limit, and optional generator Q-limit enforcement.
5. Run the load-flow study.
6. Inspect voltage magnitudes, angles, convergence, branch powers, and losses.
7. Save the project and export the desired results or plots.

## Numerical validation

The project includes a validation script comparing supported IEEE cases with reference power-flow solutions:

```bash
python validate.py
```

The project's established validation targets include:

| Quantity | Target |
| --- | --- |
| Final maximum power mismatch | ≤ `1e-8` pu |
| Bus voltage magnitude error | ≤ `1e-4` pu |
| Bus voltage angle error | ≤ `0.01` degree |
| Branch terminal P/Q error | ≤ `0.01` MW/MVAr |
| Total active loss relative error | ≤ `0.1%` |
| IEEE 118-bus flat-start NR iterations, without Q-limit enforcement | ≤ `7` |

These are **validation criteria**, not a claim that the latest local revision has passed. Confirm the current output reports `OVERALL VALIDATION: PASS` before submission.

## Testing

Run the full automated test suite:

```bash
python -m pytest tests/ -q
```

Run selected suites when troubleshooting:

```bash
python -m pytest tests/test_branch_flows.py -q
python -m pytest tests/test_ieee_validation.py -q
python -m pytest tests/test_results_export.py -q
```

If experimental tests from earlier branch-rating implementations remain in `tests/`, they may assume conflicting handling of unrated branches. Review those tests separately from the original project regression suite. Do not change assertions merely to force a pass.

## Project structure

```text
APSA/
├── loadflow/                  # Numerical power-system models and solver
│   ├── models.py              # Network, bus, line, transformer, load models
│   ├── ybus.py                # Network admittance matrix
│   ├── power.py               # Power injections and mismatches
│   ├── jacobian.py            # Analytical Newton–Raphson Jacobian
│   ├── solver.py              # Load-flow solution
│   ├── qlimits.py             # Generator reactive-power limits
│   ├── branch_flows.py        # Branch terminal flows and losses
│   ├── ieee_validation.py     # MATPOWER import and reference validation
│   └── results_export.py      # Result tables and export utilities
├── gui/                       # PySide6 interface and SLD editor
├── data/ieee/                 # IEEE benchmark case files
├── tests/                     # Automated tests
├── validate.py                # Numerical benchmark validation
├── run_gui.py                 # Desktop GUI launcher
├── main.py                    # Sample network and/or CLI entry point
└── README.md
```

The exact set of files may vary slightly by revision.

## Limitations

- This is a **steady-state balanced AC power-flow** tool, not a transient, short-circuit, protection, or electromagnetic-transients simulator.
- Numerical convergence does not guarantee that all bus voltages or branch loadings meet operational limits.
- IEEE case branches with unspecified thermal ratings cannot be reliably assessed for overload using the legacy placeholder-rating representation.
- Results depend on the network data, selected initialization, generator-limit settings, and solver tolerances.

## Submission checklist

- [ ] All required source files and IEEE case data are available.
- [ ] `python -m pytest tests/ -q` completes successfully for the intended test suite.
- [ ] `python validate.py` reports `OVERALL VALIDATION: PASS`.
- [ ] GUI launches successfully using `python run_gui.py`.
- [ ] An IEEE case can be loaded, solved, and its results exported.
- [ ] A new network can be created, saved, and reopened without data loss.
- [ ] Project screenshots, validation output, and assignment-specific documentation are included where required.
- [ ] The latest changes are committed and pushed to the intended GitHub repository.

## Academic context

**Course:** E4234 — Advanced Power System Analysis  
**Project:** AC Load Flow Simulator  
**Implementation:** Python, NumPy/SciPy, PySide6, Matplotlib  
**Reference networks:** IEEE 14-, 30-, 57-, and 118-bus test systems

