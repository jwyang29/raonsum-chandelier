#!/usr/bin/env python3
"""매다는 큐브 3개를 선을 겹쳐 재단하는 배치로 뽑는다 (칼날 전용).

🔴 칼날 재단에서만 쓴다.
   라우터는 날 굵기(3~6mm)만큼 재료를 갉아낸다. 선을 공유하면 양쪽 조각이
   그만큼 작아지고, 큐브 바깥 치수가 틀어져 마커가 안 맞는다. AR 이 어긋난다.
   라우터로 간다면 deco/make_foam.py 로 뽑은 떨어뜨린 배치를 써야 한다.

같은 폭인 조각들을 세로로 쌓아 기둥을 만든다. 기둥 안에서는
  세로선   왼쪽 하나, 오른쪽 하나로 끝난다 (조각마다 둘씩 긋지 않는다)
  가로선   이웃한 두 조각이 한 선을 나눠 쓴다
기둥끼리도 맞닿은 세로선을 나눠 쓴다.

겹치는 선을 지우는 것이 아니라, 같은 직선 위에 있는 토막들을 하나로 이어
붙인다. 그래야 장비가 한 번에 긋고 지나간다.

    python3 deco/make_foam_nest.py --t 3
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "web", "config.js")
OUT = os.path.join(HERE, "..", "markers", "print")

HOLE = 2.0
HOLE_SPAN = 25.0
MARGIN = 10.0
EPS = 0.01


def cube_edges():
    src = io.open(CONFIG, encoding="utf-8").read()
    m = re.search(r"const CUBE_PLAN = \[(.*?)\];", src, re.S)
    if not m:
        sys.exit("config.js 에서 CUBE_PLAN 을 못 찾았습니다")
    return [round(float(r.split(",")[1]) * 1000, 1)
            for r in re.findall(r"\[([^\]]+)\]", m.group(1))]


def columns(edges, t):
    """폭이 같은 것끼리 기둥으로 묶는다. 중간 면은 돌려서 폭을 큰 쪽에 맞춘다."""
    cols = []
    for i, E in enumerate(edges, 1):
        inner = round(E - 2 * t, 1)
        # 폭 E 기둥: 큰 면 2장 + 중간 면 2장(돌려서 폭 E)
        cols.append({"w": E, "pieces": [
            (E, True,  f"큐브{i} 윗면 {E:.0f}x{E:.0f} (구멍)"),
            (E, False, f"큐브{i} 아랫면 {E:.0f}x{E:.0f}"),
            (inner, False, f"큐브{i} 앞면 {E:.0f}x{inner:.0f}"),
            (inner, False, f"큐브{i} 뒷면 {E:.0f}x{inner:.0f}"),
        ]})
        # 폭 inner 기둥: 작은 면 2장
        cols.append({"w": inner, "pieces": [
            (inner, False, f"큐브{i} 옆면 {inner:.0f}x{inner:.0f}"),
            (inner, False, f"큐브{i} 옆면 {inner:.0f}x{inner:.0f}"),
        ]})
    # 키 큰 기둥을 왼쪽에 둔다. 맞닿는 세로선이 길어져 더 많이 나눠 쓴다.
    cols.sort(key=lambda c: -sum(p[0] for p in c["pieces"]))
    return cols


def merge(iv):
    """같은 직선 위의 토막들을 하나로 잇는다."""
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + EPS:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def layout(edges, t):
    cols = columns(edges, t)
    vert, horz, holes, labels = {}, {}, [], []
    x = MARGIN
    raw = 0.0        # 조각마다 따로 자를 때의 총 길이
    for c in cols:
        w, y0 = c["w"], MARGIN
        h_total = sum(p[0] for p in c["pieces"])
        # 기둥의 좌우 세로선
        for xx in (x, x + w):
            vert.setdefault(round(xx, 2), []).append((y0, y0 + h_total))
        y = y0
        for h, hole, name in c["pieces"]:
            horz.setdefault(round(y, 2), []).append((x, x + w))
            labels.append((x + 2.5, y + h - 3, name))
            if hole:
                cy = y + 11
                holes.append((x + w / 2 - HOLE_SPAN / 2, cy))
                holes.append((x + w / 2 + HOLE_SPAN / 2, cy))
            raw += 2 * (w + h)
            y += h
        horz.setdefault(round(y, 2), []).append((x, x + w))
        x += w

    segs = []
    cut = 0.0
    for xx, iv in vert.items():
        for a, b in merge(iv):
            segs.append(("v", xx, a, b)); cut += b - a
    for yy, iv in horz.items():
        for a, b in merge(iv):
            segs.append(("h", yy, a, b)); cut += b - a

    W = x + MARGIN
    H = max(sum(p[0] for p in c["pieces"]) for c in cols) + MARGIN * 2
    return W, H, segs, holes, labels, cut, raw


def write(t):
    edges = cube_edges()
    W, H, segs, holes, labels, cut, raw = layout(edges, t)
    os.makedirs(OUT, exist_ok=True)

    lines = []
    for kind, f, a, b in segs:
        if kind == "v":
            lines.append(f'<line class="cut" x1="{f:.2f}" y1="{a:.2f}" x2="{f:.2f}" y2="{b:.2f}"/>')
        else:
            lines.append(f'<line class="cut" x1="{a:.2f}" y1="{f:.2f}" x2="{b:.2f}" y2="{f:.2f}"/>')
    for cx, cy in holes:
        lines.append(f'<circle class="cut" cx="{cx:.2f}" cy="{cy:.2f}" r="{HOLE/2:.2f}"/>')
    for lx, ly, txt in labels:
        lines.append(f'<text class="note" x="{lx:.2f}" y="{ly:.2f}" font-size="4.2">{txt}</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
     width="{W:.1f}mm" height="{H:.1f}mm" viewBox="0 0 {W:.1f} {H:.1f}">
  <style>
    .cut  {{ fill: none; stroke: #000; stroke-width: 0.1; }}
    .note {{ fill: #9aa0a6; font-family: sans-serif; }}
  </style>
  {chr(10) + "  ".join(lines)}
  <text class="note" x="{MARGIN}" y="{H - 3.5}" font-size="4.2">칼날 재단 전용. 이웃한 조각이 선을 나눠 씁니다. 라우터로 자르면 날 굵기만큼 조각이 작아져 크기가 틀어집니다.</text>
</svg>
'''
    p = os.path.join(OUT, f"RAONSUM_cube_foam_{t:.0f}mm_nest.svg")
    io.open(p, "w", encoding="utf-8").write(svg)

    ents = []
    for kind, f, a, b in segs:
        x1, y1, x2, y2 = (f, a, f, b) if kind == "v" else (a, f, b, f)
        ents.append("0\nLINE\n8\nCUT\n10\n%.3f\n20\n%.3f\n11\n%.3f\n21\n%.3f"
                    % (x1, H - y1, x2, H - y2))
    for cx, cy in holes:
        ents.append("0\nCIRCLE\n8\nCUT\n10\n%.3f\n20\n%.3f\n40\n%.3f"
                    % (cx, H - cy, HOLE / 2))
    d = os.path.join(OUT, f"RAONSUM_cube_foam_{t:.0f}mm_nest.dxf")
    io.open(d, "w", encoding="utf-8").write(
        "0\nSECTION\n2\nENTITIES\n" + "\n".join(ents) + "\n0\nENDSEC\n0\nEOF\n")

    print(f"선 겹친 배치 (칼날 전용, {t:.0f}mm)")
    print(f"  판        {W:.0f} x {H:.0f} mm   ({W*H/1e6:.2f} m2)")
    print(f"  자르는 선 {len(segs)}개  총 {cut/1000:.2f} m")
    print(f"  따로 자르면        {raw/1000:.2f} m")
    print(f"  줄어든 길이        {(raw-cut)/1000:.2f} m  ({(1-cut/raw)*100:.0f}% 절감)")
    print(f"  {os.path.basename(p)}")
    print(f"  {os.path.basename(d)}")


t = 3.0
a = sys.argv[1:]
if "--t" in a:
    t = float(a[a.index("--t") + 1])
write(t)
