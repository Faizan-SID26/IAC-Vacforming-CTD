# Open Questions

Questions that **gate deeper or more confident conclusions** and need the operator /
maintenance / engineering team to answer — they can't be resolved from the data alone.
Extracted and prioritized from `FINDINGS.md` §11. Update the **Status** column as answers
come in, and log resolutions in [`PROJECT_LOG.md`](PROJECT_LOG.md).

**Priority key:** 🔴 high (blocks a current finding or the biggest lever) · 🟡 medium · ⚪ nice-to-have.

---

## A · Sensor / data semantics

| # | Question | Why it matters | Pri | Status |
|---|---|---|---|---|
| Q1 | **`Pyro Clean`** — exact meaning? Cycles since last pyro clean? Why does Tool 8 *never* reset in 56 days (min = 496)? | The per-tool Pyro-Clean sweet-spot recommendation rests on it being a cycle counter (assumption A9). | 🔴 | ✅ **Resolved (2026-06-01):** NOT a fixed-clock reset; sweet spot is an artifact → rule retired (D-13). Counter trace pending → **OQ-18 (Rohit)**. |
| Q2 | **`Machine Cycle Time = 9999`** — what event? Stop, sensor-not-ready, reset, manual override? Real cycle time during these? | Drives the `mct_capped` / `prev_mct_capped` stoppage-sentinel logic and the "next part at elevated risk" finding (A10). | 🔴 | Open |
| Q3 | **`Pos Vinyl N/S Length/Width` = 0** — feature disabled by recipe, or default-when-unset? | Determines whether the `_active` encoding is correct (A11). | 🟡 | ✅ **Resolved (2026-06-01):** zero = **camera physically blocked by excess material**. Re-encode as `_cam_blocked`; band on visible rows (D-12, MODELING_UPDATES U-1). |
| Q4 | **`TTF Circuit 2 Temp = 0` everywhere** — sensor removed, feature retired, or always-off config? | Column is dropped as a constant; confirm it's truly dead. | ⚪ | Open |
| Q5 | **`Capacity BHT` capped at 70** (5.4 % of rows) & **`Capacity THT` capped at 85** — hardware ceiling or controller setpoint cap? | Affects how to read "low capacity" under-heating signatures (Bumps on T8). | 🟡 | Open |
| Q6 | **`Top Tool Pos Close`** has only 4 values (12330/12480/12490/12500) — discrete clamp positions? What does each mean? | Could be a categorical recipe knob, not a continuous parameter. | ⚪ | Open |
| Q7 | **`BT Circuit 2 Temp`** — two regimes (most rows 22–28, others 300–833). Different heater modes? | Heavy-tailed; currently kept raw for the model to handle. | ⚪ | Open |

## B · Operations & people

