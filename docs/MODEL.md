# process-cost model

This document lists every formula the tool uses, its units, the assumptions behind it and its limits.
All outputs are **estimates for comparing options**, not quotes.

## Units

| Quantity | Symbol | Unit |
|---|---|---|
| Lengths, diameters, depths | D, L, ap, ae | mm |
| Cutting speed | Vc | m/min |
| Spindle speed | n | rpm |
| Feed (turning) | f | mm/rev |
| Feed per tooth (milling) | fz | mm/tooth |
| Feed rate | vf | mm/min |
| Times | Tm, Th, Tt, Ts, T | min |
| Machine and setup rates | Co, Cs | $/h |
| Costs | Ce, Cm, F, v | $ (currency neutral) |
| Material removal rate | MRR | mm^3/min |

## 1. Kinematics

Spindle speed: `n = 1000 * Vc / (pi * D)`.

**Turning.** D is the mean diameter of cut `Dm = (D0 + D1)/2`. This is a simplification:
each pass actually runs at a slightly different diameter, and constant-surface-speed (G96) control is
not modelled. The cutting speed you give (or the table value) is the speed at Dm.

- Feed rate `vf = f * n`.
- Passes `N = ceil(((D0 - D1)/2) / ap)` (a small tolerance stops float noise such as 1.7/0.85 adding a pass).
- Length per pass `L + approach_mm`, where `approach_mm` is the total approach plus overtravel per pass.
  If it is omitted, the documented default **2.0 mm** is used and the output prints a note saying so.
- Cutting time `Tm = N * (L + approach) / vf`.
- MRR (reported) `= 1000 * Vc * f * ap` for a full-depth pass.

**Milling.** D is the cutter diameter.

- Feed rate `vf = fz * z * n`.
- `cut_length_mm` (Lc) is the toolpath length the cutter travels **while engaged, per depth pass**.
  You compute it yourself (by hand or from CAM); the tool does not generate toolpaths.
- Passes: give `passes`, or `total_depth_mm` and `ap_mm` so that `N = ceil(total_depth / ap)`. Giving both is an error.
- `lead_in_out_mm` (required) is the extra travel per pass for entry and exit.
- Cutting time `Tm = N * (Lc + lead_in_out) / vf`.
- MRR `= ap * ae * vf`, reported only when both `ap_mm` and `ae_mm` are given.

**Machine limits (optional).** If `spindle_max_rpm` is exceeded, n is capped and the effective cutting
speed is recomputed as `Vc_eff = pi * D * n_max / 1000`; tool life then uses Vc_eff. If
`feed_max_mm_per_min` is exceeded, vf is capped and the effective feed per rev (or per tooth) is reported.
Both caps print a WARNING line.

## 2. Taylor tool life

`V * T^n = C`, with V in m/min and T in min, so `T = (C/V)^(1/n)`.

For each (work material, tool material) pair the table holds a recommended speed Vc_rec, a Taylor
exponent n and a reference tool life T_ref at Vc_rec. The constant is derived as
`C = Vc_rec * T_ref^n` (turning or milling Vc_rec, matching the operation). In the job file you may
override `Vc_m_per_min`, `taylor_n` or `taylor_C`. If you override n but not C, C is re-derived from
the table with your n. Material `"custom"` skips the table and requires Vc, n and C.

Edges used per part = `Tm / T` (fractional cutting-edge consumption).

The simple Taylor equation depends on speed only. Feed and depth effects on tool life (the extended
Taylor equation) are not modelled, so a feed cap or feed change does not change T.

## 3. Cost per part (Groover-style)

Inputs: Th handling/load/unload time per part, Tt tool-change time per edge, Co machine rate including
operator and overhead, Ce cost per cutting edge (insert price / edges, or for solid tools the tool price
plus regrinds amortised over the number of lives), Cm material cost per part, Ts setup time per batch,
Cs setup rate (defaults to Co with a printed note), Q batch size in good parts, s scrap fraction.

```
time per piece      tp = Th + Tm + (Tm/T) * Tt                     [min]
machining           Co * (Th + Tm) / 60                            [$]
tool change         Co * (Tm/T) * Tt / 60                          [$]
tooling             (Tm/T) * Ce                                    [$]
material            Cm                                             [$]
fixed per batch     F = Ts/60 * Cs                                 [$]
variable per good   v = (Cm + Co*tp/60 + (Tm/T)*Ce) / (1 - s)      [$]
cost per good part  c(Q) = v + F/Q                                 [$]
batch time          Ts + (Q/(1 - s)) * tp                          [min]
batch cost          F + v*Q                                        [$]
```

Scrap: to deliver Q good parts you start `Q/(1 - s)`. The variable cost is therefore divided by
`(1 - s)`; the setup cost is incurred once per batch and is not scaled. Scrap is assumed to be found
at the end of the cycle (full cost incurred). Default s = 0.

The cost split percentages are setup (F/Q), machining, tool change, tooling and material, each per good part.

