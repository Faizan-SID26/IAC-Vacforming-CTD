"""Experimentation on new data.

Goals
-----
1. Deviation analysis (Welch's t-test + KS + Cliff's delta effect size) — defect-vs-good per parameter.
2. Tool-conditional analysis: same comparison but within each tool to remove tool-confounding.
3. Classification feature importance via Random Forest (sklearn) per defect.
4. Isolation Forest anomaly score correlated to scrap occurrence.
5. Temporal drift: rolling mean of key params; defect counts over time.
6. Operating windows (P5/P50/P95) — both global and per-tool.

We write summarized outputs to _exp/results/*.csv so we can compare approaches.
"""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
from scipy import stats

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
EXP  = os.path.join(ROOT, "_exp")
OUT  = os.path.join(EXP, "results"); os.makedirs(OUT, exist_ok=True)

df = pd.read_parquet(os.path.join(EXP, "df_joined.parquet"))
df["BuiltTime"] = pd.to_datetime(df["BuiltTime"])
print("Loaded:", df.shape, " scrap rows:", df["is_scrap"].sum())

# ---- Defect taxonomy --------------------------------------------------------
# Process-related (the line operators can act on these via parameters)
PROCESS_DEFECTS = [
    "Wrinkle", "Dent", "Bumps / lumps", "Burnt Carpet / Vynil",
    "Low Glue/Read Thru/Impression", "Out of dimension",
    "Bad edge wrap", "Glue bleed thru", "Delamination",
]
# Non-process (material/handling)
NONPROCESS_DEFECTS = ["Hole", "Broken / Fracture", "Fabric Flaw", "Fabric Torn"]

df["defect_scope"] = np.where(df["defect"].isna(), "Good",
                       np.where(df["defect"].isin(PROCESS_DEFECTS), "Process Defect",
                       "Non-Process Defect"))
print("\nDefect scope counts:"); print(df["defect_scope"].value_counts())

# ---- Section mapping (unchanged from prior notebook) -----------------------
SECTIONS = {
    "Roll Coating": ["Roller Gap LH","Roller Gap RH","Glue Temp","Pick Material Pos"],
    "Grippers & Clamp Frame": ["Pos Vinyl N Length","Pos Vinyl N Width","Pos Vinyl S Length","Pos Vinyl S Width",
        "Stetch Length Pick Up","Stetch Length Stretch 1","Stetch Length Stretch 2","Stetch Length Stretch 3","Stetch Length Form",
        "Stretch Cross Pick Up","Stretch Cross Stretch 1","Stretch Cross Stretch 2","Stretch Cross Stretch 3","Stretch Cross Form","Top Tool Pos Close"],
    "Oven": ["Temp. THT at Trigger","Temp. BHT at Trigger","Temp Z1","Temp Z2","Temp Z3","Temp Z4",
        "heating time (tens of seconds)","Capacity THT","Capacity BHT"],
    "Vacuum": ["Vacuum Time Tool Cavity A","Vacuum Time Tool Cavity B","Graining Vacuum TTF Cavity 1","Graining Vacuum TTF Cavity 2"],
    "Machine/Other": ["Machine Cycle Time","Pyro Clean","Tool Number","BT Circuit 1 Temp","BT Circuit 2 Temp","TTF Circuit 1 Temp","TTF Circuit 2 Temp","Time Feed to Vacuum 1"],
}
ALL_PARAMS = [p for ps in SECTIONS.values() for p in ps]
ALL_PARAMS = [p for p in ALL_PARAMS if p in df.columns]

# Drop constants (zero-variance) — they cannot diagnose anything
nunique = df[ALL_PARAMS].nunique()
const_params = nunique[nunique <= 1].index.tolist()
print(f"Zero-variance / constant params (dropped from analysis): {const_params}")
ACTIVE_PARAMS = [p for p in ALL_PARAMS if p not in const_params and p != "Tool Number"]

# ---- Helper: deviation metrics ---------------------------------------------
def cliffs_delta(x, y):
    """Effect size: -1..+1, magnitude judged: <.147 negligible, <.33 small, <.474 medium, else large."""
    x = np.asarray(x); y = np.asarray(y)
    if len(x)==0 or len(y)==0: return np.nan
    # Mann-Whitney U variant
    n1, n2 = len(x), len(y)
    u, _ = stats.mannwhitneyu(x, y, alternative="two-sided")
    return (2 * u) / (n1 * n2) - 1

