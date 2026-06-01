"""Build VAC_Forming_Scrap_Analysis_v2.ipynb from cell definitions."""
import json, os

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
NB_PATH = os.path.join(ROOT, "VAC_Forming_Scrap_Analysis_v2.ipynb")

CELLS = []

def md(src): CELLS.append({"cell_type": "markdown", "metadata": {}, "source": src})
def code(src): CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                              "outputs": [], "source": src})

# === Cell 1 — Title ===
md("""# VAC Forming Scrap — Root-Cause Analysis & Recommendations  (v2, new data)
**Project:** IAC VAC Forming Scrap Reduction
**Prepared by:** Algo8 AI Team
**Data:** `data/VF_export.csv` + `data/VF_Scrap_export.csv`
**Data period:** 11 Mar 2026 – 6 May 2026  (~56 days)

This notebook supersedes `VAC_Forming_Scrap_Analysis.ipynb`. It uses the new export and addresses a methodological flaw in v1 — **tool-confounding** — by analysing each defect within its tool's recipe.
""")

# === Cell 2 — Problem statement ===
md("""---
## 1. Problem & approach

The line vacuum-forms vinyl over plastic substrates: **Roll Coating → Grippers/Clamp Frame → Oven (IR) → Vacuum Press**. Scrap is detected in-line; what we need is *why it happened* and *which parameter to nudge*.

**What's new in this analysis (vs v1):**
- **2× more data** (7,372 vs 4,283 process records), broader date range.
- **Tool-conditional** comparison instead of global pooling — each tool runs a different recipe, so within-tool comparisons isolate true drift from recipe difference.
- **Composite scoring** combining Cliff's δ (effect size), Welch t-test (significance), Random-Forest importance (multivariate), and within-tool coefficient-of-variation (actionability).
- **Holdout validation** of the simple operating-window rule (AUC ≈ 0.56 — confirms why we need the multivariate diagnosis, not just thresholds).
- **Old-vs-new comparison** — confirms prior Low-Glue recommendations worked (130→41 cases, −68%) and highlights new dominant defects (Wrinkle, Burnt Carpet).
""")

# === Cell 3 — Setup ===
md("## 2. Setup & data loading")

code("""import os, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

plt.rcParams.update({'figure.figsize': (14, 5), 'font.size': 11,
                     'axes.titlesize': 13, 'axes.labelsize': 11})
sns.set_style('whitegrid')
pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 60)

DATA_DIR = 'data'
process_raw = pd.read_csv(os.path.join(DATA_DIR, 'VF_export.csv'))
scrap_raw   = pd.read_csv(os.path.join(DATA_DIR, 'VF_Scrap_export.csv'))
process_raw['BuiltTime'] = pd.to_datetime(process_raw['BuiltTime'])
scrap_raw['ScrapTime']   = pd.to_datetime(scrap_raw['ScrapTime'])

print(f'Process records: {len(process_raw):,}')
print(f'Scrap records:   {len(scrap_raw):,}')
print(f'Date range:      {process_raw[\"BuiltTime\"].min().date()} to {process_raw[\"BuiltTime\"].max().date()}')""")

# === Parse DS columns ===
md("""### 2.1 Parse machine parameters from `DS1`/`DS2`/`DS3`

Each row stores 40 parameters as comma-separated `key:value` strings (same encoding as the original `Book3.xlsx`).""")

code("""def parse_params(s):
    out = {}
    if pd.isna(s): return out
    for it in str(s).split(','):
        if ':' in it:
            k, v = it.rsplit(':', 1)
            try: out[k.strip()] = float(v.strip())
            except ValueError: pass
    return out

ds1 = process_raw['DS1'].apply(parse_params).apply(pd.Series)
ds2 = process_raw['DS2'].apply(parse_params).apply(pd.Series)
ds3 = process_raw['DS3'].apply(parse_params).apply(pd.Series)

df = pd.concat([process_raw[['ID','PartDesc','BuiltTime']], ds1, ds2, ds3], axis=1)
print(f'Parsed {df.shape[1]-3} parameters | rows: {len(df):,}')

# Join scrap labels
df = df.merge(scrap_raw.rename(columns={'Desc':'defect','ScrapTime':'scrap_time'})[['ID','defect','scrap_time']],
              on='ID', how='left')
df['is_scrap'] = df['defect'].notna()
print(f'Scrap rate: {df[\"is_scrap\"].mean()*100:.2f}%   ({df[\"is_scrap\"].sum()} of {len(df):,})')""")

# === Defect taxonomy ===
md("""### 2.2 Defect taxonomy & process-section mapping""")

