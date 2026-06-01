# Data Dictionary

Schema, the 40 process parameters, sentinels/encodings, and the defect taxonomy.
Numeric ranges below are from the parameter profile on the original export
(`pipeline/results/eda_param_profile.csv`, n = 7,372); they characterize each column's
behaviour and will be close but not identical on the newer export.

---

## 1. Files & schema

| File | Rows | Columns | Notes |
|---|---|---|---|
| `data/VF_export_new.csv` | 8,230 | `ID, PartDesc, BuiltTime, DS1, DS2, DS3` | **Current** process export (11 Mar → 13 May 2026). |
| `data/VF_export_old.csv` | 7,372 | same | Previous export (→ 6 May). Matches all `FINDINGS.md` numbers. |
| `data/VF_Scrap_export.csv` | 386 | `ID, Desc, ScrapTime` | Scrap labels. **Not refreshed with the new process export** (see CHANGELOG / R-1). |
| `data/Book3.xlsx` | — | sheets `Process Data`, `Scrap` | Generation-1 raw source. |

- **`ID`** uniquely identifies a produced part; every scrap `ID` (386/386) joins to the process table.
- **`BuiltTime`** = production timestamp (assumed; warm-up finding depends on it).
- **`ScrapTime`** = QC/detection time, *not* production time (median lag ~6 h, max 43 d).
- **`DS1`/`DS2`/`DS3`** are comma-separated `key:value` strings holding **40 parameters total**
  (DS1 = 16, DS2 = 15, DS3 = 9). Parse with `key:value` split on `,` then `:`. Example parser:
  `pipeline/10_deep_eda.py::parse_kv`.

---

## 2. Parameters — special handling

These columns need non-naive treatment (see DECISIONS D-06). **Each rests on an assumption needing
operator confirmation — cross-referenced to [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).**

| Parameter | Behaviour | Handling | Q |
|---|---|---|---|
| `Machine Cycle Time` | `= 9999` in 9.5 % of rows (normal ~660–780). **Confirmed (team):** 9999 is the recorder's **max value** — the field saturates when the true cycle time exceeds the largest recordable number (4-digit overflow). | Keep treating 9999 as **missing** (true value unknown, only known to be ≥ max → an abnormally long / paused cycle); keep `mct_capped` + `prev_mct_capped` flags. | Q2 ✅ |
| `Pyro Clean` | Looks like a monotonic counter (951 unique). ~~Per-tool sweet spot.~~ | ⚠️ **Revised 2026-06-01:** NOT a fixed-clock reset (team); sweet spot is an artifact (unstable on split). **Feature only — sweet-spot rule retired** (D-13). Trace pending OQ-18. | Q1, Q13, Q17 |
| `Pos Vinyl N/S Length/Width` | Bimodal: ~49–60 % zero, non-zero ≈ 200+. | ⚠️ **Revised 2026-06-01:** zero = **camera blocked by excess material** (team), not "inactive". Encode `_cam_blocked = (value==0)`; compute bands/deviations on **visible rows (value>0) only** (D-12). | Q3 |
| `BT Circuit 2 Temp` | Two regimes: mostly 22–28, tail 300–833; 966 zeros. | Keep raw; model handles. | Q7 |
| `TTF Circuit 1 Temp` | 2,240 zeros (30 %); else ~28–38. | Keep; zero may = inactive circuit. | — |
| `Temp Z4` | 5,140 zeros (70 %); else ~100–180. | Bimodal off/active like Pos Vinyl. | — |
| `Capacity THT` / `Capacity BHT` | Capped at 85 / 70 respectively. | Possible hardware/controller ceiling. | Q5 |
| `Top Tool Pos Close` | Only 4 discrete values (12330/12480/12490/12500). | Likely categorical clamp position. | Q6 |

### Always-constant → dropped
| Parameter | Value | Action | Q |
|---|---|---|---|
| `Pick Material Pos` | 220 always | Drop | — |
| `TTF Circuit 2 Temp` | 0 always | Drop | Q4 |

### Recipe-fixed within tool (excluded from causal ranking, CV < 0.01)
The **Stretch Length** family (`Stetch Length Pick Up / Stretch 1–3 / Form` — note the source-typo
"Stetch"), the **Stretch Cross** family (`Stretch Cross Pick Up / Stretch 1–3 / Form`), `Roller Gap LH/RH`,
`Glue Temp`, `Top Tool Pos Close`. These vary *between* tools (recipe differences) but are nearly
constant *within* a tool. See DECISIONS D-02. **Update 2026-06-01:** the team confirmed recipes are
**editable mid-run** and a change affects the *immediate next part* (Q10 resolved). These params stay
out of *per-part* ranking but are now surfaced as **engineering setpoints**, with `Δ-from-previous-part`
features added (D-11).

