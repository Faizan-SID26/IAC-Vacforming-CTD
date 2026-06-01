# Pipeline (`pipeline/`, formerly `_exp/`)

The reproducible Generation-2 Python pipeline that produced the analysis, notebooks, and reports.
Kept as the historical reproducibility record.

> ⚠️ **Not runnable as-is.** Every script hard-codes `ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"`
> and reads `data/VF_export.csv` (the file is now `data/VF_export_old.csv`). To re-run: update `ROOT`
> to this repo's path and the filename to `VF_export_old.csv` (or `VF_export_new.csv` to refresh on
> current data). Tracked as R-3 in [`../docs/PROJECT_LOG.md`](../docs/PROJECT_LOG.md).

## Order & purpose

| Script | Purpose |
|---|---|
| `01_profile.py` | First profiling of the new CSVs vs the old `Book3.xlsx`; parse DS1/2/3, join scrap, write `df_joined.parquet`. |
| `02_experiments.py` | Early experiment sweep. |
| `03_refine.py` | Refinement pass → `df_with_features.parquet`, `unified_ranking.parquet`. |
| `10_deep_eda.py` | **Deep EDA** — schema, sentinels, time coverage, recipe-vs-drift, Pyro-Clean counter check → `results/eda_*.csv`, `df_clean.parquet`. |
| `11_hypotheses.py` | The 16 pre-registered hypothesis tests (H1–H16) → `results/`. |
| `12_models.py` | Per-`(tool, defect)` CV modelling (L1-LR / RF / GBM) + permutation importance → `results/model_*.csv`, `results/rf_imp_*.csv`. |
| `build_eda_notebook.py` | Generates `notebooks/EDA.ipynb`. |
| `build_final_notebook.py` | Generates `notebooks/VAC_Forming_Scrap_Analysis_Final.ipynb`. |
| `build_notebook.py` | Earlier notebook generator (Generation-1-era). |
| `build_docx_report.py` | Generates `reports/VAC_Forming_Scrap_Report.docx` (+ `docx_plots/`). |
| `add_part_recs_sheet.py` | Adds the per-part recommendations sheet to the Excel report. |

## Artefacts

- `df_clean.parquet`, `df_joined.parquet`, `df_with_features.parquet`, `unified_ranking.parquet` — cached intermediate frames.
- `results/*.csv` — parameter profile, daily/weekly aggregates, within-tool CV, per-defect deviation tables (`dev_global_*`), RF importances (`rf_imp_*`), model CV summary, operating windows, unified ranking.
- `docx_plots/*.png` — figures embedded in the Word report.

> ⚠️ All artefacts derive from the **old** export — regenerate after resolving the data-currency issue (R-1) if you need current-data versions.
