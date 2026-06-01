# Decisions Log

Key methodological and engineering decisions, with the rationale, so they aren't
silently re-litigated. ADR-flavoured but lightweight. The detailed evidence behind
most of these lives in [`FINDINGS.md`](FINDINGS.md); this file is the *why-we-chose-it*
index. Status: **A**ccepted / **S**uperseded.

---

### D-01 · Diagnose tool-conditionally, never pooled — **A**
**Decision.** All scrap-vs-good comparisons are done *within a single tool*; recommendations are
`(tool, defect)`-specific.
**Why.** Tools 1/2/8 run different recipes (different Roller Gap, Stretch, Glue-Temp setpoints) and
different scrap rates. Pooling scrap-vs-good across tools mostly measures *recipe × tool-rate*, not
causal drift — it manufactures spurious "signals". This is the core lesson that separates Generation 2
from Generation 1.
**Consequence.** Generation-1 pooled notebooks were archived. Defects turn out to be tool-locked
anyway (Wrinkle≈T1, Low Glue≈T2, Bumps≈T8), which validates the choice.

### D-02 · Exclude recipe-fixed parameters from causal ranking — **A**
**Decision.** Within each tool, parameters with coefficient of variation < 0.01 are treated as
recipe constants and excluded from the deviation ranking.
**Why.** A parameter that never varies inside a tool cannot explain why one part scrapped and another
didn't. Including them adds noise and false "stable = important" reads.
**Caveat.** If recipes are actually *editable* per part (open question Q10), these become candidates
for *engineering changes* rather than runtime nudges — a different use, not a dead end.

### D-03 · Rank by effect size (Cliff's δ), gated on significance — **A**
**Decision.** Rank deviating parameters by |Cliff's δ| (CRITICAL>0.474, STRONG>0.33, MODERATE>0.20),
only among those passing Welch p<0.05; KS as a shape sanity-check; Wilson CIs for all rates.
**Why.** With small n_bad per `(tool, defect)`, p-values alone reward large n and tiny effects.
Effect size is what an operator can act on. Non-parametric δ avoids normality assumptions on skewed
process parameters.

### D-04 · Describe, don't predict — engine explains scrap, doesn't forecast it — **A**
**Decision.** Ship a *diagnostic* `recommend(...)` engine, not a deployed "scrap predictor", even
though per-defect CV AUCs (0.72–0.89) show a real signal.
**Why.** The line **already detects scrap in-line**. The value is in *explaining* a detected event and
converting it to a corrective action, not re-predicting it. Avoids over-claiming causality from
observational data (deviations are associations, not interventions).

### D-05 · Operating-window count is triage, not a classifier — **A**
**Decision.** The "count of parameters outside [P5,P95]" rule is used only as a tier-1 triage flag.
**Why.** Its holdout AUC is ≈0.55 — deliberately weak. Reported honestly as a *deflationary* test: it
proves a simple threshold rule is insufficient and that the per-defect engine is needed. Don't promote
it to a standalone alarm.

### D-06 · Explicit handling of structural data surprises — **A**
**Decision.** Treat `Machine Cycle Time = 9999` as a stoppage sentinel (mask + `mct_capped` flag);
encode `Pos Vinyl *` as `(value, _active_flag)` due to bimodality; treat `Pyro Clean` as a cycle
counter with a per-tool non-monotonic sweet spot; drop always-constant columns.
**Why.** These columns break naive numeric treatment. See [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).
**Caveat.** Each rests on an assumption that needs operator confirmation (Q1–Q7).

### D-07 · Good parts on the same tool are the baseline — **A**
**Decision.** Reference "good" operating windows come from good parts *on that tool* (P5/P50/P95).
**Why.** Only same-tool good parts represent an achievable target state for that tool.
**Caveat.** Assumes good parts are genuinely acceptable, not marginal-but-passed (assumption A6).

### D-08 · No annualized savings projection — **A**
**Decision.** Do not extrapolate scrap savings to an annual figure.
**Why.** 14–15 production days inside a 56-day span is too bursty, and there's no committed production
volume to annualize against. A number here would be false precision.

### D-09 · Reorganize repo + adopt git + living project log — **A** (2026-06-01)
**Decision.** Impose a `docs/data/notebooks/pipeline/reports/figures` layout, initialise git, and keep
`PROJECT_LOG.md` as the single living source of truth.
**Why.** The flat ~40-file root mixed three generations with no history or status, forcing every
newcomer (human or AI) to re-derive context. See [`../CHANGELOG.md`](../CHANGELOG.md).

### D-10 · EDA notebook stays on old data; Final notebook on new data — **A** (2026-06-01)
**Decision.** During the reorg, repoint `EDA.ipynb` to `VF_export_old.csv` (its original audit data,
keeping its cached outputs honest) while the Final notebook stays on `VF_export_new.csv`.
**Why.** Re-pointing EDA to new data without re-running would make its narrative outputs inconsistent
with the input. This is a *temporary, documented* split — see PROJECT_LOG Next-Steps #2 to converge
both onto one canonical generation once the scrap labels are refreshed.