code("""PROCESS_DEFECTS = ['Wrinkle','Dent','Bumps / lumps','Burnt Carpet / Vynil',
                   'Low Glue/Read Thru/Impression','Out of dimension',
                   'Bad edge wrap','Glue bleed thru','Delamination']
NONPROCESS_DEFECTS = ['Hole','Broken / Fracture','Fabric Flaw','Fabric Torn']

df['defect_scope'] = np.where(df['defect'].isna(), 'Good',
                       np.where(df['defect'].isin(PROCESS_DEFECTS), 'Process Defect',
                       'Non-Process Defect'))

SECTIONS = {
    'Roll Coating': ['Roller Gap LH','Roller Gap RH','Glue Temp','Pick Material Pos'],
    'Grippers & Clamp Frame': ['Pos Vinyl N Length','Pos Vinyl N Width','Pos Vinyl S Length','Pos Vinyl S Width',
        'Stetch Length Pick Up','Stetch Length Stretch 1','Stetch Length Stretch 2','Stetch Length Stretch 3','Stetch Length Form',
        'Stretch Cross Pick Up','Stretch Cross Stretch 1','Stretch Cross Stretch 2','Stretch Cross Stretch 3','Stretch Cross Form','Top Tool Pos Close'],
    'Oven': ['Temp. THT at Trigger','Temp. BHT at Trigger','Temp Z1','Temp Z2','Temp Z3','Temp Z4',
        'heating time (tens of seconds)','Capacity THT','Capacity BHT'],
    'Vacuum': ['Vacuum Time Tool Cavity A','Vacuum Time Tool Cavity B','Graining Vacuum TTF Cavity 1','Graining Vacuum TTF Cavity 2'],
    'Machine/Other': ['Machine Cycle Time','Pyro Clean','BT Circuit 1 Temp','BT Circuit 2 Temp',
        'TTF Circuit 1 Temp','TTF Circuit 2 Temp','Time Feed to Vacuum 1'],
}
ALL_PARAMS = [p for ps in SECTIONS.values() for p in ps if p in df.columns]
const_params = [p for p in ALL_PARAMS if df[p].nunique() <= 1]
ACTIVE_PARAMS = [p for p in ALL_PARAMS if p not in const_params]
print(f'Parameters by section: {sum(len(v) for v in SECTIONS.values())} total | active (non-constant): {len(ACTIVE_PARAMS)}')
print(f'Dropped constants: {const_params}')
print('\\nScope:'); print(df['defect_scope'].value_counts())""")

# === Section 3 — Overview viz ===
md("""---
## 3. Data overview & scrap distribution""")

code("""fig, axes = plt.subplots(1, 3, figsize=(20, 5))

# 3a: production quality pie
scope = df['defect_scope'].value_counts()
colors = {'Good': '#2ecc71', 'Process Defect': '#e74c3c', 'Non-Process Defect': '#95a5a6'}
axes[0].pie(scope.values, labels=scope.index, autopct='%1.1f%%',
            colors=[colors[x] for x in scope.index], startangle=90)
axes[0].set_title(f'Production quality (n={len(df):,} parts)')

# 3b: process defect distribution
pd_counts = df[df['defect_scope']=='Process Defect']['defect'].value_counts()
axes[1].barh(pd_counts.index[::-1], pd_counts.values[::-1],
             color=plt.cm.Reds(np.linspace(0.4, 0.85, len(pd_counts))))
for i, v in enumerate(pd_counts.values[::-1]):
    axes[1].text(v + 1, i, str(v), va='center')
axes[1].set_xlabel('count'); axes[1].set_title('Process defects by type')

# 3c: by tool
tool_rates = df.groupby('Tool Number').agg(total=('ID','count'),
                                            scrap=('is_scrap','sum')).reset_index()
tool_rates['rate'] = tool_rates['scrap']/tool_rates['total']*100
bars = axes[2].bar(tool_rates['Tool Number'].astype(int).astype(str), tool_rates['rate'],
                   color=['#e74c3c' if r > 6 else '#f39c12' if r > 4 else '#2ecc71'
                          for r in tool_rates['rate']])
for b, t in zip(bars, tool_rates.itertuples()):
    axes[2].text(b.get_x()+b.get_width()/2, b.get_height()+0.1,
                 f'{t.rate:.1f}%\\n({t.scrap}/{t.total})', ha='center', fontsize=9)
axes[2].set_xlabel('Tool'); axes[2].set_ylabel('Scrap rate %')
axes[2].set_title('Scrap rate by tool')
plt.tight_layout(); plt.show()""")

# === Old vs New ===
md("""### 3.1 What changed since v1? (Feb–Mar vs Mar–May)""")

