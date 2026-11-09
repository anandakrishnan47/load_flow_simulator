
# APSA Simulator — User Guide

## 1. Starting the Application

Activate the Python virtual environment and run:

```bash
python run_gui.py
```

The PySide6 main window will open.

## 2. Selecting a Network

Use the network dropdown to select:

- 3-Bus Example
- IEEE 14-Bus
- IEEE 30-Bus
- IEEE 57-Bus
- IEEE 118-Bus

Click Load Network.

## 3. Editing Load Data

The left-hand table displays:

- Bus number
- Bus type
- Active load Pd in MW
- Reactive load Qd in MVAr

Pd and Qd are editable.

The bus number and bus type are read-only.

## 4. Running Newton-Raphson Load Flow

Set the convergence tolerance and maximum iteration count.

Optionally enable generator reactive power limits.

Click Run Load Flow.

The calculation runs in a background worker so the
main GUI remains responsive.

A successful solution displays the iteration count
and final mismatch.

## 5. Interpreting Results

### Bus Results

Vm is the voltage magnitude in per unit.

Angle is the bus voltage phase angle in degrees.

P and Q are net calculated bus injections.

### Branch Results

Branch power flows are reported at both terminals.

Positive terminal power represents power entering
the branch from its connected bus.

Active loss is the sum of the terminal active powers.

### Summary

The summary includes:

- Convergence status
- Iteration count
- Maximum mismatch
- Total active loss
- Net branch reactive absorption
- Maximum branch loading
- Power-balance residuals

## 6. Single-Line Diagram

Open the Single-Line Diagram tab.

Drag buses to reposition them.

Use the editor toolbar to add buses, lines or transformers.

Select a component to edit or delete it.

Click Apply Diagram Changes to synchronize the network.

The editor does not automatically create generators or
external-grid objects when bus types are changed.

Disconnected or invalid networks may fail to solve.

## 7. Result Charts

Open the Charts tab.

Available charts:

- Voltage Magnitude
- Voltage Angle
- Convergence
- Branch Loading

Use Save Chart as PNG to export the selected graph.

## 8. Exporting Results

After a successful calculation:

- Export CSV creates four CSV files.
- Export Excel creates an XLSX workbook.
- Export PDF creates a formatted report.

Export controls are disabled until a valid study is available.

## 9. Troubleshooting

### Missing Python package

Run:

```bash
python -m pip install -r requirements.txt
```

### Missing IEEE case files

Run:

```bash
python download_ieee_cases.py
```

### Solver does not converge

Check:

- Network connectivity
- Slack bus configuration
- Branch impedance values
- Load magnitudes
- Generator limits
- Maximum iteration count

### Qt platform plugin error

Verify the PySide6 installation and ensure the virtual
environment is active.

For automated tests in a headless environment, set
QT_QPA_PLATFORM=offscreen.

## 10. Running Tests

```bash
python -m pytest tests/ -v
```

Final verification:

```bash
python scripts/verify_project.py
```
