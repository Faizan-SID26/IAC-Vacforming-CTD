"""Modeling experiments — per-tool per-defect.

For each tool x defect (with n_bad >= 15), we fit:
  • Logistic Regression with L1 (sparse coefficients)
  • Random Forest
  • Gradient Boosting
on standardized features (within-tool good vs defect). We use stratified 5-fold CV.
Outputs: cv AUC, permutation importance, calibration curve points.

This explicitly handles the EDA findings:
  • Drops constants & recipe-fixed params (within-tool CV < 0.01)
  • Marks Machine Cycle Time = 9999 as missing
  • Adds warm-up flag (first 20 parts of day) and stoppage-after flag
  • Encodes Pos Vinyl as (active_flag, value_if_active) two-feature pair
"""
import sys, io, os, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score, brier_score_loss

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
EXP  = os.path.join(ROOT, "_exp")
OUT  = os.path.join(EXP, "results")
df = pd.read_parquet(os.path.join(EXP, "df_clean.parquet"))
print(f"rows={len(df):,}  scrap={df['is_scrap'].sum()}  rate={df['is_scrap'].mean()*100:.2f}%")

# -- Feature engineering ------------------------------------------------------
df = df.sort_values("BuiltTime").reset_index(drop=True)
df["mct_capped"] = df["Machine Cycle Time"] == 9999
df.loc[df["mct_capped"], "Machine Cycle Time"] = np.nan      # treat as missing
df["seq_in_day"] = df.groupby([df["date"], df["Tool Number"]]).cumcount()
df["is_warmup"]  = (df["seq_in_day"] < 20).astype(int)
df["prev_mct_capped"] = (df.groupby("Tool Number")["mct_capped"].shift(1)
                          .fillna(False).astype(int))

# Bimodal Pos Vinyl: split into (active flag) + (value when active)
POSV = ["Pos Vinyl N Length","Pos Vinyl N Width","Pos Vinyl S Length","Pos Vinyl S Width"]
for c in POSV:
    df[f"{c}_active"] = (df[c] > 0).astype(int)

PROCESS_DEFECTS = ["Wrinkle","Dent","Bumps / lumps","Burnt Carpet / Vynil",
                   "Low Glue/Read Thru/Impression","Out of dimension","Bad edge wrap"]
TOOLS = sorted(df["Tool Number"].dropna().unique())

# -- Choose features per tool: drop recipe-fixed & constant -------------------
PARAMS_ALL = [c for c in df.columns if c not in
              ("ID","PartDesc","BuiltTime","date","hour","dow","color","family",
               "defect","is_scrap","scope","is_map","Tool Number","seq_in_day","mct_capped")]
print(f"raw feature pool: {len(PARAMS_ALL)}")

def tool_features(tool):
    sub = df[df["Tool Number"] == tool]
    feats = []
    for c in PARAMS_ALL:
        v = sub[c]
        if v.nunique(dropna=True) < 2: continue
        # drop near-recipe-fixed (CV < 0.01)
        mu = v.mean()
        if abs(mu) > 1e-9 and (v.std()/abs(mu)) < 0.01: continue
        feats.append(c)
    return feats

def run_cv(X, y, model, cv=5):
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=0)
    aucs, briers = [], []
    for tr, te in skf.split(X, y):
        m = model.fit(X.iloc[tr], y[tr])
        proba = m.predict_proba(X.iloc[te])[:,1]
        aucs.append(roc_auc_score(y[te], proba))
        briers.append(brier_score_loss(y[te], proba))
    return np.mean(aucs), np.std(aucs), np.mean(briers)

results = []
imp_rows = []

for tool in TOOLS:
    feats = tool_features(tool)
    print(f"\n=== Tool {int(tool)} | features: {len(feats)} ===")
    sub = df[df["Tool Number"] == tool].copy()
    # Impute medians
    X_all = sub[feats].copy()
    for c in feats: X_all[c] = X_all[c].fillna(X_all[c].median())
    # Add the engineered flags (not in feats yet)
    extras = ["is_warmup","prev_mct_capped"]
    for e in extras:
        if e not in X_all.columns: X_all[e] = sub[e].values

    for defect in PROCESS_DEFECTS:
        n_bad = (sub["defect"]==defect).sum()
        if n_bad < 15:
            continue
        y = (sub["defect"]==defect).astype(int).values

        models = {
            "L1_LR": Pipeline([("s", StandardScaler()),
                               ("m", LogisticRegression(penalty="l1", solver="liblinear",
                                                        class_weight="balanced", C=0.5,
                                                        random_state=0))]),
            "RF":    RandomForestClassifier(n_estimators=400, max_depth=8, min_samples_leaf=5,
                                            class_weight="balanced", random_state=0, n_jobs=-1),
            "GBM":   GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.06,
                                                random_state=0),
        }
        row = {"tool": int(tool), "defect": defect, "n_bad": int(n_bad),
               "n_good": int(len(sub) - n_bad)}
        best_auc, best_model, best_name = 0, None, ""
        for name, mdl in models.items():
            try:
                m_auc, s_auc, brier = run_cv(X_all, y, mdl)
            except Exception as e:
                print(f"  {defect:<35} {name}  err={e}")
                continue
            row[f"{name}_auc_mean"] = round(m_auc, 3)
            row[f"{name}_auc_std"]  = round(s_auc, 3)
            row[f"{name}_brier"]    = round(brier, 4)
            if m_auc > best_auc:
                best_auc, best_name = m_auc, name
                best_model = mdl
        # Permutation importance on the best model (using full-fit on this tool)
        if best_model is not None:
            best_model.fit(X_all, y)
            pi = permutation_importance(best_model, X_all, y, n_repeats=8,
                                        random_state=0, n_jobs=-1, scoring="roc_auc")
            imp = pd.Series(pi.importances_mean, index=X_all.columns).sort_values(ascending=False)
            for k, v in imp.head(7).items():
                imp_rows.append({"tool":int(tool),"defect":defect,"feature":k,
                                 "perm_imp":round(float(v),4),"best_model":best_name})
            row["best_model"] = best_name
            row["best_top5"]  = "; ".join(imp.head(5).index.tolist())
        results.append(row)
        print(f"  {defect:<35} n_bad={n_bad:<3}  best={row.get('best_model','-'):<5}  "
              f"L1={row.get('L1_LR_auc_mean','-')}  RF={row.get('RF_auc_mean','-')}  GBM={row.get('GBM_auc_mean','-')}")
        print(f"    top features: {row.get('best_top5','-')}")

RES = pd.DataFrame(results)
IMP = pd.DataFrame(imp_rows)
RES.to_csv(os.path.join(OUT, "model_cv_summary.csv"), index=False)
IMP.to_csv(os.path.join(OUT, "model_perm_importance.csv"), index=False)
print("\nSaved model_cv_summary.csv and model_perm_importance.csv")

# Summary stats
print("\nMean AUC per defect (best model):")
RES["best_auc"] = RES[["L1_LR_auc_mean","RF_auc_mean","GBM_auc_mean"]].max(axis=1)
print(RES.groupby("defect")["best_auc"].agg(["mean","max","min"]).round(3))
print("\nMean AUC per tool:")
print(RES.groupby("tool")["best_auc"].agg(["mean","max","min","count"]).round(3))