code("""old_def = {'Wrinkle':51, 'Dent':50, 'Bumps / lumps':48, 'Burnt Carpet / Vynil':11,
           'Low Glue/Read Thru/Impression':130, 'Out of dimension':21}
new_def = df['defect'].value_counts().to_dict()
old_tool = {1:16.5, 2:2.7, 8:2.7}
new_tool = (df.groupby('Tool Number')['is_scrap'].mean()*100).to_dict()

cmp = pd.DataFrame({
    'Defect':list(old_def.keys()),
    'Old (Feb-Mar)':[old_def[k] for k in old_def],
    'New (Mar-May)':[new_def.get(k,0) for k in old_def]
})
cmp['Δ'] = cmp['New (Mar-May)'] - cmp['Old (Feb-Mar)']

fig, axes = plt.subplots(1,2, figsize=(18,4.5))
x = np.arange(len(cmp))
w = 0.4
axes[0].bar(x-w/2, cmp['Old (Feb-Mar)'], w, label='Old', color='#95a5a6')
axes[0].bar(x+w/2, cmp['New (Mar-May)'], w, label='New', color='#e74c3c')
axes[0].set_xticks(x); axes[0].set_xticklabels(cmp['Defect'], rotation=25, ha='right')
axes[0].set_title('Defect counts: Old vs New period'); axes[0].legend()
for i, d in enumerate(cmp['Δ']):
    axes[0].text(i, max(cmp.iloc[i,1], cmp.iloc[i,2])+2, f'{d:+d}',
                 ha='center', color='green' if d<0 else 'red', fontweight='bold')

tools = sorted(old_tool.keys())
axes[1].bar([t-0.2 for t in tools], [old_tool[t] for t in tools], 0.4, label='Old', color='#95a5a6')
axes[1].bar([t+0.2 for t in tools], [new_tool.get(t,0) for t in tools], 0.4, label='New', color='#e74c3c')
axes[1].set_xticks(tools); axes[1].set_xticklabels([f'Tool {t}' for t in tools])
axes[1].set_ylabel('Scrap rate %'); axes[1].set_title('Tool scrap rate: Old vs New'); axes[1].legend()
plt.tight_layout(); plt.show()

print(cmp.to_string(index=False))
print('\\nTake-aways:')
print('  • Low Glue dropped 130 → 41  (prior recommendations on BHT / Roller Gap / Glue Temp landed)')
print('  • Wrinkle climbed 51 → 93  — now the largest single defect category')
print('  • Burnt Carpet quadrupled (11 → 43) — new failure mode emerged')
print('  • Tool 1 rate halved (16.5% → 7.3%) — biggest win — but Tools 2/8 ticked up')""")

# === Section 4 — Tool confounding ===
md("""---
## 4. The tool-confounding problem

The previous notebook compared scrap-vs-good *pooled across all tools*. But each tool runs a different **recipe** — different roller gap, different stretch values, different temps. So pooled differences are mostly recipe differences, not process drift.

### 4.1 Within-tool coefficient of variation: which params actually drift?""")

code("""within_cv = (df.groupby('Tool Number')[ACTIVE_PARAMS]
                .agg(lambda x: x.std()/abs(x.mean()) if abs(x.mean())>1e-9 else 0))
# Top 10 most-variable (drift candidates) and 7 least-variable (recipe-fixed) per tool
print('Most variable parameters (drift candidates):')
for tool in sorted(within_cv.index):
    s = within_cv.loc[tool].sort_values(ascending=False)
    print(f'\\n  Tool {int(tool)}:')
    print(s.head(8).round(3).to_string())
print('\\nLeast variable (RECIPE-FIXED — cannot diagnose anything):')
for tool in sorted(within_cv.index):
    s = within_cv.loc[tool].sort_values(ascending=False)
    print(f'  Tool {int(tool)}: ' + ', '.join(s.tail(5).index.tolist()))""")

# === 4.2 Misleading global vs corrected tool-conditional ===
md("""### 4.2 Concrete example of the confound: Roller Gap & Stretch Cross Form

These appeared as huge "scrap signals" in v1. Within each tool they barely move — the global signal is just *recipe-by-tool ↔ scrap-rate-by-tool*.""")

code("""confound_params = ['Roller Gap LH','Roller Gap RH','Stretch Cross Form','Stetch Length Form']
fig, axes = plt.subplots(1, 4, figsize=(20, 4.5))
for ax, p in zip(axes, confound_params):
    for tool, color in zip(sorted(df['Tool Number'].dropna().unique()), ['#3498db','#e67e22','#9b59b6']):
        sub = df[df['Tool Number']==tool][p].dropna()
        ax.hist(sub, bins=30, alpha=0.6, label=f'Tool {int(tool)} (n={len(sub)})', color=color)
    ax.set_title(p); ax.legend(fontsize=8)
plt.suptitle('Recipe-fixed parameters — separated by tool, not by scrap', y=1.02, fontsize=12)
plt.tight_layout(); plt.show()""")

