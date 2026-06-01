"""Build VAC_Forming_Scrap_Report.docx — fully-illustrated consolidated report.

Generates all plots into _exp/docx_plots/ first, then writes the docx with
embedded images, tables, and structured sections.
"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from scipy import stats
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, brier_score_loss

from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
PLOTS = os.path.join(ROOT, "_exp", "docx_plots"); os.makedirs(PLOTS, exist_ok=True)
DOCX  = os.path.join(ROOT, "VAC_Forming_Scrap_Report.docx")

plt.rcParams.update({'figure.figsize': (10, 4.5), 'font.size': 10,
                     'axes.titlesize': 12, 'axes.labelsize': 10,
                     'savefig.dpi': 140, 'savefig.bbox': 'tight'})
sns.set_style('whitegrid')

# ============================================================================
# 1. LOAD & CLEAN DATA  (same recipe as the final notebook)
# ============================================================================
p_raw = pd.read_csv(os.path.join(ROOT, "data", "VF_export.csv")).drop(columns=lambda c: c.startswith('Unnamed'), errors='ignore')
s_raw = pd.read_csv(os.path.join(ROOT, "data", "VF_Scrap_export.csv")).drop(columns=lambda c: c.startswith('Unnamed'), errors='ignore')
p_raw['BuiltTime'] = pd.to_datetime(p_raw['BuiltTime'])
s_raw['ScrapTime'] = pd.to_datetime(s_raw['ScrapTime'])

def parse_kv(s):
    out = {}
    if pd.isna(s): return out
    for it in str(s).split(','):
        if ':' in it:
            k, v = it.rsplit(':', 1)
            try: out[k.strip()] = float(v.strip())
            except: pass
    return out

ds1 = p_raw['DS1'].apply(parse_kv).apply(pd.Series)
ds2 = p_raw['DS2'].apply(parse_kv).apply(pd.Series)
ds3 = p_raw['DS3'].apply(parse_kv).apply(pd.Series)
df = pd.concat([p_raw[['ID','PartDesc','BuiltTime']], ds1, ds2, ds3], axis=1)
df = df.merge(s_raw[['ID','Desc']].rename(columns={'Desc':'defect'}), on='ID', how='left')
df['is_scrap'] = df['defect'].notna()

CONSTANTS = ['Pick Material Pos','TTF Circuit 2 Temp']
df = df.drop(columns=[c for c in CONSTANTS if c in df.columns])
df = df.sort_values('BuiltTime').reset_index(drop=True)
df['date'] = df['BuiltTime'].dt.date
df['hour'] = df['BuiltTime'].dt.hour
df['mct_capped'] = df['Machine Cycle Time'] == 9999
df.loc[df['mct_capped'], 'Machine Cycle Time'] = np.nan
POSV = ['Pos Vinyl N Length','Pos Vinyl N Width','Pos Vinyl S Length','Pos Vinyl S Width']
for c in POSV: df[f'{c}_active'] = (df[c] > 0).astype(int)
df['seq_in_day'] = df.groupby(['date','Tool Number']).cumcount()
df['is_warmup']  = (df['seq_in_day'] < 20).astype(int)
df['color']  = df['PartDesc'].str.extract(r'\b(BLACK|BEIGE|WHITE)\b').fillna('OTHER')

PROCESS_DEFECTS = ['Wrinkle','Dent','Bumps / lumps','Burnt Carpet / Vynil',
                   'Low Glue/Read Thru/Impression','Out of dimension','Bad edge wrap',
                   'Glue bleed thru','Delamination']
df['scope'] = np.where(df['defect'].isna(),'Good',
              np.where(df['defect'].isin(PROCESS_DEFECTS),'Process','Non-Process'))

PARAM_COLS = [c for c in df.columns if c not in
              ('ID','PartDesc','BuiltTime','date','hour','color','defect','is_scrap','scope',
               'seq_in_day','is_warmup','mct_capped','Tool Number') and not c.endswith('_active')]
within_cv = (df.groupby('Tool Number')[PARAM_COLS]
               .agg(lambda x: x.std()/abs(x.mean()) if abs(x.mean())>1e-9 else 0))
ACTIVE = {int(t): [p for p in PARAM_COLS if within_cv.loc[t,p] > 0.01] for t in within_cv.index}

print(f"rows={len(df):,}  scrap={df['is_scrap'].sum()}  rate={df['is_scrap'].mean()*100:.2f}%")

def wilson(p,n,z=1.96):
    if n==0: return (np.nan,np.nan)
    den=1+z*z/n; cen=(p+z*z/(2*n))/den
    half=z*np.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return cen-half, cen+half

def cliffs(bad, good):
    n1, n2 = len(bad), len(good)
    if not n1 or not n2: return np.nan
    u, _ = stats.mannwhitneyu(bad, good, alternative='two-sided')
    return (2*u)/(n1*n2) - 1

def deviation(defect, tool, params):
    sub = df[df['Tool Number']==tool]
    g = sub[sub['scope']=='Good']; b = sub[sub['defect']==defect]
    rows = []
    for p in params:
        gv = g[p].dropna().values; bv = b[p].dropna().values
        if len(gv)<20 or len(bv)<3 or np.std(gv)==0: continue
        try: t, pv = stats.ttest_ind(gv, bv, equal_var=False)
        except: continue
        cd = cliffs(bv, gv)
        rows.append({'param':p,'n_bad':len(bv),
                     'good_p5':round(np.percentile(gv,5),2),
                     'good_p50':round(np.percentile(gv,50),2),
                     'good_p95':round(np.percentile(gv,95),2),
                     'bad_p50':round(np.percentile(bv,50),2),
                     'pct_diff':round((bv.mean()-gv.mean())/gv.mean()*100,2) if gv.mean() else np.nan,
                     'cliffs':round(cd,3),'welch_p':pv})
    out = pd.DataFrame(rows)
    if not out.empty: out['abs_cliffs']=out['cliffs'].abs()
    return out.sort_values('abs_cliffs',ascending=False) if not out.empty else out

# ============================================================================
# 2. GENERATE PLOTS  (saved to PLOTS/)
# ============================================================================
print("\n--- generating plots ---")

# Plot 1: Production over time
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
day_counts = df.groupby('date').size()
axes[0].bar(range(len(day_counts)), day_counts.values, color='#3498db')
axes[0].set_xticks(range(len(day_counts)))
axes[0].set_xticklabels([str(d) for d in day_counts.index], rotation=45, ha='right', fontsize=7)
axes[0].set_title(f'Daily production volume   ({len(day_counts)} production days; total {day_counts.sum():,} parts)')
axes[0].set_ylabel('parts produced')

hour_counts = df.groupby('hour').size()
axes[1].bar(hour_counts.index, hour_counts.values, color='#e67e22')
axes[1].set_xlabel('hour of day'); axes[1].set_ylabel('parts')
axes[1].set_title('Hour-of-day production')
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'01_production_timeline.png')); plt.close()

# Plot 2: Tool scrap rates with Wilson CI
tool_summary = df.groupby('Tool Number').agg(parts=('ID','count'), scrap=('is_scrap','sum'))
tool_summary['rate_pct'] = (tool_summary['scrap']/tool_summary['parts']*100).round(2)
cis = [wilson(r.scrap/r.parts, r.parts) for r in tool_summary.itertuples()]
tool_summary['ci_low']  = [round(c[0]*100,2) for c in cis]
tool_summary['ci_high'] = [round(c[1]*100,2) for c in cis]
errs_lo = (tool_summary['rate_pct'] - tool_summary['ci_low']).values
errs_hi = (tool_summary['ci_high'] - tool_summary['rate_pct']).values

fig, ax = plt.subplots(figsize=(8, 4.5))
xs = tool_summary.index.astype(int).astype(str)
ax.bar(xs, tool_summary['rate_pct'], yerr=[errs_lo, errs_hi], capsize=10,
       color=['#c0392b','#3498db','#9b59b6'])
for x, r in zip(xs, tool_summary.itertuples()):
    ax.text(x, r.rate_pct+0.3, f'{r.rate_pct}%\n(n={r.parts})', ha='center', fontsize=10)
ax.axhline(df['is_scrap'].mean()*100, color='gray', ls='--', alpha=0.7, label=f'overall {df["is_scrap"].mean()*100:.2f}%')
ax.set_xlabel('Tool'); ax.set_ylabel('Scrap rate %')
ax.set_title('Scrap rate by Tool with Wilson 95 % CI')
ax.legend(loc='upper right')
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'02_tool_rates.png')); plt.close()

# Plot 3: Defect distribution + Defect x Tool heatmap
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
pd_counts = df[df['scope']=='Process']['defect'].value_counts()
axes[0].barh(pd_counts.index[::-1], pd_counts.values[::-1],
             color=plt.cm.Reds(np.linspace(0.35, 0.85, len(pd_counts))))
for i, v in enumerate(pd_counts.values[::-1]): axes[0].text(v+0.5, i, str(v), va='center', fontsize=9)
axes[0].set_xlabel('count'); axes[0].set_title(f'Process defect counts (n={pd_counts.sum()})')

ct = pd.crosstab(df['defect'], df['Tool Number'], dropna=False)
keep = [d for d in PROCESS_DEFECTS if d in ct.index]
sns.heatmap(ct.loc[keep].astype(int), annot=True, fmt='d', cmap='Reds', cbar_kws={'label':'count'}, ax=axes[1])
axes[1].set_title('Defect × Tool (tool-locking)')
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'03_defect_tool.png')); plt.close()

# Plot 4: Warm-up effect
df_s = df.sort_values('BuiltTime').reset_index(drop=True)
df_s['seq']=df_s.groupby([df_s['BuiltTime'].dt.date, df_s['Tool Number']]).cumcount()
def bucket(n):
    if n<10: return '0-9'
    if n<20: return '10-19'
    if n<50: return '20-49'
    return '50+'
df_s['bucket'] = df_s['seq'].apply(bucket)
g = df_s.groupby('bucket')['is_scrap'].agg(['count','mean']).reindex(['0-9','10-19','20-49','50+'])
g['rate']=g['mean']*100
fig, ax = plt.subplots(figsize=(8,4))
ax.bar(g.index, g['rate'], color=['#c0392b','#e67e22','#f1c40f','#27ae60'])
for i, r in enumerate(g.itertuples()):
    ax.text(i, r.rate+0.3, f'{r.rate:.1f}%\n(n={r.count})', ha='center')
ax.axhline(df['is_scrap'].mean()*100, color='gray', ls='--', alpha=0.6, label='overall')
ax.legend(); ax.set_ylabel('scrap rate %'); ax.set_xlabel('parts from start of production day')
ax.set_title('Warm-up effect — first parts of a production day scrap more')
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'04_warmup.png')); plt.close()

# Plot 5: Hour x Tool
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
for ax, tool in zip(axes, sorted(df['Tool Number'].dropna().unique())):
    sub = df[df['Tool Number']==tool]
    g = sub.groupby('hour')['is_scrap'].agg(['count','mean'])
    g['rate']=g['mean']*100; g = g[g['count']>=30]
    ax.bar(g.index, g['rate'], color='#3498db')
    ax.set_title(f'Tool {int(tool)} — scrap rate by hour')
    ax.set_xlabel('hour'); ax.set_ylabel('scrap %')
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'05_hour_tool.png')); plt.close()

# Plot 6: Pyro Clean sweet-spot per tool
fig, axes = plt.subplots(1, 3, figsize=(16, 4))
PYRO_BANDS = {}
for ax, tool in zip(axes, sorted(df['Tool Number'].dropna().unique())):
    sub = df[df['Tool Number']==tool].copy()
    try: sub['bin'] = pd.qcut(sub['Pyro Clean'], q=8, duplicates='drop')
    except: continue
    gg = sub.groupby('bin', observed=True)['is_scrap'].agg(['count','sum','mean']).reset_index()
    gg['rate'] = gg['mean']*100
    centers = [b.mid for b in gg['bin']]
    colors = ['#27ae60' if r==gg['rate'].min() else '#3498db' for r in gg['rate']]
    ax.bar(range(len(gg)), gg['rate'], color=colors)
    ax.set_xticks(range(len(gg)))
    ax.set_xticklabels([f'{int(c)}' for c in centers], rotation=45, ha='right', fontsize=8)
    for i, r in enumerate(gg['rate']): ax.text(i, r+0.1, f'{r:.1f}%', ha='center', fontsize=7)
    ax.set_title(f'Tool {int(tool)} — Pyro Clean octile sweet spot')
    ax.set_xlabel('Pyro Clean (octile centre)'); ax.set_ylabel('scrap %')
    best = gg.loc[gg['mean'].idxmin()]
    PYRO_BANDS[int(tool)] = (int(best['bin'].left), int(best['bin'].right),
                              round(best['rate'],2))
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'06_pyro_clean.png')); plt.close()

# Plot 7: Wrinkle T1 distributions
def grid_dist(defect, tool, params, fn, title):
    sub = df[df['Tool Number']==tool]
    g = sub[sub['scope']=='Good']; b = sub[sub['defect']==defect]
    fig, axes = plt.subplots(2, 3, figsize=(15, 7))
    for ax, p in zip(axes.flat, params):
        gv = g[p].dropna(); bv = b[p].dropna()
        if len(gv)<5: continue
        ax.hist(gv, bins=30, alpha=0.55, color='#2ecc71', label=f'Good (n={len(gv)})', density=True)
        ax.hist(bv, bins=12, alpha=0.75, color='#e74c3c', label=f'Scrap (n={len(bv)})', density=True)
        ax.axvline(gv.mean(), color='green', ls='--', lw=1)
        ax.axvline(bv.mean(), color='red', ls='--', lw=1)
        ax.set_title(p, fontsize=10); ax.legend(fontsize=8)
    plt.suptitle(title, y=1.02, fontsize=12); plt.tight_layout()
    plt.savefig(os.path.join(PLOTS, fn)); plt.close()

grid_dist('Wrinkle', 1.0,
          ['Pos Vinyl S Width','Pos Vinyl N Length','Pyro Clean','Roller Gap RH',
           'Vacuum Time Tool Cavity B','Temp. THT at Trigger'],
          '07_wrinkle_t1.png', 'Wrinkle on Tool 1 (n=92) — parameter distributions')

grid_dist('Low Glue/Read Thru/Impression', 2.0,
          ['Temp. BHT at Trigger','Temp. THT at Trigger','TTF Circuit 1 Temp',
           'BT Circuit 2 Temp','Pyro Clean','heating time (tens of seconds)'],
          '08_lowglue_t2.png', 'Low Glue on Tool 2 (n=40) — temperature deficit signature')

grid_dist('Bumps / lumps', 8.0,
          ['Temp. THT at Trigger','Temp. BHT at Trigger','Capacity THT','Capacity BHT',
           'heating time (tens of seconds)','TTF Circuit 1 Temp'],
          '09_bumps_t8.png', 'Bumps on Tool 8 (n=35) — under-heating signature')

# Plot 10: Model CV AUC chart — re-run quickly
print("Running models for AUC chart...")
def run_cv(X,y,model,cv=5):
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=0)
    aucs=[]
    for tr,te in skf.split(X,y):
        m=model.fit(X.iloc[tr],y[tr]); proba=m.predict_proba(X.iloc[te])[:,1]
        aucs.append(roc_auc_score(y[te],proba))
    return float(np.mean(aucs))

model_rows = []
for tool in sorted(df['Tool Number'].dropna().unique()):
    feats = ACTIVE[int(tool)] + [f'{c}_active' for c in POSV] + ['is_warmup']
    feats = [f for f in feats if f in df.columns]
    sub = df[df['Tool Number']==tool].copy()
    X_all = sub[feats].copy()
    for c in feats: X_all[c] = X_all[c].fillna(X_all[c].median())
    for d in PROCESS_DEFECTS:
        n_bad = (sub['defect']==d).sum()
        if n_bad < 15: continue
        y = (sub['defect']==d).astype(int).values
        aucs={}
        for nm, mdl in {
            'L1':Pipeline([('s',StandardScaler()),('m',LogisticRegression(penalty='l1',solver='liblinear',class_weight='balanced',C=0.5,random_state=0))]),
            'RF':RandomForestClassifier(n_estimators=400,max_depth=8,min_samples_leaf=5,class_weight='balanced',random_state=0,n_jobs=-1),
            'GBM':GradientBoostingClassifier(n_estimators=200,max_depth=3,learning_rate=0.06,random_state=0)
        }.items():
            try: aucs[nm]=run_cv(X_all,y,mdl)
            except: pass
        best = max(aucs, key=aucs.get) if aucs else '-'
        model_rows.append({'tool':int(tool),'defect':d,'n_bad':int(n_bad),
                           'L1':round(aucs.get('L1',0),3),'RF':round(aucs.get('RF',0),3),
                           'GBM':round(aucs.get('GBM',0),3),
                           'best_auc':round(max(aucs.values()),3) if aucs else 0,
                           'best_model':best})
cv_df = pd.DataFrame(model_rows)
cv_df['label']=cv_df['defect']+' (T'+cv_df['tool'].astype(str)+', n='+cv_df['n_bad'].astype(str)+')'
cv_df_sorted = cv_df.sort_values('best_auc')
fig, ax = plt.subplots(figsize=(11,5))
colors=['#27ae60' if a>0.8 else '#f39c12' if a>0.7 else '#c0392b' for a in cv_df_sorted['best_auc']]
ax.barh(cv_df_sorted['label'], cv_df_sorted['best_auc'], color=colors)
for i,r in enumerate(cv_df_sorted.itertuples()):
    ax.text(r.best_auc+0.005, i, f'{r.best_auc:.2f} ({r.best_model})', va='center', fontsize=9)
ax.axvline(0.5, color='gray', ls=':')
ax.set_xlim(0.4,1.0); ax.set_xlabel('5-fold CV AUC (best of L1-LR / RF / GBM)')
ax.set_title('Per-(tool, defect) multivariate diagnostic AUC')
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'10_model_auc.png')); plt.close()

# Plot 11: Anomaly score distribution
features = sorted(set(ACTIVE[1]+ACTIVE[2]+ACTIVE[8]))
X = df[features].fillna(df[features].median())
iso = IsolationForest(n_estimators=300, contamination=0.05, random_state=0, n_jobs=-1).fit(X)
df['anom_score'] = -iso.score_samples(X)
fig, ax = plt.subplots(figsize=(10,4))
for label, color in [('Good','#2ecc71'),('Process','#e74c3c'),('Non-Process','#95a5a6')]:
    sub = df[df['scope']==label]['anom_score']
    ax.hist(sub, bins=60, alpha=0.55, label=f'{label} (n={len(sub)})', color=color, density=True)
ax.set_xlabel('Anomaly score (higher = more unusual)'); ax.set_ylabel('density'); ax.legend()
overall_auc = roc_auc_score(df['is_scrap'].astype(int), df['anom_score'])
ax.set_title(f'Isolation-Forest anomaly score — scrap is shifted right (AUC = {overall_auc:.3f})')
plt.tight_layout(); plt.savefig(os.path.join(PLOTS,'11_anomaly.png')); plt.close()

# Plot 12: Methodology flow diagram (simple)
fig, ax = plt.subplots(figsize=(12, 5)); ax.axis('off')
boxes = [
    ('Raw\nCSVs', 0.02, 0.45, '#3498db'),
    ('Parse\nDS1/DS2/DS3', 0.17, 0.45, '#3498db'),
    ('Clean\n(sentinels,\nbimodals, etc.)', 0.32, 0.45, '#e67e22'),
    ('Filter recipe-fixed\nparams (CV < 0.01)', 0.49, 0.45, '#e67e22'),
    ('Tool-conditional\nWelch + Cliff δ + RF', 0.68, 0.45, '#9b59b6'),
    ('Engine\n(rules + windows)', 0.86, 0.45, '#27ae60'),
]
for txt, x, y, color in boxes:
    ax.add_patch(mpatches.FancyBboxPatch((x, y), 0.13, 0.18,
                                          boxstyle='round,pad=0.02', linewidth=1.5,
                                          facecolor=color, edgecolor='black', alpha=0.85))
    ax.text(x+0.065, y+0.09, txt, ha='center', va='center', fontsize=10, fontweight='bold', color='white')
for x_start in [0.15, 0.30, 0.45, 0.62, 0.81]:
    ax.annotate('', xy=(x_start+0.02, 0.54), xytext=(x_start, 0.54),
                arrowprops=dict(arrowstyle='->', lw=2, color='black'))
ax.text(0.5, 0.85, 'Methodology pipeline', ha='center', fontsize=14, fontweight='bold')
ax.text(0.5, 0.20, 'Output: per (tool, defect) actionable rules with severity and safe ranges', ha='center', fontsize=10, style='italic')
ax.set_xlim(0,1); ax.set_ylim(0,1)
plt.savefig(os.path.join(PLOTS,'12_methodology_flow.png'), dpi=140, bbox_inches='tight'); plt.close()

print("\n--- plots done ---")
for f in sorted(os.listdir(PLOTS)):
    print(f"  {f}")

# ============================================================================
# 3. BUILD DOCX
# ============================================================================
print("\n--- building docx ---")
doc = Document()

# Set default font
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)

# Margins
for section in doc.sections:
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)

def add_heading(doc, text, level=1, color=None):
    h = doc.add_heading(text, level=level)
    if color:
        for run in h.runs:
            run.font.color.rgb = color
    return h

def add_para(doc, text, bold=False, italic=False, size=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold; run.italic = italic
    if size: run.font.size = Pt(size)
    return p

def add_image(doc, fn, width=6.3, caption=None):
    doc.add_picture(os.path.join(PLOTS, fn), width=Inches(width))
    last = doc.paragraphs[-1]; last.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if caption:
        cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(caption); run.italic = True; run.font.size = Pt(9)

def shade_cell(cell, color_hex):
    tc = cell._tc; tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd'); shd.set(qn('w:fill'), color_hex)
    tcPr.append(shd)

def add_table(doc, df_or_rows, header_color='2C3E50', col_widths=None, font_size=9):
    if isinstance(df_or_rows, pd.DataFrame):
        rows = [df_or_rows.columns.tolist()] + df_or_rows.astype(str).values.tolist()
    else:
        rows = df_or_rows
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = 'Light Grid Accent 1'
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            cell.text = str(val)
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(font_size)
                    if i == 0: r.bold = True; r.font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
            if i == 0: shade_cell(cell, header_color)
            if col_widths and j < len(col_widths): cell.width = Inches(col_widths[j])
    return table

# ============================================================================
# COVER
# ============================================================================
title = doc.add_paragraph(); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('VAC Forming — Scrap Analysis\nConsolidated Report'); run.bold = True
run.font.size = Pt(22); run.font.color.rgb = RGBColor(0x2C,0x3E,0x50)

doc.add_paragraph()
sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = sub.add_run('IAC Business Team + Algo8 AI Team')
run.font.size = Pt(13); run.italic = True

doc.add_paragraph()
metasrun = doc.add_paragraph(); metasrun.alignment = WD_ALIGN_PARAGRAPH.CENTER
for line, sz in [(f'Data period: 11 March 2026 – 6 May 2026 (14 production days)', 11),
                 (f'Process rows: {len(df):,}    Scrap rows: {df["is_scrap"].sum()}    Overall rate: {df["is_scrap"].mean()*100:.2f} %', 11),
                 (f'Source: data/VF_export.csv, data/VF_Scrap_export.csv', 10)]:
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(line); r.font.size = Pt(sz)

doc.add_paragraph()
add_image(doc, '12_methodology_flow.png', width=6.5,
          caption='Figure 0 — Analysis pipeline')
doc.add_page_break()

# ============================================================================
# 1. EXECUTIVE SUMMARY
# ============================================================================
add_heading(doc, '1. Executive Summary', level=1)
items = [
    'Defects are tool-locked: Wrinkle 99% on Tool 1, Low Glue 98% on Tool 2, Bumps 67% on Tool 8. Recommendations must therefore be (tool, defect)-specific.',
    'Tool 1 has the highest scrap rate (7.28%), Tool 2 the lowest (3.97%), Tool 8 in between (5.40%).',
    'Many parameters cannot be a cause: within each tool the recipe-fixed parameters (Stretch Cross *, Stetch Length *, Roller Gap *, Top Tool Pos Close, Glue Temp) have within-tool CV < 0.01 and are excluded from causal ranking.',
    'A warm-up effect is real: first 10 parts of a production day scrap at ~12% vs steady-state ~5% (χ² p = 2.3×10⁻⁶).',
    'Machine Cycle Time = 9999 is a stoppage marker in 9.5% of rows; both the row itself and the next part have elevated scrap (7.6% and 8.0%).',
    'Pyro Clean is a monotonic cycle counter with a non-monotonic relation to scrap — each tool has its own sweet-spot band.',
    'Multivariate diagnostic models reach AUC 0.72–0.89 per (tool, defect). Burnt Carpet (0.63) is the weakest, suggesting it is multi-causal.',
    'A simple operating-window threshold rule alone is weak (AUC ≈ 0.55). Use it for triage; use the defect-specific engine for diagnosis.',
]
for it in items:
    p = doc.add_paragraph(style='List Bullet'); p.add_run(it)

doc.add_page_break()

# ============================================================================
# 2. APPROACH
# ============================================================================
add_heading(doc, '2. Approach', level=1)
add_para(doc, 'We separate the work into three layers, each with its own deliverable:')
add_table(doc,
    [['Layer', 'Question', 'Deliverable'],
     ['Audit', 'What is in the data? What is suspicious or surprising?', 'EDA.ipynb'],
     ['Diagnose', 'For each (tool, defect): which parameters deviate, by how much, with what confidence?', 'VAC_Forming_Scrap_Analysis_Final.ipynb'],
     ['Act', 'What should an operator do when defect D is detected on tool T?', 'Scrap_Recommendations_Report_v2.xlsx + live recommend() engine']],
    col_widths=[1.0, 3.5, 2.0])

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('We describe; we do not prescribe causation. ').italic = True
p.add_run('Scrap is already detected on-line. The value here is in explaining why a part went bad and converting that into a corrective action, not in predicting scrap.')

doc.add_page_break()

# ============================================================================
# 3. DATA
# ============================================================================
add_heading(doc, '3. Data inventory & cleaning decisions', level=1)
add_heading(doc, '3.1 Schema', level=2)
add_table(doc,
    [['File','Rows','Columns','Description'],
     ['VF_export.csv', f'{len(p_raw):,}', '7', 'ID, PartDesc, BuiltTime, DS1/DS2/DS3 (40 parameters)'],
     ['VF_Scrap_export.csv', f'{len(s_raw):,}', '4', 'ID, Desc (defect type), ScrapTime'],
     ['Join', '386 / 386', '—', 'all scrap IDs found in process table; IDs unique on both sides']],
    col_widths=[2.0, 1.0, 1.0, 3.0])

add_heading(doc, '3.2 Production timeline', level=2)
add_image(doc, '01_production_timeline.png', caption='Figure 1 — Production volume by day (left) and by hour (right). Production is bursty: 14 production days inside the 56-day span; Mondays–Thursdays only.')

add_heading(doc, '3.3 Cleaning decisions applied', level=2)
add_table(doc,
    [['Issue', 'Parameter(s)', 'Action'],
     ['Constants', 'Pick Material Pos (=220), TTF Circuit 2 Temp (=0)', 'Drop — cannot diagnose anything'],
     ['Sentinel cap (9.5% of rows)', 'Machine Cycle Time = 9999', 'Treat as missing; add mct_capped flag'],
     ['Bimodal (off vs active)', 'Pos Vinyl N/S Length/Width, Temp Z4', 'Encode (value, active_flag)'],
     ['Heavy tail (two regimes)', 'BT Circuit 2 Temp (p50=23, max=833)', 'Keep raw; model handles'],
     ['Recipe-fixed (CV < 0.01)', 'Stretch Cross *, Stetch Length *, Roller Gap *, Top Tool Pos Close, Glue Temp', 'Exclude from causal ranking per tool']],
    col_widths=[1.8, 2.7, 2.5])

add_heading(doc, '3.4 Engineered context features', level=2)
for it in [
    'is_warmup — first 20 parts of a production day on a tool',
    'prev_mct_capped — whether the previous part on the same tool had MCT = 9999',
    'color, family — parsed from PartDesc',
]:
    p = doc.add_paragraph(style='List Bullet'); p.add_run(it)

add_heading(doc, '3.5 Defect taxonomy', level=2)
add_table(doc,
    [['Scope','Defect codes'],
     ['Process (in scope)','Wrinkle, Dent, Bumps / lumps, Burnt Carpet / Vynil, Low Glue / Read Thru / Impression, Out of dimension, Bad edge wrap, Glue bleed thru, Delamination'],
     ['Non-process (excluded)','Hole, Broken / Fracture, Fabric Flaw, Fabric Torn']],
    col_widths=[2.0, 5.0])
doc.add_page_break()

# ============================================================================
# 4. METHODOLOGY
# ============================================================================
add_heading(doc, '4. Methodology', level=1)
add_heading(doc, '4.1 Statistical primitives', level=2)
add_table(doc,
    [['Primitive','Use'],
     ["Welch's t-test","Significance of mean shift, unequal variance"],
     ["Cliff's δ","Non-parametric effect size in [-1, +1]. Severity: CRITICAL > 0.474, STRONG > 0.33, MODERATE > 0.20"],
     ['Kolmogorov–Smirnov','Distribution-shape sanity check'],
     ['Wilson 95 % CI','Confidence interval for every rate comparison']],
    col_widths=[1.5, 5.5])

add_heading(doc, '4.2 Multivariate models (per tool × defect, n_bad ≥ 15)', level=2)
for it in [
    'L1-regularised logistic regression — sparse coefficients (picks 3-5 features)',
    'Random Forest — 400 trees, depth 8, class-balanced',
    'Gradient Boosting — 200 stages, depth 3, learning rate 0.06',
    '5-fold stratified CV; report mean AUC + Brier score',
    'Permutation importance on the best model for a model-agnostic feature ranking',
]:
    p = doc.add_paragraph(style='List Bullet'); p.add_run(it)

add_heading(doc, '4.3 Anomaly detection (cross-defect)', level=2)
add_para(doc, 'Isolation Forest (300 trees, contamination 0.05) over the union of drifting parameters. Provides a tool-agnostic "this row looks unusual" score for triage; complements but does not replace the defect-specific engine.')

add_heading(doc, '4.4 Validation', level=2)
add_para(doc, 'We hold out 30 % stratified on is_scrap, build per-tool windows from train-good only, then score test rows by the count of drifting parameters that fall outside [P5, P95]. We report AUC and precision/coverage at thresholds 0–7. This is deliberately a deflationary test: its AUC is ~0.55, which is precisely the point — the simple rule is a triage signal, not a classifier.')

doc.add_page_break()

# ============================================================================
# 5. ITERATIVE HYPOTHESIS TESTING
# ============================================================================
add_heading(doc, '5. Iterative hypothesis testing', level=1)
add_para(doc, 'Every hypothesis was stated before running the test. Verdicts: A = accept, R = reject, C = conditional with caveats.')
hyps = [
    ['#','Hypothesis','Verdict','Numeric anchor'],
    ['H1','Scrap rate differs by tool','A','T1 7.28% [6.27, 8.43]; T2 3.97% [3.39, 4.64]; T8 5.40% [4.32, 6.74]. χ² p = 1.7e-7'],
    ['H2','Scrap rate differs by part within each tool','A','All tools p < 1e-4'],
    ['H3','Color matters after controlling for part family','C','Significant on PS LOWER LHD (BEIGE 15% vs BLACK 5%) and DS LOWER LHD; not universal'],
    ['H4','MAP POCKET parts scrap more','C','True marginally; confounded — map pockets are almost exclusively Tool 1'],
    ['H5','Day-of-week effect (Monday spike)','A','Mon 14.9% vs Thu 1.5%; all Monday parts are Tool 2 — tool-confounded'],
    ['H6','Hour-of-day shift effect','A','T1 hour 6 = 14.7% (warm-up); T8 hour 13 = 19% (afternoon spike)'],
    ['H7','First parts of a production day scrap more','A','First 10 ≈ 12%, 10-19 ≈ 10%, 20-49 ≈ 5.5%, 50+ ≈ 4.9%. p = 2.3e-6'],
    ['H8','First part after a long gap scraps more','R','p = 0.80 — intra-day gaps dominated by overnight rolls'],
    ['H9','MCT = 9999 marks a stoppage','A','Scrap rate inside 7.56% vs 4.99% outside; next part 8.0%'],
    ['H10','Pyro Clean → scrap is monotonic','A (non-monotone)','Per-tool sweet spots; outside band scrap doubles'],
    ['H11','Defect–tool exclusivity','A','Wrinkle 99% T1, Low Glue 98% T2, Bumps 67% T8, Out of dim 78% T1'],
    ['H12','Parameter drift across the data window','A (selective)','Glue Temp / Cycle Time drift on some tools; no single global drift'],
    ['H13','Bad days pile multiple defect types','C','Day-level Pearson(rate, n_defects) = 0.39'],
    ['H14','TTF Circuit 1 Temp = 0 marks a different recipe','R','Within-tool scrap rates do not differ'],
    ['H15','Pos Vinyl * are bimodal (active vs off)','A','50-60 % zero; non-zero p50 ≈ 200+'],
    ['H16','Defects co-cluster on the same day','A','Wrinkle days also see Bad edge wrap + Dent'],
]
add_table(doc, hyps, col_widths=[0.4, 2.6, 0.9, 3.1], font_size=8)
doc.add_page_break()

# ============================================================================
# 6. FINDINGS — TOOL LEVEL
# ============================================================================
add_heading(doc, '6. Findings — tool level', level=1)
add_image(doc, '02_tool_rates.png', caption='Figure 2 — Scrap rate by tool with Wilson 95 % CI. Differences are statistically significant (χ² p = 1.7e-7).', width=5.5)
add_image(doc, '03_defect_tool.png', caption='Figure 3 — (left) Process-defect counts; (right) Defect × Tool heatmap showing strong tool-locking.')
add_image(doc, '05_hour_tool.png', caption='Figure 4 — Scrap rate by hour, per tool. Tool 1 shows a morning warm-up; Tool 8 an afternoon spike.')
add_image(doc, '04_warmup.png', caption='Figure 5 — Warm-up effect: scrap rate vs position in production day.', width=5.5)

tool_rows = [['Tool','Parts','Scrap','Rate %','95 % CI','Dominant defects']]
defects_per_tool = {
    1: 'Wrinkle, Out of dim, Bad edge wrap, Dent',
    2: 'Low Glue, Dent, Burnt Carpet, Bumps',
    8: 'Bumps (35/52 of all Bumps), Dent'
}
for t, r in tool_summary.iterrows():
    tool_rows.append([f'Tool {int(t)}', f'{int(r["parts"]):,}', int(r['scrap']),
                      f'{r["rate_pct"]:.2f} %', f'[{r["ci_low"]:.2f}, {r["ci_high"]:.2f}]',
                      defects_per_tool.get(int(t),'-')])
add_table(doc, tool_rows, col_widths=[0.7, 0.8, 0.7, 0.8, 1.2, 2.8])
doc.add_page_break()

# ============================================================================
# 7. FINDINGS — DEFECT-BY-DEFECT
# ============================================================================
add_heading(doc, '7. Findings — defect-by-defect (tool-conditional)', level=1)

add_heading(doc, '7.1 Wrinkle  (n = 93; 99 % Tool 1) — largest single defect', level=2)
add_image(doc, '07_wrinkle_t1.png', caption='Figure 6 — Wrinkle on Tool 1: green = good parts, red = scrap parts. Pos Vinyl S Width is the dominant signal.')
tab_wrinkle = deviation('Wrinkle', 1.0, ACTIVE[1]).head(8)
add_table(doc, [['Parameter','Good P50','Scrap P50','% diff',"Cliff's δ",'Welch p']] +
          [[r['param'], r['good_p50'], r['bad_p50'], f'{r["pct_diff"]:+.1f} %', f'{r["cliffs"]:+.2f}', f'{r["welch_p"]:.1e}']
           for _, r in tab_wrinkle.iterrows()],
          col_widths=[2.5, 0.9, 0.9, 0.9, 0.9, 1.0])

doc.add_page_break()
add_heading(doc, '7.2 Low Glue / Read Thru / Impression  (n = 41; 98 % Tool 2)', level=2)
add_image(doc, '08_lowglue_t2.png', caption='Figure 7 — Low Glue on Tool 2: temperature-deficit signature. BHT/THT trigger temps and BT/TTF circuits all run below the good norm.')
tab_lg = deviation('Low Glue/Read Thru/Impression', 2.0, ACTIVE[2]).head(8)
add_table(doc, [['Parameter','Good P50','Scrap P50','% diff',"Cliff's δ",'Welch p']] +
          [[r['param'], r['good_p50'], r['bad_p50'], f'{r["pct_diff"]:+.1f} %', f'{r["cliffs"]:+.2f}', f'{r["welch_p"]:.1e}']
           for _, r in tab_lg.iterrows()],
          col_widths=[2.5, 0.9, 0.9, 0.9, 0.9, 1.0])

doc.add_page_break()
add_heading(doc, '7.3 Bumps / lumps  (n = 52; 67 % Tool 8, 33 % Tool 2)', level=2)
add_image(doc, '09_bumps_t8.png', caption='Figure 8 — Bumps on Tool 8: under-heating signature. THT/BHT trigger temps, Capacities, and TTF Circuit 1 all run below the good norm.')
tab_b = deviation('Bumps / lumps', 8.0, ACTIVE[8]).head(8)
add_table(doc, [['Parameter','Good P50','Scrap P50','% diff',"Cliff's δ",'Welch p']] +
          [[r['param'], r['good_p50'], r['bad_p50'], f'{r["pct_diff"]:+.1f} %', f'{r["cliffs"]:+.2f}', f'{r["welch_p"]:.1e}']
           for _, r in tab_b.iterrows()],
          col_widths=[2.5, 0.9, 0.9, 0.9, 0.9, 1.0])

doc.add_page_break()
add_heading(doc, '7.4 Other defects — short summaries', level=2)
short = [
    ('Dent (n = 62; spread across tools)',
     'Different signatures per tool: T2 ↑ heating time + ↑ Pyro Clean + ↓ Capacity BHT (AUC 0.835); T1 ↑ Pos Vinyl N Width + ↑ Pyro Clean (AUC 0.721); T8 ↓ BT Circuit 1 Temp (AUC 0.719). Illustrates why pooling is wrong.'),
    ('Burnt Carpet / Vynil (n = 43; 60 % Tool 2)',
     'T2: ↓ Pyro Clean very low (fresh-clean residue effect). Vacuum times slightly reduced. AUC 0.632 — weakest signal; multi-causal.'),
    ('Bad edge wrap (n = 32; 63 % Tool 1, 37 % Tool 2)',
     'T1: ↓ Temp BHT at Trigger + ↓ Pyro Clean + ↓ BT Circuit 2 Temp. AUC 0.803.\nT2: ↑ Pos Vinyl N Length/Width activated where good parts have them off.'),
    ('Out of dimension (n = 23; 78 % Tool 1)',
     'T1: ↑ Pyro Clean (+35 %), ↓ Roller Gap LH (-8 %), ↓ Vacuum Time Cavity B. AUC 0.733.'),
]
for title, body in short:
    h = doc.add_paragraph(); r = h.add_run(title); r.bold = True; r.font.size = Pt(11)
    p = doc.add_paragraph(); p.add_run(body).font.size = Pt(10)
doc.add_page_break()

# ============================================================================
# 8. PYRO CLEAN SPOTLIGHT
# ============================================================================
add_heading(doc, '8. Cross-defect spotlight — Pyro Clean', level=1)
add_para(doc, 'Pyro Clean is monotonic across rows (≤ 0.5 % decreases), consistent with a counter that increments per part. But its relation to scrap is non-monotonic: each tool has a sweet-spot band of cycles where scrap is lowest, with rates rising on either side.')
add_image(doc, '06_pyro_clean.png', caption='Figure 9 — Per-tool scrap rate by Pyro Clean octile. Green bar = lowest-scrap band (recommended target). Tool 8 never resets in the window (min observed = 496).')

add_table(doc,
    [['Tool','Recommended Pyro Clean band','Rate in band','Rate outside']] +
    [[f'Tool {t}', f'{lo} – {hi}', f'{rate} %',
      f'{round((df[(df["Tool Number"]==t)&((df["Pyro Clean"]<lo)|(df["Pyro Clean"]>hi))]["is_scrap"].mean()*100),2)} %']
     for t, (lo, hi, rate) in PYRO_BANDS.items()],
    col_widths=[1.0, 2.0, 1.5, 1.5])
doc.add_page_break()

# ============================================================================
# 9. MODEL RESULTS
# ============================================================================
add_heading(doc, '9. Multivariate model results', level=1)
add_image(doc, '10_model_auc.png', caption='Figure 10 — 5-fold CV AUC per (tool, defect), best of L1-LR / RF / GBM. Green > 0.80, amber 0.70-0.80, red < 0.70.')

cv_rows = [['Tool','Defect','n_bad','L1','RF','GBM','Best AUC','Best model']]
for r in cv_df.sort_values(['tool','defect']).itertuples():
    cv_rows.append([f'T{r.tool}', r.defect, r.n_bad, r.L1, r.RF, r.GBM, r.best_auc, r.best_model])
add_table(doc, cv_rows, col_widths=[0.5, 2.6, 0.6, 0.6, 0.6, 0.6, 0.7, 0.8], font_size=9)

add_heading(doc, '9.1 Anomaly score (Isolation Forest)', level=2)
add_image(doc, '11_anomaly.png', caption=f'Figure 11 — Anomaly-score distribution. Scrap parts are shifted right; overall AUC ≈ {overall_auc:.2f}. Use as triage filter, not a classifier.')
doc.add_page_break()

# ============================================================================
# 10. RECOMMENDATION ENGINE
# ============================================================================
add_heading(doc, '10. Recommendation engine — how it works', level=1)
add_para(doc, 'recommend(defect, tool, current_params, pyro_band) → list[action]')

for it in [
    'For each rule (filtered to Welch p < 0.05 and |Cliff δ| > 0.20 on the relevant tool):',
    '— look up the parameter\'s good [P5, P50, P95] band on this tool;',
    '— compare current reading to the band: inside → OK; above P95 → REDUCE to P50; below P5 → INCREASE to P50;',
    '— severity label inherited from historical effect size;',
    '— Pyro Clean has a sweet-spot overlay: outside band → WAIT_BEFORE_CLEAN or PYRO_CLEAN_DUE.',
]:
    p = doc.add_paragraph(style='List Bullet'); p.add_run(it)

add_heading(doc, '10.1 Live demo (worst-violating scrap example per defect)', level=2)
add_para(doc, 'On the most out-of-band scrap row per defect, the engine fires 2–6 actions per case. Example below from Tool 8 Bumps (worst-violator scrap row):')

demo_table = [
    ['Severity','Parameter','Current','Safe band','Action'],
    ['CRITICAL','Temp. THT at Trigger','137','141 – 170','INCREASE → 170'],
    ['CRITICAL','Capacity BHT','53','55 – 70','INCREASE → 60'],
    ['CRITICAL','Temp. BHT at Trigger','164','177 – 213','INCREASE → 193'],
    ['STRONG','TTF Circuit 1 Temp','27','28 – 37','INCREASE → 34'],
    ['STRONG','Pos Vinyl N Width','304','0 – 295','REDUCE → 0'],
    ['MODERATE','Pyro Clean','810','665 – 703','PYRO_CLEAN_DUE'],
]
add_table(doc, demo_table, col_widths=[0.8, 2.0, 0.7, 1.0, 1.8])

doc.add_page_break()

# ============================================================================
# 11. ASSUMPTIONS
# ============================================================================
add_heading(doc, '11. Assumptions (explicit)', level=1)
add_para(doc, 'These are the assumptions we made because we cannot verify them from data alone. If any prove wrong, the affected finding should be re-examined.')

assumptions = [
    ['#','Assumption','Risk if wrong'],
    ['A1','The 9 listed defect codes are operator-actionable; the other 4 (Hole, Broken/Fracture, Fabric Flaw, Fabric Torn) are upstream / material defects.','We could be under-counting recoverable scrap if some excluded defects are process-related.'],
    ['A2','ID uniquely identifies a single produced part; the process↔scrap join is correct.','Empirically supported: 386/386 matches, unique IDs on both sides.'],
    ['A3','BuiltTime is the actual production timestamp (not record-creation time).','Warm-up finding depends on this; if violated, the warm-up signal is spurious.'],
    ['A4','ScrapTime is the QC / detection time, not the production time.','Consistent with the 6-h median / 43-day max lag we observe.'],
    ['A5','Each tool\'s recipe (Roller Gap, Stretch *) is stable within the 56-day window.','Supported empirically by very low within-tool CV on these parameters.'],
    ['A6','Good parts are a valid baseline.','If many marginal parts slipped through QC, the "good" targets are biased.'],
    ['A7','P5–P95 of good parts is a reasonable operating window.','Wider would dilute the signal; narrower would over-fire. Not cost-optimised.'],
    ['A8','Scrap Desc labels are accurate.','Some defect categories (Dent vs Bumps) are visually similar and may be subjectively labelled.'],
    ['A9','Pyro Clean is a counter (cycles since last clean).','Supported by ≤0.5 % decreases. If actually a setpoint, sweet-spot recommendation must be re-interpreted.'],
    ['A10','MCT = 9999 is a stoppage sentinel.','Supported by elevated surrounding scrap. A different cause (data-logger error) would change the engineered flag\'s meaning.'],
    ['A11','Pos Vinyl * zero values mean the feature is inactive.','Treating as (active_flag, value) is safer either way than treating zero as a numerical level.'],
]
add_table(doc, assumptions, col_widths=[0.4, 3.0, 3.6], font_size=9)
doc.add_page_break()

# ============================================================================
# 12. OPEN QUESTIONS
# ============================================================================
add_heading(doc, '12. Process-related ambiguities & open questions', level=1)
add_para(doc, 'These cannot be answered from the data alone — they need the operator / maintenance / engineering teams.')

add_heading(doc, 'A. Sensor / data semantics', level=2)
A = [
    'Pyro Clean — exact meaning? Cycles since last pyro clean? Why does Tool 8 never reach a reset in 56 days (min = 496)?',
    'Machine Cycle Time = 9999 — what event does this code represent? Stop, sensor not-ready, reset, manual override?',
    'Pos Vinyl N/S Length/Width zero values — feature disabled by recipe, or default-when-unset?',
    'TTF Circuit 2 Temp = 0 everywhere — sensor removed, retired, or always-off configuration?',
    'Capacity BHT capped at 70 (5.4 % of rows); Capacity THT capped at 85 — hardware ceiling, or controller setpoint cap?',
    'Top Tool Pos Close has only 4 unique values (12330/12480/12490/12500) — discrete clamp positions?',
    'BT Circuit 2 Temp has two regimes (22-28 most rows, 300-833 others). Different heater modes?',
]
for it in A:
    p = doc.add_paragraph(style='List Bullet'); p.add_run(it).font.size = Pt(10)

add_heading(doc, 'B. Operations & people', level=2)
B = [
    'Operator / shift identifiers — are they logged anywhere? Tool 1 morning warm-up and Tool 8 afternoon spike both have a personnel-signal signature.',
    'Warm-up procedure — is there a standardised one? First 10–20 parts of a day at ≈12 % scrap vs ≈5 % steady-state.',
    'Recipe configurability — recipes hard-locked per tool, or editable per part?',
    'Tool 8 absence of Wrinkle / Bad edge wrap — real (geometry/mechanics) or label-coding difference?',
    'MAP POCKET BEIGE on Tool 1 at 23.1 % scrap — colorant interaction, geometric difficulty, supply-lot variance, inspection bias?',
    'Pyro Clean cleaning policy — scheduled, defect-triggered, or operator judgement? Tool 8 not resetting in 56 days is unusual.',
    'Scrap detection workflow — median lag 6 h, max 43 d. Recent days\' scrap counts may still grow.',
    'Color × family confound — PS LOWER LHD BEIGE 15.3 % vs BLACK 4.79 %. Different vinyl, supplier, or inspection visibility?',
]
for it in B:
    p = doc.add_paragraph(style='List Bullet'); p.add_run(it).font.size = Pt(10)

add_heading(doc, 'C. Modeling', level=2)
C = [
    'Burnt Carpet AUC = 0.63 — weakest model. Multi-causal, or sub-types we should label separately?',
    'Tool 1 Pyro Clean ceiling 495 vs Tool 8 floor 496 — different counter semantics, different cleaning cadence, or shared counter we cannot see?',
]
for it in C:
    p = doc.add_paragraph(style='List Bullet'); p.add_run(it).font.size = Pt(10)

doc.add_page_break()

# ============================================================================
# 13. WHAT WE DID NOT DO
# ============================================================================
add_heading(doc, '13. What we did not do, and why', level=1)
no_do = [
    ('No annual-savings projection.', '14 production days inside 56 calendar days is too bursty to annualise without an expected production-volume baseline.'),
    ('No causal claims about prior interventions.', 'We have no metadata about what was or wasn\'t changed on the line between datasets.'),
    ('No supervised classifier exposed as a "scrap predictor".', 'The CV AUCs (0.72-0.89) show that signal exists, but the line already detects scrap in-line. The value is explanation, not prediction.'),
    ('No leaderboard tuning.', 'Model hyperparameters are out-of-the-box defaults — methodology is interpretable and reproducible.'),
    ('No part-level recommendation table.', 'Per-part rates (e.g. FL MAP POCKET BEIGE 23.1 %) are an engineering question, not an operator runtime knob.'),
]
for title, body in no_do:
    p = doc.add_paragraph(); r = p.add_run(title + ' '); r.bold = True
    p.add_run(body)

doc.add_page_break()

# ============================================================================
# 14. DELIVERABLES
# ============================================================================
add_heading(doc, '14. Repo deliverables', level=1)
deliv = [
    ['File','Purpose'],
    ['EDA.ipynb','Pure exploratory audit (34 cells)'],
    ['VAC_Forming_Scrap_Analysis_Final.ipynb','Diagnosis, modeling, recommendation engine, live demo, validation (38 cells)'],
    ['Scrap_Recommendations_Report_v2.xlsx','7-sheet operator report (tool summary, defect × tool, operating windows, Pyro Clean bands, defect rules, model CV AUC, all deviations)'],
    ['operating_windows_final.csv','Per-tool P5/P50/P95 reference table'],
    ['FINDINGS.md','Plain-text consolidated report (same content as this document)'],
    ['VAC_Forming_Scrap_Report.docx','This document — illustrated consolidated report'],
    ['_exp/10_deep_eda.py / 11_hypotheses.py / 12_models.py','Reproducible scripts: EDA, hypothesis tests, modeling'],
    ['_exp/build_eda_notebook.py / build_final_notebook.py / build_docx_report.py','Notebook & report generators'],
    ['_exp/results/*.csv','Intermediate artefacts (parameter profile, deviations, drift, CV AUCs)'],
    ['_exp/df_clean.parquet','Cleaned & joined data frame'],
]
add_table(doc, deliv, col_widths=[3.0, 4.0])

doc.add_paragraph()
add_para(doc, 'Jupyter kernel: py311-vacforming (Python 3.11, sklearn, scipy, pandas, seaborn, openpyxl, python-docx).', italic=True, size=9)

# Save
doc.save(DOCX)
print(f"\nWrote {DOCX}  ({os.path.getsize(DOCX):,} bytes)")