## 4. Optimum cutting speeds (feed held constant)

From Groover's derivation for a single-pass operation where Tm is proportional to 1/V:

```
minimum cost:            Tc = (1/n - 1) * (Tt + Ce / (Co/60)),   V = C / Tc^n
maximum production rate: Tp = (1/n - 1) * Tt,                    V = C / Tp^n
```

Both are reported beside your Vc together with the predicted tool life, time per part and cost per part
at that speed (machine caps applied). Undefined cases are stated, never crashed on:
Tt = 0 makes the maximum-rate speed unbounded; Tt = 0 and Ce = 0 make the minimum-cost speed unbounded;
n outside (0, 1) makes both undefined. Because the tool uses ceil(N) passes that do not depend on V,
Tm is exactly proportional to 1/V and the identities hold for multi-pass jobs too.

## 5. Break-even batch size

Each scenario is a straight line in total batch cost: `F + v*Q`.
For a machining scenario F is the setup cost and v the variable cost per good part (section 3).
For an outsource scenario (`"type": "outsource"`) F = `fixed_fee` and v = `price_per_part`.

```
Q* = (F_A - F_B) / (v_B - v_A)
```

- The option with the lower v wins at large batches; the other wins below Q*.
- The smallest whole batch where the at-scale option is **strictly** cheaper is found by rounding Q*
  and checking total cost at the neighbouring integers (if Q* is a whole number the two are equal at Q*).
- Equal v (parallel lines): no break-even; the lower-F option is cheaper at every size.
- Q* <= 0, or Q* < 1 part: one option is cheaper at every batch size (stated explicitly).

The report prints a table of cost per part at log-spaced sizes 1 to 10000 (plus the break-even
neighbours), a log-log text chart, and optionally (`--svg FILE`) an SVG chart generated with the
standard library.

## 6. Sensitivity

One factor at a time, each varied by -2s, -s, +s, +2s percent (s = `--step`, default 10, must be in (0, 50)):
Vc, feed (f or fz), Co, Ts, Ce, Tt, Th, Cm, Q and the Taylor exponent n. When Vc or n is varied, **C is
held fixed**, so tool life changes with them. Q is varied continuously (non-integer batch sizes are
allowed in this table). Rows are sorted by the largest absolute % change (tornado ordering). A parameter
whose base value is 0 shows no change.

## 7. Job file

JSON only. Either one complete job at the top level, or a `scenarios` list where each scenario is merged
over the top-level `operation` and `costs` sections (scenario values win). Unknown keys are rejected with
a suggestion, required fields are never defaulted, and invalid values exit with code 2 and a message
naming the field. Optional fields with defaults: `approach_mm` (2.0 mm, noted), `setup_rate_per_h`
(= machine rate, noted), `Vc_m_per_min`/`taylor_n`/`taylor_C` (from the table, noted), `scrap_rate` (0).

## 8. Data sources (indicative)

The materials table (`process_cost/materials.py`, `process-cost materials`) holds **indicative,
textbook-order starting assumptions**, chosen to sit inside the ranges given in general public references:

- S. Kalpakjian and S. R. Schmid, *Manufacturing Engineering and Technology* (Taylor n ranges by tool
  material; typical speed ranges).
- M. P. Groover, *Fundamentals of Modern Manufacturing* (Taylor equation, cost-per-piece model,
  minimum-cost and maximum-production-rate speeds).
- *Machinery's Handbook* (Industrial Press), speed and feed tables.
- Public cutting-data ranges in Sandvik Coromant and Kennametal catalogues (reference tool life of
  about 15 min for carbide).

No specific table, page or grade is reproduced. The values are not machining data sheet values for any
insert, coating, geometry, coolant or machine. **Check real tool life against the tool maker's data and
shop trials before relying on any number.** Ceramic tools are not included because their speeds and
Taylor constants depend too strongly on grade and work material to give one defensible value.

Values used: HSS n = 0.125 (T_ref 30 min), uncoated carbide n = 0.25 and coated carbide n = 0.30
(T_ref 15 min). Coated-carbide turning speeds: AISI 1018 220, AISI 1045 185, 304 130, 6061 450,
grey cast iron 150, free-cutting brass 260, Ti-6Al-4V 65 m/min; uncoated carbide and HSS are lower
(HSS about 21-29% of coated carbide). Milling speeds are listed separately.

## 9. Limits

- No constant-surface-speed, no facing, threading, drilling or finishing-pass logic; one operation per scenario.
- Rapid traverse, tool approach moves other than the stated allowances, and machine acceleration are ignored.
- Taylor equation depends on speed only; tool wear variation and breakage are not modelled.
- Cutting forces, power, surface finish and chatter are not checked: a speed or feed can be
  economically optimal and still exceed the machine's power or the part's tolerance.
- Overheads are lumped into Co; no queue time, inspection, or inventory-carrying cost.
- Money values in the examples are illustrative.
