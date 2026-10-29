#!/usr/bin/env python3
"""샹들리에 오브젝트들의 그림자를 바닥 시트지 커팅용 SVG 로 뽑는다.

그림자는 위에서 본 실루엣이므로, web/blobs.json 의 3D 형태를 바닥면에 투영하고
외곽선을 딴다. 볼록껍질로 감싸면 갈고리와 구멍이 사라져 밋밋해지므로,
투영을 격자에 채운 뒤 marching squares 로 윤곽을 추적한다. 구멍도 같이 나온다.

배치는 원형 좌대를 비우고 황금각 나선으로 퍼뜨린다. 크리스탈이 링에 앉는 방식과
같은 규칙이라 작품과 결이 맞는다. 관객이 사방에서 보며 좌대를 돌기 때문에
어느 방향에서 봐도 같아야 하고, 비어 보이는 쪽(앞뒤)이 생기면 안 된다.
각도 간격을 재서 한쪽이 벌어지면 알려 준다.

    python3 make_shadows.py --pedestal 800 --count 26 --out shadows.svg
"""
import json, math, os, sys

def arg(n, d, c=str):
    a = sys.argv[1:]
    return c(a[a.index(n) + 1]) if n in a else d

HERE = os.path.dirname(os.path.abspath(__file__))
BLOBS = arg("--blobs", os.path.join(HERE, "..", "web", "blobs.json"))
OUT   = arg("--out", os.path.join(HERE, "shadows.svg"))
COUNT = arg("--count", 26, int)
GRID  = arg("--grid", 220, int)

# 배치 (mm). 시트지는 좌대 위에서 시작해 옆면을 타고 바닥으로 퍼진다.
PED_D     = arg("--pedestal", 1050.0, float)  # 원형 좌대 지름
PED_H     = arg("--pedh", 320.0, float)       # 좌대 높이. 옆면 띠의 세로가 된다
DEVICE    = arg("--device", 400.0, float)     # 센싱 장치 한 변. 그 자리는 비운다
SPREAD_D  = arg("--spread", PED_D + 1200.0, float)  # 바닥까지 전체 퍼지는 지름
CLEAR_D   = arg("--clear", PED_D, float)      # 바닥 구역이 시작하는 지름. 기본은 좌대 둘레
SEED      = arg("--seed", 3, int)
# 어느 면에 붙일지. 기본은 바닥만이다.
# 좌대 위와 옆면도 넣을 수 있게 남겨 뒀다. 그때는 마커를 피해야 하므로
# 상판에 들어가는 개수가 확 줄고, 면마다 커팅 파일이 따로 나온다.
ZONES     = arg("--zones", "floor").split(",")

# 구역별 개수. 좌대 위는 마커를 피해야 해서 자리가 적다.
N_TOP   = arg("--ntop", 7, int)
N_SIDE  = arg("--nside", 6, int)
N_FLOOR = arg("--nfloor", 26, int)

# 크기 (긴 변). 좌대 위는 좁아서 작고, 테두리를 넘어서면서 커졌다가 멀어지며 준다.
SIZE_TOP  = arg("--sizetop", 105.0, float)
SIZE_NEAR = arg("--near", 260.0, float)
SIZE_FAR  = arg("--far", 110.0, float)

# 바닥에서 안쪽으로 모으는 정도. 반지름을 t**BIAS 로 잡는다.
# 0.5 가 면적 기준으로 고르게 퍼지는 값이고, 1 보다 크면 좌대 가까이로 모인다.
BIAS    = arg("--bias", 1.25, float)
# 서로 떨어뜨리는 정도. 중심 거리가 (크기합) * 이 값 이상이어야 한다.
# 작을수록 촘촘해진다. 0.46 이 거의 안 닿는 정도다.
FLOOR_K = arg("--k", 0.40, float)
# 좌대 테두리에서 띄울 폭. 바닥 조각이 좌대 밑으로 들어가면 안 된다.
# 마커는 좌대 윗면 가장자리까지 차 있다. 평면으로 보면 테두리 바로 바깥이
# 마커 흰 여백과 13mm 까지 가까워진다. 실제로는 좌대 몸통이 사이를 가려서
# 카메라 영상에서 붙어 보이지 않지만, 붙이는 사람 눈에 보이는 여백도 필요하다.
RIM_PAD = arg("--rimpad", 40.0, float)

# 🔴 어떤 그림자를 쓸지. 바닥에 까는 것은 완만한 곡선만 쓴다.
# 라이브러리에는 애벌레처럼 혹이 줄지어 난 것과, 가는 목으로 두 덩어리가 이어진 것이
# 섞여 있다. 커팅해서 바닥에 깔아 놓으면 그 둘이 특히 지저분하다.
# 셋이 재는 것이 다르다. 하나만으로는 안 걸러진다.
# 🔴 그림자가 "고리"나 "선"으로 읽혀야 한다. 관객이 천에 그린 획이 크리스탈이 되고,
# 그 크리스탈의 그림자다. 뭉개진 덩어리가 되면 획이었다는 게 안 보인다.
# 폭이 고른지(band), 그 폭에 비해 긴지(path), 너무 납작하지 않은지(width) 를 본다.
BAND_MIN  = arg("--band", 0.58, float)    # 면적/둘레 ÷ 반폭. 폭이 고르면 1 에 가깝다
PATH_MIN  = arg("--path", 5.0, float)     # 길이가 반폭의 몇 배인지. 덩어리는 작다
WIDTH_MIN = arg("--width", 0.15, float)   # 반폭 ÷ 긴 변. 실오라기를 막는다
# 혹은 "얼마나 급한가"가 아니라 "몇 군데나 급한가"로 센다.
# 곡률 반지름만 보면 한쪽 끝이 매끈하게 뾰족해진 것까지 걸린다. 그건 완만한 모양이다.
# 애벌레는 급한 자리가 줄줄이 있고, 잎사귀는 한 군데뿐이다. 그 차이를 센다.
BUMP_R   = arg("--bumpr", 0.075, float)   # 이보다 급하게 꺾이면 혹 한 자리로 센다
BUMP_MAX = arg("--bumps", 2, int)         # 봐주는 혹 자리 수
SOFT_MAX = arg("--soft", 60, int)         # 혹을 깎아 보는 횟수 상한. 0 이면 안 깎는다
LIGHT_N  = arg("--lights", 28, int)       # 빛 방향을 몇 개나 훑을지
SCORE_N  = arg("--scoregrid", 120, int)   # 고를 때 쓰는 격자. 본 격자보다 성기게
PER_BLOB = arg("--perblob", 4, int)       # 덩어리 하나에서 몇 장까지 쓸지
HOOP_MIX = arg("--hoops", 0.35, float)    # 바닥에서 고리가 차지할 비율
# 이보다 작은 구멍은 메운다. 시트지에서 떼어낼 수가 없다 (긴 변 기준).
MIN_HOLE = arg("--minhole", 0.06, float)

