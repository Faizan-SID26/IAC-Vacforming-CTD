# Modeling Updates — incorporating the team's assumption review

**Trigger:** On 2026-06-01 the operations/engineering team reviewed our data-science assumptions
(see `FINDINGS.md` §10) and returned confirmations + corrections + process insights.
This document translates each answer into a **concrete modeling change**, backed by an evidence
check against the labeled data, and defines the **validation plan** for the next data drop.

- Reproducible evidence: [`../pipeline/20_assumption_update_checks.py`](../pipeline/20_assumption_update_checks.py) (run from repo root).
- Evidence uses `data/VF_export_old.csv` (the fully-labeled window → 6 May) to avoid the unlabeled-week denominator issue (R-1).
- Decision records updated: `DECISIONS.md` D-02 (superseded), D-06 (revised), D-11…D-14 (new).

---

## 1. Confirmed assumptions → lock them in (no code change, raise confidence)

| Our assumption | Team verdict | Effect on modeling |
|---|---|---|
| A2 `ID` uniquely identifies a part | ✅ Confirmed | Join is sound; keep. |
| A3 `BuiltTime` is the real production time (from printed labels) | ✅ Confirmed | **Warm-up / cold-start timing analysis is valid** — it depends on this. |
| A4 `ScrapTime` = QC detection time | ✅ Confirmed | Explains detection lag; reinforces R-1 (recent days under-labelled). |
| A6 Good parts are a valid baseline | ✅ Confirmed | Per-tool good-part operating windows stand. |
| A7 P5–P95 outlier targeting | ✅ Confirmed/accepted | Keep the band rule as the recommendation target. |
| A8 Scrap `Desc` labels are accurate | ✅ Confirmed | Defect-specific models stand; no relabelling needed. |

**Action:** mark these "Confirmed by team 2026-06-01" in `FINDINGS.md` §10; they move from
*assumption* to *validated premise*.

---

## 2. Corrections that change the model

### U-1 · Pos Vinyl zeros = **camera blocked by excess material**, not "feature inactive" 🔴
**Team:** a zero does not mean the feature is off — the camera view was *physically blocked by
excess material*.

**What we did before:** encoded `Pos Vinyl *_active = (value > 0)` and otherwise treated the raw
value (including 0) as a numeric position in deviation tests.

**Why that's wrong now:** a blocked reading is `0`, but the part's true vinyl position is *not* zero —
the 0 is a missing/over-material state. Feeding 0 into a numeric comparison **dilutes the baseline**.

**Evidence (CHECK 1 / 1b):**
- Camera-blocked rows scrap *less*, not more: **3.99 % vs 8.07 %** (χ² p = 6.5e-13) — so "excess
  material → defect" is too naive; blocked is largely a benign part/recipe state. Direction must be
  learned, not assumed.
- The headline Wrinkle signal is partly an artifact: Pos Vinyl S Width (Wrinkle vs good, Tool 1)
  **δ = 0.358 "STRONG" on all rows → δ = 0.180 (below MODERATE) on camera-visible rows only.**
  ~481 good rows had value 0 and were diluting the good distribution.

**Modeling change:**
1. Replace the `_active` flag with an explicit **`{param}_cam_blocked = (value == 0)`** feature (same
   bit, correct *meaning*; keep it as a model input — it carries part/recipe signal).
2. In **deviation tables / operating windows for Pos Vinyl params, use camera-visible rows only**
   (`value > 0`); never compute a percentile band over the zeros.
3. **Re-rank the Wrinkle and Bad-edge-wrap signatures** under this rule — expect Pos Vinyl to drop in
   importance and the genuinely thermal/roller signals to rise.

### U-2 · Pyro Clean is **not** a clockwork 56-day/8-week reset → drop the sweet-spot rule 🔴
**Team:** the machine does not reset pyro cleaning on a fixed clock; the counter-like pattern is a
data artifact. **Rohit will provide the parameter list to trace why.**

**Evidence (CHECK 4):** the "lowest-scrap Pyro octile" is **unstable on a random 50/50 split for all
three tools** (different band each half) — i.e. the sweet spot is over-fit noise, not a real window.

**Modeling change:**
1. **Remove the Pyro-Clean sweet-spot overlay from the engine** (`recommend(...)` Pyro block and the
   `PYRO_SWEET` table). It currently emits `WAIT_BEFORE_CLEAN` / `PYRO_CLEAN_DUE` — retire these.
2. Keep `Pyro Clean` as a raw model feature only (no prescriptive rule) **pending Rohit's parameter
   list** (tracked as new open item OQ-18).
3. Add a banner to the v2 report's `4_Pyro_Clean_bands` sheet that it is **deprecated/under review**.

### U-3 · Recipes are **adjustable mid-run** and affect the next part → recipe-fixed ≠ off-limits 🟡
**Team:** tool recipes are not hard-locked; operators can change parameters mid-run and the change
shows on the *immediately next* part.

**What we did before (D-02):** excluded within-tool low-CV ("recipe-fixed") parameters from causal
ranking.

**Modeling change:**
1. **Keep** low-CV params out of the *per-part deviation* ranking (they barely vary, so they can't
   explain part-to-part scrap) **but** surface them in a separate **"engineering setpoint" lane** of
   the recommendation output — they are now *legitimate levers*, just at recipe granularity, not
   per-part. (D-02 superseded by D-11.)
2. Add **lag-1 / Δ-from-previous-part features** for the adjustable parameters
   (`{param}_delta = value − value_prev_same_tool`) to exploit the "change affects next part"
   dynamic. Useful both as model features and to *attribute* a good/bad next part to an adjustment.

---

## 3. Process insights → the unifying mechanism is **thermal stability**

The team's operational answers all point to one root cause. Treat them as one feature family.

