# VAC Forming — Consolidated Scrap Analysis Report

**Project:** IAC + Algo8 AI · VAC Forming Scrap Reduction
**Data window analysed:** 11 March 2026 → 6 May 2026  (14 production days inside a 56-day span)
**Source files:** `data/VF_export.csv` (7,372 process rows) · `data/VF_Scrap_export.csv` (386 scrap rows)
**Overall scrap rate observed:** **5.24 %** (348 process-related, 38 non-process)

> ⚠️ **Data-currency note (added 2026-06-01).** This report reflects the **old** export
> (`VF_export_old.csv`, 7,372 rows, → 6 May). The data was later refreshed to `VF_export_new.csv`
> (8,230 rows, → 13 May) **without** a matching scrap-label refresh, which drops the apparent rate to
> ≈ 4.69 %. The methodology and findings below stand; the **headline numbers are old-data**. See
> [`../data/README.md`](../data/README.md) and [`PROJECT_LOG.md`](PROJECT_LOG.md) (R-1, R-2) before
> quoting figures externally.

> **Reading order**
> Executive summary → Approach → Data → Methodology → Hypotheses → Findings → Engine → Validation → **Assumptions** → **Open process questions** → What we did not do → Deliverables.

---

## 1. Executive summary

1. **Defects are tool-locked.** Wrinkle is 99 % Tool 1, Low Glue 98 % Tool 2, Bumps 67 % Tool 8. Recommendations must be `(tool, defect)`-specific, not global.
2. **Tool-conditional analysis is mandatory.** Tools run different recipes (different Roller Gap, Stretch Cross Form, Stretch Length, Glue Temp setpoints). Comparing scrap-vs-good *pooled across tools* mostly measures recipe × tool-rate, not causal drift.
3. **Several parameters cannot be "the cause" by construction.** Within each tool, parameters with coefficient of variation < 0.01 are recipe-fixed and excluded from causal ranking.
4. **The data have structural surprises** we treat explicitly: `Machine Cycle Time = 9999` (9.5 % of rows) is a stoppage sentinel; `Pos Vinyl *` parameters are bimodal (~50–60 % zero); `Pyro Clean` is a monotonic cycle counter with a **non-monotonic** scrap relationship.
5. **A warm-up effect is real**: first 10 parts of a production day scrap at ≈ 12 % vs steady-state ≈ 5 % (χ² p = 2.3 × 10⁻⁶).
6. **Per-(tool, defect) discriminative models reach AUC 0.72 – 0.89**. The diagnostic signal is real. Burnt Carpet (AUC 0.63) is the weakest and looks multi-causal.
7. **Simple operating-window rule alone is weak** (holdout AUC ≈ 0.55). We use it for triage only; defect-specific engine for diagnosis.

---

## 2. Approach

We separate the work into three layers, each with its own deliverable:

| Layer | Question | Deliverable |
|---|---|---|
| **Audit** | What is in the data? What is suspicious or surprising? | `EDA.ipynb` |
| **Diagnose** | For each `(tool, defect)`, which parameters deviate, by how much, with what confidence? | `VAC_Forming_Scrap_Analysis_Final.ipynb` |
| **Act** | What should an operator do when defect *D* is detected on tool *T*? | `Scrap_Recommendations_Report_v2.xlsx` + live `recommend(...)` engine |

Important: we **describe**, we do not **prescribe causation**. Scrap is already detected on-line; the value of this analysis is in *explaining* why a part went bad and converting that into a corrective action, not in predicting scrap.

---

## 3. Data inventory & cleaning decisions

### 3.1 Raw schema

- `VF_export.csv` — `ID`, `PartDesc`, `BuiltTime`, `DS1`, `DS2`, `DS3`. The DS columns are comma-separated `key:value` strings holding 40 parameters total (DS1 = 16, DS2 = 15, DS3 = 9).
- `VF_Scrap_export.csv` — `ID`, `Desc` (defect type), `ScrapTime`.
- Every scrap `ID` is found in the process table (386/386). Production IDs are unique.

### 3.2 Time coverage

- 14 production days inside a 56-day span — 43 zero-production calendar days.
- Days of week present: Monday – Thursday only.
- Hours present: 04 → 16, with bulk between 06 and 15.

### 3.3 Cleaning decisions (made in EDA, applied in the final notebook)