# 커팅용 한 장. 시트지 롤 폭 안에 들어가게 모은다 (mm).
ROLL_W   = arg("--rollw", 1200.0, float)
NEST_CELL = arg("--cell", 2.5, float)     # 자리를 찾을 때 쓰는 격자 (mm)
NEST_ROTS = arg("--rots", 16, int)        # 조각을 몇 각도까지 돌려 볼지
NEST_PASSES = arg("--passes", 3, int)     # 다 놓고 나서 위로 올려 보는 횟수
NEST_GAP = arg("--nestgap", 5.0, float)
NEST_MG  = arg("--nestmargin", 15.0, float)

# 🔴 마커 회피. 이 값이 AR 인식을 지킨다.
# 바코드 마커는 검은 사각형 둘레에 흰 여백(quiet zone)이 있어야 외곽선이 사각형으로
# 잡힌다. 검은 시트지가 여백에 닿으면 마커와 한 덩어리가 되어 사각형이 아니게 되고,
# 그 마커는 아예 안 읽힌다. 그래서 흰 블록 둘레로 한 번 더 비운다.
_MK   = 100.0                                 # 마커 검은 사각형 한 변
BLOCK = _MK * 1.5                             # 흰 여백 포함 블록 (make_sheets.py 와 같다)
MARK_CLEAR = arg("--markclear", 55.0, float)  # 블록 바깥으로 더 비울 폭
_RIM  = 20.0                                  # 마커를 좌대 테두리에서 떼는 폭

# 마커를 놓은 원의 반지름. 비우면 좌대 지름에서 자동으로 잡는다.
# web/config.js 의 refreshPedestal 과 같은 식이다. 한쪽만 고치면 안 맞는다.
MARK_R = arg("--markring", math.floor(
    (math.sqrt(max(0.0, (PED_D / 2 - _RIM) ** 2 - (_MK / 2) ** 2)) - _MK / 2) / 5) * 5, float)

# 네 마커의 중심. web/config.js 의 MARKERS 와 같은 순서다 (+Z, -X, -Z, +X).
MARK_POS = [(0, MARK_R), (-MARK_R, 0), (0, -MARK_R), (MARK_R, 0)]
KEEP_H = BLOCK / 2 + MARK_CLEAR               # 마커마다 비울 정사각형의 절반

GOLDEN = math.pi * (3 - math.sqrt(5))


# ── 투영과 래스터화 ────────────────────────────────────────────
AXES = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}


def project(v, axis):
    """한 축을 버리고 평면에 투영한다. 버리는 축이 빛이 오는 방향이다."""
    a, b = AXES[axis]
    return [(v[i + a], v[i + b]) for i in range(0, len(v), 3)]


def light_dirs(n):
    """빛이 올 수 있는 방향을 고르게 n 개 고른다. 반구만 보면 된다.
    반대편에서 비춘 그림자는 좌우만 뒤집힌 같은 그림이다."""
    out = []
    for i in range(n):
        z = (i + 0.5) / n                      # 0 바로 위부터 1 까지
        r = math.sqrt(max(0.0, 1 - z * z))
        a = i * GOLDEN
        out.append((math.cos(a) * r, math.sin(a) * r, z))
    return out


def project_dir(v, d):
    """아무 방향에서나 비춘 그림자. d 가 빛이 오는 방향이다.

    축 셋만 쓰면 덩어리진 것만 남는다. 길쭉하게 보이는 방향이 따로 있는데
    그게 축과 나란하다는 보장이 없다. 방향을 넓게 훑어야 모양이 다양해진다.
    """
    dx, dy, dz = d
    L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    dx, dy, dz = dx / L, dy / L, dz / L
    # d 와 나란하지 않은 아무 벡터로 평면 기저를 만든다
    hx, hy, hz = (0.0, 0.0, 1.0) if abs(dz) < 0.9 else (1.0, 0.0, 0.0)
    ux, uy, uz = hy * dz - hz * dy, hz * dx - hx * dz, hx * dy - hy * dx
    L = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
    ux, uy, uz = ux / L, uy / L, uz / L
    wx, wy, wz = dy * uz - dz * uy, dz * ux - dx * uz, dx * uy - dy * ux
    return [(v[i] * ux + v[i + 1] * uy + v[i + 2] * uz,
             v[i] * wx + v[i + 1] * wy + v[i + 2] * wz)
            for i in range(0, len(v), 3)]


def best_axis(v):
    """형태가 가장 넓게 보이는 방향을 고른다.

    ribbon 처럼 한 축으로 납작한 형태는 방향을 잘못 잡으면 가느다란 선이 된다.
    바닥 그래픽은 형태가 읽혀야 하므로 투영 넓이가 가장 큰 방향을 쓴다.
    """
    best, area = "z", -1
    for ax in AXES:
        p = project(v, ax)
        xs = [q[0] for q in p]; ys = [q[1] for q in p]
        a = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if a > area:
            best, area = ax, a
    return best


def rasterize(pts2, index, n):
    """삼각형을 격자에 채운다. 스캔라인으로 단순하게."""
    xs = [p[0] for p in pts2]; ys = [p[1] for p in pts2]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    sx = (n - 3) / max(1e-9, hi_x - lo_x)
    sy = (n - 3) / max(1e-9, hi_y - lo_y)
    s = min(sx, sy)                      # 가로세로 비율을 지킨다
    ox = (n - (hi_x - lo_x) * s) / 2
    oy = (n - (hi_y - lo_y) * s) / 2
    g = [bytearray(n) for _ in range(n)]

    for t in range(0, len(index), 3):
        tri = []
        for k in range(3):
            px, py = pts2[index[t + k]]
            tri.append(((px - lo_x) * s + ox, (py - lo_y) * s + oy))
        ymin = max(0, int(min(p[1] for p in tri)))
        ymax = min(n - 1, int(math.ceil(max(p[1] for p in tri))))
        for yy in range(ymin, ymax + 1):
            yc = yy + 0.5
            xs_hit = []
            for a in range(3):
                (x1, y1), (x2, y2) = tri[a], tri[(a + 1) % 3]
                if (y1 <= yc < y2) or (y2 <= yc < y1):
                    xs_hit.append(x1 + (yc - y1) / (y2 - y1) * (x2 - x1))
            xs_hit.sort()
            for a in range(0, len(xs_hit) - 1, 2):
                for xx in range(max(0, int(xs_hit[a])), min(n - 1, int(xs_hit[a + 1])) + 1):
                    g[yy][xx] = 1
    return g


