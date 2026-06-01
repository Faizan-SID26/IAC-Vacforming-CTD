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

### D-02 · Exclude recipe-fixed parameters from causal ranking — **S** (superseded by D-11, 2026-06-01)
**Decision.** Within each tool, parameters with coefficient of variation < 0.01 are treated as
recipe constants and excluded from the deviation ranking.
**Why.** A parameter that never varies inside a tool cannot explain why one part scrapped and another
didn't. Including them adds noise and false "stable = important" reads.
**Update.** The team confirmed recipes are **editable mid-run** (Q10 resolved). Low-CV params are
still excluded from *per-part* ranking, but they are no longer off-limits — see **D-11**.

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

### D-06 · Explicit handling of structural data surprises — **A** (partially revised 2026-06-01)
**Decision.** Treat `Machine Cycle Time = 9999` as a stoppage sentinel (mask + `mct_capped` flag);
encode `Pos Vinyl *` as `(value, _active_flag)` due to bimodality; treat `Pyro Clean` as a cycle
counter with a per-tool non-monotonic sweet spot; drop always-constant columns.
**Why.** These columns break naive numeric treatment. See [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).
**Update (team review).** MCT sentinel and dropped-constants **stand** — 9999 confirmed as the
recorder's **max-value overflow** (field saturates when the true cycle time exceeds the largest
recordable number; Q2 resolved), so keep masking it as missing. Two encodings revised:
- **Pos Vinyl** zero = *camera blocked by excess material*, not "inactive" → see **D-12**.
- **Pyro Clean** is *not* a clockwork-reset counter; the sweet spot is an artifact → see **D-13**.
See [`MODELING_UPDATES.md`](MODELING_UPDATES.md) U-1/U-2 for evidence.

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

---

> Decisions D-11…D-14 arise from the **2026-06-01 team assumption review**.
> Full rationale + evidence in [`MODELING_UPDATES.md`](MODELING_UPDATES.md).

### D-11 · Recipe-fixed params become an "engineering setpoint" lane, not discarded — **A** (2026-06-01)
**Decision.** Keep low-CV params out of *per-part* deviation ranking, but surface them as
recipe-level engineering levers, and add Δ-from-previous-part features for adjustable params.
**Why.** Team confirmed recipes are editable mid-run and a change affects the next part. Supersedes D-02.

### D-12 · Pos Vinyl zero = camera blocked (excess material); model the flag, band on visible rows — **A** (2026-06-01)
**Decision.** Replace `_active` with `_cam_blocked = (value==0)`; compute Pos Vinyl percentile bands /
deviation stats on camera-visible rows only.
**Why.** A blocked reading isn't position 0; including the zeros dilutes the baseline and inflated the
Wrinkle Pos-Vinyl signal (δ 0.358 → 0.180 on visible-only rows). Revises D-06.

### D-13 · Retire the Pyro-Clean sweet-spot rule — **A** (2026-06-01)
**Decision.** Remove the Pyro-Clean band overlay and `PYRO_CLEAN_DUE`/`WAIT_BEFORE_CLEAN` actions from
the engine; keep Pyro as a feature only, pending Rohit's parameter list (OQ-18).
**Why.** Team says pyro cleaning is not a fixed-clock reset; the sweet spot is unstable on a random
split (artifact). Revises D-06.

### D-14 · Unify cold-start (warm-up + restart) thermally; drop the operator/shift framing — **A** (2026-06-01)
**Decision.** Model `is_cold_start = is_warmup OR is_restart`; add gap/seq features and color×temperature
interactions with beige-specific tight heating windows. Do not model shift/operator identity.
**Why.** Team confirmed spikes are lunch cool-down/restart (same operators) and the warm-up effect is
weather-driven thermal; beige is a thermodynamic-balance problem. Evidence: cold-start 13.5 % vs 5.0 %
(p=2.5e-7); beige 8.7 % vs black 4.1 %.
