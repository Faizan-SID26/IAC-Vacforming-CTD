"""Deep EDA — assume nothing.

Audits the raw CSV exports for: schema, ranges, sentinels, gaps, sensor anomalies,
recipe-vs-drift parameters, distributions per tool/part/color, defect timestamps,
clustering, and structural surprises. Outputs go to _exp/results/eda_*.
"""
import sys, io, os, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 80)

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
DATA = os.path.join(ROOT, "data")
OUT  = os.path.join(ROOT, "_exp", "results"); os.makedirs(OUT, exist_ok=True)

# =============================================================================
# 0. RAW LOAD — keep close to the source
# =============================================================================
p_raw = pd.read_csv(os.path.join(DATA, "VF_export.csv"))
s_raw = pd.read_csv(os.path.join(DATA, "VF_Scrap_export.csv"))
print(f"VF_export       rows={len(p_raw):>6}  cols={p_raw.shape[1]}")
print(f"VF_Scrap_export rows={len(s_raw):>6}  cols={s_raw.shape[1]}")
print("VF_export columns       :", p_raw.columns.tolist())
print("VF_Scrap_export columns :", s_raw.columns.tolist())
print("Unnamed cols look like row indices? ",
      (p_raw["Unnamed: 0"] == np.arange(len(p_raw))).all() if "Unnamed: 0" in p_raw.columns else "—")

p_raw = p_raw.drop(columns=[c for c in p_raw.columns if c.startswith("Unnamed")])
s_raw = s_raw.drop(columns=[c for c in s_raw.columns if c.startswith("Unnamed")])
p_raw["BuiltTime"] = pd.to_datetime(p_raw["BuiltTime"])
s_raw["ScrapTime"] = pd.to_datetime(s_raw["ScrapTime"])

print(f"\nID-uniqueness   process={p_raw['ID'].is_unique}  scrap={s_raw['ID'].is_unique}")
print(f"Scrap IDs in process: {s_raw['ID'].isin(p_raw['ID']).sum()} / {len(s_raw)}  "
      f"missing={(~s_raw['ID'].isin(p_raw['ID'])).sum()}")

# =============================================================================
# 1. DATE COVERAGE — gaps, weekend pattern, production density
# =============================================================================
p_raw["date"] = p_raw["BuiltTime"].dt.date
p_raw["hour"] = p_raw["BuiltTime"].dt.hour
p_raw["dow"]  = p_raw["BuiltTime"].dt.dayofweek    # 0=Mon
day_counts = p_raw.groupby("date").size()
print(f"\nDates covered: {day_counts.shape[0]}   range {p_raw['BuiltTime'].min()} to {p_raw['BuiltTime'].max()}")
print("First / last few production days (counts):")
print(day_counts.head(8).to_string())
print("...")
print(day_counts.tail(8).to_string())
all_days = pd.date_range(p_raw["BuiltTime"].min().date(), p_raw["BuiltTime"].max().date(), freq="D").date
missing_days = sorted(set(all_days) - set(day_counts.index))
print(f"\nDays in span with ZERO production: {len(missing_days)}")
if missing_days:
    print(" first 10 missing:", missing_days[:10])
print("\nDay-of-week production:")
print(p_raw.groupby("dow").size().rename("rows").to_string())
print("\nHour-of-day production:")
print(p_raw.groupby("hour").size().rename("rows").to_string())

# =============================================================================
# 2. PARSE DS1/DS2/DS3 and audit key coverage
# =============================================================================
def parse_kv(s):
    out = {}
    if pd.isna(s): return out
    for it in str(s).split(","):
        if ":" in it:
            k, v = it.rsplit(":", 1)
            try: out[k.strip()] = float(v.strip())
            except: pass
    return out

key_count = {}
for col in ["DS1","DS2","DS3"]:
    for s in p_raw[col].dropna():
        for k in parse_kv(s):
            key_count.setdefault(col, {}).setdefault(k, 0)
            key_count[col][k] += 1

# Show frequency of each key in each DS column (should be ~all rows; if not, sparse)
print("\nKey coverage per DS column (count out of N rows):")
N = len(p_raw)
for col, kc in key_count.items():
    print(f"\n  {col}:")
    for k, n in sorted(kc.items()):
        print(f"    {k:<40} {n:>6} / {N} ({n/N*100:5.1f}%)")

# Build parsed frame
ds1 = p_raw["DS1"].apply(parse_kv).apply(pd.Series)
ds2 = p_raw["DS2"].apply(parse_kv).apply(pd.Series)
ds3 = p_raw["DS3"].apply(parse_kv).apply(pd.Series)
P   = pd.concat([p_raw[["ID","PartDesc","BuiltTime","date","hour","dow"]], ds1, ds2, ds3], axis=1)
PARAMS = [c for c in P.columns if c not in
          ("ID","PartDesc","BuiltTime","date","hour","dow")]
print(f"\nTotal parameters parsed: {len(PARAMS)}")