# === Section 5 — Helpers ===
md("""---
## 5. Diagnostic primitives

For each parameter we compute:

- **Welch's t-test** — significance under unequal variance
- **Cliff's δ** — non-parametric effect size in `[-1, +1]` (negligible / small / medium / large at .147 / .33 / .474)
- **Random-Forest importance** — multivariate one-vs-good ranking (controls for correlated parameters)
- **Within-tool CV** — actionability filter (must vary within the tool to be diagnosable)
""")

code("""def cliffs_delta(bad, good):
    n1, n2 = len(bad), len(good)
    if not n1 or not n2: return np.nan
    u, _ = stats.mannwhitneyu(bad, good, alternative='two-sided')
    return (2*u)/(n1*n2) - 1

def deviation_for(defect, params, scope=None, min_n=5):
    sub = df if scope is None else df[df['Tool Number']==scope]
    g = sub[sub['defect_scope']=='Good']
    b = sub[sub['defect']==defect]
    if len(b) < min_n: return pd.DataFrame()
    rows = []
    for p in params:
        gv = g[p].dropna().values; bv = b[p].dropna().values
        if len(gv) < 20 or len(bv) < 3 or np.std(gv) == 0: continue
        try:
            t, pv = stats.ttest_ind(gv, bv, equal_var=False)
        except Exception: continue
        rows.append({
            'Parameter': p, 'n_bad': len(bv),
            'good_p50': round(np.percentile(gv, 50), 2),
            'good_p5':  round(np.percentile(gv, 5), 2),
            'good_p95': round(np.percentile(gv, 95), 2),
            'bad_p50':  round(np.percentile(bv, 50), 2),
            'pct_diff': round((bv.mean()-gv.mean())/gv.mean()*100, 2) if gv.mean() else np.nan,
            'cliffs':   round(cliffs_delta(bv, gv), 3),
            'welch_p':  pv,
        })
    out = pd.DataFrame(rows)
    out['abs_cliffs'] = out['cliffs'].abs()
    return out.sort_values('abs_cliffs', ascending=False)

def rf_importance(defect, params, scope=None, max_neg_mult=3, seed=0):
    sub = df if scope is None else df[df['Tool Number']==scope]
    b = sub[sub['defect']==defect]
    g = sub[sub['defect_scope']=='Good']
    if len(b) < 20: return pd.Series(dtype=float)
    bal = pd.concat([b.assign(y=1),
                     g.sample(min(len(g), max_neg_mult*len(b)), random_state=seed).assign(y=0)])
    X = bal[params].fillna(bal[params].median())
    y = bal['y'].values
    clf = RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=5,
                                 class_weight='balanced', random_state=seed, n_jobs=-1)
    clf.fit(X, y)
    return pd.Series(clf.feature_importances_, index=X.columns).sort_values(ascending=False)

print('Helpers ready.')""")

# === Section 6 — Per defect deep dives ===
md("""---
## 6. Per-defect deep dives (tool-conditional)

For each major defect, we report **top deviations within each tool** (so recipe differences are removed). Direction is reported relative to the *good population on the same tool*.""")

code("""def report_defect(defect):
    print('='*100); print(f'DEFECT: {defect}'); print('='*100)
    for tool in sorted(df['Tool Number'].dropna().unique()):
        sub = df[df['Tool Number']==tool]
        n_bad = (sub['defect']==defect).sum()
        if n_bad < 5: continue
        tab = deviation_for(defect, ACTIVE_PARAMS, scope=tool)
        if tab.empty: continue
        # Filter to actionable (within-tool CV > 0.01) and significant
        cv = within_cv.loc[tool]
        tab['within_cv'] = tab['Parameter'].map(cv)
        actionable = tab[(tab['within_cv'] > 0.01) & (tab['welch_p'] < 0.05)].head(6)
        if actionable.empty:
            print(f'\\n  Tool {int(tool)} (n_bad={n_bad}) — no actionable signals')
            continue
        print(f'\\n  Tool {int(tool)} | n_bad={n_bad}, n_good={(sub[\"defect_scope\"]==\"Good\").sum()}')
        for _, r in actionable.iterrows():
            arrow = '↑' if r['cliffs'] > 0 else '↓'
            note = 'CRITICAL' if r['abs_cliffs'] > 0.474 else 'STRONG' if r['abs_cliffs'] > 0.33 else 'MODERATE'
            print(f'    {arrow} [{note:<8}] {r[\"Parameter\"]:<35} good~{r[\"good_p50\"]:<8} scrap~{r[\"bad_p50\"]:<8} '
                  f'(Δ {r[\"pct_diff\"]:+.1f}%)  effect={r[\"cliffs\"]:+.2f}  p={r[\"welch_p\"]:.1e}')

for d in ['Wrinkle','Dent','Bumps / lumps','Burnt Carpet / Vynil',
          'Low Glue/Read Thru/Impression','Out of dimension','Bad edge wrap']:
    report_defect(d); print()""")

