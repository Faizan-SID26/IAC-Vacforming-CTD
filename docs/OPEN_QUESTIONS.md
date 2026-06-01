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
| Q1 | **`Pyro Clean`** — exact meaning? Cycles since last pyro clean? Why does Tool 8 *never* reset in 56 days (min = 496)? | The per-tool Pyro-Clean sweet-spot recommendation rests on it being a cycle counter (assumption A9). | 🔴 | Open |
| Q2 | **`Machine Cycle Time = 9999`** — what event? Stop, sensor-not-ready, reset, manual override? Real cycle time during these? | Drives the `mct_capped` / `prev_mct_capped` stoppage-sentinel logic and the "next part at elevated risk" finding (A10). | 🔴 | Open |
| Q3 | **`Pos Vinyl N/S Length/Width` = 0** — feature disabled by recipe, or default-when-unset? | Determines whether the `_active` encoding is correct (A11). | 🟡 | Open |
| Q4 | **`TTF Circuit 2 Temp = 0` everywhere** — sensor removed, feature retired, or always-off config? | Column is dropped as a constant; confirm it's truly dead. | ⚪ | Open |
| Q5 | **`Capacity BHT` capped at 70** (5.4 % of rows) & **`Capacity THT` capped at 85** — hardware ceiling or controller setpoint cap? | Affects how to read "low capacity" under-heating signatures (Bumps on T8). | 🟡 | Open |
| Q6 | **`Top Tool Pos Close`** has only 4 values (12330/12480/12490/12500) — discrete clamp positions? What does each mean? | Could be a categorical recipe knob, not a continuous parameter. | ⚪ | Open |
| Q7 | **`BT Circuit 2 Temp`** — two regimes (most rows 22–28, others 300–833). Different heater modes? | Heavy-tailed; currently kept raw for the model to handle. | ⚪ | Open |

## B · Operations & people

| # | Question | Why it matters | Pri | Status |
|---|---|---|---|---|
| Q8 | **Operator / shift identifiers** — logged anywhere? | Tool 1 morning warm-up and Tool 8 afternoon spike both look like an unseen personnel signal. | 🔴 | Open |
| Q9 | **Warm-up procedure** — is there a standardized one? | First 10–20 parts of a day scrap ≈ 12 % vs ≈ 5 % steady-state — **the single biggest operational lever**. A pre-warm cycle could close it. | 🔴 | Open |
| Q10 | **Recipe configurability** — recipes hard-locked per tool, or editable per part? | If editable, "recipe-fixed" parameters become *engineering-change* candidates, not just runtime nudges (see DECISIONS D-02). | 🟡 | Open |
| Q11 | **Tool 8 absence of Wrinkle / Bad edge wrap** — real (geometry/mechanics) or label coding? | Affects whether T8 recommendations should ever cover those defects. | 🟡 | Open |
| Q12 | **MAP POCKET BEIGE on Tool 1 at 23.1 % scrap** — colorant interaction, geometry, supply-lot, or inspection bias? | A standout part-level rate that may need an engineering, not operator, fix. | 🟡 | Open |
| Q13 | **`Pyro Clean` policy** — scheduled, defect-triggered, or operator judgement? | Needed to act on the sweet-spot finding; Tool 8 not resetting in 56 days is unusual. | 🟡 | Open |
| Q14 | **Scrap detection workflow** — median lag 6 h, max 43 d. Discovered downstream / at customer? | **Directly drives the data-currency blocker (R-1):** recent days' scrap totals are incomplete. | 🔴 | Open |
| Q15 | **Color × family confound** — PS LOWER LHD: BEIGE 15.3 % vs BLACK 4.79 %. Different vinyl source / supplier / inspection visibility? | Determines if "color" is causal or a proxy. | 🟡 | Open |

## C · Modeling

| # | Question | Why it matters | Pri | Status |
|---|---|---|---|---|
| Q16 | **Burnt Carpet AUC = 0.63** — weakest model. Multi-causal, or conflating sub-types? | Would benefit from sub-labelling before the model can improve. | 🟡 | Open |
| Q17 | **Tool 1 Pyro Clean ceiling 495** vs Tool 8 never resetting — different cleaning cadence, counter semantics, or a shared counter? | Tied to Q1/Q13. | ⚪ | Open |

---

### Most-leverage trio to chase first
**Q14 + Q1 + Q9** — Q14 unblocks the data-currency issue that gates *all* headline numbers; Q1
unblocks the Pyro-Clean recommendations; Q9 is the biggest operational scrap-reduction lever.
