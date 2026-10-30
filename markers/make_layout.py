#!/usr/bin/env python3
"""설치용 배치도. 실제 마커 그림을 그대로 넣어 그린다 (A4 SVG 두 장).

현장에서 들고 보는 종이다. 설치를 마치면 마커를 옮기거나 다시 찍을 수 없으므로,
붙이기 전에 이 종이와 하나씩 맞춰 보는 것이 마지막 기회다.

🔴 마커를 네모와 번호로만 그리면 안 된다. 열아홉 장이 다 비슷하게 생겨서
   번호만 보고는 못 고른다. 실제 격자를 그려 두면 인쇄물과 눈으로 맞출 수 있다.

    python3 make_layout.py [출력폴더]

치수는 web/config.js 에서 읽어 온다. 좌대를 실측해서 고치면 이 종이도 바뀐다.
"""
import json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "web", "config.js")
GRIDS = json.load(open(os.path.join(HERE, "grids.json"), encoding="utf-8"))
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = _pos[0] if _pos else os.path.join(HERE, "print")

W, H = 210.0, 297.0
INK, MUTE, LINE, HOT = "#15181c", "#6b7784", "#d6dbe0", "#c2185b"
GREEN, AMBER = "#1f9d55", "#c98a00"
MONO = "ui-monospace, SFMono-Regular, Menlo, monospace"
SANS = "-apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"
SRC = open(CONFIG, encoding="utf-8").read()


def cfg(pattern, default=None):
    m = re.search(pattern, SRC)
    if not m:
        if default is None:
            sys.exit(f"config.js 에서 못 찾음: {pattern}")
        return default
    return float(m.group(1))


PED_D   = cfg(r'diameter:\s*num\("ped",\s*([\d.]+)\)')
PED_H   = cfg(r'height:\s*num\("pedh",\s*([\d.]+)\)')
MARKER  = cfg(r'markerSize:\s*num\("msize",\s*([\d.]+)\)')
DEVICE  = cfg(r'deviceSize:\s*([\d.]+)')
CLOTH   = cfg(r'clothSize:\s*([\d.]+)')
RIM     = cfg(r'rimMargin:\s*([\d.]+)')

_m = re.search(r"export const CUBE_CODES = \[(.*?)\];", SRC, re.S)
CUBE_CODES = [[int(v) for v in re.findall(r"\d+", row)]
              for row in re.findall(r"\[([^\]]+)\]", _m.group(1))] if _m else []
_m = re.search(r"const CUBE_PLAN = \[(.*?)\];", SRC, re.S)
CUBE_PLAN = [(float(a), float(b))
             for a, b in re.findall(r"\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]", _m.group(1))] if _m else []

# refreshPedestal 과 같은 계산. 🔴 검은 사각형이 아니라 흰 여백 포함 한 변으로 잰다.
_half = MARKER * 1.5 / 2
_pedR = PED_D / 2 - RIM
_outer = math.sqrt(max(0.0, _pedR * _pedR - _half * _half)) - _half
_inner = DEVICE / 2 + _half + 0.005
MRING = math.floor(_outer * 200) / 200 if _outer >= _inner else _inner