| Issue | Parameter(s) | Action |
|---|---|---|
| Constants | `Pick Material Pos` (= 220 always), `TTF Circuit 2 Temp` (= 0 always) | **Drop** |
| Sentinel cap | `Machine Cycle Time = 9999` (9.5 % of rows) | Treat the 9999 reading as missing; add `mct_capped` flag |
| Bimodal (off vs active) | `Pos Vinyl N/S Length/Width`, `Temp Z4` | Encode as `(value, _active_flag)` |
| Heavy-tailed (two regimes) | `BT Circuit 2 Temp` (p50 = 23, max = 833) | Keep raw — model handles |
| Recipe-fixed within tool (CV < 0.01) | `Stretch Cross *`, `Stetch Length *`, `Roller Gap *`, `Top Tool Pos Close`, `Glue Temp`, … | **Exclude from causal ranking** per tool |

### 3.4 Engineered context features

- `is_warmup` — first 20 parts of a production day on a tool.
- `prev_mct_capped` — whether the immediately preceding part on the same tool had `MCT = 9999`.
- `color`, `family` parsed from `PartDesc`.

### 3.5 Defect taxonomy

- **Process-related (in scope for recommendations):** Wrinkle, Dent, Bumps / lumps, Burnt Carpet / Vynil, Low Glue / Read Thru / Impression, Out of dimension, Bad edge wrap, Glue bleed thru, Delamination.
- **Non-process (excluded from recommendation engine):** Hole, Broken / Fracture, Fabric Flaw, Fabric Torn.

---

## 4. Methodology

### 4.1 Statistical primitives

For every candidate `(tool, defect, parameter)`:

- **Welch's t-test** (unequal variance) — significance.
- **Cliff's δ** ∈ [−1, +1] — non-parametric effect size. Severity: CRITICAL > 0.474, STRONG > 0.33, MODERATE > 0.20.
- **Kolmogorov–Smirnov** — distribution-shape sanity check.
- **Wilson 95 % confidence interval** for all rate comparisons.

### 4.2 Multivariate models (per tool × defect, n_bad ≥ 15)

- **L1-regularised logistic regression** (sparse coefficients).
- **Random Forest** (400 trees, depth 8, class-balanced).
- **Gradient Boosting** (200 stages, depth 3, lr 0.06).

5-fold stratified cross-validation; we report mean AUC and Brier score. We then use **permutation importance** on the best model to get a model-agnostic feature ranking.

### 4.3 Anomaly detection

Isolation Forest (300 trees, contamination 0.05) over the union of drifting parameters. Provides a tool-agnostic "this row looks unusual" score; useful as a tier-1 alarm only.

### 4.4 Validation

We split 70/30 stratified on `is_scrap`, build per-tool operating windows from train-good only, score test rows by **count of parameters outside [P5, P95]**, and report AUC + flag-rate / coverage at thresholds 0…7. This is deliberately a *deflationary* test — its AUC is ~0.55, which is precisely the point: a simple threshold rule is not enough; the defect-specific engine is.

---

## 5. Iterative hypothesis testing

Every hypothesis below was stated *before* running the test. Verdict codes: **A** = accept, **R** = reject, **C** = conditionally true with caveats.

