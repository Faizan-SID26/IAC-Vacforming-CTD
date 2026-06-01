# Project Log — VAC Forming Scrap Reduction

> **This is the living source of truth for the project.** Read the top three sections to
> get oriented in 60 seconds; append to the dated journal at the bottom as work continues.
> History of *what was built when* lives in [`../CHANGELOG.md`](../CHANGELOG.md); the *why*
> behind methodology lives in [`DECISIONS.md`](DECISIONS.md).

---

## Current status (as of 2026-06-01, PM — after team assumption review)

| Aspect | State |
|---|---|
| **Phase** | Gen-2 analysis delivered. **Modeling approach now updated** per the team's assumption review — see [`MODELING_UPDATES.md`](MODELING_UPDATES.md). Awaiting the May 14–28 data drop to implement + validate. |
| **Modeling spec** | Phase 1 **done**: 6 changes (U-1…U-6) specified and evidence-checked against labeled data ([`../pipeline/20_assumption_update_checks.py`](../pipeline/20_assumption_update_checks.py)). Not yet wired into the notebook/engine (Phase 2, needs the new data). |
| **Latest data** | `data/VF_export_new.csv` — 8,230 process rows, 11 Mar → 13 May 2026, 15 production days. |
| **Latest analysis** | `notebooks/VAC_Forming_Scrap_Analysis_Final.ipynb` (runs on new data). |
| **Latest deliverable** | `reports/Scrap_Recommendations_Report_v2.xlsx` (7 sheets + Live Recommendations). |
| **Engine** | `recommend(defect, tool, current_params, pyro_band)` works in-notebook (cell §11). **Not** wired to a live data feed in the current generation. |
| **Known blocker** | Scrap-label file is stale relative to the new process export (see "Risks" below). |

### The one-paragraph "where we are"

We have a working, tool-conditional scrap-diagnosis engine. For each `(tool, defect)` pair it
identifies which process parameters deviate from the tool's good-part operating window, by how
much, and with what statistical confidence, then emits operator actions (INCREASE/REDUCE toward
the good P50, plus Pyro-Clean timing). The methodology is validated (per-defect models reach
AUC 0.72–0.89) and the limitations are explicitly catalogued. The main thing standing between
"analysis" and "production" is **(a)** resolving the data-currency mismatch and **(b)** the 17
open process questions that need the operator/engineering team.

---

## Latest direction & newest approach

The project's center of gravity is the **Generation-2 tool-conditional methodology** (see
[`DECISIONS.md`](DECISIONS.md) D-01). Everything current builds on it:

- Diagnose **within each tool**, never pooled — because tools run different recipes.
- Separate **recipe-fixed** parameters (low within-tool CV → excluded from causal ranking) from
  **drift-able** ones.
- Rank deviations by **effect size (Cliff's δ)** gated on significance (Welch p), not by p alone.
- Treat the operating-window count as **triage**, and the per-defect model as **diagnosis**.

Generation 3 (May 26) was a **data refresh**, not a method change: same engine, new export.

---

## Next steps (pick up here)

**Immediate (Phase 2 — on the May 14–28 data drop):**

- **N-A. Confirm the new export is scrap-labeled** (OQ-20). If yes → true out-of-time holdout; if not → we can only *issue* recommendations, not *score* them.
- **N-B. Implement U-1…U-6** from [`MODELING_UPDATES.md`](MODELING_UPDATES.md) in the Final notebook/engine: re-encode Pos Vinyl (`_cam_blocked`, visible-only bands), retire the Pyro sweet-spot rule, add unified `is_cold_start` + gap/seq features, add color×temperature interactions + beige windows, add the recipe "engineering-setpoint" lane + Δ-from-prev features, add Tool-8 cross-tool fallback.
- **N-C. Run the holdout protocol** (MODELING_UPDATES §5): freeze engine on ≤6 May, score 14–28 May per-(tool, defect), report action precision / false-fire, backtest cold-start & beige rates.
- **N-D. Deliver** the "May 14–28 recommendations + how-we-did" report; append results here.

**Standing items (pre-existing):**

1. **Resolve data currency (blocker, ~½ day).** Obtain a refreshed `VF_Scrap_export.csv` that
   covers through 13 May, or explicitly scope the analysis to the labelled window (≤ 6 May).
   Until then, do not quote a single headline scrap rate externally — old data says 5.24 %, new
   says ≈ 4.69 % only because the denominator grew. See Risk R-1.
2. **Reconcile the docs to the chosen data generation (~½ day).** `FINDINGS.md` quotes old-data
   numbers; the Final notebook runs new data. Decide the canonical dataset, then re-run the Final
   notebook and update `FINDINGS.md`'s headline figures + the v2 report. Consider re-pointing
   `EDA.ipynb` to the same generation and re-running.
3. **Close the highest-value open questions** with the operator team (see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md)).
   Highest leverage: Q1 Pyro-Clean semantics, Q2 `MCT=9999` meaning, Q8/Q9 operator-shift &
   warm-up procedure (the warm-up effect is the single biggest operational lever).
