
# APSA Simulator — Software Architecture

## 1. Architecture Overview

The application has four principal layers:

1. Electrical network data models
2. Numerical power-flow analysis
3. GUI and interactive diagram
4. Visualization and reporting

## 2. Network Data Models

File: loadflow/models.py

Core objects:

- Network
- Bus
- Line
- Transformer
- Generator
- Load
- Shunt
- ExternalGrid

All power values use the network base MVA where required.

## 3. Numerical Analysis

### Ybus

File: loadflow/ybus.py

Constructs the sparse complex bus-admittance matrix.

### Power Calculation

File: loadflow/power.py

Calculates bus active and reactive power injections.

### Jacobian

File: loadflow/jacobian.py

Constructs the analytical Newton-Raphson Jacobian.

### Solver

File: loadflow/solver.py

Solves the nonlinear power-balance equations.

The Newton-Raphson state vector contains:

- Voltage angles of non-slack buses
- Voltage magnitudes of PQ buses

### Generator Q Limits

File: loadflow/qlimits.py

Handles generator reactive power limit enforcement
and PV-to-PQ switching.

### Branch Flows

File: loadflow/branch_flows.py

Calculates terminal power flows, branch losses
and loading percentages.

## 4. Benchmark Validation

File: loadflow/ieee_validation.py

Loads MATPOWER benchmark cases and compares
results against PYPOWER.

Supported benchmark sizes:

- 14 buses
- 30 buses
- 57 buses
- 118 buses

## 5. GUI Layer

File: gui/main_window.py

Main application window and workflow coordination.

File: gui/controller.py

Loads networks, applies load changes and runs studies.

File: gui/worker.py

Executes load flow in a QThread.

## 6. Diagram Layer

Files:

- gui/diagram_items.py
- gui/diagram_scene.py
- gui/diagram_editor.py

Uses Qt QGraphicsScene and QGraphicsView.

Electrical network objects are distinct from
graphical item positions.

## 7. Reporting Layer

Files:

- loadflow/results_export.py
- gui/results_charts.py
- gui/export_dialog.py

Provides CSV, Excel, PDF and PNG exports.

## 8. Data Flow

Network selection
    -> Network object
    -> Load/diagram edits
    -> Study controller
    -> Newton-Raphson solver
    -> Branch-flow calculation
    -> StudyResult
    -> GUI result tables
    -> Charts and exports

## 9. Units and Conventions

- Voltage magnitude: per unit
- Voltage angle in solver results: degrees
- Internal trigonometric calculations: radians
- Active power: MW in reports
- Reactive power: MVAr in reports
- Branch impedance: per unit
- MVA ratings: MVA

Positive bus power injection denotes net power
entering the electrical network.

Positive branch terminal power denotes power
entering the branch at that terminal.

## 10. Software Testing

Unit tests verify individual numerical modules.

Benchmark tests compare against PYPOWER.

Integration tests verify the full analysis pipeline.

GUI tests verify widgets, signals, network editing
and asynchronous calculations.

GitHub Actions runs regression tests on changes.