FLOOR = [(0, "+Z", 0, 1), (7, "-X", -1, 0), (44, "-Z", 0, -1), (63, "+X", 1, 0)]
CUBE_FACES = [("+Z", "바닥 0 쪽"), ("+X", "바닥 63 쪽"), ("-Z", "바닥 44 쪽"),
              ("-X", "바닥 7 쪽"), ("밑면", "똑바로 아래")]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Sheet:
    def __init__(self):
        self.o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" '
                  f'height="{H}mm" viewBox="0 0 {W} {H}">',
                  f'<rect width="{W}" height="{H}" fill="#fff"/>']

    def t(self, x, y, s, size=3.2, fill=INK, weight=400, anchor="start", mono=False):
        self.o.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}" '
            f'font-family="{MONO if mono else SANS}">{esc(s)}</text>')

    def line(self, x0, y0, x1, y1, c=LINE, w=0.3, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.o.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
                      f'stroke="{c}" stroke-width="{w}"{d}/>')

    def rect(self, x, y, w, h, fill="none", c=None, sw=0.3, dash=None):
        st = f' stroke="{c}" stroke-width="{sw}"' if c else ""
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.o.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                      f'fill="{fill}"{st}{d}/>')

    def circle(self, cx, cy, r, c, sw=0.3, dash=None, fill="none"):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.o.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" '
                      f'stroke="{c}" stroke-width="{sw}"{d}/>')

    def marker(self, code, cx, cy, block, label=None):
        """실제 마커 한 장. block 은 흰 여백 포함 한 변이다.

        grids.json 은 5x5 이고 바깥 한 겹이 검은 테두리, 1 이 흰 칸이다.
        흰 여백은 검은 사각형의 25% 씩이라 block = 검은 사각형 x 1.5 다.
        """
        g = GRIDS[str(code)]
        black = block / 1.5
        quiet = (block - black) / 2
        self.rect(cx - block/2, cy - block/2, block, block, "#fff", LINE, 0.25)
        cell = black / 5
        x0 = cx - block / 2 + quiet
        y0 = cy - block / 2 + quiet
        for r in range(5):
            for c in range(5):
                if g[r][c]:
                    continue                      # 흰 칸은 종이 그대로 둔다
                self.o.append(
                    f'<rect x="{x0 + c*cell:.3f}" y="{y0 + r*cell:.3f}" '
                    f'width="{cell + 0.03:.3f}" height="{cell + 0.03:.3f}" fill="#333"/>')
        if label:
            self.t(cx, cy + block / 2 + 4.0, label, 3.0, INK, 700, "middle", True)

    def save(self, path):
        self.o.append("</svg>")
        open(path, "w", encoding="utf-8").write("\n".join(self.o))
        return os.path.getsize(path)


def head(s, title, sub):
    s.t(14, 17, title, 6.0, INK, 700)
    s.t(W - 14, 17, "A4", 3.0, MUTE, 400, "end")
    s.t(14, 23, sub, 2.9, MUTE)
    s.line(14, 27, W - 14, 27)


def dim(s, x0, x1, y, label):
    s.line(x0, y, x1, y, MUTE, 0.3)
    for x in (x0, x1):
        s.line(x, y - 1.3, x, y + 1.3, MUTE, 0.3)
    s.t((x0 + x1) / 2, y - 1.8, label, 2.7, MUTE, 400, "middle", True)


def blank(s, x, y, w=26, unit="mm"):
    s.line(x, y + 1, x + w, y + 1, "#9aa5b1", 0.35)
    s.t(x + w + 1, y, unit, 2.6, MUTE)


# ---------------------------------------------------------------
#  1장: 바닥 배치
# ---------------------------------------------------------------