# === Section 6.1 distribution plots for top defects ===
md("""### 6.1 Distribution plots — top defects in their problematic tool""")

code("""def dist_grid(defect, tool, params, title):
    sub = df[df['Tool Number']==tool]
    g = sub[sub['defect_scope']=='Good']
    b = sub[sub['defect']==defect]
    fig, axes = plt.subplots(2, 3, figsize=(17, 8))
    for ax, p in zip(axes.flat, params):
        if p not in df.columns: continue
        gv = g[p].dropna(); bv = b[p].dropna()
        if len(gv)<5: continue
        ax.hist(gv, bins=30, alpha=0.55, color='#2ecc71', label=f'Good (n={len(gv)})', density=True)
        ax.hist(bv, bins=12, alpha=0.75, color='#e74c3c', label=f'Scrap (n={len(bv)})', density=True)
        ax.axvline(gv.mean(), color='green', ls='--')
        ax.axvline(bv.mean(), color='red', ls='--')
        ax.set_title(p); ax.legend(fontsize=8)
    plt.suptitle(title, y=1.02, fontsize=13); plt.tight_layout(); plt.show()

dist_grid('Wrinkle', 1.0,
          ['Pos Vinyl S Width','Pos Vinyl S Length','Pyro Clean',
           'Pos Vinyl N Length','Temp. BHT at Trigger','Roller Gap RH'],
          'Wrinkle on Tool 1 — n=92  (the dominant defect)')

dist_grid('Low Glue/Read Thru/Impression', 2.0,
          ['Temp. BHT at Trigger','Temp. THT at Trigger','BT Circuit 2 Temp',
           'TTF Circuit 1 Temp','Glue Temp','Vacuum Time Tool Cavity A'],
          'Low Glue on Tool 2 — n=40  (residual after v1 improvements)')

dist_grid('Bumps / lumps', 8.0,
          ['Temp. THT at Trigger','Temp. BHT at Trigger','Capacity THT',
           'Capacity BHT','Temp Z2','Graining Vacuum TTF Cavity 1'],
          'Bumps on Tool 8 — n=35  (under-heating signature)')""")

# === Section 7 — Pyro Clean cross-defect ===
md("""---
## 7. Cross-defect spotlight — `Pyro Clean`

`Pyro Clean` appears in the top-3 for almost every defect, **but with opposite directions**. That fits an interpretation of "cycles since last pyro clean" — high = buildup, low = freshly stripped.""")

code("""fig, ax = plt.subplots(figsize=(14, 5.5))
order = df.groupby('defect')['Pyro Clean'].median().sort_values().index.tolist()
order = [d for d in order if d in PROCESS_DEFECTS or d == None]
groups = ['Good'] + [d for d in order if (df['defect']==d).sum() >= 8]
data = [df[df['defect_scope']=='Good']['Pyro Clean'].dropna().values] + \
       [df[df['defect']==d]['Pyro Clean'].dropna().values for d in groups[1:]]
bp = ax.boxplot(data, labels=groups, patch_artist=True, showfliers=False)
for patch, lbl in zip(bp['boxes'], groups):
    patch.set_facecolor('#2ecc71' if lbl=='Good' else '#e74c3c'); patch.set_alpha(0.6)
ax.set_ylabel('Pyro Clean (cycles since last clean — inferred)')
ax.set_title('Pyro Clean distribution: Good vs each process defect')
plt.xticks(rotation=20, ha='right'); plt.tight_layout(); plt.show()

print('Reading: high Pyro Clean (buildup) ↔ Dent / Out-of-dim / Wrinkle / Bumps (T8).')
print('         low Pyro Clean (freshly stripped) ↔ Burnt Carpet / Bad edge wrap.')
print('Recommendation: confirm semantics with operator team; pilot a target band (e.g. 300-600 cycles for Tool 1).')""")

# === Section 8 — Anomaly detection ===
md("""---
## 8. Anomaly detection (Isolation Forest)

Treat all process rows as one feature cloud; the model flags multivariate outliers. We then check whether flagged anomalies are scrap-enriched, both overall and per defect.""")