# ── marching squares ───────────────────────────────────────────
# 각 셀의 네 모서리 상태로 경계 선분을 만든다. 구멍도 자연히 닫힌 고리로 나온다.
EDGES = {
    1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 6: [(0, 2)],
    7: [(3, 2)], 8: [(2, 3)], 9: [(2, 0)], 11: [(2, 1)], 12: [(1, 3)],
    13: [(1, 0)], 14: [(0, 3)], 5: [(3, 0), (1, 2)], 10: [(0, 1), (2, 3)],
}
MID = {0: (0.5, 0.0), 1: (1.0, 0.5), 2: (0.5, 1.0), 3: (0.0, 0.5)}


def contours(g, n):
    segs = {}
    for y in range(n - 1):
        for x in range(n - 1):
            code = (g[y][x] and 1) | ((g[y][x + 1] and 1) << 1) \
                 | ((g[y + 1][x + 1] and 1) << 2) | ((g[y + 1][x] and 1) << 3)
            for a, b in EDGES.get(code, []):
                p = (round(x + MID[a][0], 1), round(y + MID[a][1], 1))
                q = (round(x + MID[b][0], 1), round(y + MID[b][1], 1))
                segs.setdefault(p, []).append(q)

    loops = []
    while segs:
        start = next(iter(segs))
        loop, cur = [start], start
        while True:
            nxt = segs.get(cur)
            if not nxt:
                break
            step = nxt.pop()
            if not nxt:
                segs.pop(cur, None)
            if step == start:
                break
            loop.append(step)
            cur = step
        if len(loop) > 12:
            loops.append(loop)
    return loops


def simplify(pts, tol):
    if len(pts) < 4:
        return pts
    keep = [0, len(pts) - 1]
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        ax, ay = pts[i]; bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        worst, wi = 0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / L
            if d > worst:
                worst, wi = d, k
        if worst > tol:
            keep.append(wi); stack += [(i, wi), (wi, j)]
    return [pts[i] for i in sorted(set(keep))]


def chaikin(pts, passes=2):
    for _ in range(passes):
        out = []
        for a, b in zip(pts, pts[1:] + pts[:1]):
            out.append((a[0] * .75 + b[0] * .25, a[1] * .75 + b[1] * .25))
            out.append((a[0] * .25 + b[0] * .75, a[1] * .25 + b[1] * .75))
        pts = out
    return pts


def outline(variant, n, axis=None, dir=None):
    """한 방향에서 본 그림자. axis 나 dir 이 빛이 오는 방향이다."""
    pts2 = (project_dir(variant["verts"], dir) if dir
            else project(variant["verts"], axis or best_axis(variant["verts"])))
    g = rasterize(pts2, variant["index"], n)
    loops = [chaikin(simplify(l, 1.1)) for l in contours(g, n)]
    loops = [l for l in loops if len(l) > 8]
    if not loops:
        return None
    # 격자 좌표를 가장 긴 변이 1 인 좌표로
    xs = [p[0] for l in loops for p in l]; ys = [p[1] for l in loops for p in l]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    s = 1.0 / max(w, h, 1e-9)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    loops = [[((p[0] - cx) * s, (p[1] - cy) * s) for p in l] for l in loops]
    # 작은 구멍은 메운다. 시트지에서 떼어낼 수가 없고 때가 탄 것처럼 보인다.
    big = max(loops, key=_area)
    return [big] + [l for l in loops if l is not big
                    and math.sqrt(_area(l)) >= MIN_HOLE / 2]


# ── 모양 고르기 ────────────────────────────────────────────────
def _area(loop):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def _perim(loop):
    return sum(math.hypot(x2 - x1, y2 - y1)
               for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1]))