def sheet_floor():
    s = Sheet()
    head(s, "바닥 마커 배치", "인쇄물과 그림을 하나씩 맞춰 보세요. "
         "설치 후에는 옮길 수 없습니다.")

    K = 124.0 / PED_D                 # 좌대가 124mm 가 되는 축척
    CX, CY = W / 2, 98.0
    s.t(14, 34, f"1 : {1000/K:.0f}   위에서 내려다본 그림", 2.8, MUTE, 600, "start", True)

    s.circle(CX, CY, PED_D / 2 * K, "#aab4bf", 0.5, fill="#fafbfc")
    d = DEVICE * K
    s.rect(CX - d/2, CY - d/2, d, d, "#eefaf2", GREEN, 0.6)
    c = CLOTH * K
    s.rect(CX - c/2, CY - c/2, c, c, "none", AMBER, 0.45, "1.8 1.4")
    s.circle(CX, CY, MRING * K, HOT, 0.35, "2 1.8")
    s.t(CX, CY - 1.5, "장치", 2.7, GREEN, 700, "middle")
    s.t(CX, CY + 2.6, f"{DEVICE*1000:.0f} mm 각", 2.4, GREEN, 400, "middle", True)
    s.t(CX, CY + 7.0, f"천 {CLOTH*1000:.0f} mm", 2.3, AMBER, 400, "middle", True)

    # 🔴 위에서 내려다본 그림이라 종이 위쪽이 -Z 여야 손이 맞는다.
    #    +Z 를 위로 그리면 좌우가 뒤집혀 7번과 63번 자리가 바뀐다.
    blk = MARKER * 1.5 * K
    for code, name, dx, dz in FLOOR:
        mx, my = CX + dx * MRING * K, CY + dz * MRING * K
        s.marker(code, mx, my, blk, str(code))
        s.t(mx, my - blk/2 - 1.8, name, 2.5, MUTE, 400, "middle", True)

    ay = CY - PED_D / 2 * K - 6
    s.line(CX, ay + 5, CX, ay, HOT, 0.5)
    s.o.append(f'<path d="M {CX-1.5:.2f} {ay+1.7:.2f} L {CX:.2f} {ay-0.7:.2f} '
               f'L {CX+1.5:.2f} {ay+1.7:.2f} Z" fill="{HOT}"/>')
    s.t(CX + 3, ay + 1.4, "네 장 모두 인쇄물 위쪽을 이 방향으로 (44번 쪽)", 2.7, HOT, 600)

    dim(s, CX, CX + MRING * K, CY + PED_D/2*K + 8, f"{MRING*1000:.0f} mm")
    dim(s, CX - PED_D/2*K, CX + PED_D/2*K, CY + PED_D/2*K + 15, f"좌대 {PED_D*1000:.0f} mm")

    y = CY + PED_D/2*K + 25
    s.line(14, y, W - 14, y)
    y += 7
    s.t(14, y, "붙이기 전에 확인", 3.6, INK, 700)
    y += 6
    for head_, body in [
        (f"검은 사각형이 {MARKER*1000:.0f} mm 인가",
         "자로 재세요. 여기가 틀리면 월드 전체가 그 비율로 틀어집니다."),
        (f"중심에서 {MRING*1000:.0f} mm 인가",
         "네 장 모두 같은 거리. 장치 한가운데에서 마커 한가운데까지."),
        ("네 장이 한 방향인가",
         "둥근 좌대에는 맞출 모서리가 없습니다. 테이프로 기준선 하나를 긋고"),
        ("", "네 장을 그 선과 나란히 놓으세요."),
        ("흰 여백을 안 잘랐는가", "여백이 없으면 검출기가 사각형을 못 찾습니다."),
        ("무광인가", "유광은 조명이 반사되면 그 마커가 통째로 사라집니다."),
    ]:
        if head_:
            s.t(14, y, "•  " + head_, 3.1, INK, 600)
            y += 4.1
        if body:
            s.t(17.5, y, body, 2.75, MUTE)
            y += 4.1

    y += 3
    s.line(14, y, W - 14, y)
    y += 6.5
    s.t(14, y, "붙인 뒤 재서 여기 적으세요", 3.4, HOT, 700)
    y += 5.2
    s.t(14, y, "설치가 끝나면 못 옮깁니다. 실제 자리를 숫자로 넣어 보정합니다.", 2.8, MUTE)
    y += 4.2
    s.t(14, y, "장치 한가운데가 원점입니다. 거기서 마커 한가운데까지 재세요.", 2.8, MUTE)
    y += 7
    for i, (code, name, dx, dz) in enumerate(FLOOR):
        col, row = i % 2, i // 2
        bx, by = 14 + col * 92, y + row * 8
        s.t(bx, by, str(code), 3.4, INK, 700, "start", True)
        s.t(bx + 10, by, name, 2.7, MUTE, 400, "start", True)
        blank(s, bx + 20, by, 24)
        blank(s, bx + 52, by, 20, "도")
    y += 17
    s.t(14, y, "좌대 지름", 2.8, MUTE); blank(s, 36, y, 24)
    s.t(66, y, "좌대 높이", 2.8, MUTE); blank(s, 88, y, 24)
    s.t(118, y, "바닥에서 천장", 2.8, MUTE); blank(s, 148, y, 24)

    s.t(14, 293.5, "raonsum-chandelier / markers/make_layout.py", 2.3, MUTE)
    return s


# ---------------------------------------------------------------
#  2장: 큐브 다섯 면
# ---------------------------------------------------------------