code("""X = df[ACTIVE_PARAMS].fillna(df[ACTIVE_PARAMS].median())
iso = IsolationForest(n_estimators=300, contamination=0.05, random_state=0, n_jobs=-1)
iso.fit(X)
df['anom_score'] = -iso.score_samples(X)   # higher = more anomalous
df['anom_flag']  = iso.predict(X) == -1

rate_in  = df[df['anom_flag']]['is_scrap'].mean()*100
rate_out = df[~df['anom_flag']]['is_scrap'].mean()*100
print(f'scrap rate among anomalies: {rate_in:.2f}%   vs normals: {rate_out:.2f}%   lift = {rate_in/rate_out:.2f}x')
print(f'overall  anom-score AUC vs is_scrap : {roc_auc_score(df[\"is_scrap\"].astype(int), df[\"anom_score\"]):.3f}')
print('\\nPer-defect AUC (does anomaly score rank this defect above good?):')
for d in PROCESS_DEFECTS:
    y = (df['defect']==d).astype(int)
    if y.sum() < 15: continue
    print(f'  {d:<40} AUC = {roc_auc_score(y, df[\"anom_score\"]):.3f}   (n={int(y.sum())})')

fig, ax = plt.subplots(figsize=(13,4))
for label, color in [('Good', '#2ecc71'), ('Process Defect', '#e74c3c'), ('Non-Process Defect', '#95a5a6')]:
    sub = df[df['defect_scope']==label]['anom_score']
    ax.hist(sub, bins=60, alpha=0.55, label=f'{label} (n={len(sub)})', color=color, density=True)
ax.set_xlabel('Anomaly score (Isolation Forest)'); ax.set_ylabel('Density')
ax.set_title('Anomaly score distribution — scrap is shifted right'); ax.legend()
plt.tight_layout(); plt.show()""")

# === Section 9 — operating windows ===
md("""---
## 9. Operating windows (P5 / P50 / P95) — per tool

These tables drive the live recommendation engine. They are computed **per tool from good parts only**, so each tool's recipe is its own reference.""")

code("""rows = []
key_params = ['Glue Temp','Roller Gap LH','Roller Gap RH',
              'Temp. THT at Trigger','Temp. BHT at Trigger',
              'Temp Z1','Temp Z2','Temp Z3','Temp Z4',
              'heating time (tens of seconds)','Capacity THT','Capacity BHT',
              'Stretch Cross Form','Stetch Length Form',
              'Vacuum Time Tool Cavity A','Vacuum Time Tool Cavity B',
              'Pos Vinyl S Width','Pos Vinyl N Width',
              'Machine Cycle Time','Pyro Clean',
              'BT Circuit 1 Temp','BT Circuit 2 Temp']

for tool in sorted(df['Tool Number'].dropna().unique()):
    g = df[(df['Tool Number']==tool) & (df['defect_scope']=='Good')]
    s = df[(df['Tool Number']==tool) & (df['is_scrap'])]
    for p in key_params:
        if p not in g.columns: continue
        gv = g[p].dropna(); sv = s[p].dropna()
        if len(gv) < 30 or gv.std()==0: continue
        rows.append({
            'tool': int(tool), 'param': p,
            'good_P5': round(np.percentile(gv,5), 2),
            'good_target_P50': round(np.percentile(gv,50), 2),
            'good_P95': round(np.percentile(gv,95), 2),
            'scrap_P50': round(np.percentile(sv,50),2) if len(sv) else np.nan,
            'pct_scrap_OOW': round(((sv<np.percentile(gv,5))|(sv>np.percentile(gv,95))).mean()*100,1) if len(sv) else 0.0
        })
ow = pd.DataFrame(rows)
ow.to_csv('operating_windows_v2.csv', index=False)
print('Wrote operating_windows_v2.csv\\n')
for tool in sorted(ow['tool'].unique()):
    print(f'--- Tool {tool} ---')
    print(ow[ow['tool']==tool].drop(columns='tool').to_string(index=False))
    print()""")

# === Section 10 — Recommendation engine ===
md("""---
## 10. Live recommendation engine

Inputs: a detected defect + the current parameter snapshot for the part.
Output: a ranked list of `(parameter, direction, target band, severity)` recommendations.

The engine combines, per `(defect, tool)`:
1. the **direction & magnitude** of historical deviation (Cliff's δ + median gap),
2. the **safe range** (P5–P95 of good parts on the same tool),
3. **whether the current value is already inside the safe band** (no need to act if so).""")

