#!/usr/bin/env python3
"""매다는 큐브 3개를 판 면적이 가장 작아지게 재단 배치한다.

🔴 칼날 재단 전용이다.
   맞닿은 조각이 한 선을 나눠 쓴다. 라우터는 날 굵기만큼 갉아내므로 그러면
   양쪽이 작아지고 큐브 바깥 치수가 틀어진다. 마커가 안 맞고 AR 이 어긋난다.

조각이 전부 124~160mm 로 고만고만해서, 키 순으로 줄을 채우는 방식(FFDH)이면
거의 최적에 닿는다. 판 폭을 1mm 씩 바꿔 가며 전부 해보고 면적이 가장 작은
것을 고른다. 조각을 눕혀도 되므로 두 방향 다 본다.

같은 직선 위의 토막은 하나로 이어 붙인다. 지우는 게 아니라 잇는 것이라
장비가 한 번에 긋고 지나간다.

글씨는 넣지 않는다. 재단 파일에 자르는 선 말고 다른 것이 섞이면 사고가 난다.
어느 조각이 무엇인지 보려면 --labels 로 따로 뽑는다 (업체에 보내지 말 것).

    python3 deco/make_foam_pack.py --t 3
    python3 deco/make_foam_pack.py --t 3 --labels
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "web", "config.js")
OUT = os.path.join(HERE, "..", "markers", "print")

HOLE, HOLE_SPAN, MARGIN, EPS = 2.0, 25.0, 8.0, 0.01


def cube_edges():
    src = io.open(CONFIG, encoding="utf-8").read()
    m = re.search(r"const CUBE_PLAN = \[(.*?)\];", src, re.S)
    if not m:
        sys.exit("config.js 에서 CUBE_PLAN 을 못 찾았습니다")
    return [round(float(r.split(",")[1]) * 1000, 1)
            for r in re.findall(r"\[([^\]]+)\]", m.group(1))]


def pieces_of(edges, t):
    out = []
    for i, E in enumerate(edges, 1):
        inner = round(E - 2 * t, 1)
        out += [
            (E, E, True,  f"큐브{i} 윗면 (구멍)"),
            (E, E, False, f"큐브{i} 아랫면"),
            (E, inner, False, f"큐브{i} 앞면"),
            (E, inner, False, f"큐브{i} 뒷면"),
            (inner, inner, False, f"큐브{i} 옆면"),
            (inner, inner, False, f"큐브{i} 옆면"),
        ]
    return out


def shelf_pack(pieces, W):
    """키 큰 것부터 줄을 채운다. 눕혀서 더 낮아지면 눕힌다."""
    items = []
    for w, h, hole, name in pieces:
        # 구멍 뚫는 면은 돌려도 되지만 정사각형이라 어차피 같다
        if h > w and h <= W:
            w, h = h, w
        items.append((w, h, hole, name))
    items.sort(key=lambda p: (-p[1], -p[0]))

    rows, cur, cw, ch = [], [], 0.0, 0.0
    for w, h, hole, name in items:
        if w > W:
            return None
        if cw + w > W + EPS:
            rows.append((cur, ch)); cur, cw, ch = [], 0.0, 0.0
        cur.append((w, h, hole, name)); cw += w; ch = max(ch, h)
    if cur:
        rows.append((cur, ch))
    return rows, sum(r[1] for r in rows)


def best_layout(pieces):
    widths = sorted({p[0] for p in pieces} | {p[1] for p in pieces})
    lo, hi = max(widths), int(sum(max(p[0], p[1]) for p in pieces))
    best = None
    for W in range(int(lo), hi + 1):
        got = shelf_pack(pieces, W)
        if not got:
            continue
        rows, H = got
        area = W * H
        if best is None or area < best[0] - EPS:
            best = (area, W, H, rows)
    return best


def merge(iv):
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + EPS:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def build(rows, W, H):
    vert, horz, holes, labels = {}, {}, [], []
    y = MARGIN
    for row, rh in rows:
        x = MARGIN
        for w, h, hole, name in row:
            for xx in (x, x + w):
                vert.setdefault(round(xx, 2), []).append((y, y + h))
            for yy in (y, y + h):
                horz.setdefault(round(yy, 2), []).append((x, x + w))
            if hole:
                cy = y + 11
                holes.append((x + w / 2 - HOLE_SPAN / 2, cy))
                holes.append((x + w / 2 + HOLE_SPAN / 2, cy))
            labels.append((x + 2.5, y + h - 3, f"{name} {w:.0f}x{h:.0f}"))
            x += w
        y += rh
    segs, cut = [], 0.0
    for xx, iv in vert.items():
        for a, b in merge(iv):
            segs.append(("v", xx, a, b)); cut += b - a
    for yy, iv in horz.items():
        for a, b in merge(iv):
            segs.append(("h", yy, a, b)); cut += b - a
    return segs, holes, labels, cut


def write(t, with_labels):
    edges = cube_edges()
    pieces = pieces_of(edges, t)
    used = sum(p[0] * p[1] for p in pieces)
    area, W, H, rows = best_layout(pieces)
    segs, holes, labels, cut = build(rows, W, H)
    SW, SH = W + MARGIN * 2, H + MARGIN * 2

    body = []
    for kind, f, a, b in segs:
        if kind == "v":
            body.append(f'<line class="cut" x1="{f:.2f}" y1="{a:.2f}" x2="{f:.2f}" y2="{b:.2f}"/>')
        else:
            body.append(f'<line class="cut" x1="{a:.2f}" y1="{f:.2f}" x2="{b:.2f}" y2="{f:.2f}"/>')
    for cx, cy in holes:
        body.append(f'<circle class="cut" cx="{cx:.2f}" cy="{cy:.2f}" r="{HOLE/2:.2f}"/>')
    if with_labels:
        for lx, ly, txt in labels:
            body.append(f'<text class="note" x="{lx:.2f}" y="{ly:.2f}" font-size="4.2">{txt}</text>')

    svg = ('<svg xmlns="http://www.w3.org/2000/svg"\n'
           f'     width="{SW:.1f}mm" height="{SH:.1f}mm" viewBox="0 0 {SW:.1f} {SH:.1f}">\n'
           '  <style>\n'
           '    .cut  { fill: none; stroke: #000; stroke-width: 0.1; }\n'
           '    .note { fill: #9aa0a6; font-family: sans-serif; }\n'
           '  </style>\n  ' + "\n  ".join(body) + '\n</svg>\n')

    os.makedirs(OUT, exist_ok=True)
    tag = "_labels" if with_labels else ""
    p = os.path.join(OUT, f"RAONSUM_cube_foam_{t:.0f}mm_min{tag}.svg")
    io.open(p, "w", encoding="utf-8").write(svg)

    if not with_labels:
        ents = []
        for kind, f, a, b in segs:
            x1, y1, x2, y2 = (f, a, f, b) if kind == "v" else (a, f, b, f)
            ents.append("0\nLINE\n8\nCUT\n10\n%.3f\n20\n%.3f\n11\n%.3f\n21\n%.3f"
                        % (x1, SH - y1, x2, SH - y2))
        for cx, cy in holes:
            ents.append("0\nCIRCLE\n8\nCUT\n10\n%.3f\n20\n%.3f\n40\n%.3f"
                        % (cx, SH - cy, HOLE / 2))
        d = os.path.join(OUT, f"RAONSUM_cube_foam_{t:.0f}mm_min.dxf")
        io.open(d, "w", encoding="utf-8").write(
            "0\nSECTION\n2\nENTITIES\n" + "\n".join(ents) + "\n0\nENDSEC\n0\nEOF\n")
        print(f"  {os.path.basename(d)}")

    print(f"  {os.path.basename(p)}")
    print(f"  판 {SW:.0f} x {SH:.0f} mm   ({SW*SH/1e6:.3f} m2)")
    print(f"  조각 실면적 {used/1e6:.3f} m2   버리는 몫 {(1-used/(SW*SH))*100:.0f}%")
    print(f"  자르는 선 {len(segs)}개  총 {cut/1000:.2f} m")


t, labels_on = 3.0, "--labels" in sys.argv
a = sys.argv[1:]
if "--t" in a:
    t = float(a[a.index("--t") + 1])
print(f"면적 최소 배치 ({t:.0f}mm, 칼날 전용)")
write(t, labels_on)