| # | Hypothesis | Verdict | Numeric anchor |
|---|---|---|---|
| H1 | Scrap rate differs by tool | **A** | T1 = 7.28 % [6.27, 8.43], T2 = 3.97 % [3.39, 4.64], T8 = 5.40 % [4.32, 6.74]. χ² p = 1.7 × 10⁻⁷ |
| H2 | Scrap rate differs by part within each tool | **A** | All three tools p < 10⁻⁴ |
| H3 | Color matters after controlling for part family | **C** | Significant on PS LOWER LHD (BEIGE 15 % vs BLACK 5 %) and DS LOWER LHD; not universal — RR MAP POCKET is opposite |
| H4 | MAP POCKET parts scrap more (marginally) | **C** | True marginally; **confounded** — map pockets are almost exclusively Tool 1. Effect inside Tool 1 is null |
| H5 | Day-of-week effect (Monday spike) | **A** | Mon 14.9 % vs Thu 1.5 %; but all Monday parts are Tool 2 — tool-confounded |
| H6 | Hour-of-day shift effect | **A** | T1 hour 6 = 14.7 % (warm-up); T8 hour 13 = 19 % (afternoon spike) |
| H7 | First parts of a production day scrap more | **A** | First 10 ≈ 12 %, 10–19 ≈ 10 %, 20–49 ≈ 5.5 %, 50+ ≈ 4.9 %. χ² p = 2.3 × 10⁻⁶ |
| H8 | First part after a long gap scraps more | **R** | Not significant (p = 0.80); intra-day gaps are dominated by overnight rolls |
| H9 | `Machine Cycle Time = 9999` marks a stoppage | **A** | Scrap rate inside flag = 7.56 % vs 4.99 % outside; **next** part after flag = 8.0 % |
| H10 | Pyro Clean → scrap is monotonic | **A (non-monotone)** | Each tool has a sweet-spot band; outside it scrap doubles. T1 0–121 cycles; T2 459–710; T8 587–730 |
| H11 | Defect–tool exclusivity | **A** | Wrinkle 99 % T1, Low Glue 98 % T2, Bumps 67 % T8, Out of dim 78 % T1 |
| H12 | Parameter drift across the data window | **A (selective)** | Glue Temp / Machine Cycle Time drift on some tools; not one global drift |
| H13 | Bad days pile multiple defect types | **C** | Day-level Pearson(rate, n_defects) = 0.39 |
| H14 | `TTF Circuit 1 Temp = 0` marks a different recipe | **R** | Within-tool scrap rates do not differ by TTF = 0 vs > 0 |
| H15 | `Pos Vinyl *` are bimodal (active vs off) | **A** | 50–60 % zero; non-zero p50 ≈ 200+. Use `_active` flag |
| H16 | Defects co-cluster on the same day | **A** | Wrinkle days also see Bad edge wrap + Dent |

---

## 6. Findings — tool-level

| Tool | Parts | Scrap | Rate (95 % CI) | Dominant defects | Strongest signal |
|---|---:|---:|---|---|---|
| **1** | 2,240 | 163 | 7.28 % [6.27, 8.43] | Wrinkle, Out of dim, Bad edge wrap, Dent | Morning warm-up (hour 6 ≈ 15 %); Pyro Clean sweet-spot **0–76 cycles** (outside: 8.3 %) |
| **2** | 3,781 | 150 | 3.97 % [3.39, 4.64] | Low Glue, Dent, Burnt Carpet, Bumps | Low BHT/THT temps → Low Glue; Pyro Clean sweet spot **426–584** |
| **8** | 1,351 | 73 | 5.40 % [4.32, 6.74] | Bumps (35/52 of all Bumps), Dent | Afternoon spike (hour 13 ≈ 19 %); under-heating signature (THT/BHT/Capacities low) → Bumps; Pyro Clean min = 496 (never reset in window) |

---

## 7. Findings — defect-by-defect (tool-conditional)

### 7.1 Wrinkle  (n = 93; 99 % Tool 1) — largest single defect

Within Tool 1, scrap vs good (drift parameters only):

- ↑ **Pos Vinyl S Width** (+29 %) — strongest signal.
- ↑ Pos Vinyl N Length (+61 %), ↑ Pos Vinyl N Width (+38 %).
- ↓ Roller Gap RH (−30 %).
- ↓ Vacuum Time Tool Cavity A/B.
- ↑ Pyro Clean above the 76-cycle sweet-spot threshold.

5-fold CV AUC = **0.775** (L1-LR / RF tied). Multivariate signal is robust.

### 7.2 Low Glue / Read Thru / Impression  (n = 41; 98 % Tool 2)

Within Tool 2:
- ↓ **Temp. BHT at Trigger** (~ 194 → 171, −9 %).
- ↓ Temp. THT at Trigger (~ −6 %).
- ↓ TTF Circuit 1 Temp, ↓ BT Circuit 1/2 Temp.
- Pyro Clean often very low (< 34 cycles — fresh-clean state).

5-fold CV AUC = **0.867** (GBM) — strongest single defect signature in the dataset.

### 7.3 Dent  (n = 62; spread across all three tools)

Different signatures per tool — illustrates why pooling is wrong:
- **Tool 2** (n=28): ↑ heating time (+11 %), ↑ Pyro Clean (+36 %), ↓ Capacity BHT (−7 %), zone temps too high. AUC = **0.835**.
- **Tool 1** (n=19): ↑ Graining Vacuum TTF Cavity 1, ↑ Pos Vinyl N Width (+64 %), ↑ Pyro Clean. AUC = 0.721.
- **Tool 8** (n=15): ↓ BT Circuit 1 Temp. AUC = 0.719.

