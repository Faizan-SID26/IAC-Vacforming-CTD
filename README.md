# VAC Forming — Scrap Reduction Analysis & Recommendation System

**Client / context:** IAC + Algo8 AI · Vacuum-forming line scrap reduction
**Goal:** Explain *why* parts are scrapped on the VAC forming line and convert that into
operator-actionable, `(tool, defect)`-specific corrective recommendations.
**Status:** Analysis complete on the May-2026 data refresh. See [`docs/PROJECT_LOG.md`](docs/PROJECT_LOG.md) for the live status and next steps.

---

## TL;DR — what this project concluded

- **Scrap is tool-locked.** Wrinkle ≈ Tool 1, Low Glue ≈ Tool 2, Bumps ≈ Tool 8. Every recommendation must be `(tool, defect)`-specific, never global.
- **Tool-conditional diagnosis works.** Per-`(tool, defect)` discriminative models reach **AUC 0.72–0.89**; a simple operating-window rule alone is too weak (AUC ≈ 0.55) to be a classifier — it is a triage signal only.
- **Three big operational levers:** a morning **warm-up effect** (first ~10 parts of a day scrap ≈ 12 % vs ≈ 5 % steady-state), per-tool **Pyro-Clean sweet spots** (non-monotonic), and a `Machine Cycle Time = 9999` **stoppage sentinel** that elevates the next part's risk.
- **17 open process questions** remain for the operator / engineering team to close the loop (see [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md)).

The full, citable analysis write-up is [`docs/FINDINGS.md`](docs/FINDINGS.md).

---

## Repository map

| Path | What's in it |
|---|---|
| **[`README.md`](README.md)** | You are here — entry point & navigation. |
| **[`CHANGELOG.md`](CHANGELOG.md)** | Dated history of every wave of work. Read this to see *how* the project evolved. |
| **[`docs/`](docs/)** | All project documentation (see below). |
| **[`data/`](data/)** | Raw data exports + provenance notes ([`data/README.md`](data/README.md)). |
| **[`notebooks/`](notebooks/)** | The two **active** analysis notebooks. Superseded ones are in `notebooks/archive/`. |
| **[`pipeline/`](pipeline/)** | Reproducible Python pipeline (profiling → EDA → hypotheses → models) + intermediate artefacts. Generated the notebooks & reports. |
| **[`reports/`](reports/)** | Deliverables: operator Excel report, Word report, operating-windows CSV. Superseded ones in `reports/archive/`. |
| **[`figures/`](figures/)** | Static plot exports (from the first-generation analysis). |

### `docs/` contents

| Doc | Purpose |
|---|---|
| [`PROJECT_LOG.md`](docs/PROJECT_LOG.md) | **Living development journal** — current status, latest direction, next steps, and a dated log of decisions. Update this as work continues. |
| [`FINDINGS.md`](docs/FINDINGS.md) | The consolidated analysis report (methodology, hypotheses, findings, validation, assumptions). |
| [`DECISIONS.md`](docs/DECISIONS.md) | Key methodological decisions and *why* they were made (so they aren't re-litigated). |
| [`DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) | The 40 process parameters, sentinels, encodings, and defect taxonomy. |
| [`OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) | The 17 open process/engineering questions blocking deeper conclusions. |
| `Process_VAC_Forming.vsdx` | Visio diagram of the physical forming process. |

---

## The two active notebooks

Run order doesn't matter (they're independent), but conceptually: **audit → diagnose**.

1. **[`notebooks/EDA.ipynb`](notebooks/EDA.ipynb)** — exploratory audit: schema, sentinels, time coverage, recipe-vs-drift, tool/part/color structure, Pyro-Clean counter behaviour. *Currently points at `data/VF_export_old.csv` — the data it was originally run against.*
2. **[`notebooks/VAC_Forming_Scrap_Analysis_Final.ipynb`](notebooks/VAC_Forming_Scrap_Analysis_Final.ipynb)** — diagnosis, per-`(tool, defect)` modelling, the live `recommend(...)` engine, validation, and report export. *Points at the current `data/VF_export_new.csv`.*

> ⚠️ **Data-currency caveat:** the two notebooks read **different** data generations (old vs new). This is deliberate and documented — see [`CHANGELOG.md`](CHANGELOG.md) and [`data/README.md`](data/README.md). The scrap-label file did **not** grow with the new process data, so headline rates differ between the docs (5.24 % on old data) and a fresh Final run (≈ 4.69 % on new data). Resolve before quoting a single number externally.

### Running

```bash
# from the repo root
jupyter lab            # then open notebooks/...
```
Kernel used during development: **`py311-vacforming`** (Python 3.11 · pandas, numpy, scipy, scikit-learn, seaborn, openpyxl). Paths inside the notebooks are relative to the `notebooks/` folder (`../data/...`, `../reports/...`).

---

## Where to go next

Start with **[`docs/PROJECT_LOG.md`](docs/PROJECT_LOG.md) → "Current status" and "Next steps."** It is the single source of truth for what is done, what is in-flight, and what to pick up.
