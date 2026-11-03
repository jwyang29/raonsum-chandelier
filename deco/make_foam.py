#!/usr/bin/env python3
"""매다는 큐브 3개를 포맥스(폼보드) 재단용 SVG 로 뽑는다.

🔴 바깥 한 변은 마커 인쇄물에 맞춰 고정이다. 바꾸면 AR 이 틀어진다.
   web/config.js 의 CUBE_PLAN 에서 읽어 온다.

포맥스는 종이처럼 접을 수 없으므로 면 6장을 따로 재단해 맞대 붙인다.
판 두께를 빼지 않으면 바깥 치수가 두께의 두 배만큼 커진다. 그래서 면마다
크기가 조금씩 다르다.

   윗면/아랫면   E x E              2장
   앞면/뒷면     E x (E - 2t)       2장
   옆면 2장      (E - 2t) x (E - 2t)

   쌓으면  t + (E - 2t) + t = E  로 바깥이 정확히 E 가 된다.

마커 인쇄물은 조립이 끝난 바깥면에 붙인다. 종이가 이음매를 덮고 지나가므로
오히려 단단해진다. 윗면에는 마커가 없고 낚싯줄 구멍 둘만 있다.

    python3 deco/make_foam.py           5mm 와 3mm 둘 다
    python3 deco/make_foam.py --t 5     5mm 만
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "web", "config.js")
OUT = os.path.join(HERE, "..", "markers", "print")

# 조각 사이 여백 (mm).
# 🔴 칼날(커팅플로터)은 날이 얇아 6mm 면 넉넉하다. 그런데 CNC 라우터는 날이
#    3~6mm 라 그만큼을 통째로 갉아먹는다. 어느 쪽으로 갈지 모를 때는 넓은
#    쪽으로 둔다. 판을 조금 더 쓰는 값으로 다시 자르는 일을 막는다.
GAP = 12.0
HOLE = 2.0       # 낚싯줄 구멍 지름 (mm)
HOLE_SPAN = 25.0 # 구멍 두 개 사이 (mm)
MARGIN = 12.0    # 판 가장자리 여백


def cube_edges():
    """config.js 의 CUBE_PLAN 에서 한 변 길이를 읽는다. 두 군데 적지 않는다."""
    src = io.open(CONFIG, encoding="utf-8").read()
    m = re.search(r"const CUBE_PLAN = \[(.*?)\];", src, re.S)
    if not m:
        sys.exit("config.js 에서 CUBE_PLAN 을 못 찾았습니다")
    out = []
    for row in re.findall(r"\[([^\]]+)\]", m.group(1)):
        parts = [p.strip() for p in row.split(",")]
        out.append(round(float(parts[1]) * 1000, 1))   # m -> mm
    return out


def rect(x, y, w, h, cls="cut"):
    return (f'<rect class="{cls}" x="{x:.2f}" y="{y:.2f}" '
            f'width="{w:.2f}" height="{h:.2f}"/>')


def label(x, y, text, size=4.2):
    return (f'<text class="note" x="{x:.2f}" y="{y:.2f}" '
            f'font-size="{size}">{text}</text>')


def circle(cx, cy, d):
    return f'<circle class="cut" cx="{cx:.2f}" cy="{cy:.2f}" r="{d/2:.2f}"/>'


def build(edges, t):
    """면 조각들을 왼쪽에서 오른쪽으로, 큐브마다 한 줄씩 늘어놓는다."""
    rows, W = [], 0.0
    for i, E in enumerate(edges, 1):
        inner = round(E - 2 * t, 1)
        if inner <= 10:
            sys.exit(f"큐브{i}: 한 변 {E}mm 에 두께 {t}mm 는 너무 두껍습니다")
        pieces = [
            ("윗면 (구멍)", E, E, True),
            ("아랫면 (마커)", E, E, False),
            ("앞면 (마커)", E, inner, False),
            ("뒷면 (마커)", E, inner, False),
            ("옆면 (마커)", inner, inner, False),
            ("옆면 (마커)", inner, inner, False),
        ]
        rows.append((i, E, inner, pieces))
        W = max(W, sum(p[1] for p in pieces) + GAP * (len(pieces) - 1))

    H = sum(max(p[2] for p in r[3]) + 16 for r in rows) + GAP * (len(rows) - 1)
    W += MARGIN * 2
    H += MARGIN * 2

    body, y = [], MARGIN
    for i, E, inner, pieces in rows:
        rowh = max(p[2] for p in pieces)
        body.append(label(MARGIN, y + 6,
            f"큐브{i}   바깥 한 변 {E:.0f} mm   판 두께 {t:.0f} mm   "
            f"좁은 변 {inner:.0f} mm", 5.4))
        y += 11
        x = MARGIN
        for name, w, h, holes in pieces:
            body.append(rect(x, y, w, h))
            body.append(label(x + 2, y + h - 2.5, f"{name} {w:.0f}x{h:.0f}"))
            if holes:
                cy = y + 10
                body.append(circle(x + w / 2 - HOLE_SPAN / 2, cy, HOLE))
                body.append(circle(x + w / 2 + HOLE_SPAN / 2, cy, HOLE))
            x += w + GAP
        y += rowh + GAP

    return W, H, "\n  ".join(body)


def write(t):
    edges = cube_edges()
    W, H, body = build(edges, t)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
     width="{W:.1f}mm" height="{H:.1f}mm" viewBox="0 0 {W:.1f} {H:.1f}">
  <style>
    /* 재단선. 업체에 보낼 때는 이 선만 자르면 된다 */
    .cut  {{ fill: none; stroke: #000; stroke-width: 0.1; }}
    /* 설명 글씨. 자르는 선이 아니다. 업체에 "글씨는 무시" 라고 일러 둔다 */
    .note {{ fill: #9aa0a6; font-family: sans-serif; }}
  </style>
  {body}
  <text class="note" x="{MARGIN}" y="{H - 4}" font-size="4">
    검은 선만 자릅니다. 회색 글씨는 설명이라 자르지 않습니다.
    면을 맞대 붙이면 바깥 한 변이 표시된 치수가 됩니다.
  </text>
</svg>
'''
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"RAONSUM_cube_foam_{t:.0f}mm.svg")
    io.open(p, "w", encoding="utf-8").write(svg)
    print(f"  {os.path.basename(p)}   판 {W:.0f} x {H:.0f} mm")
    write_dxf(t, edges, H)
    for i, E in enumerate(cube_edges(), 1):
        print(f"      큐브{i}  바깥 {E:.0f}mm  큰 면 {E:.0f}x{E:.0f}  "
              f"중간 {E:.0f}x{E-2*t:.0f}  작은 면 {E-2*t:.0f}x{E-2*t:.0f}")
    return p


def write_dxf(t, edges, H):
    """같은 조각을 DXF 로도 뽑는다.

    재단 업체는 SVG 보다 DXF 나 AI 를 달라는 곳이 많다. 선만 들어 있으면
    되므로 LINE 과 CIRCLE 만 쓴 최소 형식으로 적는다. 설명 글씨는 넣지
    않는다. 자르는 선 말고 다른 것이 섞이면 사고가 난다.

    ⚠️ DXF 는 y 가 위로 가고 SVG 는 아래로 간다. 뒤집어 적는다.
    """
    ents = []
    def line(x1, y1, x2, y2):
        ents.append("0\nLINE\n8\nCUT\n10\n%.3f\n20\n%.3f\n11\n%.3f\n21\n%.3f"
                    % (x1, H - y1, x2, H - y2))
    def box(x, y, w, h):
        line(x, y, x + w, y); line(x + w, y, x + w, y + h)
        line(x + w, y + h, x, y + h); line(x, y + h, x, y)
    def circ(cx, cy, d):
        ents.append("0\nCIRCLE\n8\nCUT\n10\n%.3f\n20\n%.3f\n40\n%.3f"
                    % (cx, H - cy, d / 2))

    y = MARGIN
    for i, E in enumerate(edges, 1):
        inner = round(E - 2 * t, 1)
        pieces = [(E, E, True), (E, E, False), (E, inner, False),
                  (E, inner, False), (inner, inner, False), (inner, inner, False)]
        y += 11
        x = MARGIN
        for w, h, holes in pieces:
            box(x, y, w, h)
            if holes:
                cy = y + 10
                circ(x + w / 2 - HOLE_SPAN / 2, cy, HOLE)
                circ(x + w / 2 + HOLE_SPAN / 2, cy, HOLE)
            x += w + GAP
        y += max(p[1] for p in pieces) + GAP

    body = "\n".join(ents)
    dxf = ("0\nSECTION\n2\nENTITIES\n" + body + "\n0\nENDSEC\n0\nEOF\n")
    p = os.path.join(OUT, "RAONSUM_cube_foam_%.0fmm.dxf" % t)
    io.open(p, "w", encoding="utf-8").write(dxf)
    print("  %s   (업체가 DXF 를 달라고 하면 이것)" % os.path.basename(p))


ts = []
a = sys.argv[1:]
if "--t" in a:
    ts = [float(a[a.index("--t") + 1])]
else:
    ts = [5.0, 3.0]
print("포맥스 재단용 SVG")
for t in ts:
    write(t)
