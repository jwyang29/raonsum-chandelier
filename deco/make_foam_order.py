#!/usr/bin/env python3
"""업체에 보낼 재단 발주서를 글로 뽑는다.

치수를 손으로 옮겨 적으면 틀린다. config.js 에서 읽어 만든다.
SVG 와 같은 숫자가 나와야 하므로 계산도 make_foam_pack.py 와 같은 식을 쓴다.
"""
import io, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "web", "config.js")
OUT = os.path.join(HERE, "..", "markers", "print")

t = 3.0
a = sys.argv[1:]
if "--t" in a:
    t = float(a[a.index("--t") + 1])

src = io.open(CONFIG, encoding="utf-8").read()
m = re.search(r"const CUBE_PLAN = \[(.*?)\];", src, re.S)
edges = [round(float(r.split(",")[1]) * 1000, 1)
         for r in re.findall(r"\[([^\]]+)\]", m.group(1))]

rows, holes = [], []
for i, E in enumerate(edges, 1):
    inner = round(E - 2 * t, 1)
    rows.append((E, E, 2, f"큐브{i} 윗면/아랫면"))
    rows.append((E, inner, 2, f"큐브{i} 앞면/뒷면"))
    rows.append((inner, inner, 2, f"큐브{i} 옆면"))
    holes.append((E, E))

total = sum(r[2] for r in rows)
area = sum(r[0] * r[1] * r[2] for r in rows) / 1e6

L = []
L.append("포맥스 재단 발주")
L.append("")
L.append(f"재료      포맥스 (PVC) {t:.0f}mm")
L.append("재단      칼날 (커팅플로터)")
L.append("          ※ 레이저 불가 (PVC 라 염소 발생)")
L.append("          ※ 라우터 불가 (도면이 선을 공유하는 배치)")
L.append(f"총 수량   {total}장")
L.append("")
L.append("사각형 목록 (단위 mm)")
L.append("")
L.append("  가로 x 세로      장수    용도")
L.append("  " + "-" * 44)
for w, h, n, name in rows:
    L.append(f"  {w:>3.0f} x {h:<3.0f}        {n}장    {name}")
L.append("")
L.append("타공")
L.append("")
L.append("  Ø2mm 구멍 2개, 간격 25mm")
L.append("  아래 세 가지 치수에서 각각 1장씩에만 뚫습니다 (총 3장, 구멍 6개)")
for w, h in holes:
    L.append(f"    {w:.0f} x {h:.0f}  중 1장")
L.append("")
L.append("참고")
L.append("")
L.append(f"  조각 실면적 {area:.3f} m2")
L.append("  도면대로 배치하면 546 x 718 mm 판 한 장에 들어갑니다")
L.append("  치수가 1mm 라도 다르면 쓸 수 없습니다. 반올림하지 말아 주세요")
L.append("")
txt = "\n".join(L)

os.makedirs(OUT, exist_ok=True)
p = os.path.join(OUT, f"RAONSUM_cube_foam_{t:.0f}mm_발주서.txt")
io.open(p, "w", encoding="utf-8").write(txt)
print(txt)
print(f"[저장] {os.path.basename(p)}")
