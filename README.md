# process-cost

A standard-library Python tool that estimates turning and milling cycle time and cost per part, with Taylor tool life, optimum cutting speeds, break-even batch size and a sensitivity table.

## Run it

Needs Python 3.10 or newer. No dependencies.

```
git clone https://github.com/ahmedakmal2211-ship-it/process-cost.git
cd process-cost
python -m process_cost report examples/turning_shaft.json
```

## Example output

The example part is a 40 mm to 36 mm turned shaft, 120 mm long, AISI 1045, with two scenarios (CNC lathe and manual lathe). All numbers in the examples are illustrative. The output below is trimmed; the full report also prints a sensitivity table for each scenario.

```
process-cost 0.1.0: Turned shaft, 40 -> 36 mm OD x 120 mm, AISI 1045 (illustrative numbers)

Estimate: CNC lathe
-------------------
Operation : turning D0 40 -> D1 36 mm, L 120 mm, ap 1 mm, f 0.25 mm/rev (Dm = 38 mm)
Taylor    : n = 0.3, C = 416.9   Batch Q = 50 good parts

Cutting                      Value  Unit
cutting speed Vc             185.0  m/min
spindle speed n             1549.7  rpm
feed rate vf                 387.4  mm/min
passes N                         2  -
cutting time Tm              0.630  min
tool life T                   15.0  min
cycle time per part tp       1.672  min

Cost per good part  $/part      %
setup                 2.85   24.4
machining             2.58   22.1
tool change           0.07    0.6
tooling               0.19    1.6
material              6.00   51.3
cost per part        11.69  100.0
Batch cost: $584.30  (setup $142.50 + variable $8.84/part x 50)

Speed (feed held)    Vc m/min  T min  tp min  $/part
your Vc                 185.0   15.0   1.672   11.69
min cost                215.9    9.0   1.600   11.65
max production rate     323.3    2.3   1.515   11.94

Break-even batch size
Scenario      Fixed F $/batch  Variable v $/part
CNC lathe              142.50               8.84
Manual lathe            21.67              10.15
Result: break-even Q* = 91.91 parts: Manual lathe is cheaper below, CNC lathe is cheaper from Q = 92 parts
```

The break-even command on the milling example (in-house mill against an outsource quote) ends with:

```
Result: break-even Q* = 33.48 parts: Outsource quote is cheaper below, In-house VMC is cheaper from Q = 34 parts
```

## Input JSON

A job file is JSON. It is either one complete job, or a `scenarios` list where each scenario is merged over the top-level `operation` and `costs` sections (scenario values win). Unknown keys are rejected, and invalid values exit with code 2 and a message naming the field.

Trimmed from `examples/turning_shaft.json`:

```json
{
  "name": "Turned shaft ...",
  "batch_size": 50,                      // good parts per batch, Q
  "operation": {                         // shared by all scenarios
    "type": "turning",                   // or "milling"
    "material": "aisi_1045",             // key from the materials table, or "custom"
    "tool_material": "coated_carbide",
    "D0_mm": 40, "D1_mm": 36,            // start and finish diameter, mm
    "length_mm": 120,
    "ap_mm": 1.0,                        // depth of cut per pass, mm
    "approach_mm": 2.0                   // approach + overtravel per pass, mm
  },
  "costs": {
    "cost_per_edge": 4.50,               // Ce, $ per cutting edge
    "material_cost_per_part": 6.00       // Cm, $
  },
  "scenarios": [
    {
      "name": "CNC lathe",
      "operation": { "feed_mm_per_rev": 0.25, "spindle_max_rpm": 4000 },
      "costs": { "machine_rate_per_h": 95, "setup_min": 90,
                 "handling_min": 1.0, "tool_change_min": 1.0 }
    }
  ]
}
```

The real file is plain JSON and has no comments; the comments above are for reading only. Optional fields: `Vc_m_per_min`, `taylor_n`, `taylor_C` (default from the table), `approach_mm` (2.0 mm), `setup_rate_per_h` (machine rate), `scrap_rate` (0). A scenario with `"type": "outsource"`, `price_per_part` and `fixed_fee` can be used as the comparison option for break-even (see `examples/milling_plate.json`). Milling jobs use `tool_diameter_mm`, `teeth`, `feed_mm_per_tooth`, `cut_length_mm` and `lead_in_out_mm`. Full field rules are in `docs/MODEL.md`.

