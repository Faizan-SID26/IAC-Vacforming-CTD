# Data — provenance & currency

Full schema and per-parameter detail: [`../docs/DATA_DICTIONARY.md`](../docs/DATA_DICTIONARY.md).

| File | Rows | Window | Role |
|---|---|---|---|
| `VF_export_new.csv` | 8,230 | 11 Mar → **13 May** 2026 (15 prod. days) | **Current** process export. Used by `notebooks/VAC_Forming_Scrap_Analysis_Final.ipynb`. |
| `VF_export_old.csv` | 7,372 | 11 Mar → **6 May** 2026 (14 prod. days) | Previous export. Matches all `FINDINGS.md` headline numbers. Used by `notebooks/EDA.ipynb`. |
| `VF_Scrap_export.csv` | 386 | — (`ScrapTime` to ~6 May) | Scrap labels (`ID, Desc, ScrapTime`). |
| `Book3.xlsx` | — | — | Generation-1 raw source (`Process Data` + `Scrap` sheets). |

## ⚠️ Data-currency caveat (important)

The process export was refreshed on **2026-05-26** (old → new, +1 week of production), but the
**scrap-label file was not refreshed with it.** So the extra week (May 7–13) is essentially
**unlabelled** — consistent with the scrap-detection lag (median ~6 h, max 43 d; some defects found
downstream / at the customer).

**Consequence:** the apparent scrap rate drops from **5.24 %** (386 / 7,372, old) to **≈ 4.69 %**
(386 / 8,230, new) purely because the denominator grew while labelled scrap did not — *not* because
the line improved. Don't quote a single headline rate until this is resolved.

**To resolve:** obtain a refreshed `VF_Scrap_export.csv` covering through 13 May, **or** scope analysis
to the labelled window (≤ 6 May, i.e. use `VF_export_old.csv`). Tracked as R-1 in
[`../docs/PROJECT_LOG.md`](../docs/PROJECT_LOG.md) and Q14 in
[`../docs/OPEN_QUESTIONS.md`](../docs/OPEN_QUESTIONS.md).
