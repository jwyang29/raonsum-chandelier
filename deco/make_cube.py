#!/usr/bin/env python3
"""매단 마커 큐브의 뼈대를 STL 로 뽑는다.

면을 통째로 찍으면 안 된다. 205mm 큐브의 겉넓이가 0.21 제곱미터라, 1.6mm 벽으로
닫아도 PLA 400g 이 넘는다. 낚싯줄에 매다는 물건에 그 무게는 쓸 데가 없다.

그래서 뼈대만 찍고 면은 인쇄물이 맡는다. 네모 테두리 + 가운데 십자 하나.
마커 종이를 그 위에 붙이면 테두리 8mm 와 십자가 다 받쳐 준다.

    판 6장 = 옆면 4 + 밑면 1 + 윗면 1
    윗면에만 낚싯줄 구멍 2개가 뚫려 있다. 나머지 다섯 면에 마커를 붙인다.
    (윗면은 아무도 못 보므로 마커가 없다)

판마다 따로 뽑는다. 다 눕혀서 찍으므로 서포트가 필요 없다.

    python3 make_cube.py [출력폴더]

치수는 web/config.js 의 CUBE_PLAN 에서 읽어 온다. 두 군데 적으면 한쪽만
고치게 되고, 그러면 종이와 뼈대가 안 맞는다.
"""
import math, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "web", "config.js")
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = _pos[0] if _pos else os.path.join(HERE, "cube")


def arg(name, default, cast=float):
    a = sys.argv[1:]
    return cast(a[a.index(name) + 1]) if name in a else default


T    = arg("--thick", 2.5)    # 판 두께
W    = arg("--rim", 8.0)      # 테두리 폭. 마커 종이가 붙는 자리다
BW   = arg("--brace", 6.0)    # 가운데 십자 폭
HOLE = arg("--hole", 3.0)     # 낚싯줄 구멍 한 변. 0.3mm 줄이라 넉넉하다
BAR  = arg("--bar", 16.0)     # 윗면 가로대 폭. 구멍이 여기 뚫린다
EDGE = arg("--edge", 22.0)    # 구멍을 테두리에서 이만큼 안쪽에
LIP  = arg("--lip", 5.0)      # 위아래 판 안쪽 턱 폭. 옆면이 여기 끼어 직각이 나온다
PLA  = arg("--density", 1.24) # g/cm3


def cube_plan():
    src = open(CONFIG, encoding="utf-8").read()
    m = re.search(r"const CUBE_PLAN = \[(.*?)\];", src, re.S)
    if not m:
        sys.exit("config.js 에서 CUBE_PLAN 을 못 찾았습니다")
    return [(float(a), float(b))
            for a, b in re.findall(r"\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]", m.group(1))]


# ---------------------------------------------------------------
#  상자만 쓴다. 겹쳐 놓아도 슬라이서가 알아서 합친다.
#  곡면이 없으니 삼각형을 직접 적는 게 가장 짧다.
# ---------------------------------------------------------------

def box(x0, y0, z0, x1, y1, z1):
    """축에 나란한 상자 하나를 삼각형 12개로."""
    p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    q = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    out = []
    for a, b, c, d in q:
        out.append((p[a], p[b], p[c]))
        out.append((p[a], p[c], p[d]))
    return out


def write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            ux, uy, uz = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
            vx, vy, vz = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
            n = (uy*vz - uz*vy, uz*vx - ux*vz, ux*vy - uy*vx)
            L = math.sqrt(sum(v*v for v in n)) or 1.0
            f.write(struct.pack("<12fH", n[0]/L, n[1]/L, n[2]/L,
                                *a, *b, *c, 0))
    return os.path.getsize(path)


