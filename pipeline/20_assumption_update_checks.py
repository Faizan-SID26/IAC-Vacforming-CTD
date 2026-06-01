"""Validate the team's assumption answers (reviewed 2026-06-01) against the labeled data
and prototype the UPDATED feature encodings.

Uses data/VF_export_old.csv (the fully-labeled window, -> 6 May) so the scrap denominator
is not inflated by the unlabeled May 7-13 week (project risk R-1).

Run from repo root:  python pipeline/20_assumption_update_checks.py
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
from scipy import stats
pd.set_option("display.width", 200)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

def parse_kv(s):
    out = {}
    if pd.isna(s): return out
    for it in str(s).split(","):
        if ":" in it:
            k, v = it.rsplit(":", 1)
            try: out[k.strip()] = float(v.strip())
            except: pass
    return out

p = pd.read_csv(os.path.join(DATA, "VF_export_old.csv"))
p = p.drop(columns=[c for c in p.columns if c.startswith("Unnamed")])
s = pd.read_csv(os.path.join(DATA, "VF_Scrap_export.csv"))
p["BuiltTime"] = pd.to_datetime(p["BuiltTime"])
ds = pd.concat([p["DS1"].apply(parse_kv).apply(pd.Series),
                p["DS2"].apply(parse_kv).apply(pd.Series),
                p["DS3"].apply(parse_kv).apply(pd.Series)], axis=1)
df = pd.concat([p[["ID","PartDesc","BuiltTime"]], ds], axis=1)
df = df.merge(s[["ID","Desc"]].rename(columns={"Desc":"defect"}), on="ID", how="left")
df["is_scrap"] = df["defect"].notna()
df = df.sort_values("BuiltTime").reset_index(drop=True)
df["date"] = df["BuiltTime"].dt.date
df["color"] = df["PartDesc"].str.extract(r"\b(BLACK|BEIGE|WHITE)\b").fillna("OTHER")
N = len(df); base = df["is_scrap"].mean()
print(f"Labeled set: {N:,} rows  base scrap rate {base*100:.2f}%\n")

def rate(mask, label):
    sub = df[mask]
    r = sub["is_scrap"].mean()*100 if len(sub) else float("nan")
    return f"  {label:<46} n={len(sub):>5}  scrap={sub['is_scrap'].sum():>4}  rate={r:5.2f}%"

def chi2(a, b):
    """2x2 chi-square of is_scrap across boolean mask a vs b."""
    ct = pd.crosstab(a, df["is_scrap"])
    if ct.shape == (2,2):
        return stats.chi2_contingency(ct)[1]
    return float("nan")

# ============================================================================
print("="*78)
print("CHECK 1  Pos Vinyl == 0  ==  camera blocked by EXCESS MATERIAL  (team A10)")
print("  Hypothesis: a blocked camera (zero) is an excess-material signal and should")
print("  scrap MORE -- especially Wrinkle / Bad edge wrap on Tool 1.")
print("="*78)
POSV = ["Pos Vinyl N Length","Pos Vinyl N Width","Pos Vinyl S Length","Pos Vinyl S Width"]
df["cam_blocked_any"] = (df[POSV] == 0).any(axis=1).astype(int)
df["cam_blocked_cnt"] = (df[POSV] == 0).sum(axis=1)
print(rate(df["cam_blocked_any"]==1, "any Pos Vinyl camera blocked (==0)"))
print(rate(df["cam_blocked_any"]==0, "no camera blocked"))
print(f"    chi2 p = {chi2(df['cam_blocked_any']==1, df['cam_blocked_any']==0):.2e}")
for t in [1.0,2.0,8.0]:
    tm = df["Tool Number"]==t
    print(rate(tm & (df["cam_blocked_any"]==1), f"Tool {int(t)}: camera blocked"))
    print(rate(tm & (df["cam_blocked_any"]==0), f"Tool {int(t)}: not blocked"))
print("  By blocked-camera count (0..4):")
for k in range(5):
    print(rate(df["cam_blocked_cnt"]==k, f"  {k} cameras blocked"))
print("  Defect mix among camera-blocked rows:")
print(df[df['cam_blocked_any']==1]['defect'].value_counts().head(6).to_string())

# ----------------------------------------------------------------------------
print("\nCHECK 1b  Does the corrected encoding change the Wrinkle diagnosis?")
print("  Compare Pos Vinyl S Width (Wrinkle vs good, Tool 1) on ALL rows vs")
print("  camera-VISIBLE-only rows. The raw zeros dilute the 'good' baseline.")
def cliffs_delta(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    if len(a)==0 or len(b)==0: return np.nan
    return ((a[:,None] > b).sum() - (a[:,None] < b).sum()) / (len(a)*len(b))
t1 = df[df["Tool Number"]==1]
col = "Pos Vinyl S Width"
for label, sub in [("ALL Tool-1 rows", t1), ("camera-VISIBLE only (val>0)", t1[t1[col]>0])]:
    bad = sub[sub["defect"]=="Wrinkle"][col]; good = sub[sub["defect"].isna()][col]
    d = cliffs_delta(bad.values, good.values)
    pv = stats.mannwhitneyu(bad, good).pvalue if len(bad) and len(good) else float("nan")
    sev = "CRITICAL" if abs(d)>0.474 else "STRONG" if abs(d)>0.33 else "MODERATE" if abs(d)>0.20 else "weak/none"
    print(f"  {label:<30} n_bad={len(bad):>3} n_good={len(good):>4}  cliffs={d:+.3f} ({sev})  p={pv:.2e}")
print("  -> excluding blocked rows removes the dilution; the true effect is much weaker.")

# ============================================================================
print("\n"+"="*78)
print("CHECK 2  Restart-after-break (lunch / cool-down) warm-up  (team: spikes)")
print("  Hypothesis: parts right after an intra-day production GAP scrap more,")
print("  same thermal mechanism as morning warm-up -- NOT operator variation.")
print("="*78)
df["prev_time"] = df.groupby(["date","Tool Number"])["BuiltTime"].shift(1)
df["gap_min"] = (df["BuiltTime"] - df["prev_time"]).dt.total_seconds()/60
g = df["gap_min"].dropna()
print(f"  Intra-day inter-part gap (min): median={g.median():.1f}  p90={g.quantile(.9):.1f}  "
      f"p99={g.quantile(.99):.1f}  max={g.max():.1f}")
df["seq_in_day"] = df.groupby(["date","Tool Number"]).cumcount()
for thr in [15, 25, 40, 60]:
    # restart = first part after a gap > thr, but not the morning warm-up (seq>=5)
    restart = (df["gap_min"] > thr) & (df["seq_in_day"] >= 5)
    print(rate(restart, f"first part after gap > {thr} min (mid-day restart)"))
print(rate(df["seq_in_day"] < 10, "morning warm-up (first 10 parts of day)"))
print(rate(df["seq_in_day"] >= 20, "steady state (seq >= 20, no recent gap)"))
# combined cold-start
df["is_restart"] = ((df["gap_min"] > 25) & (df["seq_in_day"] >= 5)).astype(int)
df["is_warmup"]  = (df["seq_in_day"] < 10).astype(int)
df["is_cold_start"] = ((df["is_warmup"]==1) | (df["is_restart"]==1)).astype(int)
print(rate(df["is_cold_start"]==1, "UNIFIED cold-start (warmup OR restart)"))
print(rate(df["is_cold_start"]==0, "warm machine (neither)"))
print(f"    chi2 p = {chi2(df['is_cold_start']==1, df['is_cold_start']==0):.2e}")

# ============================================================================
print("\n"+"="*78)
print("CHECK 3  Beige thermodynamic difficulty  (team: white reflects, black absorbs)")
print("="*78)
for c in ["BLACK","BEIGE","WHITE","OTHER"]:
    print(rate(df["color"]==c, f"color = {c}"))
print("  Within Tool 1 (where the beige spike was reported):")
for c in ["BLACK","BEIGE","WHITE"]:
    print(rate((df["Tool Number"]==1)&(df["color"]==c), f"  Tool 1 {c}"))
# beige vs heating-parameter spread (thermal-balance claim)
for col in ["Temp. THT at Trigger","Temp. BHT at Trigger","Temp Z1"]:
    if col in df:
        bg = df[df["color"]=="BEIGE"][col]; bk = df[df["color"]=="BLACK"][col]
        print(f"  {col:<24} BEIGE mean={bg.mean():.1f} sd={bg.std():.1f} | BLACK mean={bk.mean():.1f} sd={bk.std():.1f}")

# ============================================================================
print("\n"+"="*78)
print("CHECK 4  Pyro Clean sweet-spot stability  (team A5/A9: NOT clockwork reset)")
print("  If the 'sweet spot' is an artifact, the lowest-scrap octile should be")
print("  unstable / not reproduce on a random split.")
print("="*78)
rng = np.random.RandomState(0)
for t in [1.0,2.0,8.0]:
    sub = df[df["Tool Number"]==t].copy()
    half = rng.rand(len(sub)) < 0.5
    def best_oct(d):
        try: b = pd.qcut(d["Pyro Clean"], 8, duplicates="drop")
        except Exception: return None
        gg = d.groupby(b, observed=True)["is_scrap"].mean()
        return gg.idxmin()
    a = best_oct(sub[half]); b = best_oct(sub[~half])
    print(f"  Tool {int(t)}: lowest-scrap Pyro octile  splitA={a}  splitB={b}  "
          f"{'STABLE' if str(a)==str(b) else 'UNSTABLE (different band)'}")

print("\nDONE.")
