#!/usr/bin/env python3
"""
정규화 범위를 실제 녹화에서 다시 재는 스크립트.

hub_v1.py 의 PRESS_MM_RANGE, SPEED_CMS_RANGE, WIND_RANGE 는 이 결과로 정했다.
천의 장력이나 센서 높이를 바꾸면 분포가 달라지므로 다시 돌려서 확인할 것.
녹화는 playground_v24.py 를 돌리고 R 키로 만든다.

    python3 probe_ranges.py
"""
import sys, os, csv, math, glob
sys.path.insert(0, os.path.expanduser("~/Desktop/playground"))
from playground_v24 import Tracker, stroke_feeling

rows_out = []
for path in sorted(glob.glob(os.path.expanduser("~/Desktop/playground/recordings/*.csv"))):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in rows[0].keys() if c.startswith("d")]
    tr = Tracker()
    def on_clean(clean, feel, _p=path):
        xs=[p[0] for p in clean]; ys=[p[1] for p in clean]
        w,h = max(xs)-min(xs), max(ys)-min(ys)
        diag = math.hypot(w,h)
        L = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(clean, clean[1:]))
        turn = 0.0
        for a,b,c in zip(clean, clean[1:], clean[2:]):
            v1=(b[0]-a[0], b[1]-a[1]); v2=(c[0]-b[0], c[1]-b[1])
            turn += math.atan2(v1[0]*v2[1]-v1[1]*v2[0], v1[0]*v2[0]+v1[1]*v2[1])
        aspect = 1 - (min(w,h)/max(w,h)) if max(w,h) > 1e-6 else 0
        rows_out.append(dict(rec=os.path.basename(_p)[4:17], n=len(clean),
            speed_cms=feel["speed"], press_mm=feel["press"], spread=feel["spread"],
            len_fu=L, diag=diag, wind=(L/diag if diag>1e-6 else 1), aspect=aspect,
            turn_rad=turn, feeling=feel["feeling"]))
    tr.on_clean = on_clean
    t0 = 0.0
    for r in rows:
        tr.feed([int(r[c]) for c in cols], float(r["t"]))
    tr.finish_now()

print(f"{'rec':14}{'n':>5}{'speed':>8}{'press':>8}{'spread':>8}{'len_fu':>9}{'wind':>7}{'aspect':>8}{'turn':>8}  feeling")
for r in rows_out:
    print(f"{r['rec']:14}{r['n']:>5}{r['speed_cms']:>8.1f}{r['press_mm']:>8.1f}{r['spread']:>8.1f}"
          f"{r['len_fu']:>9.0f}{r['wind']:>7.2f}{r['aspect']:>8.2f}{r['turn_rad']:>8.2f}  {r['feeling']}")

def rng(k):
    v=[r[k] for r in rows_out]
    v.sort()
    return f"min {v[0]:.2f}  p10 {v[int(.1*(len(v)-1))]:.2f}  med {v[len(v)//2]:.2f}  p90 {v[int(.9*(len(v)-1))]:.2f}  max {v[-1]:.2f}"
print()
for k in ("speed_cms","press_mm","wind","aspect","turn_rad"):
    print(f"{k:10} {rng(k)}")