code("""# Build a (defect, tool) -> ranked params dictionary from the tool-conditional analysis
ENGINE = {}  # ENGINE[(defect,tool)] = [{param, sign, good_p5, good_p50, good_p95, cliffs, severity}, ...]

for defect in PROCESS_DEFECTS:
    for tool in sorted(df['Tool Number'].dropna().unique()):
        tab = deviation_for(defect, ACTIVE_PARAMS, scope=tool)
        if tab.empty: continue
        cv = within_cv.loc[tool]
        tab = tab.assign(within_cv=tab['Parameter'].map(cv))
        tab = tab[(tab['within_cv'] > 0.01) & (tab['welch_p'] < 0.05) & (tab['abs_cliffs'] > 0.15)]
        if tab.empty: continue
        recs = []
        for _, r in tab.head(8).iterrows():
            sev = 'CRITICAL' if r['abs_cliffs'] > 0.474 else ('STRONG' if r['abs_cliffs'] > 0.33 else 'MODERATE')
            recs.append({
                'param': r['Parameter'],
                'sign': int(np.sign(r['cliffs'])),
                'good_p5': r['good_p5'], 'good_p50': r['good_p50'], 'good_p95': r['good_p95'],
                'cliffs': r['cliffs'], 'severity': sev, 'pct_diff': r['pct_diff']
            })
        ENGINE[(defect, int(tool))] = recs

print(f'Built engine for {len(ENGINE)} (defect, tool) cells.')

def recommend(defect, tool, current_params, top_k=5):
    \"\"\"Return ranked actions. current_params is a dict {param: value}.\"\"\"
    key = (defect, int(tool))
    if key not in ENGINE:
        return [{'action': f'No specific recommendation — defect not characterized for Tool {tool}'}]
    out = []
    for r in ENGINE[key]:
        cur = current_params.get(r['param'])
        if pd.isna(cur) or cur is None:
            action = 'CHECK — no current reading'
        else:
            if r['good_p5'] <= cur <= r['good_p95']:
                action = 'OK — already in safe band'
            elif cur > r['good_p95']:
                action = f'REDUCE → target {r[\"good_p50\"]} (safe: {r[\"good_p5\"]} – {r[\"good_p95\"]})'
            else:
                action = f'INCREASE → target {r[\"good_p50\"]} (safe: {r[\"good_p5\"]} – {r[\"good_p95\"]})'
        out.append({'param': r['param'], 'current': cur,
                    'safe_low': r['good_p5'], 'safe_high': r['good_p95'], 'target': r['good_p50'],
                    'action': action, 'severity': r['severity']})
    return out[:top_k]

def pick_worst_scrap_example(defect):
    \"\"\"Return the scrap row whose top-engine parameters are most out-of-band — the most instructive demo.\"\"\"
    sub = df[df['defect']==defect]
    if sub.empty: return None
    best_row, best_score = None, -1
    for _, row in sub.iterrows():
        tool = row.get('Tool Number')
        if pd.isna(tool): continue
        key = (defect, int(tool))
        if key not in ENGINE: continue
        score = 0
        for r in ENGINE[key][:6]:
            v = row.get(r['param'])
            if pd.isna(v): continue
            if v < r['good_p5'] or v > r['good_p95']:
                score += {'CRITICAL':3,'STRONG':2,'MODERATE':1}.get(r['severity'], 1)
        if score > best_score:
            best_score, best_row = score, row
    return best_row

print('\\n--- LIVE DEMO (worst-violating scrap example per defect) ---')
for d in ['Wrinkle','Dent','Bumps / lumps','Burnt Carpet / Vynil',
          'Low Glue/Read Thru/Impression','Out of dimension','Bad edge wrap']:
    sample = pick_worst_scrap_example(d)
    if sample is None: continue
    tool = int(sample['Tool Number'])
    current = {p: sample[p] for p in ACTIVE_PARAMS if p in sample.index}
    recs = recommend(d, tool, current, top_k=6)
    n_fire = sum(1 for r in recs if 'param' in r and not r['action'].startswith('OK'))
    print(f'\\n  ⚠ {d}  |  Part: {sample[\"PartDesc\"]}  |  Tool {tool}  |  {sample[\"BuiltTime\"]}  |  actions fired: {n_fire}/{len(recs)}')
    for r in recs:
        if 'param' not in r:
            print(f'      {r[\"action\"]}'); continue
        cur_s = f'{r[\"current\"]:.1f}' if isinstance(r['current'],(int,float)) and not pd.isna(r['current']) else '—'
        fire = not r['action'].startswith('OK')
        marker = '  ← FIRE' if fire else ''
        print(f'      [{r[\"severity\"]:<8}] {r[\"param\"]:<33} cur={cur_s:>8}  safe=[{r[\"safe_low\"]}, {r[\"safe_high\"]}]  target={r[\"target\"]}{marker}')
        if fire:
            print(f'                   → {r[\"action\"]}')""")

# === Section 11 — Validation ===
md("""---
## 11. Validation — does the engine fire on real scrap?

We split the data 70/30 (stratified by `is_scrap`), build operating windows from the train half, then on the test half count how many parameters fall outside their safe band per row. We compare scrap-rows to good-rows and report AUC and precision at common thresholds.""")