def volume(tris):
    """부호 있는 사면체 합. 겹친 상자는 두 번 세므로 어림값이다."""
    v = 0.0
    for a, b, c in tris:
        v += (a[0]*(b[1]*c[2]-b[2]*c[1])
              - a[1]*(b[0]*c[2]-b[2]*c[0])
              + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
    return abs(v)


# ---------------------------------------------------------------
#  판 한 장
# ---------------------------------------------------------------

def ring(w, h):
    """바깥 w x h 네모 테두리. 판의 왼쪽 아래 모서리가 원점이다."""
    return (box(0, 0, 0, w, W, T)              # 아래
            + box(0, h - W, 0, w, h, T)        # 위
            + box(0, 0, 0, W, h, T)            # 왼쪽
            + box(w - W, 0, 0, w, h, T))       # 오른쪽


def cross(w, h):
    """가운데 십자. 마커 종이 한가운데가 처지지 않게 받친다."""
    return (box(0, h/2 - BW/2, 0, w, h/2 + BW/2, T)
            + box(w/2 - BW/2, 0, 0, w/2 + BW/2, h, T))


def marker_panel(w, h):
    return ring(w, h) + cross(w, h)


def lip(e):
    """위아래 판 안쪽에 두르는 턱. 옆면 네 장이 여기 딱 끼어 직각이 나온다.

    🔴 테이프로만 맞추면 큐브가 비뚤어진다. 비뚤면 다섯 면이 저마다 다른
       포즈를 내놓고, 앵커가 그걸 평균내서 월드가 흔들린다. 종이를 똑바로
       붙이는 것보다 이게 더 중요하다.
    턱은 안쪽을 향하므로 눕혀 찍을 때 위로 선다. 서포트가 필요 없다.
    """
    a, b = T, e - T                      # 옆면 두께만큼 비워 두는 자리
    return (box(a, a, T, b, a + LIP, T + T)
            + box(a, b - LIP, T, b, b, T + T)
            + box(a, a, T, a + LIP, b, T + T)
            + box(b - LIP, a, T, b, b, T + T))


def top_panel(e):
    """윗면. 십자 대신 가로대를 놓고 거기에 낚싯줄 구멍 둘을 뚫는다.

    구멍은 네모다. 줄을 꿰기도 쉽고 상자만으로 닫힌 구멍이 나온다.
    둘을 최대한 벌려야 큐브가 안 돈다. 한 줄로 매면 줄이 꼬여 천천히 돈다.
    """
    t = ring(e, e)
    cy = e / 2
    xs = sorted([EDGE, e - EDGE])              # 구멍 두 개의 중심
    h = HOLE / 2
    # 가로대를 x 방향으로 토막 내어 구멍을 남긴다
    cuts = []
    for x0 in xs:
        cuts.append((x0 - h, x0 + h))
    edges = [0.0] + [v for c in cuts for v in c] + [e]
    for i in range(0, len(edges) - 1, 2):      # 구멍이 아닌 구간은 통으로
        a, b = edges[i], edges[i + 1]
        if b - a > 0.01:
            t += box(a, cy - BAR/2, 0, b, cy + BAR/2, T)
    for a, b in cuts:                          # 구멍 위아래만 남긴다
        t += box(a, cy - BAR/2, 0, b, cy - h, T)
        t += box(a, cy + h, 0, b, cy + BAR/2, T)
    # 가로대와 직각으로 하나 더. 윗면이 휘지 않게 한다.
    t += box(e/2 - BW/2, 0, 0, e/2 + BW/2, e, T)
    return t


# ---------------------------------------------------------------

os.makedirs(OUT, exist_ok=True)
print(f"판 두께 {T}mm / 테두리 {W}mm / 십자 {BW}mm / 구멍 {HOLE}mm 각")
print()

for i, (floor_y, face) in enumerate(cube_plan(), start=1):
    e = face * 1000.0                 # m -> mm
    side_h = e - 2 * T                # 옆면은 위아래 판 사이에 끼인다
    parts = [
        (f"cube{i}_side.stl",   marker_panel(e, side_h), 4, "옆면 (마커 붙임)"),
        (f"cube{i}_bottom.stl", marker_panel(e, e) + lip(e), 1, "밑면 (마커 붙임)"),
        (f"cube{i}_top.stl",    top_panel(e) + lip(e),       1, "윗면 (낚싯줄 구멍 2개)"),
    ]
    total_cm3 = 0.0
    print(f"큐브{i}  한 변 {e:.0f}mm  (바닥 {floor_y:.2f}m 에 매단다)")
    for name, tris, n, note in parts:
        write_stl(os.path.join(OUT, name), tris)
        cm3 = volume(tris) / 1000.0
        total_cm3 += cm3 * n
        print(f"   {name:<20} x{n}   {len(tris)//2:>3}면  {cm3*PLA:5.0f} g/장   {note}")
    hx = e - 2 * EDGE
    print(f"   -> 6장 합쳐 약 {total_cm3*PLA:.0f} g,  낚싯줄 구멍 간격 {hx:.0f}mm")
    print()

print(f"{OUT} 에 넣었습니다.")
print("눕혀서 서포트 없이 찍습니다. 인필 20% 면 충분합니다.")
print("위아래 판 안쪽에 턱이 있습니다. 옆면 네 장을 그 안에 끼우면 직각이 나옵니다.")
