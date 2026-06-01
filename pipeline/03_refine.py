"""Refinements:
- Identify which params actually VARY within a tool (recipe-fixed vs drift-able)
- Combine tool-conditional t-test + Cliff's delta + RF importance into a single score
- Compute holdout validation of the recommendation engine
- Quantify potential scrap-reduction $ if all recommendations applied
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
EXP  = os.path.join(ROOT, "_exp")
df = pd.read_parquet(os.path.join(EXP, "df_with_features.parquet"))
print("rows:", len(df))

PROCESS_DEFECTS = ["Wrinkle","Dent","Bumps / lumps","Burnt Carpet / Vynil",
                   "Low Glue/Read Thru/Impression","Out of dimension","Bad edge wrap"]
ACTIVE_PARAMS = [c for c in df.columns if c not in
                 ["ID","PartDesc","BuiltTime","defect","scrap_time","is_scrap",
                  "defect_scope","Tool Number","date","anom_score","anom_flag",
                  "Unnamed: 0","Pick Material Pos","TTF Circuit 2 Temp"]]
print("ACTIVE_PARAMS:", len(ACTIVE_PARAMS))

# 1. Within-tool variance — flag "recipe-fixed" parameters that cannot be the diagnosis
within_var = (df.groupby("Tool Number")[ACTIVE_PARAMS]
                .agg(lambda x: x.std()/abs(x.mean()) if abs(x.mean())>1e-9 else 0))
within_var.to_csv(os.path.join(EXP, "results", "within_tool_cv.csv"))
print("\nWithin-tool coefficient of variation (top 5 most variable / least variable per tool):")
for t in within_var.index:
    s = within_var.loc[t].sort_values(ascending=False)
    print(f"\n  Tool {int(t)} -- most variable:")
    print(s.head(7).round(4).to_string())
    print(f"  Tool {int(t)} -- least variable (recipe-fixed candidates):")
    print(s.tail(7).round(4).to_string())

# 2. Per-tool, per-defect unified ranking
print("\n\n=== UNIFIED RANKING: tool x defect ===")
def cliffs(x, y):
    n1,n2 = len(x), len(y)
    if not n1 or not n2: return np.nan
    u,_ = stats.mannwhitneyu(x, y, alternative="two-sided")
    return (2*u)/(n1*n2) - 1

ALL_TOOLS = sorted(df["Tool Number"].dropna().unique().tolist())
unified_rows = []
for tool in ALL_TOOLS:
    pop = df[df["Tool Number"]==tool]
    g = pop[pop["defect_scope"]=="Good"]
    cv = within_var.loc[tool]
    for d in PROCESS_DEFECTS:
        b = pop[pop["defect"]==d]
        if len(b) < 5: continue
        # RF importance for this tool x defect
        try:
            bal = pd.concat([b.assign(y=1), g.sample(min(len(g), 3*len(b)), random_state=0).assign(y=0)])
            X = bal[ACTIVE_PARAMS].fillna(bal[ACTIVE_PARAMS].median())
            y = bal["y"].values
            clf = RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=4,
                                         class_weight="balanced", random_state=0, n_jobs=-1)
            clf.fit(X, y)
            imp = pd.Series(clf.feature_importances_, index=X.columns)
        except Exception as e:
            print("rf err", e); imp = pd.Series(0.0, index=ACTIVE_PARAMS)
        for p in ACTIVE_PARAMS:
            gv = g[p].dropna().values; bv = b[p].dropna().values
            if len(gv)<10 or len(bv)<3: continue
            if np.std(gv) == 0: continue
            cd = cliffs(bv, gv)
            try:
                _, pv = stats.ttest_ind(gv, bv, equal_var=False)
            except: pv = 1.0
            unified_rows.append({
                "tool": int(tool), "defect": d, "param": p,
                "n_bad": len(bv), "n_good": len(gv),
                "good_p50": round(np.percentile(gv, 50), 2),
                "good_p5":  round(np.percentile(gv, 5), 2),
                "good_p95": round(np.percentile(gv, 95), 2),
                "bad_p50":  round(np.percentile(bv, 50), 2),
                "pct_diff": round((bv.mean()-gv.mean())/gv.mean()*100, 2) if gv.mean() else np.nan,
                "abs_cliffs": round(abs(cd), 3),
                "cliffs":     round(cd, 3),
                "welch_p":    pv,
                "rf_imp":     round(float(imp.get(p, 0)), 4),
                "within_cv":  round(float(cv.get(p, 0)), 4),
            })
U = pd.DataFrame(unified_rows)
# Composite score (only ACTIONABLE parameters: within_cv > 0.01)
U["actionable"] = U["within_cv"] > 0.01
U["sig"] = U["welch_p"] < 0.01
U["composite"] = (U["abs_cliffs"] * 0.6 + U["rf_imp"] * 100 * 0.4) * U["actionable"].astype(int) * U["sig"].astype(int)
U.to_csv(os.path.join(EXP, "results", "unified_ranking.csv"), index=False)
print(f"\nTotal rows in unified table: {len(U)}")
print("\nTop-3 actionable signals per (tool x defect):")
for (t,d), grp in U.sort_values("composite", ascending=False).groupby(["tool","defect"]):
    top = grp.head(3)
    if (top["composite"] > 0).any():
        print(f"\n[Tool {t} | {d}] n_bad={top['n_bad'].iloc[0]}")
        for _, r in top.iterrows():
            arrow = "↑" if r["cliffs"]>0 else "↓"
            print(f"  {arrow} {r['param']:<35} good~{r['good_p50']:<8} scrap~{r['bad_p50']:<8} ({r['pct_diff']:+.1f}%)  effect={r['cliffs']:+.2f}  rf={r['rf_imp']:.3f}")

# 3. Holdout validation — does the recommendation engine "fire" on real scrap?
print("\n\n=== HOLDOUT VALIDATION ===")
# Build recipes from training half; check whether scrap-half observations are out-of-window
train, test = train_test_split(df, test_size=0.3, random_state=0, stratify=df["is_scrap"])
print(f"train: {len(train)} ({train['is_scrap'].sum()} scrap)  test: {len(test)} ({test['is_scrap'].sum()} scrap)")
# Build per-tool windows from train-good
def build_windows(d):
    w = {}
    for tool in d["Tool Number"].dropna().unique():
        sub = d[(d["Tool Number"]==tool) & (d["defect_scope"]=="Good")]
        w[int(tool)] = {}
        for p in ACTIVE_PARAMS:
            v = sub[p].dropna()
            if len(v) < 30 or v.std()==0: continue
            w[int(tool)][p] = (np.percentile(v,5), np.percentile(v,95))
    return w
windows = build_windows(train)
# Score test rows: count out-of-window params per row
def oow_count(row, w):
    tool = row.get("Tool Number")
    if pd.isna(tool) or int(tool) not in w: return np.nan
    cnt = 0
    for p, (lo, hi) in w[int(tool)].items():
        v = row.get(p)
        if pd.isna(v): continue
        if v < lo or v > hi: cnt += 1
    return cnt
test = test.copy()
test["oow_count"] = test.apply(lambda r: oow_count(r, windows), axis=1)
print(test.groupby("is_scrap")["oow_count"].describe())
# AUC
auc = roc_auc_score(test["is_scrap"].astype(int), test["oow_count"].fillna(test["oow_count"].median()))
print(f"\nAUC of out-of-window count vs scrap: {auc:.3f}")

# Top thresholds
for thr in [0, 1, 2, 3, 4, 5]:
    flagged = test["oow_count"] >= thr
    if not flagged.any(): continue
    rate = test[flagged]["is_scrap"].mean()*100
    cov  = (flagged & test["is_scrap"].astype(bool)).sum() / max(1, test["is_scrap"].sum()) * 100
    print(f"  oow>={thr}: flagged={flagged.sum()} ({flagged.mean()*100:.1f}% of test)  scrap-rate-in-flag={rate:.2f}%  scrap-coverage={cov:.1f}%")

# 4. Potential savings — if Tool 1 reached Tool 2 scrap rate
print("\n=== Hypothetical savings ===")
TOTAL_RATE = df["is_scrap"].mean()*100
T1 = df[df["Tool Number"]==1]; T2 = df[df["Tool Number"]==2]; T8 = df[df["Tool Number"]==8]
t1_rate = T1["is_scrap"].mean()*100
t2_rate = T2["is_scrap"].mean()*100
print(f"  Current rates: T1={t1_rate:.2f}% T2={t2_rate:.2f}% T8={T8['is_scrap'].mean()*100:.2f}%")
# If T1 dropped to T8 rate (more realistic target than T2)
t8_rate = T8["is_scrap"].mean()*100
avoidable = (t1_rate - t8_rate) / 100 * len(T1)
print(f"  Avoidable T1 scrap if reduced to T8 level: {avoidable:.0f} parts -> ~${avoidable*67:,.0f}")
total_avoidable = (t1_rate-t8_rate)/100*len(T1) + (t2_rate-3)/100*len(T2)
print(f"  All-tool potential ~ ${total_avoidable*67:,.0f} over data period (~56 days)")

# Save
U.to_parquet(os.path.join(EXP, "unified_ranking.parquet"), index=False)
print("\nSaved unified_ranking.parquet")