## Formulas

Units: lengths in mm, Vc in m/min, n in rpm, f in mm/rev, fz in mm/tooth, vf in mm/min, times in min, rates in $/h, costs in $.

| Quantity | Formula | Units |
|---|---|---|
| Spindle speed | `n = 1000 * Vc / (pi * D)` (D = mean diameter Dm for turning, cutter diameter for milling) | rpm |
| Feed rate | turning `vf = f * n`; milling `vf = fz * z * n` | mm/min |
| Cutting time | `Tm = N * (L + approach) / vf`; milling uses cut length plus lead-in/out | min |
| Taylor tool life | `V * T^n = C`, so `T = (C/V)^(1/n)` | T in min, V in m/min |
| Time per piece | `tp = Th + Tm + (Tm/T) * Tt` | min |
| Variable cost per good part | `v = (Cm + Co*tp/60 + (Tm/T)*Ce) / (1 - s)` | $/part |
| Fixed cost per batch | `F = Ts/60 * Cs` | $ |
| Cost per good part | `c(Q) = v + F/Q` | $/part |
| Break-even batch size | `Q* = (F_A - F_B) / (v_B - v_A)` | parts |

Th is handling time, Tt tool-change time per edge, Co machine rate, Ce cost per edge, Cm material cost, Ts setup time, Cs setup rate, s scrap fraction. Optimum speeds (minimum cost and maximum production rate) and the sensitivity method are derived in `docs/MODEL.md`.

## Commands

```
python -m process_cost estimate    JOB.json              cycle time, cost per part, optimum speeds
python -m process_cost breakeven   JOB.json [--svg FILE] break-even batch size between 2 scenarios
python -m process_cost sensitivity JOB.json [--step N]   one-at-a-time sensitivity table
python -m process_cost report      JOB.json [--svg FILE] [--step N]   all of the above
python -m process_cost materials                         list the indicative cutting data table
python -m process_cost JOB.json                          same as report
python -m process_cost --version
```

`--step` is the percent step (default 10; the table uses -2s, -s, +s, +2s). `--svg FILE` also writes a cost-per-part against batch-size chart. If the package is installed with `pip install .`, the command `process-cost` does the same job as `python -m process_cost`.

## Running tests

```
pip install pytest
python -m pytest -q
```

Expected result: `160 passed` (a deprecation warning from a locally installed pytest plugin may also appear).

## Assumptions and limits

- The materials table holds indicative, textbook-order data. It is not a machining data sheet. It was sanity-checked against public secondary sources, not against the textbooks page by page (see `docs/MODEL.md`, "Cross-check status").
- Real tool life must be checked with the tool maker and by shop trials before you rely on any number.
- Turning uses the mean diameter Dm = (D0 + D1)/2 for every pass. Constant surface speed is not modelled.
- Taylor tool life depends on speed only. Feed and depth of cut do not change tool life.
- One operation per scenario. No facing, threading, drilling or finishing passes. Rapid moves and acceleration are ignored.
- Cutting force, power, surface finish and chatter are not checked. An economic optimum speed can still exceed machine power or tolerance.
- Overheads are lumped into the machine rate. No queue time, inspection or inventory cost.
- You supply the milling cut length yourself; the tool does not generate toolpaths.
- It is not a substitute for CAM or quoting software. Use it to compare options, not to quote.

## Data sources

General textbook references, named in `docs/MODEL.md`. No table or page is reproduced.

- S. Kalpakjian and S. R. Schmid, *Manufacturing Engineering and Technology*.
- M. P. Groover, *Fundamentals of Modern Manufacturing* (Taylor equation, cost-per-piece model, optimum speeds).
- *Machinery's Handbook*, Industrial Press.
- Public cutting-data ranges in tool-maker catalogues.

## Licence

MIT. Copyright (c) 2026 Akmal Azeem