def deviation_table(bad_df, good_df, params):
    rows = []
    for p in params:
        g = good_df[p].dropna().values
        b = bad_df[p].dropna().values
        if len(b) < 3 or len(g) < 20: continue
        if np.std(g) == 0: continue
        gm, gs = g.mean(), g.std()
        bm, bs = b.mean(), b.std()
        try:
            t, pv = stats.ttest_ind(g, b, equal_var=False)
            ks_stat, ks_p = stats.ks_2samp(g, b)
            cd = cliffs_delta(b, g)
        except Exception:
            continue
        rows.append({
            "Parameter": p,
            "n_good": len(g), "n_bad": len(b),
            "good_mean": round(gm,3), "good_std": round(gs,3),
            "bad_mean":  round(bm,3), "bad_std":  round(bs,3),
            "z_diff": round((bm - gm) / (gs if gs else 1), 3),
            "pct_diff": round((bm - gm) / gm * 100, 2) if gm else np.nan,
            "welch_p": pv, "ks_p": ks_p,
            "cliffs_delta": round(cd, 3),
            "abs_effect": round(abs(cd), 3),
        })
    out = pd.DataFrame(rows).sort_values("abs_effect", ascending=False)
    out["welch_q"] = stats.false_discovery_control(out["welch_p"].fillna(1).values) if len(out) else []
    return out

good = df[df["defect_scope"] == "Good"]

print(f"\n--- 1. Global deviation table per defect ---")
defect_devs = {}
for d in PROCESS_DEFECTS:
    sub = df[df["defect"] == d]
    if len(sub) < 5: continue
    tab = deviation_table(sub, good, ACTIVE_PARAMS)
    defect_devs[d] = tab
    fn = os.path.join(OUT, f"dev_global_{d.replace('/','_').replace(' ','_')}.csv")
    tab.to_csv(fn, index=False)
    print(f"\n[{d}]  n_bad={len(sub)}  top 8 by |effect|:")
    print(tab.head(8)[["Parameter","good_mean","bad_mean","pct_diff","welch_p","cliffs_delta"]].to_string(index=False))

# ---- 2. Tool-conditional deviation ----------------------------------------
print(f"\n--- 2. Tool-conditional deviation (top 5 each) ---")
tool_dev = {}
for tool in sorted(df["Tool Number"].dropna().unique()):
    sub_all = df[df["Tool Number"] == tool]
    g = sub_all[sub_all["defect_scope"]=="Good"]
    for d in PROCESS_DEFECTS:
        b = sub_all[sub_all["defect"]==d]
        if len(b) < 5: continue
        t = deviation_table(b, g, ACTIVE_PARAMS)
        if t.empty: continue
        key = (int(tool), d)
        tool_dev[key] = t
        print(f"\n  Tool {int(tool)} :: {d}  (n_bad={len(b)}, n_good={len(g)})")
        print(t.head(5)[["Parameter","good_mean","bad_mean","pct_diff","cliffs_delta","welch_p"]].to_string(index=False))

# ---- 3. Random Forest feature importance per defect ----------------------
print(f"\n--- 3. Random Forest one-vs-good feature importance ---")
try:
    from sklearn.ensemble import RandomForestClassifier
    rf_feat_imps = {}
    for d in PROCESS_DEFECTS:
        sub_bad = df[df["defect"]==d]
        if len(sub_bad) < 25: continue
        bal = pd.concat([sub_bad.assign(y=1),
                         good.sample(min(len(good), 3*len(sub_bad)), random_state=7).assign(y=0)])
        X = bal[ACTIVE_PARAMS].fillna(bal[ACTIVE_PARAMS].median())
        y = bal["y"].values
        clf = RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=5,
                                     class_weight="balanced", random_state=0, n_jobs=-1)
        clf.fit(X, y)
        imp = pd.Series(clf.feature_importances_, index=X.columns).sort_values(ascending=False)
        rf_feat_imps[d] = imp
        # OOB approx via train acc to sanity check
        sc = clf.score(X, y)
        print(f"\n  [{d}] train_acc={sc:.3f}  top-8 importances:")
        for p, v in imp.head(8).items(): print(f"    {p:<35} {v:.3f}")
        imp.to_csv(os.path.join(OUT, f"rf_imp_{d.replace('/','_').replace(' ','_')}.csv"))
except ImportError:
    print("sklearn not available -- skipping RF section")

# ---- 4. Isolation Forest: are scrap rows anomalous in feature space? ------
print(f"\n--- 4. Isolation Forest anomaly correlation with scrap ---")
try:
    from sklearn.ensemble import IsolationForest
    X = df[ACTIVE_PARAMS].fillna(df[ACTIVE_PARAMS].median())
    iso = IsolationForest(n_estimators=300, contamination=0.05, random_state=0, n_jobs=-1)
    iso.fit(X)
    df["anom_score"] = -iso.score_samples(X)  # higher = more anomalous
    df["anom_flag"]  = iso.predict(X) == -1
    rate_in = df[df["anom_flag"]]["is_scrap"].mean()*100
    rate_out = df[~df["anom_flag"]]["is_scrap"].mean()*100
    print(f"  scrap rate among anomalies: {rate_in:.2f}%  vs  normals: {rate_out:.2f}%  lift={rate_in/rate_out:.2f}x")
    # AUC-style — does anom_score rank scrap higher?
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(df["is_scrap"].astype(int), df["anom_score"])
    print(f"  anomaly-score vs scrap AUC = {auc:.3f}  (>.5 means anomalies are scrap-enriched)")
    # Per-defect AUC
    for d in PROCESS_DEFECTS:
        y = (df["defect"]==d).astype(int)
        if y.sum() < 20: continue
        a = roc_auc_score(y, df["anom_score"])
        print(f"    {d:<35} AUC={a:.3f}")