# =============================================================================
# 3. PER-PARAMETER PROFILE — type, nunique, min/p1/p5/p50/p95/p99/max, zeros
# =============================================================================
prof = []
for c in PARAMS:
    v = P[c]
    nn = v.dropna()
    if len(nn) == 0: continue
    prof.append({
        "param": c, "n_nonnull": int(nn.shape[0]),
        "n_unique": int(v.nunique(dropna=True)),
        "n_zero": int((nn == 0).sum()),
        "min": float(nn.min()),
        "p1":  float(np.percentile(nn, 1)),
        "p5":  float(np.percentile(nn, 5)),
        "p50": float(np.percentile(nn, 50)),
        "mean": float(nn.mean()),
        "p95": float(np.percentile(nn, 95)),
        "p99": float(np.percentile(nn, 99)),
        "max": float(nn.max()),
        "std": float(nn.std()),
    })
prof_df = pd.DataFrame(prof).round(3)
prof_df.to_csv(os.path.join(OUT, "eda_param_profile.csv"), index=False)
print("\nParameter profile (range + unique counts):")
print(prof_df.to_string(index=False))

# Flag suspicious sentinels
print("\nSentinel candidates (max value appears in >=10 rows -> possible cap):")
for c in PARAMS:
    v = P[c].dropna()
    if v.empty: continue
    mx = v.max()
    n_at_max = (v == mx).sum()
    if n_at_max >= 10 and v.nunique() > 5:
        print(f"  {c:<35} max={mx:>10}  rows-at-max={n_at_max:>5}  ({n_at_max/len(v)*100:.1f}%)")

# =============================================================================
# 4. PER-TOOL / PER-PART STRUCTURE
# =============================================================================
print("\nProduction by Tool:")
tool_counts = P.groupby("Tool Number").size()
print(tool_counts.to_string())

print("\nPart catalogue (top 30 by volume):")
part_counts = P.groupby("PartDesc").size().sort_values(ascending=False)
print(part_counts.head(30).to_string())
print(f"\nUnique parts: {part_counts.shape[0]}")

# Color in PartDesc?
P["color"] = P["PartDesc"].str.extract(r"\b(BLACK|BEIGE|WHITE|GREY|GRAY)\b", expand=False).fillna("OTHER")
print("\nColor distribution (parsed from PartDesc):")
print(P["color"].value_counts().to_string())

# Part-Tool mapping — do parts pin to a single tool?
pt = P.groupby(["PartDesc","Tool Number"]).size().unstack(fill_value=0)
multi_tool_parts = (pt > 0).sum(axis=1)
print(f"\nParts produced on >1 tool: {(multi_tool_parts > 1).sum()}  /  {len(multi_tool_parts)}")
print(" Examples:")
print(pt[(pt > 0).sum(axis=1) > 1].head(10).to_string())

# =============================================================================
# 5. WITHIN-TOOL VARIANCE — recipe vs drifting
# =============================================================================
print("\nWithin-tool coefficient of variation (sample):")
cv = (P.groupby("Tool Number")[PARAMS]
        .agg(lambda x: x.std()/abs(x.mean()) if abs(x.mean())>1e-9 else 0))
cv.to_csv(os.path.join(OUT, "eda_within_tool_cv.csv"))
for t in cv.index:
    print(f"\n  Tool {int(t)} -- variance > 0.05 (drift candidates):")
    s = cv.loc[t].sort_values(ascending=False)
    print(s[s > 0.05].round(4).to_string())
    print(f"  Tool {int(t)} -- variance < 0.01 (recipe-fixed):")
    print(s[s < 0.01].round(4).to_string())

# =============================================================================
# 6. DEFECT TABLE — counts, timing diff (built vs scrap), per tool & part
# =============================================================================
s_raw = s_raw.merge(P[["ID","PartDesc","Tool Number","BuiltTime"]], on="ID", how="left")
s_raw["lag_min"] = (s_raw["ScrapTime"] - s_raw["BuiltTime"]).dt.total_seconds()/60.0
print("\nScrap defect counts:")
print(s_raw["Desc"].value_counts().to_string())
print("\nScrap detection lag (minutes from BuiltTime → ScrapTime):")
print(s_raw["lag_min"].describe().round(1).to_string())
print("\nDefects per Tool:")
print(s_raw.groupby(["Tool Number","Desc"]).size().unstack(fill_value=0).to_string())

# Cross-tab defect x color
P_full = P.merge(s_raw[["ID","Desc"]], on="ID", how="left").rename(columns={"Desc":"defect"})
P_full["is_scrap"] = P_full["defect"].notna()
print("\nScrap rate by color:")
print((P_full.groupby("color")["is_scrap"].agg(["sum","count","mean"])
       .assign(rate_pct=lambda x: x["mean"]*100)).round(3).to_string())

print("\nTop 15 parts by scrap rate (min 50 produced):")
ps = P_full.groupby("PartDesc").agg(total=("ID","count"), scrap=("is_scrap","sum"))
ps["rate"] = ps["scrap"]/ps["total"]*100
print(ps[ps["total"]>=50].sort_values("rate", ascending=False).head(15).round(2).to_string())