def sheet_cubes():
    s = Sheet()
    head(s, "매단 큐브 면 배치", "큐브마다 옆면 넷 + 밑면 하나. "
         "윗면은 마커 없이 낚싯줄 구멍만 있습니다.")

    y = 37
    for ci, codes in enumerate(CUBE_CODES):
        floor_y, face = CUBE_PLAN[ci] if ci < len(CUBE_PLAN) else (0.0, 0.13)
        s.t(14, y, f"큐브 {ci+1}", 4.4, INK, 700)
        s.t(37, y, f"바닥 {floor_y:.2f} m", 3.0, MUTE)
        s.t(W - 14, y, f"한 변 {face*1000:.0f} mm   검은 사각형 "
                       f"{face/1.5*1000:.1f} mm", 2.8, MUTE, 400, "end")
        y += 4.5
        s.line(14, y, W - 14, y)
        y += 8.5

        blk = 25.0
        step = (W - 28) / 5
        for fi, (name, looks) in enumerate(CUBE_FACES):
            cx = 14 + step * (fi + 0.5)
            s.t(cx, y - 2.5, name, 3.0, INK if fi < 4 else HOT, 700, "middle", True)
            s.marker(codes[fi], cx, y + blk / 2, blk, str(codes[fi]))
            s.t(cx, y + blk + 8.5, looks, 2.5, MUTE, 400, "middle")
        y += blk + 16

    s.line(14, y, W - 14, y)
    y += 7
    s.t(14, y, "붙이는 방향", 3.6, INK, 700)
    y += 6
    for a, b in [
        ("옆면 넷", "인쇄물 위쪽이 천장을 향하게. 각 면이 적힌 바닥 마커를 바라보게."),
        ("밑면", "인쇄물 위쪽이 44번 반대쪽을 향하게. 똑바로 아래를 봅니다."),
        ("윗면", "마커 없음. 날개는 전부 안쪽으로 접어 바깥엔 마커만 보이게."),
    ]:
        s.t(14, y, "•  " + a, 3.1, INK, 600)
        s.t(33, y, b, 2.8, MUTE)
        y += 5.2

    y += 2
    s.t(14, y, "밑면이 왜 있나", 3.1, INK, 700)
    y += 4.8
    for line in [
        "옆면은 세워져 있어서, 좌대 바로 앞에 선 사람이 올려다보면 모서리로 보여",
        "안 읽힙니다. 밑면은 법선이 아래라 그 자세에서 가장 정면으로 보입니다.",
    ]:
        s.t(14, y, line, 2.75, MUTE)
        y += 4.1

    y += 4
    s.line(14, y, W - 14, y)
    y += 6.5
    s.t(14, y, "매단 뒤 재서 여기 적으세요", 3.4, HOT, 700)
    y += 5.2
    s.t(14, y, "바닥에서 큐브 한가운데까지의 높이입니다. "
               "한 변은 인쇄물이라 못 바꿉니다.", 2.8, MUTE)
    y += 7
    for ci in range(len(CUBE_CODES)):
        bx = 14 + ci * 62
        s.t(bx, y, f"큐브{ci+1}", 3.0, INK, 700)
        blank(s, bx + 16, y, 26, "m")

    y += 9
    s.t(14, y, "반드시 두 줄로 매세요. 한 줄이면 줄이 꼬여 큐브가 천천히 돕니다.",
        2.9, HOT, 600)
    y += 4.3
    s.t(14, y, "마커가 돌면 샹들리에가 그만큼 통째로 같이 돕니다. "
               "흔들리는 건 (수 cm) 괜찮습니다.", 2.75, MUTE)

    s.t(14, 288, "raonsum-chandelier / markers/make_layout.py", 2.5, MUTE)
    return s


os.makedirs(OUT, exist_ok=True)
a = os.path.join(OUT, "RAONSUM_layout_1_floor_A4.svg")
b = os.path.join(OUT, "RAONSUM_layout_2_cubes_A4.svg")
sa, sb = sheet_floor().save(a), sheet_cubes().save(b)
print(f"마커 반지름 {MRING*1000:.0f}mm / 좌대 {PED_D*1000:.0f}mm / "
      f"검은 사각형 {MARKER*1000:.0f}mm")
print(f"  {os.path.basename(a)}  {sa//1024}KB")
print(f"  {os.path.basename(b)}  {sb//1024}KB")