### 7.4 Bumps / lumps  (n = 52; 67 % Tool 8, 33 % Tool 2)

- **Tool 8 (under-heating signature)**: ↓ Temp. THT (−11 %), ↓ Temp. BHT (−8 %), ↓ Capacity BHT, ↓ Capacity THT, ↓ TTF Circuit 1 Temp. AUC = **0.890** — the strongest model.
- **Tool 2**: ↓ heating time, ↑ Pos Vinyl N Length / Width. AUC = 0.763.

### 7.5 Burnt Carpet / Vynil  (n = 43; 60 % Tool 2)

- **Tool 2**: ↓ Pyro Clean (very low — recently freshly cleaned). AUC = **0.632** — weakest single defect; likely multi-causal.
- Vacuum times slightly reduced.

### 7.6 Bad edge wrap  (n = 32; 63 % Tool 1, 37 % Tool 2)

- **Tool 1**: ↓ Temp. BHT at Trigger, ↓ Pyro Clean, ↓ BT Circuit 2 Temp. AUC = **0.803**.
- **Tool 2**: ↑ Pos Vinyl N Length/Width (activated — good parts have these off).

### 7.7 Out of dimension  (n = 23; 78 % Tool 1)

- **Tool 1**: ↑ Pyro Clean (+35 %), ↓ Roller Gap LH (−8 %), ↓ Vacuum Time Cavity B. AUC = 0.733.

---

## 8. Recommendation engine — how it works

`recommend(defect, tool, current_params, pyro_band) → list[action]`

For each rule in the engine (filtered to `welch_p < 0.05` and `|cliffs| > 0.2` on the relevant tool):

1. Look up the parameter's good `[P5, P50, P95]` on this tool.
2. Compare the current reading to that band:
   - inside → `OK`.
   - above P95 → `REDUCE → target P50`.
   - below P5 → `INCREASE → target P50`.
3. Severity label inherited from the historical effect size.
4. Pyro Clean has its own rule overlay: outside the per-tool sweet spot → `WAIT_BEFORE_CLEAN` or `PYRO_CLEAN_DUE`.

The output of a live demo (worst-violating scrap example per defect) fires 2–6 actions per case; see notebook cell §11.

---

## 9. Validation

70/30 stratified holdout. Train-good per-tool windows → score test rows by **count of out-of-window drifting parameters**.

- AUC of OOW-count vs `is_scrap` = **0.555**.
- At threshold ≥ 4: 9.1 % of test flagged, **9.90 % scrap rate inside flag**, 17.2 % scrap coverage.
- At threshold ≥ 6: 3.5 % of test flagged, **13.0 % scrap rate inside flag**, 8.6 % scrap coverage.

> The OOW-count rule is not a classifier — it is a triage signal. Real diagnosis comes from the defect-specific engine.

---

## 10. Assumptions (explicit)

These are the assumptions we made because we cannot verify them from data alone. If any prove wrong, the affected finding should be re-examined.

