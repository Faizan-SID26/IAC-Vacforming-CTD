"""Profile the new /data CSVs and compare to old Book3.xlsx."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 60)

ROOT = r"C:\Users\12345\Desktop\IAC\Vacforming"
DATA = os.path.join(ROOT, "data")

p = pd.read_csv(os.path.join(DATA, "VF_export.csv"))
s = pd.read_csv(os.path.join(DATA, "VF_Scrap_export.csv"))
print("process:", p.shape, " scrap:", s.shape)
print("process cols:", p.columns.tolist())
print("scrap cols:  ", s.columns.tolist())

p["BuiltTime"] = pd.to_datetime(p["BuiltTime"])
s["ScrapTime"] = pd.to_datetime(s["ScrapTime"])
print(f"process date range: {p['BuiltTime'].min()} -> {p['BuiltTime'].max()}")
print(f"scrap   date range: {s['ScrapTime'].min()} -> {s['ScrapTime'].max()}")
print(f"unique IDs in process: {p['ID'].nunique()}    duplicate IDs: {p['ID'].duplicated().sum()}")
print(f"unique IDs in scrap:   {s['ID'].nunique()}    duplicate IDs: {s['ID'].duplicated().sum()}")
print(f"scrap IDs found in process: {s['ID'].isin(p['ID']).sum()} / {len(s)}")
print(f"scrap defect descriptions:")
print(s["Desc"].value_counts())

# Parse DS1/DS2/DS3
def parse_params(v):
    out = {}
    if pd.isna(v): return out
    for it in str(v).split(","):
        if ":" in it:
            k, val = it.rsplit(":", 1)
            try: out[k.strip()] = float(val.strip())
            except: pass
    return out

ds1 = p["DS1"].apply(parse_params).apply(pd.Series)
ds2 = p["DS2"].apply(parse_params).apply(pd.Series)
ds3 = p["DS3"].apply(parse_params).apply(pd.Series)
print(f"\nDS1 keys ({ds1.shape[1]}):", list(ds1.columns))
print(f"DS2 keys ({ds2.shape[1]}):", list(ds2.columns))
print(f"DS3 keys ({ds3.shape[1]}):", list(ds3.columns))
overlap = set(ds1.columns) & set(ds2.columns)
print("overlap DS1∩DS2:", overlap)
overlap = (set(ds1.columns) | set(ds2.columns)) & set(ds3.columns)
print("overlap DS3 vs rest:", overlap)

df = pd.concat([p[["ID","PartDesc","BuiltTime"]], ds1, ds2, ds3], axis=1)
print("\nfull df shape:", df.shape)
print("null counts (top 10):")
print(df.isna().sum().sort_values(ascending=False).head(10))

# Join with scrap
m = df.merge(s.rename(columns={"Desc":"defect","ScrapTime":"scrap_time"}),
             on="ID", how="left")
m["is_scrap"] = m["defect"].notna()
print(f"\nrows with scrap label: {m['is_scrap'].sum()}  rate: {m['is_scrap'].mean()*100:.2f}%")
print("\nDefect counts (post-join):")
print(m["defect"].value_counts(dropna=False).head(20))

# Save for downstream
os.makedirs(os.path.join(ROOT, "_exp"), exist_ok=True)
m.to_parquet(os.path.join(ROOT, "_exp", "df_joined.parquet"), index=False)
print("\nWrote _exp/df_joined.parquet")
print("Tool numbers present:", sorted(m["Tool Number"].dropna().unique()))
print("\nProduction by Tool:")
print(m.groupby("Tool Number").size())
print("\nScrap-rate by Tool:")
print((m.groupby("Tool Number")["is_scrap"].agg(["sum","count","mean"])
       .assign(rate_pct=lambda x: (x["mean"]*100).round(2))))
print("\nTop part_desc by scrap count (process defects only — drop non-process later):")
print(m[m["is_scrap"]].groupby("PartDesc").size().sort_values(ascending=False).head(15))