4. **Operationalize the engine (scoping needed).** The Gen-1 `Scrap_Recommendation_Engine.ipynb`
   (archived) already contains the live **DB-write** pattern. To deploy: wrap `recommend(...)`
   behind that connection, feed it live `(tool, defect, params)` at scrap-detection time, and
   write actions back. Decide cadence (real-time vs batch) and target table first.
5. **Strengthen the weakest model.** Burnt Carpet / Vynil sits at AUC 0.63 and looks multi-causal
   — likely needs sub-labelling (Q16). Low priority until labels improve.

---

## Risks & watch-items

| ID | Risk | Mitigation / status |
|---|---|---|
| **R-1** | **Data currency mismatch** — process export refreshed (→13 May) but scrap labels did not (→ effectively 6 May). Inflates the "good" denominator and deflates the apparent scrap rate. | Open. Step 1 above. |
| **R-2** | **Docs vs notebook drift** — `FINDINGS.md` numbers are old-data; Final notebook is new-data. | Open. Step 2 above. |
| **R-3** | **Pipeline scripts not re-runnable as-is** — `pipeline/*.py` hard-code `C:\Users\12345\…` and read `VF_export.csv`. | Kept as historical record; edit `ROOT` + filename to re-run. |
| **R-4** | **Causal language** — deviation tables are associations within the data, *not* interventions. Easy to over-read as "the cause". | Documented in `FINDINGS.md` §10.3 & `DECISIONS.md`. Keep wording disciplined. |
| **R-5** | **17 open process questions** gate several findings (sentinels, Pyro-Clean, color×family confound). | Tracked in `OPEN_QUESTIONS.md`. |

---

## Key artefacts quick-reference

| Want to… | Open… |
|---|---|
| Understand the whole analysis | `docs/FINDINGS.md` |
| See the live diagnosis + engine | `notebooks/VAC_Forming_Scrap_Analysis_Final.ipynb` |
| Hand operators a report | `reports/Scrap_Recommendations_Report_v2.xlsx` |
| Look up a parameter / sentinel | `docs/DATA_DICTIONARY.md` |
| Reproduce the stats from scratch | `pipeline/10_deep_eda.py → 11_hypotheses.py → 12_models.py` |
| Find the live DB-write pattern | `notebooks/archive/Scrap_Recommendation_Engine.ipynb` |

---

## Dated journal

Append newest entries at the top. One entry per working session; note **what changed, what was
learned, and what's next** so the thread is never lost.

### 2026-06-01 (PM) — Team assumption review → modeling approach updated
- Team returned verdicts on our DS assumptions: confirmed A2/A3/A4/A6/A7/A8; corrected the Pos Vinyl and Pyro-Clean encodings; gave process insights (warm-up is weather-driven, spikes are lunch restart not operators, recipes are editable mid-run, Tool-8 gaps are volume, beige is thermodynamic).
- **Evidence-checked every claim** against the labeled data (`pipeline/20_assumption_update_checks.py`):
  - Pyro sweet spot **unstable on a random split** → confirmed artifact (retire it).
  - Cold-start (warm-up ∪ restart) **13.5 % vs 5.0 %**, p=2.5e-7 → unify thermally.
  - Beige **8.7 %** vs black 4.1 %; runs cooler + more variable on THT → thermodynamic balance holds.
  - Pos Vinyl: blocked rows scrap *less* (4.0 % vs 8.1 %); Wrinkle's Pos-Vinyl signal **δ 0.358 → 0.180** once blocked rows excluded → encoding was inflating it.
- Wrote [`MODELING_UPDATES.md`](MODELING_UPDATES.md) (U-1…U-6 + validation plan); updated DECISIONS (D-02 superseded, D-06 revised, D-11…D-14), OPEN_QUESTIONS (Q3/Q8/Q9/Q10/Q11/Q12/Q15 resolved; OQ-18/19/20 added), DATA_DICTIONARY, FINDINGS §10.
- **Learned:** the separate operational findings (warm-up, afternoon spike, beige) share **one root cause — thermal stability**. That reframes the recommendation story around temperature readiness.
- **Next:** await the May 14–28 export; confirm it's labeled (OQ-20); implement U-1…U-6 and run the holdout.

### 2026-06-01 (AM) — Reorganization & logging
- Inventoried the entire repo; reconstructed the three-generation history (see CHANGELOG).
- Restructured into `docs/ data/ notebooks/ pipeline/ reports/ figures/`; initialised git; fixed notebook paths.
- Authored this log + README, CHANGELOG, DECISIONS, DATA_DICTIONARY, OPEN_QUESTIONS.
- **Learned / surfaced:** the data-currency mismatch (R-1) and docs-vs-notebook drift (R-2) — neither was previously written down. These are now the top of "Next steps".
- **Next:** resolve data currency (refreshed scrap export) before any further analysis or external reporting.