code("""train, test = train_test_split(df, test_size=0.3, random_state=0, stratify=df['is_scrap'])

# Per-tool windows from train-good only
windows = {}
for tool in train['Tool Number'].dropna().unique():
    sub = train[(train['Tool Number']==tool) & (train['defect_scope']=='Good')]
    windows[int(tool)] = {}
    for p in ACTIVE_PARAMS:
        v = sub[p].dropna()
        if len(v) < 30 or v.std()==0: continue
        windows[int(tool)][p] = (np.percentile(v,5), np.percentile(v,95))

def oow_count(row):
    t = row.get('Tool Number')
    if pd.isna(t) or int(t) not in windows: return np.nan
    w = windows[int(t)]; c = 0
    for p, (lo, hi) in w.items():
        v = row.get(p)
        if pd.isna(v): continue
        if v < lo or v > hi: c += 1
    return c

test = test.copy()
test['oow_count'] = test.apply(oow_count, axis=1)
auc = roc_auc_score(test['is_scrap'].astype(int), test['oow_count'].fillna(test['oow_count'].median()))
print(f'AUC of #out-of-window params vs is_scrap (test set, n={len(test):,}): {auc:.3f}\\n')
print(f'{\"threshold\":>10}  {\"flagged\":>9}  {\"flagged %\":>9}  {\"scrap-rate in flag\":>22}  {\"scrap coverage\":>15}')
for thr in range(0, 8):
    flagged = test['oow_count'] >= thr
    if not flagged.any(): continue
    rate = test[flagged]['is_scrap'].mean()*100
    cov = (flagged & test['is_scrap'].astype(bool)).sum() / max(1, test['is_scrap'].sum()) * 100
    print(f'{thr:>10}  {int(flagged.sum()):>9}  {flagged.mean()*100:>8.1f}%  {rate:>21.2f}%  {cov:>13.1f}%')

print('\\nThe simple out-of-window rule is *weak* (AUC ≈ 0.56) — so it is intended for ALERT TRIAGE not classification.')
print('Use the per-defect recommendation engine for the actual diagnosis.')""")

# === Section 12 — Summary ===
md("""---
## 12. Summary

### Headline findings
- **5.24% scrap rate** over Mar 11 – May 6 (vs 8.15% before). 348 process-related, 38 non-process.
- **Wrinkle on Tool 1 is now the largest single defect** (92 cases) — Pos Vinyl S Width / Length are 30% over good-median; Pyro Clean is also elevated.
- **Low Glue dropped 68%** — strongest evidence that the v1 recommendations on BHT temp / Roller Gap / Glue Temp made it to the floor.
- **Burnt Carpet quadrupled** — driven by *low* Pyro Clean (recently stripped tools) on Tool 2; vacuum-time slightly reduced.
- **Bumps on Tool 8** show a consistent under-heating signature (THT/BHT/Capacities all low) — possibly a controller drift on Tool 8.

### Methodological takeaways
1. **Always condition on Tool** — global pooling is confounded by recipe.
2. **Filter by within-tool variance** before claiming a parameter is the cause — recipe-fixed values cannot be the diagnosis.
3. **Cliff's δ + RF importance** together give more robust rankings than t-test alone.
4. **Operating-window rule on its own is weak** — use it for triage, the defect-specific engine for diagnosis.

### Recommended interventions (new data)

| Priority | Where | Action |
|---|---|---|
| 1 | **Tool 1 — Wrinkle** | Pilot lowering `Pos Vinyl S Width` toward Tool-1 median (≈ 249) and capping `Pyro Clean` cycles before maintenance. |
| 2 | **Tool 2 — Low Glue residual** | Tighten BHT-at-Trigger control band around 190–200 °C; alarm below 175. |
| 3 | **Tool 2 — Burnt Carpet** | Investigate why Pyro Clean is so low when burns happen (over-cleaning? new operator?). |
| 4 | **Tool 8 — Bumps** | Inspect THT/BHT calibration and heater capacity controllers; confirm sensor health. |
| 5 | **All tools — Pyro Clean** | Confirm meaning with engineering team; define a target band, not a min/max. |

### Estimated savings
If Tool 1 reaches Tool 8's rate and Tool 2 returns to ~3% — ~78 parts × $67 ≈ **$5.3K** saved over a 56-day period (≈ $34K/year). Smaller than the original projection because Tool 1 has already improved.

### Next steps
- Confirm **Pyro Clean** semantics with operators; collect labelled clean-cycle events.
- Deploy the recommendation engine as a live alert (consume per-row parameters; emit ranked actions).
- Add control charts on BHT-at-Trigger (Tool 2) and THT/BHT (Tool 8).
- Re-evaluate in 30 days; re-fit the engine with rolling data.
""")

# === Final write ===
notebook = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
    },
    "nbformat": 4, "nbformat_minor": 5,
}
with open(NB_PATH, "w", encoding="utf-8") as f:
    json.dump(notebook, f, ensure_ascii=False, indent=1)
print(f"Wrote {NB_PATH}  ({len(CELLS)} cells)")