---

## 3. Full parameter list (40)

Grouped roughly by process stage. Ranges = [min … P50 … max] from the old export.

**Heating / temperature**
- `Temp. THT at Trigger` [127 · 159 · 228] — top-heater trigger temp.
- `Temp. BHT at Trigger` [142 · 190 · 222] — bottom-heater trigger temp.
- `heating time (tens of seconds)` [258 · 470 · 886]
- `Temp Z1`/`Z2`/`Z3` [~107 · ~140 · 180] — heater zone temps. `Temp Z4` [bimodal, 70 % zero].
- `Capacity THT` [0 · 65 · 85 (capped)], `Capacity BHT` [0 · 60 · 70 (capped)] — heater capacities.
- `BT Circuit 1 Temp` [21 · 25 · 29], `BT Circuit 2 Temp` [bimodal 0/22–28/300–833].
- `TTF Circuit 1 Temp` [0 · 28 · 38], `TTF Circuit 2 Temp` [0 always → dropped].
- `Glue Temp` [143 · 155 · 161] — recipe-fixed within tool.

**Vacuum / forming**
- `Vacuum Time Tool Cavity A` [13 · 72 · 88], `Vacuum Time Tool Cavity B` [9 · 71 · 87]
- `Graining Vacuum TTF Cavity 1` [1 · 87 · 90], `Graining Vacuum TTF Cavity 2` [1 · 88 · 91]
- `Time Feed to Vacuum 1` [46 · 70 · 82]
- `Machine Cycle Time` [656 · 780 · 9999-sentinel]

**Stretch / mechanical (recipe-fixed within tool)**
- `Stetch Length Pick Up / Stretch 1 / Stretch 2 / Stretch 3 / Form` [~15400 … ~18500]
- `Stretch Cross Pick Up / Stretch 1 / Stretch 2 / Stretch 3 / Form` [~4800 … ~9800]
- `Roller Gap LH` [-1 · 19 · 20], `Roller Gap RH` [-3 · 18 · 18]
- `Top Tool Pos Close` [4 discrete values]
- `Pick Material Pos` [220 always → dropped]

**Vinyl positioning (bimodal active/off → `_active` flag)**
- `Pos Vinyl N Length` / `N Width` / `S Length` / `S Width`

**Maintenance / counter**
- `Pyro Clean` [1 · 471 · 951] — cycle counter, per-tool sweet spot.

**Identity**
- `Tool Number` ∈ {1, 2, 8}.

### Engineered features (added in analysis)
`is_warmup` (first parts of a production day on a tool) · `prev_mct_capped` · `color`/`family`
parsed from `PartDesc` · `is_scrap` (= scrap join hit).

**Updated feature set (2026-06-01, per [`MODELING_UPDATES.md`](MODELING_UPDATES.md)):**
`is_cold_start` = `is_warmup` ∪ `is_restart` (first part after a >~25-min intra-day gap) ·
`mins_since_prev_on_tool` · `seq_in_day` · `{PosVinyl}_cam_blocked` (replaces `_active`) ·
`{recipe_param}_delta` (vs previous part on tool) · `color × heating-param` interactions.
Dropped: any shift/operator feature (spikes are thermal, not personnel — D-14).

---

## 4. Defect taxonomy

**Process-related (in scope for recommendations)** — Wrinkle, Dent, Bumps / lumps,
Burnt Carpet / Vynil, Low Glue / Read Thru / Impression, Out of dimension, Bad edge wrap,
Glue bleed thru, Delamination.

**Non-process (excluded from the engine — upstream/material)** — Hole, Broken / Fracture,
Fabric Flaw, Fabric Torn.

Current scrap counts (`VF_Scrap_export.csv`): Wrinkle 93 · Dent 62 · Bumps/lumps 52 ·
Burnt Carpet/Vynil 43 · Low Glue 41 · Bad edge wrap 32 · Out of dimension 23 · Hole 17 ·
Fabric Flaw 10 · Fabric Torn 7 · Broken/Fracture 4 · Glue bleed thru 1 · Delamination 1.

**Defect ↔ tool locking:** Wrinkle 99 % T1 · Low Glue 98 % T2 · Bumps 67 % T8 · Out-of-dim 78 % T1.
This is why all diagnosis is tool-conditional (DECISIONS D-01).