| # | Question | Why it matters | Pri | Status |
|---|---|---|---|---|
| Q8 | **Operator / shift identifiers** — logged anywhere? | Tool 1 morning warm-up and Tool 8 afternoon spike both look like an unseen personnel signal. | 🔴 | ✅ **Resolved (2026-06-01):** NOT personnel — spikes are **lunch cool-down / restart** cycles; same operators throughout. Drop shift framing; model as thermal cold-start (D-14). |
| Q9 | **Warm-up procedure** — is there a standardized one? | First 10–20 parts of a day scrap ≈ 12 % vs ≈ 5 % steady-state — **the single biggest operational lever**. A pre-warm cycle could close it. | 🔴 | ✅ **Resolved (2026-06-01):** **No standard** — operators ad-hoc (e.g. bulbs on longer when cold); effect is **weather-dependent**. Recommend standardizing; add weather field (OQ-19). |
| Q10 | **Recipe configurability** — recipes hard-locked per tool, or editable per part? | If editable, "recipe-fixed" parameters become *engineering-change* candidates, not just runtime nudges (see DECISIONS D-02). | 🟡 | ✅ **Resolved (2026-06-01):** **Editable mid-run**; a change affects the *immediate next part*. Surface recipe params as engineering levers; add Δ-from-prev features (D-11). |
| Q11 | **Tool 8 absence of Wrinkle / Bad edge wrap** — real (geometry/mechanics) or label coding? | Affects whether T8 recommendations should ever cover those defects. | 🟡 | ✅ **Resolved (2026-06-01):** **Low production volume (RHD IP)**, not immunity. Don't hard-exclude; cross-tool fallback for T8 (U-6). |
| Q12 | **MAP POCKET BEIGE on Tool 1 at 23.1 % scrap** — colorant interaction, geometry, supply-lot, or inspection bias? | A standout part-level rate that may need an engineering, not operator, fix. | 🟡 | ✅ **Resolved (2026-06-01):** **Temperature / inspection bias**, not geometry (beige thermodynamics). Tighten beige temp windows (D-14, U-5). |
| Q13 | **`Pyro Clean` policy** — scheduled, defect-triggered, or operator judgement? | Needed to act on the sweet-spot finding; Tool 8 not resetting in 56 days is unusual. | 🟡 | ✅ **Resolved (2026-06-01):** not a fixed-clock schedule (see Q1). Sweet-spot rule retired pending OQ-18. |
| Q14 | **Scrap detection workflow** — median lag 6 h, max 43 d. Discovered downstream / at customer? | **Directly drives the data-currency blocker (R-1):** recent days' scrap totals are incomplete. | 🔴 | ◐ **Partially (2026-06-01):** lag confirmed (A4 ✅). Still gates R-1 — need to know if the May 14–28 export is labeled (**OQ-20**). |
| Q15 | **Color × family confound** — PS LOWER LHD: BEIGE 15.3 % vs BLACK 4.79 %. Different vinyl source / supplier / inspection visibility? | Determines if "color" is causal or a proxy. | 🟡 | ✅ **Resolved (2026-06-01):** beige is a real **thermodynamic-balance** difficulty (white reflects / black absorbs). Add color×temp interactions (D-14, U-5). |

## C · Modeling

| # | Question | Why it matters | Pri | Status |
|---|---|---|---|---|
| Q16 | **Burnt Carpet AUC = 0.63** — weakest model. Multi-causal, or conflating sub-types? | Would benefit from sub-labelling before the model can improve. | 🟡 | Open |
| Q17 | **Tool 1 Pyro Clean ceiling 495** vs Tool 8 never resetting — different cleaning cadence, counter semantics, or a shared counter? | Tied to Q1/Q13. | ⚪ | ◐ Folded into **OQ-18** (Pyro artifact trace). |

## D · New questions from the 2026-06-01 team review

| # | Question | Why it matters | Pri | Owner |
|---|---|---|---|---|
| OQ-18 | The **parameter list to trace the Pyro-Clean counter artifact** — why does the data look like a clockwork counter when cleaning isn't on a fixed clock? | Needed before any Pyro-based recommendation can return. | 🔴 | Rohit |
| OQ-19 | Is **ambient temperature / weather** logged anywhere we can join? | The warm-up effect is explicitly weather-driven; a weather feature would sharpen the cold-start model. | 🟡 | Ops |
| OQ-20 | Is the **May 14–28 export scrap-labeled**, or process-only? | Gates whether we can *score* the holdout (validate) or only *issue* recommendations. | 🔴 | Data |

---

### What's resolved vs still open (post-review)
- ✅ **Resolved by the team:** Q3, Q8, Q9, Q10, Q11, Q12, Q15, and Q1/Q13/Q17 (Pyro, pending the OQ-18 trace).
- ◐ **Partial:** Q14 (lag confirmed; labeling of the new export = OQ-20).
- ⬜ **Still open:** Q2 (MCT=9999 event), Q4–Q7 (sensor semantics), Q5 (capacity caps), Q16 (Burnt Carpet sub-typing), plus new **OQ-18/19/20**.

### Most-leverage to chase next
**OQ-20 + OQ-18 + Q2** — OQ-20 decides if the incoming fortnight is a true validation set; OQ-18
unblocks any Pyro recommendation; Q2 still underpins the stoppage-sentinel logic.
