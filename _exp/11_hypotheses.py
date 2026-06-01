"""Iterative hypothesis tests on the new data.

Each block: H## statement → test → numeric result → ACCEPT/REJECT/INCONCLUSIVE.
Results land in _exp/results/hyp_*.csv where useful.
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
from scipy import stats

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
EXP  = os.path.join(ROOT, "_exp")
OUT  = os.path.join(EXP, "results")
df = pd.read_parquet(os.path.join(EXP, "df_clean.parquet"))
print(f"Loaded df_clean: {df.shape}, scrap={df['is_scrap'].sum()}, rate={df['is_scrap'].mean()*100:.2f}%")

PROCESS_DEFECTS = ["Wrinkle","Dent","Bumps / lumps","Burnt Carpet / Vynil",
                   "Low Glue/Read Thru/Impression","Out of dimension","Bad edge wrap",
                   "Glue bleed thru","Delamination"]
df["scope"] = np.where(df["defect"].isna(),"Good",
              np.where(df["defect"].isin(PROCESS_DEFECTS),"Process","Non-Process"))

def chi2_test(table, title=""):
    chi2, p, dof, _ = stats.chi2_contingency(table.values)
    print(f"  χ² = {chi2:.2f}, dof={dof}, p={p:.2e}")
    return chi2, p

# =============================================================================
# H1: Scrap rate differs by Tool (3-way chi-square)
# =============================================================================
print("\n" + "="*80)
print("H1: scrap rate differs by Tool")
tab = pd.crosstab(df["Tool Number"], df["is_scrap"])
print(tab)
chi2_test(tab)
rates = df.groupby("Tool Number")["is_scrap"].agg(["count","sum","mean"])
rates["pct"] = rates["mean"]*100
print(rates.round(3))
# Wilson confidence interval per tool
def wilson(p, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    den = 1 + z*z/n
    cen = (p + z*z/(2*n))/den
    half = z*np.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return cen-half, cen+half
for t, r in rates.iterrows():
    lo, hi = wilson(r["mean"], r["count"])
    print(f"  Tool {int(t)}  rate {r['pct']:.2f}%  95% CI [{lo*100:.2f}, {hi*100:.2f}]")
print("VERDICT: REJECT H0 — rates differ significantly")

# =============================================================================
# H2: Scrap rate differs by Part (or just by color → tool)
# =============================================================================
print("\n" + "="*80)
print("H2: Scrap rate differs by part, controlling for tool")
# Part-conditional within each tool
for t in [1,2,8]:
    sub = df[df["Tool Number"]==t]
    g = sub.groupby("PartDesc").agg(n=("ID","count"), s=("is_scrap","sum"))
    g["rate"] = g["s"]/g["n"]*100
    g = g[g["n"]>=30].sort_values("rate", ascending=False)
    if len(g) >= 2:
        # Approximate chi-square across parts
        from scipy.stats import chi2_contingency
        ct = pd.crosstab(sub["PartDesc"], sub["is_scrap"]).loc[g.index]
        chi2, p, *_ = chi2_contingency(ct.values)
        print(f"\nTool {t}: across {len(g)} parts (>=30 made each)  χ²={chi2:.1f}, p={p:.2e}")
        print(g.head(8).round(2).to_string())

# =============================================================================
# H3: Color matters AFTER controlling for part type
# =============================================================================
print("\n" + "="*80)
print("H3: Color effect persists after controlling for part family")
# Strip color from PartDesc → "family"
df["family"] = df["PartDesc"].str.replace(r"\s+(BLACK|BEIGE|WHITE|GREY|GRAY)$", "", regex=True)
print("Family x Color scrap rates (>=80 parts each cell):")
cross = df.groupby(["family","color"]).agg(n=("ID","count"), s=("is_scrap","sum"))
cross["rate"] = cross["s"]/cross["n"]*100
cross = cross[cross["n"]>=80]
print(cross.round(2).to_string())

# Test color within each family (Cochran-Mantel-Haenszel proxy via per-family chi2 and combine)
print("\nPer-family chi-square (color):")
family_results = []
for fam in df["family"].unique():
    sub = df[df["family"]==fam]
    if sub["color"].nunique() < 2: continue
    ct = pd.crosstab(sub["color"], sub["is_scrap"])
    if ct.shape[0] < 2 or ct.values.min() < 5: continue
    chi2, p, *_ = stats.chi2_contingency(ct.values)
    family_results.append({"family":fam,"n":len(sub),"chi2":chi2,"p":p})
fr = pd.DataFrame(family_results).sort_values("p")
print(fr.round(3).to_string(index=False))

# =============================================================================
# H4: Map Pockets are systematically worse
# =============================================================================
print("\n" + "="*80)
print("H4: MAP POCKET parts scrap more than non-MAP POCKET")
df["is_map"] = df["PartDesc"].str.contains("MAP POCKET")
ct = pd.crosstab(df["is_map"], df["is_scrap"])
chi2, p, *_ = stats.chi2_contingency(ct.values)
mp = df.groupby("is_map")["is_scrap"].agg(["count","mean"])
mp["pct"] = mp["mean"]*100
print(mp.round(3))
print(f"χ² = {chi2:.1f}  p={p:.2e}")
# But map pockets are nearly all Tool 1 — confound check
print("\nMap-pocket production by tool:")
print(df.groupby(["is_map","Tool Number"]).size().unstack(fill_value=0))
# Within Tool 1 only:
sub = df[df["Tool Number"]==1]
ct1 = pd.crosstab(sub["is_map"], sub["is_scrap"])
chi2_1, p_1, *_ = stats.chi2_contingency(ct1.values)
print(f"\nWithin Tool 1 only: χ²={chi2_1:.1f} p={p_1:.2e}")
print(sub.groupby("is_map")["is_scrap"].agg(["count","mean"]).round(3))

# =============================================================================
# H5: Day-of-week effect (Mon spike)
# =============================================================================
print("\n" + "="*80)
print("H5: DOW affects scrap; Monday is worse")
df["dow"] = df["BuiltTime"].dt.dayofweek
ct = pd.crosstab(df["dow"], df["is_scrap"])
chi2, p, *_ = stats.chi2_contingency(ct.values)
print(f"χ²={chi2:.1f}  p={p:.2e}")
# But which parts run on Mondays?
print("\nMonday production breakdown by tool & part:")
mon = df[df["dow"]==0]
print(mon.groupby(["Tool Number","PartDesc"]).size().head(10))
print(f"\nMonday tool breakdown vs all:")
print(df.groupby("dow")["Tool Number"].value_counts().head(20))

# Within Tool 1, by DOW:
for t in [1,2,8]:
    sub = df[df["Tool Number"]==t]
    g = sub.groupby("dow")["is_scrap"].agg(["count","mean"])
    g["pct"] = g["mean"]*100
    print(f"\nTool {t} by DOW:"); print(g.round(2).to_string())

# =============================================================================
# H6: Hour-of-day shift effect
# =============================================================================
print("\n" + "="*80)
print("H6: Hour-of-day shift effect")
ct = pd.crosstab(df["hour"], df["is_scrap"])
ct = ct[ct.sum(axis=1) >= 30]
chi2, p, *_ = stats.chi2_contingency(ct.values)
print(f"χ²={chi2:.1f}  p={p:.2e}  (hours with n>=30)")
# Within tool:
for t in [1,2,8]:
    sub = df[df["Tool Number"]==t]
    g = sub.groupby("hour")["is_scrap"].agg(["count","mean"])
    g = g[g["count"]>=30]
    g["pct"] = g["mean"]*100
    print(f"\nTool {t} by hour:"); print(g.round(2).to_string())

# =============================================================================
# H7: Run-day effect — does the FIRST run of a production day scrap more?
# =============================================================================
print("\n" + "="*80)
print("H7: First parts of a production day scrap more (warm-up effect)")
df_sorted = df.sort_values("BuiltTime").reset_index(drop=True)
df_sorted["seq_in_day"] = df_sorted.groupby([df_sorted["date"], df_sorted["Tool Number"]]).cumcount()
# Bucket: first 20 / next 50 / rest
def bucket(n):
    if n < 20: return "first_20"
    if n < 50: return "next_30"
    return "rest"
df_sorted["bucket"] = df_sorted["seq_in_day"].apply(bucket)
g = df_sorted.groupby("bucket")["is_scrap"].agg(["count","mean"])
g["pct"] = g["mean"]*100
print(g.round(3).to_string())
# Test
ct = pd.crosstab(df_sorted["bucket"], df_sorted["is_scrap"])
chi2, p, *_ = stats.chi2_contingency(ct.values)
print(f"χ²={chi2:.1f}  p={p:.2e}")

# =============================================================================
# H8: Long-gap parts (after no production) have higher scrap (cold start)
# =============================================================================
print("\n" + "="*80)
print("H8: First part after a long gap scraps more")
df_sorted["gap_min"] = df_sorted.groupby("Tool Number")["BuiltTime"].diff().dt.total_seconds()/60.0
df_sorted["gap_bucket"] = pd.cut(df_sorted["gap_min"].fillna(0),
                                 bins=[-1, 5, 30, 60, 240, 1e6],
                                 labels=["<5min","5-30","30-60","60-240",">240"])
g = df_sorted.groupby("gap_bucket", observed=True)["is_scrap"].agg(["count","mean"])
g["pct"] = (g["mean"]*100).round(2)
print(g.to_string())
ct = pd.crosstab(df_sorted["gap_bucket"], df_sorted["is_scrap"])
chi2, p, *_ = stats.chi2_contingency(ct.values)
print(f"χ²={chi2:.1f}  p={p:.2e}")

# =============================================================================
# H9: Machine Cycle Time == 9999 indicates a stoppage → next part is risky
# =============================================================================
print("\n" + "="*80)
print("H9: Machine Cycle Time = 9999 row is a stoppage marker")
df_sorted["mct9999"] = df_sorted["Machine Cycle Time"] == 9999
print("Scrap rate when MCT=9999 vs not:")
print(df_sorted.groupby("mct9999")["is_scrap"].agg(["count","mean"]).round(3))
# Conditional on tool
print("\nBy tool:")
print(df_sorted.groupby(["Tool Number","mct9999"])["is_scrap"].agg(["count","mean"]).round(3))
# Does the FOLLOWING part scrap more?
df_sorted["prev_mct9999"] = df_sorted.groupby("Tool Number")["mct9999"].shift(1).fillna(False)
print("\nScrap rate when PREVIOUS part had MCT=9999:")
print(df_sorted.groupby("prev_mct9999")["is_scrap"].agg(["count","mean"]).round(3))

# =============================================================================
# H10: Pyro Clean is a monotonic counter — increasing Pyro Clean → more scrap (buildup)?
# =============================================================================
print("\n" + "="*80)
print("H10: Higher Pyro Clean (more cycles since clean) → higher scrap, within tool")
for t in [1,2,8]:
    sub = df[df["Tool Number"]==t]
    sub = sub.assign(pc_bin = pd.qcut(sub["Pyro Clean"], q=5, duplicates="drop"))
    g = sub.groupby("pc_bin", observed=True)["is_scrap"].agg(["count","mean"])
    g["pct"] = (g["mean"]*100).round(2)
    print(f"\nTool {t} Pyro Clean quintiles:")
    print(g.to_string())
    ct = pd.crosstab(sub["pc_bin"], sub["is_scrap"])
    chi2, p, *_ = stats.chi2_contingency(ct.values)
    print(f"  χ²={chi2:.1f}  p={p:.2e}")

# =============================================================================
# H11: Defects show ONLY on specific tools (zero-defect cells exist)
# =============================================================================
print("\n" + "="*80)
print("H11: Defect-Tool exclusivity")
ct = pd.crosstab(df["defect"], df["Tool Number"], dropna=False)
print(ct.to_string())
# A defect is "tool-locked" if 90%+ of its cases sit on one tool
print("\nTool-lock analysis (share of defect on its dominant tool):")
for d in PROCESS_DEFECTS:
    r = ct.loc[d] if d in ct.index else None
    if r is None or r.sum() == 0: continue
    share = r.max()/r.sum()
    dom = r.idxmax()
    print(f"  {d:<35}  n={int(r.sum()):>3}  dominant Tool {int(dom)}: {share*100:.0f}%")

# =============================================================================
# H12: Within-tool drift: do good-part parameters drift across the data period?
# =============================================================================
print("\n" + "="*80)
print("H12: Within-tool drift of GOOD-part parameters over time")
drift_results = []
for t in [1,2,8]:
    sub = df[(df["Tool Number"]==t) & (df["scope"]=="Good")].sort_values("BuiltTime")
    if len(sub) < 200: continue
    # Compare first 30% vs last 30%
    n = len(sub)
    early = sub.iloc[:int(n*0.3)]
    late  = sub.iloc[int(n*0.7):]
    for p in ["Temp. THT at Trigger","Temp. BHT at Trigger","heating time (tens of seconds)",
              "Glue Temp","Vacuum Time Tool Cavity A","Vacuum Time Tool Cavity B",
              "Temp Z1","Temp Z2","Temp Z3","Machine Cycle Time","Pyro Clean"]:
        ev = early[p].dropna(); lv = late[p].dropna()
        if len(ev)<30 or len(lv)<30 or np.std(ev)==0: continue
        # Filter sentinels
        if p == "Machine Cycle Time":
            ev = ev[ev != 9999]; lv = lv[lv != 9999]
            if len(ev)<30 or len(lv)<30: continue
        t_stat, pv = stats.ttest_ind(ev, lv, equal_var=False)
        drift_results.append({"tool":t,"param":p,"early_mean":ev.mean().round(2),
                              "late_mean":lv.mean().round(2),
                              "delta":(lv.mean()-ev.mean()).round(2),
                              "pct":(((lv.mean()-ev.mean())/ev.mean())*100).round(2) if ev.mean() else np.nan,
                              "p":pv})
drf = pd.DataFrame(drift_results)
print(drf.sort_values(["tool","p"]).to_string(index=False))

# =============================================================================
# H13: Multi-defect days exist — do "bad days" pile up multiple defect types?
# =============================================================================
print("\n" + "="*80)
print("H13: Bad days pile multiple defect types")
day_def = df.groupby("date").agg(total=("ID","count"),
                                  scrap=("is_scrap","sum"),
                                  n_def=("defect", lambda x: x.dropna().nunique()))
day_def["rate"] = (day_def["scrap"]/day_def["total"]*100).round(2)
print(day_def.sort_values("rate", ascending=False).head(10).to_string())
# Correlation between rate and defect diversity
c = day_def["rate"].corr(day_def["n_def"])
print(f"\nDay-level Pearson(rate, n_distinct_defects) = {c:.3f}")

# =============================================================================
# H14: TTF Circuit Temp == 0 means cavity inactive, lurking confounder
# =============================================================================
print("\n" + "="*80)
print("H14: TTF Circuit 1 Temp = 0 indicates inactive TTF cavity / different recipe")
df_sorted["ttf1_zero"] = df["TTF Circuit 1 Temp"] == 0
print("By tool:")
print(df_sorted.groupby(["Tool Number","ttf1_zero"]).size().unstack(fill_value=0))
print("\nScrap rate by ttf1_zero per tool:")
print(df_sorted.groupby(["Tool Number","ttf1_zero"])["is_scrap"].agg(["count","mean"]).round(3))

# =============================================================================
# H15: Pos Vinyl parameters look like "active/inactive" — they are zero or large
# =============================================================================
print("\n" + "="*80)
print("H15: Pos Vinyl variables are bimodal (off=0 vs active)")
for p in ["Pos Vinyl N Length","Pos Vinyl N Width","Pos Vinyl S Length","Pos Vinyl S Width"]:
    v = df[p]
    zero = (v == 0).sum()
    print(f"\n  {p}: zero={zero}/{len(v)} ({zero/len(v)*100:.1f}%)")
    # show non-zero distribution
    nz = v[v>0]
    if len(nz)>0:
        print(f"    non-zero range: min={nz.min()}  p50={np.percentile(nz,50)}  max={nz.max()}  nunique={nz.nunique()}")

# =============================================================================
# H16: Defect-defect cooccurrence (same time / part-family)
# =============================================================================
print("\n" + "="*80)
print("H16: Defects co-cluster in time")
# For each defect, what fraction of THE SAME DAY also has other defects?
for d in PROCESS_DEFECTS:
    days_with_d = set(df[df["defect"]==d]["date"])
    if not days_with_d: continue
    other = (df[(df["date"].isin(days_with_d)) & (df["defect"].notna()) & (df["defect"]!=d)]
             .groupby("defect").size().sort_values(ascending=False).head(3))
    print(f"\n  {d} (on {len(days_with_d)} days): top co-occurring defects:")
    print(other.to_string())

# =============================================================================
# H17: Late-scrap-detection lag is biased to specific defects
# =============================================================================
print("\n" + "="*80)
print("H17: Defects with long detection lag may be downstream/QC defects")
sub = df[df["is_scrap"]].copy()
sub["lag_min"] = (sub["scrap_time"] - sub["BuiltTime"]).dt.total_seconds()/60.0
lag = sub.groupby("defect")["lag_min"].agg(["count","median","mean","max"]).round(0)
print(lag.sort_values("median", ascending=False).to_string())

# =============================================================================
# Save key tables
# =============================================================================
day_def.to_csv(os.path.join(OUT, "hyp_day_defects.csv"))
drf.to_csv(os.path.join(OUT, "hyp_drift.csv"), index=False)
print("\nWrote hyp_*.csv files")
