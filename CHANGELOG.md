# Changelog

A dated history of how this project evolved. Reconstructed from file timestamps,
notebook/script contents, and `FINDINGS.md` during the June 2026 reorganization.
Newest first. For the *why* behind methodology choices, see [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## 2026-06-01 — Repository reorganization & project logs

- Initialised **git** to make development trackable; committed the original unorganized state first, then this reorganized layout.
- Restructured a flat ~40-file root into `docs/ data/ notebooks/ pipeline/ reports/ figures/` with `archive/` sub-folders for superseded work.
- Renamed `_exp/` → `pipeline/`. Moved gen-1 notebooks/reports/figures into archives.
- Rewrote internal relative paths in the two active notebooks so they run from `notebooks/` (`data/…` → `../data/…`, outputs → `../reports/…`). Repointed `EDA.ipynb`'s broken `data/VF_export.csv` reference to `../data/VF_export_old.csv` (the data it was actually audited against).
- Removed an orphaned Excel lock file (`~$…v2.xlsx`); added `.gitignore`.
- Authored `README.md`, `CHANGELOG.md`, and `docs/{PROJECT_LOG, DECISIONS, DATA_DICTIONARY, OPEN_QUESTIONS}.md`; moved `FINDINGS.md` and the Visio diagram into `docs/`.
- **No analysis logic changed.** This was structure + documentation only.

---

## Generation 3 — 2026-05-26 — Data refresh (new process export)

- New process export landed: **`VF_export_new.csv` (8,230 rows, 11 Mar → 13 May 2026, 15 production days)**, extending the previous export by one week. The earlier export was preserved as `VF_export_old.csv` (7,372 rows, → 6 May, 14 days).
- **The scrap-label file (`VF_Scrap_export.csv`, 386 rows) was *not* refreshed alongside it.** The extra week of production (May 7–13) therefore carries essentially no scrap labels yet — consistent with the known scrap-detection lag (median ~6 h, max 43 d).
- Re-ran the Final notebook against the new data and regenerated:
  - `reports/Scrap_Recommendations_Report_v2.xlsx` (added a `Live Reccomendations` sheet)
  - `reports/operating_windows_final.csv`
  - `reports/VF_Full_RawData_With_Recommendations.xlsx`
- ⚠️ Consequence: headline scrap rate shifts from **5.24 % (old)** to **≈ 4.69 % (new)** purely because the denominator grew while labelled scrap did not. `FINDINGS.md` still quotes the old-data numbers. See [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) → data currency.

---

## Generation 2 — 2026-05-11 → 2026-05-14 — Rigorous rebuild (tool-conditional)

The pivotal redesign. The first-generation analysis pooled scrap-vs-good *across tools*,
which mostly measured recipe × tool-rate rather than causal drift. Gen 2 rebuilt everything
**tool-conditionally**.

- Built a reproducible Python pipeline in `_exp/` (now `pipeline/`):
  `01_profile → 02_experiments → 03_refine`, then the deeper `10_deep_eda → 11_hypotheses → 12_models`.
- Established the core methodology: within-tool recipe-vs-drift separation (CV filter), Welch t-test + Cliff's δ + KS + Wilson CIs, per-`(tool, defect)` L1-LR / RandomForest / GradientBoosting with 5-fold CV + permutation importance, Isolation-Forest anomaly score, and a deflationary operating-window validation.
- Ran **16 pre-registered hypotheses** (H1–H16); documented accept/reject/conditional verdicts.
- Generated deliverables via `build_eda_notebook.py`, `build_final_notebook.py`, `build_docx_report.py`, `add_part_recs_sheet.py`:
  - `EDA.ipynb` (34 cells), `VAC_Forming_Scrap_Analysis_Final.ipynb` (38 cells)
  - `Scrap_Recommendations_Report_v2.xlsx` (7 sheets), `VAC_Forming_Scrap_Report.docx`
  - `FINDINGS.md` — the consolidated report
- Data source: `VF_export.csv` (the 7,372-row export, now `VF_export_old.csv`).
- *Note:* the `pipeline/*.py` scripts carry a hard-coded `ROOT = C:\Users\12345\...` path and read `VF_export.csv`; they are kept as the historical reproducibility record and would need path edits to re-run today.

---

## Generation 1 — 2026-03-13 — First-pass analysis (pooled)

- Initial exploration straight from `Book3.xlsx` (sheets `Process Data` + `Scrap`).
- `VAC_Forming_Scrap_Analysis.ipynb` (48 cells) — pooled scrap-vs-good analysis; treated Low Glue as the single largest defect (n≈130 under the then-current join) and produced parameter-distribution plots (`figures/01…10_*.png`).
- `Scrap_Recommendation_Engine.ipynb` (25 cells) — a z-score / deviation-score engine with a **live database write** path (the only notebook that connects to a DB).
- `Scrap_Recommendations_Report.xlsx` (v1, single sheet), plus `deviation_heatmap.png`, `tool_comparison.png`, `engine_validation.png`.
- **Superseded by Generation 2** once the pooled approach was found to confound tool/recipe effects. Retained in `notebooks/archive/` and `reports/archive/` for provenance — notably the DB-write code in the engine notebook is the reference for any future live deployment.