# =============================================================================
# 7. TEMPORAL — daily rate, run-lengths of scrap, autocorrelation
# =============================================================================
daily = P_full.groupby("date").agg(total=("ID","count"), scrap=("is_scrap","sum"))
daily["rate"] = daily["scrap"]/daily["total"]*100
daily.to_csv(os.path.join(OUT, "eda_daily.csv"))
print(f"\nDaily rate (top 5 highest):")
print(daily.sort_values("rate", ascending=False).head(5).round(2).to_string())
print("\nDaily rate (bottom 5 lowest, n>=50):")
print(daily[daily["total"]>=50].sort_values("rate").head(5).round(2).to_string())

# Run-length: are scraps clustered in sequence?
P_full_sorted = P_full.sort_values("BuiltTime").reset_index(drop=True)
scrap_runs = []
prev = None; run = 0
for v in P_full_sorted["is_scrap"]:
    if v and prev:        run += 1
    elif v and not prev:  run = 1
    else:
        if run > 0: scrap_runs.append(run)
        run = 0
if run: scrap_runs.append(run)
print(f"\nScrap run-lengths (consecutive scrap parts) — count by length:")
rl = pd.Series(scrap_runs).value_counts().sort_index()
print(rl.to_string())
print(f"Expected if independent (rough): mean rate {P_full['is_scrap'].mean()*100:.2f}%")
# Lag-1 autocorrelation of is_scrap (in time order)
ac = P_full_sorted["is_scrap"].astype(int)
lag1 = np.corrcoef(ac[:-1], ac[1:])[0,1]
print(f"Lag-1 autocorrelation of is_scrap (time-ordered): {lag1:.3f}")

# =============================================================================
# 8. SHIFT / HOUR-OF-DAY effect
# =============================================================================
P_full["hour"] = P_full["BuiltTime"].dt.hour
shift_rate = P_full.groupby("hour")["is_scrap"].agg(["sum","count","mean"])
shift_rate["rate_pct"] = (shift_rate["mean"]*100).round(2)
print("\nScrap rate by hour:")
print(shift_rate[["sum","count","rate_pct"]].to_string())

# Day-of-week
dow_rate = P_full.groupby(P_full["BuiltTime"].dt.dayofweek)["is_scrap"].agg(["sum","count","mean"])
dow_rate["rate_pct"] = (dow_rate["mean"]*100).round(2)
_dow_map = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
dow_rate.index = [_dow_map[i] for i in dow_rate.index]
print("\nScrap rate by DOW:")
print(dow_rate[["sum","count","rate_pct"]].to_string())

# =============================================================================
# 9. SENTINEL DEEP DIVE — Machine Cycle Time = 9999
# =============================================================================
mc = P["Machine Cycle Time"]
print(f"\nMachine Cycle Time = 9999 rows: {(mc==9999).sum()}  ({(mc==9999).mean()*100:.2f}%)")
print(f"  In scrap rows:    {((mc==9999) & P_full['is_scrap']).sum()}")
print(f"  In good rows:     {((mc==9999) & ~P_full['is_scrap']).sum()}")
print(f"  Scrap rate among 9999 rows: {P_full.loc[mc==9999,'is_scrap'].mean()*100:.2f}%")
print(f"  Scrap rate elsewhere:       {P_full.loc[mc!=9999,'is_scrap'].mean()*100:.2f}%")
print("  9999 occurrences by tool:")
print((P.assign(cap=mc==9999).groupby("Tool Number")["cap"].agg(["sum","mean"])).round(3).to_string())

# =============================================================================
# 10. PYRO CLEAN — does it look like a counter?
# =============================================================================
print("\nPyro Clean stats (per tool):")
pc = P.groupby("Tool Number")["Pyro Clean"].agg(["min","max","mean","std","nunique"])
print(pc.round(1).to_string())

# Is it monotonically increasing in time within a tool? Compute fraction of decreasing steps.
print("\nPyro Clean monotonicity within each tool (sorted by time):")
for t in sorted(P["Tool Number"].dropna().unique()):
    sub = P[P["Tool Number"]==t].sort_values("BuiltTime")["Pyro Clean"].dropna().values
    if len(sub) < 50: continue
    diffs = np.diff(sub)
    inc = (diffs > 0).mean()*100
    dec = (diffs < 0).mean()*100
    same = (diffs == 0).mean()*100
    big_drop = (diffs < -50).sum()
    print(f"  Tool {int(t)}: inc={inc:.1f}%  dec={dec:.1f}%  same={same:.1f}%  big-drops(<-50)={big_drop}")

# =============================================================================
# 11. SAVE PARSED FRAME
# =============================================================================
P_full.to_parquet(os.path.join(ROOT, "_exp", "df_clean.parquet"), index=False)
print(f"\nSaved _exp/df_clean.parquet  ({len(P_full)} rows, {P_full.shape[1]} cols)")