def _hull(pts):
    p = sorted(set(pts))
    if len(p) < 3:
        return p
    def half(ps):
        h = []
        for q in ps:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (q[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(q)
        return h
    return half(p)[:-1] + half(p[::-1])[:-1]


def _resample(loop, n):
    """둘레를 n 등분해 점을 다시 찍는다. 원래 점은 간격이 제각각이라
    그대로 재면 점이 촘촘한 데가 더 급하게 꺾인 것처럼 나온다.

    ⚠️ 누적 길이로 걷는다. 변마다 남은 거리를 들고 다니면, 변 하나가 간격보다
    짧을 때 그 변에서 한 점도 못 찍고 넘어가 결과가 통째로 빈다.
    """
    P = _perim(loop)
    if P < 1e-12:
        return []
    step = P / n
    out, target, acc = [], 0.0, 0.0
    for (ax, ay), (bx, by) in zip(loop, loop[1:] + loop[:1]):
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-12:
            continue
        while target <= acc + L and len(out) < n:
            u = (target - acc) / L
            out.append((ax + (bx - ax) * u, ay + (by - ay) * u))
            target += step
        acc += L
    while len(out) < n:          # 반올림으로 마지막 한둘이 빌 수 있다
        out.append(loop[-1])
    return out


def _dist(g, n):
    """채워진 칸마다 가장 가까운 바깥까지의 거리. 체임퍼 (3,4) 두 번 훑기.
    3 이 한 칸이다. 이걸로 그림자의 '폭'을 잰다. 구멍 안쪽도 바깥으로 친다."""
    INF = 1 << 20
    d = [[(INF if g[y][x] else 0) for x in range(n)] for y in range(n)]
    for y in range(n):
        row = d[y]; prev = d[y - 1] if y else None
        for x in range(n):
            if row[x] == 0:
                continue
            v = row[x]
            if x:
                v = min(v, row[x - 1] + 3)
            if prev is not None:
                if x:
                    v = min(v, prev[x - 1] + 4)
                v = min(v, prev[x] + 3)
                if x + 1 < n:
                    v = min(v, prev[x + 1] + 4)
            row[x] = v
    for y in range(n - 1, -1, -1):
        row = d[y]; nxt = d[y + 1] if y + 1 < n else None
        for x in range(n - 1, -1, -1):
            if row[x] == 0:
                continue
            v = row[x]
            if x + 1 < n:
                v = min(v, row[x + 1] + 3)
            if nxt is not None:
                if x + 1 < n:
                    v = min(v, nxt[x + 1] + 4)
                v = min(v, nxt[x] + 3)
                if x:
                    v = min(v, nxt[x - 1] + 4)
            row[x] = v
    return d


def band_score(g, loops, n):
    """고리나 선으로 읽히는지를 셋으로 잰다.

    폭이 고른 띠는 넓이가 (폭 x 길이), 둘레가 (2 x 길이)라 넓이/둘레가 곧 반폭이다.
    그래서 넓이/둘레를 가장 두꺼운 데의 반폭으로 나누면,
      폭이 고른 띠와 고리는 1 에 가깝고,
      가운데가 불룩한 덩어리는 0.5 쯤으로 떨어진다.
    목이 잘록한 아령도 같은 이유로 떨어진다. 따로 재지 않아도 걸린다.

    path 는 길이가 반폭의 몇 배인지다. 덩어리는 작고 획은 크다.
    width 는 반폭이 긴 변의 몇 배인지다. 리본을 옆에서 본 실오라기를 막는다.
    """
    A = sum(sum(r) for r in g)
    P = sum(_perim(l) for l in loops)
    half = max(max(r) for r in _dist(g, n)) / 3.0
    if A < 4 or P < 1 or half < 1:
        return 0.0, 0.0, 0.0
    return (A / P) / half, A / (2 * half * half), half / n


def shape_score(loops):
    """외곽선의 혹만 센다. 고리와 선인지는 band_score 가 격자에서 본다."""
    main = max(loops, key=_area)

    # 혹. 세 점의 외접원으로 곡률 반지름을 재고, BUMP_R 밑으로 내려가는
    #    구간이 몇 '군데'인지 센다. 값이 아니라 군데 수를 세는 게 핵심이다.
    #    잎사귀처럼 한쪽 끝만 뾰족한 건 한 군데, 애벌레는 줄줄이다.
    D = _resample(main, 300)
    nD = len(D)
    k = max(2, nD // 25)
    tight = []
    for i in range(nD):
        ax, ay = D[i - k]; bx, by = D[i]; cx, cy = D[(i + k) % nD]
        ar = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2
        r = 9.9 if ar < 1e-12 else (
            math.hypot(bx - ax, by - ay) * math.hypot(cx - bx, cy - by)
            * math.hypot(cx - ax, cy - ay) / (4 * ar))
        tight.append(r < BUMP_R)
    return sum(1 for i in range(nD) if tight[i] and not tight[i - 1])


def _lowpass(loop, k, n=240):
    """외곽선을 둘레 방향으로 흐린다. 혹이 깎이고 전체 흐름은 남는다."""
    p = _resample(loop, n)
    m = len(p)
    if m < 8:
        return loop
    for _ in range(k):
        p = [((p[i - 1][0] + 2 * p[i][0] + p[(i + 1) % m][0]) / 4,
              (p[i - 1][1] + 2 * p[i][1] + p[(i + 1) % m][1]) / 4) for i in range(m)]
    return p


def _renorm(loops):
    xs = [q[0] for l in loops for q in l]
    ys = [q[1] for l in loops for q in l]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    s = 1.0 / max(w, h, 1e-9)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [[((q[0] - cx) * s, (q[1] - cy) * s) for q in l] for l in loops]


def soften(loops):
    """혹이 많으면 외곽선을 흐려서 깎아 본다. 그래도 안 되면 버린다.

    버리기만 하면 남는 게 둥근 덩어리뿐이다. 선으로 읽히는 그림자는 리본 쪽에서
    나오는데 그쪽이 하필 혹투성이라, 깎아야 획이 살면서 완만한 것이 생긴다.
    ⚠️ 구멍은 깎아도 살려 둔다. 구멍이 메워지면 고리가 고리로 안 보인다.
    """
    k = 0
    while shape_score(loops) > BUMP_MAX and k < SOFT_MAX:
        k += 10
        soft = [_lowpass(l, k) for l in loops]
        soft = _renorm([l for l in soft if _perim(l) > 1e-6])
        if not soft:
            return None
        loops = soft
    if shape_score(loops) > BUMP_MAX:
        return None
    big = max(loops, key=_area)
    return [big] + [l for l in loops if l is not big
                    and math.sqrt(_area(l)) >= MIN_HOLE / 2]


def shape_pool(variants, n):
    """고리나 선으로 읽히는 그림자만 모은다.

    한 덩어리를 여러 방향에서 비춘다. 투영에서 버리는 축이 빛이 오는 방향이므로,
    방향이 다르면 같은 덩어리의 다른 그림자다. 라이브러리를 다시 굽지 않고도
    후보가 수십 배가 된다.

    고르는 건 성긴 격자에서 한다. 거르고 남은 것만 본 격자로 다시 뽑으면
    같은 결과를 훨씬 빨리 얻는다. 한 덩어리에서 너무 많이 쓰면 비슷한 게
    줄줄이 나오므로 PER_BLOB 장까지만 쓴다.
    """
    dirs = light_dirs(LIGHT_N)
    pool, seen = [], 0
    for i, v in enumerate(variants):
        got = []
        for j, d in enumerate(dirs):
            pts2 = project_dir(v["verts"], d)
            g = rasterize(pts2, v["index"], SCORE_N)
            ls = [l for l in contours(g, SCORE_N) if len(l) > 8]
            if not ls:
                continue
            seen += 1
            band, path, width = band_score(g, ls, SCORE_N)
            if band < BAND_MIN or path < PATH_MIN or width < WIDTH_MIN:
                continue
            o = outline(v, n, None, d)
            if not o:
                continue
            soft = soften(o)
            if not soft:
                continue
            got.append({"kind": v["kind"], "name": f"{i}d{j}", "loops": soft,
                        "hoop": len(soft) > 1, "band": band, "path": path})
        # 고리를 먼저 집는다. 선은 어차피 많이 남는다.
        got.sort(key=lambda s: (not s["hoop"], -s["path"]))
        pool += got[:PER_BLOB]
    return pool, seen


# ── 마커와 장치 회피 ───────────────────────────────────────────
# 형태를 반지름 size/2 인 원으로 보고 비울 사각형과 겹치는지 본다.
# 블롭이 원보다 홀쭉해서 이 검사는 조금 보수적이다. 인식이 걸린 문제라 그게 낫다.
def _clear_of(x, y, size, cx, cy, half, pad=0.0):
    r = size / 2 + pad
    dx = max(abs(x - cx) - half, 0.0)
    dy = max(abs(y - cy) - half, 0.0)
    return math.hypot(dx, dy) >= r


def ok_on_top(x, y, size):
    if not _clear_of(x, y, size, 0, 0, DEVICE / 2, 10):   # 장치 자리
        return False
    return all(_clear_of(x, y, size, mx, my, KEEP_H) for mx, my in MARK_POS)


def min_radius(loops, size, x, y, rot):
    """배치한 뒤 외곽선이 중심에 가장 가까워지는 거리.

    크기의 절반으로 어림하면 안 된다. 그림자는 들쭉날쭉해서 실제로 안쪽으로
    뻗는 길이가 크기의 절반보다 한참 짧다. 어림으로 막으면 좌대에서 멀찍이
    떨어져 버리고, 어림으로 통과시키면 좌대 밑으로 들어간다.
    """
    c = math.cos(math.radians(rot))
    s = math.sin(math.radians(rot))
    m = 1e9
    for loop in loops:
        for px, py in loop:
            X, Y = px * size, py * size
            m = min(m, math.hypot(x + X * c - Y * s, y + X * s + Y * c))
    return m


def spaced(x, y, size, placed, k=0.46):
    return all(math.hypot(x - p["x"], y - p["y"]) >= (size + p["size"]) * k
               for p in placed)


# ── 배치 ───────────────────────────────────────────────────────
def angles(seed):
    """황금각으로 계속 돌아가는 각. 구역이 바뀌어도 이어져서 한 흐름으로 읽힌다."""
    rng = __import__("random").Random(seed)
    i = 0
    while True:
        yield i * GOLDEN + rng.uniform(-0.09, 0.09)
        i += 1


def place_top(rng, ang):
    """좌대 상판. 장치와 마커를 뺀 고리 안에 들어가는 것만 남긴다."""
    pedR = PED_D / 2
    out, tries = [], 0
    while len(out) < N_TOP and tries < N_TOP * 400:
        tries += 1
        size = SIZE_TOP * rng.uniform(0.78, 1.22)
        lo = DEVICE / 2 * math.sqrt(2) + size / 2 + 12
        hi = pedR - size / 2 - 12
        if hi <= lo:
            break
        a = next(ang)
        r = lo + (hi - lo) * math.sqrt(rng.random())
        x, y = math.cos(a) * r, math.sin(a) * r
        if not ok_on_top(x, y, size) or not spaced(x, y, size, out):
            continue
        out.append({"zone": "top", "x": x, "y": y, "size": size,
                    "rot": math.degrees(a) + rng.uniform(-22, 22)})
    return out


def place_side(rng, ang):
    """좌대 옆면. 원통이라 펼치면 가로 pi*지름, 세로 좌대 높이인 띠가 된다.
    시트지는 한 방향으로만 휘면 되므로 그대로 둘러 붙일 수 있다."""
    W = math.pi * PED_D
    cap = PED_H * 0.62
    out = []
    for i in range(N_SIDE):
        a = next(ang) % (2 * math.pi)
        size = min(cap, SIZE_TOP * 1.35) * rng.uniform(0.8, 1.2)
        out.append({"zone": "side",
                    "u": a / (2 * math.pi) * W,          # 둘레를 따라간 거리
                    "v": PED_H / 2 + rng.uniform(-1, 1) * (PED_H / 2 - size / 2 - 8),
                    "ang": a, "size": size,
                    "rot": rng.uniform(-28, 28)})        # 아래로 흐르는 방향
    return out


def place_floor(rng, ang, shapes):
    """바닥. 좌대 둘레에서 시작해 바깥으로 퍼진다.

    반지름을 t**BIAS 로 잡는다. 0.5 면 면적 기준으로 고르게 퍼지고,
    1 보다 크면 좌대 가까이로 모인다. 모을수록 서로 닿기 쉬워지므로
    겹치는 자리는 버리고 다음 황금각으로 넘어간다.

    🔴 어느 형태가 올지 여기서 정한다. 좌대 테두리를 넘는지 보려면 실제 외곽선이
    있어야 하고, 외곽선은 형태가 정해져야 나온다. 중심 거리로만 막으면
    들쭉날쭉한 그림자가 좌대 밑으로 들어간다 (실제로 7개가 112mm 까지 들어갔다).
    """
    r0, r1 = CLEAR_D / 2, SPREAD_D / 2
    pedR = PED_D / 2
    # 고리와 선을 정해진 비율로 번갈아 쓴다. 그냥 돌려 가며 쓰면 후보에 많은 쪽으로
    # 쏠려서 바닥이 한 가지로 보인다.
    hoops = [s for s in shapes if s["hoop"]]
    lines = [s for s in shapes if not s["hoop"]]
    n_hoop = n_line = 0
    out, tries = [], 0
    while len(out) < N_FLOOR and tries < N_FLOOR * 400:
        tries += 1
        t = (len(out) + 0.5) / N_FLOOR
        r = r0 + (r1 - r0) * t ** BIAS
        a = next(ang)
        size = (SIZE_NEAR + (SIZE_FAR - SIZE_NEAR) * t) * rng.uniform(0.86, 1.14)
        rot = math.degrees(a) + rng.uniform(-22, 22)
        take_hoop = bool(hoops) and (not lines or n_hoop < HOOP_MIX * (len(out) + 1))
        bucket, idx = (hoops, n_hoop) if take_hoop else (lines, n_line)
        sh = bucket[idx % len(bucket)]

        # 테두리를 넘으면 넘은 만큼 바깥으로 민다. 형태마다 안쪽으로 뻗는 길이가
        # 달라서, 이렇게 해야 각자 테두리에 딱 붙는 자리까지 들어온다.
        x, y = math.cos(a) * r, math.sin(a) * r
        for _ in range(6):
            m = min_radius(sh["loops"], size, x, y, rot)
            if m >= pedR + RIM_PAD:
                break
            r += (pedR + RIM_PAD - m) + 2
            x, y = math.cos(a) * r, math.sin(a) * r
        else:
            continue

        if not spaced(x, y, size, out, FLOOR_K):
            continue
        if take_hoop:
            n_hoop += 1
        else:
            n_line += 1
        out.append({"zone": "floor", "x": x, "y": y, "size": size, "rot": rot,
                    "loops": sh["loops"], "kind": sh["kind"], "hoop": sh["hoop"]})
    return out


# ── 그리기 ─────────────────────────────────────────────────────
def path_of(loops, size):
    d = []
    for loop in loops:
        pts = [(x * size, y * size) for x, y in loop]
        d.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z")
    return " ".join(d)


def group(p, ox, oy, fill="#111"):
    return (f'<g transform="translate({ox + p["x"]:.2f},{oy + p["y"]:.2f}) '
            f'rotate({p["rot"]:.1f})"><path d="{path_of(p["loops"], p["size"])}" '
            f'fill="{fill}" fill-rule="evenodd"/></g>')


def abs_loops(p):
    """배치된 상태의 외곽선을 mm 좌표로 돌려준다. 회전까지 먹인다.
    SVG 의 rotate 와 같은 방향이어야 커팅한 조각이 도면과 같은 각으로 나온다."""
    c = math.cos(math.radians(p["rot"]))
    s = math.sin(math.radians(p["rot"]))
    out = []
    for loop in p["loops"]:
        out.append([((x * p["size"]) * c - (y * p["size"]) * s,
                     (x * p["size"]) * s + (y * p["size"]) * c) for x, y in loop])
    return out


def spin(loops, deg):
    """외곽선을 그 자리에서 돌린다. SVG 의 rotate 와 같은 방향이다."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[(x * c - y * s, x * s + y * c) for x, y in l] for l in loops]


def _bitmap(loops, cell, pad):
    """조각을 격자로 찍는다. 한 줄을 정수 하나로 들고 AND 한 번으로 부딪힘을 본다.

    구멍은 비워서 찍는다 (even-odd). 고리의 구멍이 종이의 1/10 쯤 되는데
    메워 버리면 그만큼이 통째로 자투리가 된다. 부풀릴 때 구멍 가장자리도 같이
    안으로 자라므로, 구멍 속에 들어간 조각도 같은 폭만큼 떨어진다.
    """
    xs = [q[0] for l in loops for q in l]
    ys = [q[1] for l in loops for q in l]
    d = max(1, int(round(pad / cell)))
    ox, oy = min(xs) - d * cell, min(ys) - d * cell
    w = int(math.ceil((max(xs) - min(xs)) / cell)) + 2 * d + 1
    h = int(math.ceil((max(ys) - min(ys)) / cell)) + 2 * d + 1

    rows = [0] * h
    for yy in range(h):
        yc = (yy + 0.5) * cell + oy
        hit = []
        for l in loops:
            for (x1, y1), (x2, y2) in zip(l, l[1:] + l[:1]):
                if (y1 <= yc < y2) or (y2 <= yc < y1):
                    hit.append(x1 + (yc - y1) / (y2 - y1) * (x2 - x1))
        if len(hit) < 2:
            continue
        hit.sort()
        m = 0
        for a in range(0, len(hit) - 1, 2):
            i0 = max(0, int((hit[a] - ox) / cell))
            i1 = min(w - 1, int((hit[a + 1] - ox) / cell))
            if i1 >= i0:
                m |= ((1 << (i1 - i0 + 1)) - 1) << i0
        rows[yy] = m

    for _ in range(d):                       # 여백만큼 부풀린다
        rows = [(rows[i] | (rows[i] << 1) | (rows[i] >> 1)
                 | (rows[i - 1] if i else 0)
                 | (rows[i + 1] if i + 1 < h else 0)) for i in range(h)]

    top = [None] * w
    bot = [None] * w
    for yy, m in enumerate(rows):
        mm = m
        while mm:
            b = (mm & -mm).bit_length() - 1
            if b < w:
                if top[b] is None:
                    top[b] = yy
                bot[b] = yy
            mm &= mm - 1
    return {"rows": rows, "w": w, "h": h, "ox": ox, "oy": oy,
            "top": top, "bot": bot}


def nest(items, roll_w, gap, margin):
    """조각을 롤 폭 안에 최대한 붙여서 모은다.

    선반식으로 네모 칸을 쌓으면 오목한 데가 전부 버려진다. 여기서는 조각을
    격자로 찍어 두고, 실제 모양끼리 안 닿는 가장 낮은 자리를 찾는다.
    갈고리 안쪽에 다른 조각이 들어간다. 각도도 NEST_ROTS 가지로 돌려 본다.

    🔴 돌리고 자리를 바꾸므로 "읽는 순서 = 번호"가 깨진다.
    그래서 번호를 적은 _nest_key.svg 를 따로 낸다. 커팅 파일에는 글자가 못 들어간다
    (전부 칼금이 된다).
    """
    cell = NEST_CELL
    W = int((roll_w - 2 * margin) / cell)
    angles = [i * 360.0 / NEST_ROTS for i in range(NEST_ROTS)]

    prep = []
    for i, p in enumerate(items):
        base = abs_loops(p)
        xs = [q[0] for l in base for q in l]
        ys = [q[1] for l in base for q in l]
        prep.append({"i": i, "base": base,
                     "area": (max(xs) - min(xs)) * (max(ys) - min(ys))})
    prep.sort(key=lambda a: -a["area"])      # 큰 것부터. 나중에 넣으면 자리가 없다

    sheet_rows = []
    sky = [0] * W
    put = [None] * len(items)

    for a in prep:
        best = None
        for ang in angles:
            loops = spin(a["base"], ang)
            bm = _bitmap(loops, cell, gap / 2)
            if bm["w"] > W:
                continue
            for x in range(W - bm["w"] + 1):
                y = 0
                for j in range(bm["w"]):
                    if bm["top"][j] is None:
                        continue
                    y = max(y, sky[x + j] - bm["top"][j])
                y = max(0, y)
                # 스카이라인은 오목한 데를 못 본다. 닿으면 한 칸씩 내린다.
                for _ in range(400):
                    if not _clash(sheet_rows, bm, x, y):
                        break
                    y += 1
                else:
                    continue
                score = (y + bm["h"], x)
                if best is None or score < best[0]:
                    best = (score, x, y, ang, bm, loops)
        if best is None:
            continue
        _, x, y, ang, bm, loops = best
        while len(sheet_rows) < y + bm["h"]:
            sheet_rows.append(0)
        for r, m in enumerate(bm["rows"]):
            sheet_rows[y + r] |= m << x
        for j in range(bm["w"]):
            if bm["bot"][j] is not None:
                sky[x + j] = max(sky[x + j], y + bm["bot"][j] + 1)
        put[a["i"]] = {"x": x, "y": y, "ang": ang, "bm": bm, "loops": loops}

    _compact(put, W, NEST_PASSES)

    out = [None] * len(items)
    for i, s in enumerate(put):
        if not s:
            continue
        out[i] = {
            "loops": s["loops"],
            "dx": margin + s["x"] * cell - s["bm"]["ox"],
            "dy": margin + s["y"] * cell - s["bm"]["oy"],
            "ang": s["ang"],
        }
    placed = [o for o in out if o]
    used = max((o["dy"] + max(q[1] for l in o["loops"] for q in l))
               for o in placed) if placed else 0
    return out, used + margin, len(placed)


def _compact(put, W, passes):
    """스카이라인은 이미 놓인 조각 밑의 빈 데를 못 본다. 갈고리 안쪽이 그렇다.
    다 놓고 나서 한 조각씩 들어내고 위로 올려 본다. 옆으로도 조금 밀어 본다."""
    for _ in range(passes):
        order = sorted((i for i, s in enumerate(put) if s), key=lambda i: put[i]["y"])
        moved = False
        for i in order:
            me = put[i]
            rest = [s for j, s in enumerate(put) if s and j != i]
            top = 0
            for s in rest:
                top = max(top, s["y"] + s["bm"]["h"])
            rows = [0] * top
            for s in rest:
                for r, m in enumerate(s["bm"]["rows"]):
                    rows[s["y"] + r] |= m << s["x"]
            bm = me["bm"]
            best = (me["y"], me["x"])
            for dx in (0, -2, 2, -4, 4, -6, 6):
                x = me["x"] + dx
                if x < 0 or x + bm["w"] > W:
                    continue
                for y in range(0, best[0] + 1):
                    if not _clash(rows, bm, x, y):
                        if (y, abs(dx)) < (best[0], abs(best[1] - me["x"])):
                            best = (y, x)
                        break
            if best != (me["y"], me["x"]):
                me["y"], me["x"] = best
                moved = True
        if not moved:
            break


def _clash(sheet_rows, bm, x, y):
    for r, m in enumerate(bm["rows"]):
        if not m:
            continue
        yy = y + r
        if yy >= len(sheet_rows):
            return False                     # 아래는 아직 빈 종이다
        if sheet_rows[yy] & (m << x):
            return True
    return False


def sheet(w, h, body, extra=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.1f}mm" height="{h:.1f}mm" '
            f'viewBox="0 0 {w:.1f} {h:.1f}">{extra}<g id="shadows">{body}</g></svg>')


def main():
    data = json.load(open(BLOBS))
    shapes, seen = shape_pool(data["variants"], GRID)
    if not shapes:
        sys.exit("쓸 만한 형태가 하나도 없습니다. --neck / --curv / --hull 을 낮추세요")
    hp = [s for s in shapes if s["hoop"]]
    print(f"빛 {LIGHT_N} 방향에서 그림자 {seen}장을 보고 {len(shapes)}장을 골랐습니다 "
          f"(고름 {BAND_MIN} / 길이 {PATH_MIN} / 폭 {WIDTH_MIN} / 혹 {BUMP_MAX}군데)")
    print(f"  고리 {len(hp)}장 / 선 {len(shapes)-len(hp)}장")

    rng = __import__("random").Random(SEED)
    ang = angles(SEED)

    placed = []
    if "top" in ZONES:
        placed += place_top(rng, ang)
    if "side" in ZONES:
        placed += place_side(rng, ang)
    if "floor" in ZONES:
        placed += place_floor(rng, ang, shapes)
    for i, p in enumerate(placed):
        if "loops" in p:          # place_floor 는 형태까지 정해서 돌려준다
            continue
        sh = shapes[i % len(shapes)]
        p["loops"], p["kind"] = sh["loops"], sh["kind"]

    top   = [p for p in placed if p["zone"] == "top"]
    side  = [p for p in placed if p["zone"] == "side"]
    floor = [p for p in placed if p["zone"] == "floor"]

    base = os.path.splitext(OUT)[0]
    pedR = PED_D / 2
    made = []

    # 1) 좌대 상판. 지름만 한 원 안에 든다.
    if top:
        tw = PED_D + 40
        with open(base + "_top_cut.svg", "w") as f:
            f.write(sheet(tw, tw, "".join(group(p, tw / 2, tw / 2) for p in top)))
        made.append(base + "_top_cut.svg")

    # 2) 좌대 옆면. 펼친 띠. 둘러 붙일 때 겹칠 여유로 10mm 를 더 둔다.
    if side:
        sw, sh_ = math.pi * PED_D + 10, PED_H
        with open(base + "_side_cut.svg", "w") as f:
            f.write(sheet(sw, sh_, "".join(
                f'<g transform="translate({p["u"]:.2f},{p["v"]:.2f}) rotate({p["rot"]:.1f})">'
                f'<path d="{path_of(p["loops"], p["size"])}" fill="#111" fill-rule="evenodd"/></g>'
                for p in side)))
        made.append(base + "_side_cut.svg")

    # 3) 바닥을 한 장으로 모은 커팅 파일. 실제로 칼이 지나가는 건 이것이다.
    nested, nest_h, nest_n = nest(floor, ROLL_W, NEST_GAP, NEST_MG)
    def _d(n):
        return " ".join(
            "M" + " L".join(f"{qx + n['dx']:.2f},{qy + n['dy']:.2f}" for qx, qy in l) + " Z"
            for l in n["loops"])
    nest_body = "".join(f'<path d="{_d(n)}" fill="#111" fill-rule="evenodd"/>'
                        for n in nested if n)
    with open(base + "_nest.svg", "w") as f:
        f.write(sheet(ROLL_W, nest_h, nest_body))
    made.append(base + "_nest.svg")

    # 3-1) 같은 자리에 번호만 얹은 것. 어느 조각이 몇 번인지 보는 용도다.
    #      돌려 가며 붙였기 때문에 읽는 순서로는 번호를 알 수 없다.
    #      ⚠️ 커팅에 넣지 않는다. 글자도 테두리도 전부 칼금이 된다.
    key = []
    for i, n in enumerate(nested):
        if not n:
            continue
        xs = [q[0] + n["dx"] for l in n["loops"] for q in l]
        ys = [q[1] + n["dy"] for l in n["loops"] for q in l]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        key.append(f'<path d="{_d(n)}" fill="#e7ebef" stroke="#9fb0c0" stroke-width="1"/>'
                   f'<text x="{cx:.1f}" y="{cy + 11:.1f}" font-size="30" fill="#17a98c" '
                   f'text-anchor="middle" font-family="sans-serif" font-weight="700">'
                   f'{i + 1}</text>')
    with open(base + "_nest_key.svg", "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{ROLL_W:.1f}mm" '
                f'height="{nest_h:.1f}mm" viewBox="0 0 {ROLL_W:.1f} {nest_h:.1f}">'
                f'<rect width="{ROLL_W:.1f}" height="{nest_h:.1f}" fill="#fff"/>'
                + "".join(key) + "</svg>")
    made.append(base + "_nest_key.svg")

    # 4) 바닥을 실제 놓이는 자리 그대로 둔 것. 큰 커터가 있을 때만 쓴다.
    pad = 120
    W = SPREAD_D + pad * 2
    with open(base + "_cut.svg", "w") as f:
        f.write(sheet(W, W, "".join(group(p, W / 2, W / 2) for p in floor)))
    made.append(base + "_cut.svg")

    # 4) 도면. 어디에 무엇이 가는지 보는 용도다. 커팅에는 쓰지 않는다.
    guide = (
        f'<circle cx="{W/2}" cy="{W/2}" r="{pedR:.1f}" fill="none" stroke="#9fb0c0" stroke-width="2.5"/>'
        f'<rect x="{W/2-DEVICE/2:.1f}" y="{W/2-DEVICE/2:.1f}" width="{DEVICE}" height="{DEVICE}" '
        f'fill="#eef2f6" stroke="#9fb0c0" stroke-width="1.5"/>'
        + "".join(
            (f'<rect x="{W/2+mx-KEEP_H:.1f}" y="{W/2+my-KEEP_H:.1f}" '
             f'width="{KEEP_H*2:.1f}" height="{KEEP_H*2:.1f}" fill="#fff6e8" '
             f'stroke="#e8b36b" stroke-width="1.5" stroke-dasharray="7 6"/>' if top else "")
            + f'<rect x="{W/2+mx-BLOCK/2:.1f}" y="{W/2+my-BLOCK/2:.1f}" '
              f'width="{BLOCK}" height="{BLOCK}" fill="#fff" stroke="#c9d3dd" stroke-width="1.5"/>'
            for mx, my in MARK_POS)
        + f'<circle cx="{W/2}" cy="{W/2}" r="{SPREAD_D/2:.1f}" fill="none" '
          f'stroke="#e3e9ee" stroke-width="1.5" stroke-dasharray="6 10"/>')

    body = "".join(group(p, W / 2, W / 2) for p in floor + top)
    # 번호. 커팅 한 장에서 왼쪽 위부터 오른쪽으로 읽는 순서와 같다.
    nums = "".join(
        f'<text x="{W/2 + p["x"]:.1f}" y="{W/2 + p["y"] + 24:.1f}" font-size="68" '
        f'fill="#17a98c" stroke="#fff" stroke-width="7" paint-order="stroke" '
        f'text-anchor="middle" font-family="sans-serif" '
        f'font-weight="700">{i + 1}</text>'
        for i, p in enumerate(floor))
    zones = " / ".join(f"{n} {len(g)}" for n, g in
                       (("상판", top), ("옆면", side), ("바닥", floor)) if g)
    caption = (f"{zones} 개 · 좌대 {PED_D/1000:.2f}m 는 비움 · "
               f"전체 {SPREAD_D/1000:.1f}m · 1:1")
    warn = ("주황 점선 안은 비워 둘 것. 마커 흰 여백에 검은 시트지가 닿으면 그 마커는 안 읽힙니다"
            if top else
            f"번호는 {os.path.basename(base)}_nest_key.svg 에서 찾습니다")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W:.1f}mm" height="{W:.1f}mm"
     viewBox="0 0 {W:.1f} {W:.1f}">
  <rect width="{W:.1f}" height="{W:.1f}" fill="#fff"/>
  <g id="guides">{guide}</g>
  <g id="shadows">{body}</g>
  <g id="numbers">{nums}</g>
  <text x="{W/2}" y="{W - 64}" font-size="22" fill="#8b97a6" text-anchor="middle"
        font-family="sans-serif">{caption}</text>
  <text x="{W/2}" y="{W - 36}" font-size="20" fill="#e8b36b" text-anchor="middle"
        font-family="sans-serif">{warn}</text>
</svg>'''
    with open(OUT, "w") as f:
        f.write(svg)

    # 5) 전시 모습 미리보기(web/venue.html)가 그대로 깔 수 있게 좌표도 내보낸다.
    jpath = base + ".json"
    with open(jpath, "w") as f:
        json.dump({
            "pedestal": PED_D, "pedh": PED_H, "spread": SPREAD_D,
            "markRing": MARK_R, "device": DEVICE,
            "items": [{k: (round(v, 2) if isinstance(v, float) else v)
                       for k, v in p.items() if k != "loops"}
                      | {"loops": [[[round(x, 4), round(y, 4)] for x, y in l]
                                   for l in p["loops"]]}
                      for p in placed],
        }, f, separators=(",", ":"))

    # 사방에서 보는 작품이라 한쪽이 벌어지면 그쪽이 "뒤"로 읽힌다.
    flat = [p for p in placed if p["zone"] != "side"]
    angs = sorted(math.degrees(math.atan2(p["y"], p["x"])) % 360 for p in flat)
    gaps = [(b - a) for a, b in zip(angs, angs[1:])] + [angs[0] + 360 - angs[-1]]
    even = 360 / max(1, len(flat))

    print(f"구역 {zones} 개")
    if top and len(top) < N_TOP:
        print(f"  상판은 장치 {DEVICE:.0f}mm 와 마커를 빼고 남는 자리가 좁아 {len(top)}개만 들어갔습니다")
    print(f"각도 간격 최대 {max(gaps):.1f}도 (고르면 {even:.1f}도). "
          f"{'사방이 고릅니다' if max(gaps) < even * 2.2 else '한쪽이 벌어집니다. --seed 를 바꿔 보세요'}")
    if len(floor) < N_FLOOR:
        print(f"  바닥은 {FLOOR_K} 간격으로 {N_FLOOR}개가 안 들어가 {len(floor)}개만 놓았습니다. "
              f"--k 를 낮추거나 --spread 를 키우세요")
    sizes = sorted(p["size"] for p in placed)
    print(f"그림자 긴 변 {sizes[0]:.0f}~{sizes[-1]:.0f}mm (중앙값 {sizes[len(sizes)//2]:.0f}mm)")
    fs = sum(1 for p in floor if p.get("hoop"))
    print(f"바닥 {len(floor)}개 중 고리 {fs}개 ({fs/max(1,len(floor)):.0%}, 목표 {HOOP_MIX:.0%})")
    rr = sorted(math.hypot(p["x"], p["y"]) for p in floor)
    print(f"좌대 중심에서 {rr[0]/1000:.2f}~{rr[-1]/1000:.2f}m "
          f"(전체 지름 {SPREAD_D/1000:.2f}m, 안쪽으로 모으는 정도 {BIAS})")
    # 실제로 칼이 둘러싸는 넓이. 구멍은 뺀다.
    shape_mm2 = 0.0
    for p in floor:
        big = max(p["loops"], key=_area)
        s2 = p["size"] * p["size"]
        shape_mm2 += _area(big) * s2 - sum(_area(l) * s2 for l in p["loops"] if l is not big)
    use = shape_mm2 / max(1e-9, ROLL_W * nest_h)
    print(f"커팅 한 장: 폭 {ROLL_W:.0f}mm x 길이 {nest_h:.0f}mm, {nest_n}개, "
          f"모양이 종이의 {use:.0%} (나머지는 자투리)")
    if nest_n < len(floor):
        print(f"  ⚠️ {len(floor)-nest_n}개가 롤 폭에 안 들어갔습니다. --rollw 를 키우세요")
    over = [p for p in floor
            if min_radius(p["loops"], p["size"], p["x"], p["y"], p["rot"]) < PED_D / 2]
    print(f"좌대 안으로 들어간 조각 {len(over)}개"
          + ("" if not over else "  ⚠️ --rimpad 를 올리세요"))
    print(f"도면:   {os.path.abspath(OUT)}")
    for m in made:
        print(f"커팅용: {os.path.abspath(m)}")
    print(f"좌표:   {os.path.abspath(jpath)}")


main()