### U-4 · Cold-start (warm-up **and** post-break restart) is thermal, weather-dependent 🔴
**Team:** warm-up scrap (12 %) vs steady (5 %) is **weather/temperature dependent**; operators use
*unstandardized* methods (e.g. leaving heating bulbs on longer when cold). Morning/afternoon spikes
are **lunch-break cool-down/restart cycles, not operator variation** (same operators throughout).

**Evidence (CHECK 2):** unified cold-start (first-10-of-day **or** first part after a >25-min gap)
= **13.5 % vs 5.0 %** warm (χ² p = 2.5e-7). Morning warm-up dominates in this window; intra-day
gaps are rarer but elevated where present.

**Modeling change:**
1. Replace the lone `is_warmup` with a **`is_cold_start`** feature = `is_warmup OR is_restart`, where
   `is_restart = (intra-day gap to previous part on tool > ~25 min) AND (seq_in_day ≥ 5)`. Add
   `mins_since_prev_on_tool` and `seq_in_day` as continuous features.
2. **Drop the "operator/shift" framing** — there is no personnel signal; do not model shift identity.
3. Recommendation output gains a **cold-start advisory**: when a part is in a cold-start window,
   prioritise heating-readiness (THT/BHT/zone temps at setpoint) and flag that a *standardised*
   warm-up (pre-warm cycle / sacrificial parts / weather-aware bulb timing) is the systemic fix.
4. If/when an **ambient-temperature or weather** field is available, add it; the warm-up effect is
   explicitly weather-driven (OQ-19).

### U-5 · Beige = delicate thermodynamic balance → color×temperature, tighter beige windows 🟡
**Team:** beige is hardest (white reflects heat, black absorbs; beige sits in between). The Tool-1
beige scrap is tied to **temperature / inspection bias**, not geometry.

**Evidence (CHECK 3):** beige **8.67 %** vs black 4.14 % vs white 5.32 %; Tool-1 beige **9.95 %** vs
white 2.26 %. Beige runs *cooler and more variable* on the top-heater trigger (THT mean 156.8 sd 12.7
vs black 162.6 sd 9.6) — consistent with a harder-to-hold thermal setpoint.

**Modeling change:**
1. Keep `color` as a feature and add **`color × heating-parameter` interactions** (THT/BHT/zone temps)
   for the heat-driven defects (Wrinkle, Bumps, Low Glue, Burnt Carpet).
2. Compute **color-conditioned operating windows for beige** on heating params (tighter than the
   pooled tool window) and let the engine apply the beige-specific band when `color == BEIGE`.
3. Frame beige recommendations as *temperature-stability* actions, not geometry.

### U-6 · Tool 8 is not immune to Wrinkle/Bad-edge-wrap — it's a volume (RHD IP) effect ⚪
**Team:** the absence on Tool 8 is low production volume (right-hand-drive IP), not immunity.

**Modeling change:** do not hard-exclude those defects from Tool 8. Where Tool-8 n_bad is too small to
fit a model, **fall back to the cross-tool signature** for that defect rather than returning "no
characterized signal". Note the small-sample caveat in the output.

---

## 4. Net change summary (engine before → after)

| Component | Before | After |
|---|---|---|
| Pos Vinyl encoding | `_active = value>0`; raw 0 used in stats | `_cam_blocked = value==0` feature; bands/devs on **visible rows only** |
| Pyro Clean | sweet-spot band rule + `PYRO_CLEAN_DUE` actions | **removed** (feature-only, under review) |
| Warm-up | `is_warmup` (first 20) | `is_cold_start` = warm-up **or** post-break restart; +gap/seq features |
| Shift/operator | hypothesised personnel signal | **dropped** (confirmed thermal restart, not people) |
| Recipe-fixed params | excluded entirely | excluded from per-part rank, **surfaced as engineering setpoints**; +Δ-from-prev features |
| Color | plain categorical | **color×temperature interactions** + beige-specific tight windows |
| Tool 8 rare defects | "no signal" | cross-tool fallback signature + small-sample caveat |

---

## 5. Validation plan for the incoming data (May 14 → ~28)

The team will share ~2 weeks of new data (from 14 May) to **test how well the recommendations hold**
and to **issue recommendations for that period**. Protocol:

1. **Freeze the engine** on the labeled training window (≤ 6 May, `VF_export_old.csv`) with the
   updated approach above — no peeking at the test fortnight.
2. **Confirm the new data is labeled** for 14–28 May (this is the gap that caused R-1). If scrap
   labels are present, this becomes a true out-of-time holdout; if not, we can only *issue* (not
   *score*) recommendations.
3. **Score:** for each scrapped part in the holdout, run `recommend(defect, tool, params)` and check
   whether the flagged parameters were genuinely out-of-window → precision/recall of the actions;
   for good parts, measure the false-fire rate. Report per-(tool, defect).
4. **Backtest the operational levers:** cold-start rate, beige rate, and (de-scoped) Pyro behaviour
   on the new fortnight vs the training window — did they move?
5. **Deliver:** a short "May 14–28 recommendations + how-we-did" report; append results to
   `PROJECT_LOG.md` and, if material, a v3 of the Excel report.

**Definition of done for Phase 1 (this doc):** updated approach specified + evidence-checked.
**Phase 2 (on data arrival):** implement U-1…U-6 in the notebook/engine, run the holdout protocol.

---

## 6. New open questions raised

| ID | Question | Owner |
|---|---|---|
| OQ-18 | The parameter list to trace the Pyro-Clean counter artifact. | Rohit |
| OQ-19 | Is ambient temperature / weather logged anywhere? (warm-up is weather-driven) | Ops |
| OQ-20 | Is the May 14–28 export scrap-labeled, or process-only? (gates scoring vs issuing) | Data |