except ImportError:
    print("sklearn not available")

# ---- 5. Temporal drift -----------------------------------------------------
print(f"\n--- 5. Temporal trend ---")
df["date"] = df["BuiltTime"].dt.date
daily = df.groupby("date").agg(total=("ID","count"),
                                scrap=("is_scrap","sum")).reset_index()
daily["rate"] = (daily["scrap"]/daily["total"]*100).round(2)
print(daily.head(10).to_string(index=False))
print("...")
print(daily.tail(10).to_string(index=False))
print(f"\nOverall scrap rate: {daily['scrap'].sum()/daily['total'].sum()*100:.2f}%")
daily.to_csv(os.path.join(OUT, "daily_scrap.csv"), index=False)

# Per-defect rolling counts
weekly = (df.assign(week=df["BuiltTime"].dt.to_period("W").astype(str))
            .groupby(["week","defect"]).size().unstack(fill_value=0))
weekly.to_csv(os.path.join(OUT, "weekly_defects.csv"))
print(f"\nWeekly defect heatmap saved")

# ---- 6. Operating windows (global + per-tool) -----------------------------
print(f"\n--- 6. Operating windows ---")
critical = ["Glue Temp","Roller Gap LH","Roller Gap RH","Temp. THT at Trigger","Temp. BHT at Trigger",
            "Temp Z1","Temp Z2","Temp Z3","Temp Z4","heating time (tens of seconds)",
            "Stretch Cross Form","Stetch Length Form","Vacuum Time Tool Cavity A","Vacuum Time Tool Cavity B",
            "Machine Cycle Time","Pyro Clean"]
rows = []
for tool in [None] + sorted(df["Tool Number"].dropna().unique().tolist()):
    pop = df if tool is None else df[df["Tool Number"]==tool]
    g = pop[pop["defect_scope"]=="Good"]; sc = pop[pop["is_scrap"]]
    if len(g) < 50: continue
    for p in critical:
        if p not in pop.columns: continue
        gv = g[p].dropna(); sv = sc[p].dropna()
        if len(gv)<20: continue
        rows.append({
            "tool": "ALL" if tool is None else int(tool),
            "param": p,
            "good_p5":  round(np.percentile(gv,5),2),
            "good_p50": round(np.percentile(gv,50),2),
            "good_p95": round(np.percentile(gv,95),2),
            "scrap_p50": round(np.percentile(sv,50),2) if len(sv) else np.nan,
            "out_of_window_in_scrap_pct": round(((sv<np.percentile(gv,5))|(sv>np.percentile(gv,95))).mean()*100,1) if len(sv) else np.nan,
        })
windows = pd.DataFrame(rows)
windows.to_csv(os.path.join(OUT, "operating_windows.csv"), index=False)
print(windows.head(40).to_string(index=False))

# ---- Comparison report: vs old data conclusions ---------------------------
print(f"\n--- 7. Old-vs-New change summary ---")
old_counts = {"Wrinkle":51, "Dent":50, "Bumps / lumps":48, "Burnt Carpet / Vynil":11,
              "Low Glue/Read Thru/Impression":130, "Out of dimension":21}
new_counts = df["defect"].value_counts().to_dict()
for d, oc in old_counts.items():
    nc = new_counts.get(d, 0)
    print(f"  {d:<35}  old={oc:>3}   new={nc:>3}   delta={nc-oc:+d}")

# Tool comparison
old_tool_rate = {1:16.5, 2:2.7, 8:2.7}
print("\nTool process-scrap rate change:")
for t, r in old_tool_rate.items():
    pop = df[df["Tool Number"]==t]
    nr = pop["is_scrap"].mean()*100 if len(pop) else np.nan
    pdef = (pop["defect_scope"]=="Process Defect").mean()*100 if len(pop) else np.nan
    print(f"  Tool {t}:  old_process_rate={r}%   new_all_scrap={nr:.2f}%   new_process_only={pdef:.2f}%")

# Save processed df with extras
df.to_parquet(os.path.join(EXP, "df_with_features.parquet"), index=False)
print("\nWrote df_with_features.parquet")