> ✅/⚠️ **Team review (2026-06-01).** The operations/engineering team reviewed these. **Confirmed:**
> A2 (ID), A3 (`BuiltTime`, from printed labels), A4 (`ScrapTime` = QC time), A6 (good baseline),
> A7 (P5–P95), A8 (labels). **Overturned:** A9 (`Pyro Clean` is *not* a fixed-clock counter — sweet-spot
> retired) and A11 (`Pos Vinyl` zero = *camera blocked by excess material*, not "inactive"). Plus
> process insights (warm-up is weather-driven; spikes are lunch restart, not operators; recipes are
> editable mid-run; beige is thermodynamic). Full translation to modeling changes in
> [`MODELING_UPDATES.md`](MODELING_UPDATES.md); resolutions tracked in [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

### 10.1 Scoping assumptions

- **A1. Process-defect taxonomy.** We assume the 9 defect codes listed in §3.5 are *operator-actionable* and the other 4 (Hole, Broken / Fracture, Fabric Flaw, Fabric Torn) are upstream / material defects out of scope. **Risk if wrong**: some "non-process" defects may actually be process-actionable, in which case we are under-counting recoverable scrap.
- **A2. ID semantics.** We assume `ID` uniquely identifies a single produced part and that join is correct. Both tables show unique IDs and 386/386 matches.
- **A3. `BuiltTime` is the actual production timestamp** (not a record-creation time). The warm-up finding relies on this.
- **A4. `ScrapTime` is the QC / detection time**, not the production time. The 6-hour median lag + 43-day max are consistent with downstream / customer-side detection on some defect types.

### 10.2 Methodological assumptions

- **A5. Tools have stable recipes within the window.** We assume each tool's recipe (Roller Gap, Stretch Cross, etc.) was not deliberately changed during the 56-day window. The low within-tool CV on these parameters supports this empirically.
- **A6. Good parts are a valid baseline.** For each tool we use *good* parts on the same tool as the reference. We assume good parts represent acceptable process state. If many "good" parts are actually marginal but happened to pass QC, our targets are biased.
- **A7. P5–P95 is a reasonable operating window.** Wider would dilute the signal; narrower would over-fire. We did not run a cost-weighted optimisation of band width.
- **A8. Defect labels are accurate.** We assume the scrap `Desc` column is correctly assigned by inspection. Some defects look ambiguous (e.g. "Dent" vs "Bumps / lumps") and could be subjectively labelled.
- **A9. `Pyro Clean` is a counter** (cycles since last clean). The monotonicity check (≤ 0.5 % decreases) strongly supports this. If it is actually a different quantity (e.g. a setpoint), the sweet-spot recommendation must be re-interpreted.
- **A10. `Machine Cycle Time = 9999` is a stoppage sentinel.** The 9.5 % prevalence and the elevated scrap rate around it are consistent with this. A different cause (e.g. data-logger error) would change how the `prev_mct_capped` flag should be used.
- **A11. `Pos Vinyl *` zero values mean the feature is inactive.** Treating them as a `_active` flag follows. If they are instead "default-when-unset", this encoding is still safer than treating zero as a numerical level.

### 10.3 What we did *not* assume (and explicitly avoided)

- We did **not** assume the prior recommendations (from the earlier dataset) caused any change in the current data. The defect-mix shift is described, not attributed.
- We did **not** assume causality from the deviation tables — they are *associations within the data*, not interventions.
- We did **not** project annualised savings — the data window is bursty (14 production days) and we have no expected production volume to extrapolate against.

---

## 11. Process-related open questions / ambiguities

These need the operator / maintenance / engineering teams. Each affects how recommendations should be applied or interpreted.

### A. Sensor / data semantics

1. **`Pyro Clean`** — exact meaning? Cycles since last pyro clean? Why does Tool 8 *never* reach a reset in 56 days (min observed = 496)?
2. **`Machine Cycle Time = 9999`** — what event does this code represent? Stop, sensor not-ready, reset, manual override? What is the real cycle time during these events?
3. **`Pos Vinyl N/S Length/Width` zero values** — feature disabled by recipe, or default-when-unset?
4. **`TTF Circuit 2 Temp = 0` everywhere** — sensor removed, feature retired, or always-off configuration?
5. **`Capacity BHT` capped at 70** (5.4 % of rows) and **`Capacity THT` capped at 85** — actual hardware ceiling, or controller setpoint cap?
6. **`Top Tool Pos Close`** has only 4 unique values (12330 / 12480 / 12490 / 12500) — discrete clamp positions? What does each correspond to?
7. **`BT Circuit 2 Temp`** has two regimes (most rows 22–28, others 300–833). Are these different heater modes?

### B. Operations & people

8. **Operator / shift identifiers** — Are they logged anywhere? Tool 1 morning warm-up and Tool 8 afternoon spike both have the signature of a personnel signal we cannot see.
9. **Warm-up procedure** — Is there a standardised one? The data shows the first 10–20 parts of a production day at ≈ 12 % scrap vs ≈ 5 % steady-state. A pre-warm cycle or sacrificial warm-up parts could close this gap.
10. **Recipe configurability** — Are recipes hard-locked per tool, or editable per part? If editable, our "recipe-fixed" parameters become candidates for *engineering changes* rather than runtime operator nudges.
11. **Tool 8 absence of Wrinkle / Bad edge wrap** — Is this real (different geometry / mechanics) or label coding (those defects coded differently on Tool 8)?
12. **MAP POCKET BEIGE on Tool 1 at 23.1 % scrap** — colorant interaction, geometric difficulty, supply-lot variance, or inspection bias?
13. **`Pyro Clean` policy** — Scheduled cleaning, defect-triggered, or operator judgement? Tool 8 not resetting in 56 days is unusual.
14. **Scrap detection workflow** — Median lag 6 h, max 43 d. Are some defects discovered downstream or at the customer? Recent days' scrap totals are likely incomplete.
15. **Color × family confound** — PS LOWER LHD: BEIGE 15.3 % vs BLACK 4.79 %. Different vinyl source? Different supplier? Inspection visibility?

### C. Modeling

16. **Burnt Carpet AUC = 0.63** — weakest model. Multi-causal, or are we conflating sub-types? Would help to sub-label.
17. **Tool 1 Pyro Clean ceiling 495** — Tool 1 resets, Tool 8 has not. Different cleaning cadence, different counter semantics, or counter shared with something we can't see?

---

## 12. What we did **not** do, and why

- **No annual-savings projection.** 14 production days inside 56 calendar days is too bursty to annualise without a baseline volume.
- **No causal claims about prior interventions.** We have no metadata about what was or wasn't changed on the line between the previous dataset and this one.
- **No supervised classifier exposed as a "scrap predictor".** The CV AUCs (0.72 – 0.89) say a signal exists, but the line already detects scrap in-line. The value is in *explaining* the event, not predicting it.
- **No leaderboard tuning.** Model hyperparameters are out-of-the-box defaults. The methodology is interpretable and reproducible; we did not chase a tenth of an AUC point.
- **No part-level recommendation table.** The per-part rates (e.g. `FL MAP POCKET BEIGE` 23.1 %) are an open question for engineering, not an operator-runtime knob.

---

## 13. Repo deliverables

| File | Purpose |
|---|---|
| `EDA.ipynb` | Pure exploratory audit — schema, ranges, sentinel detection, time coverage, recipe-vs-drift, tool/part/color structure, Pyro Clean counter analysis. 34 cells. |
| `VAC_Forming_Scrap_Analysis_Final.ipynb` | Diagnosis, multivariate modeling, recommendation engine, live demo, validation. 38 cells. |
| `Scrap_Recommendations_Report_v2.xlsx` | 7-sheet operator report: tool summary, defect × tool, operating windows, Pyro Clean bands, defect rules (67 rows), model CV AUCs, all deviations (305 rows). |
| `operating_windows_final.csv` | Per-tool [P5, P50, P95] reference table for the recommendation engine. |
| `FINDINGS.md` | **This document.** |
| `_exp/10_deep_eda.py` | Reproducible deep EDA pipeline. |
| `_exp/11_hypotheses.py` | Reproducible hypothesis test suite. |
| `_exp/12_models.py` | Reproducible per-(tool, defect) CV modeling experiments. |
| `_exp/build_eda_notebook.py`, `_exp/build_final_notebook.py` | Notebook generators. |
| `_exp/results/*.csv` | Intermediate artefacts: parameter profile, hypothesis tables, drift, model summaries, unified ranking. |
| `_exp/df_clean.parquet` | Cleaned, joined frame (parsed parameters + scrap labels). |

**Jupyter kernel:** `py311-vacforming` (Python 3.11, sklearn, scipy, pandas, seaborn, openpyxl).

---

## 14. One-line per major finding (for quick reference)

- **Scrap rate is 5.24 % over the window**, varying by tool (3.97 – 7.28 %).
- **Defects are tool-locked**; analysis is `(tool, defect)`-specific.
- **Tool 1 problem = Wrinkle** (Pos Vinyl S Width over-set, morning warm-up).
- **Tool 2 problem = Low Glue** (BHT/THT trigger temps run low; tightest BHT band around 190 – 200 °C).
- **Tool 8 problem = Bumps** (under-heating signature: THT/BHT/Capacities low together; afternoon spike).
- **Pyro Clean has per-tool sweet spots**; the relationship is non-monotonic.
- **Warm-up effect**: first 10 parts of a day scrap at ≈ 12 % — strong candidate for an operations intervention.
- **`Machine Cycle Time = 9999`** is a stoppage sentinel; the next part is at elevated risk.
- **Discriminative models reach AUC 0.72 – 0.89**; the simple OOW rule alone is too weak (0.55) to be a classifier.
- **17 open process questions** documented in §11 for the operator team to close the loop with engineering reality.
