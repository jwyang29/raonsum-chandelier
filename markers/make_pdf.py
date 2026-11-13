#!/usr/bin/env python3
"""인쇄용 마커 PDF를 만든다. 외부 라이브러리 없이 PDF를 직접 쓴다.

SVG를 변환기로 돌리면 인쇄 배율이 틀어질 위험이 있어서, 치수를 직접 잡는다.
마커는 5x5 셀 격자(바깥 한 겹은 검은 테두리)임을 src/ 원본에서 전수 검사로
확인했으므로 벡터 사각형으로 다시 그린다. 그래서 어떤 크기로 찍어도 선이 또렷하다.

    python3 make_pdf.py [출력폴더]
    python3 make_pdf.py print --tabs        종이로 접어 만들 때 (날개 붙음)
    python3 make_pdf.py print --cubetop     큐브 윗면에도 마커 (아래 설명 참고)
    python3 make_pdf.py print --cube 130,135,160    큐브 한 변 (mm)
    python3 make_pdf.py print --ink 0       검은 칸을 진짜 검정으로
    python3 make_pdf.py print --nodb        현장 보정값을 안 읽는다

기본은 **각 면만** 이다. 큐브를 3mm 포맥스로 다시 만들었으므로 접을 일이
없다. 면마다 한 장씩, 오릴 선 하나와 마커만 있다.
"""
import json, math, os, re, sys

MM = 72 / 25.4            # mm -> PDF 포인트
_pos = [a for a in sys.argv[1:] if not a.startswith("--") and not a.isdigit()]
OUT = _pos[0] if _pos else os.path.expanduser("~/Desktop")
HERE = os.path.dirname(os.path.abspath(__file__))
GRIDS = {int(k): v for k, v in json.load(open(os.path.join(HERE, "grids.json"))).items()}

FLOOR = [(0, "FLOOR 1"), (7, "FLOOR 2"), (44, "FLOOR 3"), (63, "FLOOR 4")]
CEILING = (26, "CEILING")
# 천장 마커는 선택이다. 큐브 밑면이 그 자리를 맡는다. 달면 덤으로 하나 더 잡힌다.
# A4 한 장에 들어가게 줄였다 (흰 여백 포함 200mm).
FLOOR_MM, CEIL_MM = 100.0, 133.3

# 천장에서 낚싯줄로 매단 큐브. 옆면 넷에 서로 다른 번호를 붙인다.
# 🔴 여기 CUBE_CODES 는 web/config.js 의 것과 같아야 한다. 64개 중에서
#    회전까지 넣은 거리를 보고 고른 조합이다. 함부로 바꾸지 말 것.
CUBE_CODES = [[21, 52, 50, 38, 11], [14, 13, 28, 41, 19],
              [42, 49, 56, 25, 22]]

# 면이 보는 방향과, 그 방향에 있는 바닥 마커. 붙일 때 이걸 보고 맞춘다.
#   +Z 는 바닥 0번이 있는 쪽, +X 는 63번, -Z 는 44번, -X 는 7번
# 다섯째는 밑면이다. 세워진 옆면이 안 보이는 자세(바로 밑에서 올려다볼 때)를 맡는다.
CUBE_DIRS = [("+Z", 0), ("+X", 63), ("-Z", 44), ("-X", 7), ("BOTTOM", None)]

# 큐브마다 흰 여백 포함 한 변 (mm). web/config.js 의 CUBE_PLAN 과 같아야 한다.
# 높이 매달수록 멀어지므로 커진다. 관객이 2.0m 뒤에서도 읽히는 최소값이다.
#   바닥 1.25m -> 130    2.15m -> 135    3.05m -> 160
# 셋 다 날개까지 A4 에 들어간다 (160 + 24 = 184mm).
# --cube 130,135,160 으로 한꺼번에 바꾼다.
CUBE_FACE_MM = [130.0, 135.0, 160.0]
for _i, _a in enumerate(sys.argv):
    if _a == "--cube":
        CUBE_FACE_MM = [float(v) for v in sys.argv[_i + 1].split(",")]
while len(CUBE_FACE_MM) < 3:
    CUBE_FACE_MM.append(CUBE_FACE_MM[-1])
QUIET = 0.25              # 여백은 마커 한 변의 25%. 셀 하나보다 넓어야 한다

# 🔴 검은 칸의 밝기 (0 이 검정, 255 가 흰색). make_sheets.py 의 --ink 와 같은 값을 쓴다.
# AR.js 3.4.5 는 영상을 고정 문턱 100 으로 흑백 두 값으로 자른다. 카메라가 본 밝기가
# 그걸 넘으면 그 마커는 통째로 사라진다. ARToolKit 에 직접 넣어 재 본 여유는 이렇다.
#   0 검정 / 40  카메라가 2.0배 밝게 찍어도 읽힘
#   60          1.6배까지
#   80          1.2배까지
#   90          여유 없음
# 인쇄는 이쪽이 쓰인다. SVG 쪽만 바꾸면 실제로 찍히는 건 그대로 검정이다.
# 기본을 51(#333)로 둔다. --ink 0 이면 검정이다.
INK = 51
for _i, _a in enumerate(sys.argv):
    if _a == "--ink":
        INK = int(sys.argv[_i + 1])
if INK > 60:
    print(f"⚠️ 검은 칸 밝기 {INK} 는 여유가 거의 없습니다. 60 이하를 권합니다")
INK_G = INK / 255.0
def cal_from_db():
    """현장 보정값을 Firebase 에서 읽는다. 못 읽으면 None.

    🔴 설치를 마친 뒤에 좌대를 실측해서 넣은 값은 config.js 가 아니라 /cal 에
       있다 (hub/setcal.py). config.js 만 읽으면 이 종이가 현장과 다른 숫자를
       말한다. 실제로 config 기본값으로는 420mm, 현장은 450mm 였다.
       다시 인쇄해서 그 숫자대로 붙이면 마커가 3cm 씩 틀어진다.
    읽기는 공개라 비밀값이 필요 없다. 망이 없으면 조용히 config.js 로 간다.
    """
    import urllib.request, urllib.error
    try:
        src = open(os.path.join(HERE, "..", "web", "config.js"), encoding="utf-8").read()
        m = re.search(r'databaseURL:\s*"([^"]+)"', src)
        if not m:
            return None
        with urllib.request.urlopen(m.group(1).rstrip("/") + "/cal.json", timeout=6) as r:
            return json.loads(r.read().decode() or "null") or None
    except Exception:
        return None


CAL = None if "--nodb" in sys.argv else cal_from_db()


def marker_ring_mm():
    """바닥 마커 네 장을 놓을 반지름.

    현장 보정값(/cal)의 mring 이 있으면 그걸 쓴다. 없으면 config.js 의
    refreshPedestal 과 같은 계산을 한다. 숫자를 두 군데 적지 않는다.
    🔴 검은 사각형이 아니라 흰 여백 포함 한 변으로 잰다.
    """
    if CAL and CAL.get("mring"):
        return float(CAL["mring"]) * 1000
    src = open(os.path.join(HERE, "..", "web", "config.js"), encoding="utf-8").read()

    def num(pat, dflt):
        m = re.search(pat, src)
        return float(m.group(1)) if m else dflt

    ped = num(r'diameter:\s*num\("ped",\s*([\d.]+)\)', 1.05)
    rim = num(r'rimMargin:\s*([\d.]+)', 0.02)
    dev = num(r'deviceSize:\s*([\d.]+)', 0.40)
    half = FLOOR_MM / 1000 * (1 + QUIET * 2) / 2
    pedR = ped / 2 - rim
    outer = math.sqrt(max(0.0, pedR * pedR - half * half)) - half
    inner = dev / 2 + half + 0.005
    return (math.floor(outer * 200) / 200 if outer >= inner else inner) * 1000


MRING_MM = marker_ring_mm()
A4 = (210.0, 297.0)
A3 = (297.0, 420.0)

# 날개(풀칠 탭) 폭과 종이 가장자리 여백.
TAB    = 12.0
MARGIN = 8.0

# 🔴 기본은 "각 면만" 이다. 큐브를 3mm 포맥스로 다시 만들었으므로 접을 일이
#    없다. 면만 오려서 붙이면 된다. 날개가 있으면 오릴 선이 늘고, 날개 폭
#    때문에 큐브3(160mm)이 A4 가장자리에 바짝 붙어 프린터가 줄여 버린다.
#    종이로 접어 만들던 때로 돌아가려면 --tabs 를 준다.
TABS = "--tabs" in sys.argv

# 큐브 윗면 마커. 기본은 안 넣는다.
#
# 🔴 재 보니 윗면은 관객 폰에서 거의 안 보인다. 폰을 1.50m 높이로 들고 큐브
#    축에서 0.60m 떨어져 서면 윗면 법선과의 각이 이렇다.
#       큐브1  79도    큐브2  119도    큐브3  144도
#    실측 한계가 60도다. 큐브1 윗면이 60도 안에 들어오려면 폰을 1.73m 까지
#    들어 올려야 한다. 큐브2 와 3 은 아예 등을 돌리고 있다.
#
# 🔴 그리고 쓸 번호가 없다. 3x3 격자 64개 중 지금 쓰는 18개와 회전까지 넣어
#    거리 2 이상인 남은 번호는 35 와 37 **둘뿐**이다 (markers/pick_top_codes.py).
#    큐브는 셋이라 하나는 거리 1 짜리를 써야 하는데, 거리 1 은 칸 하나만
#    잘못 읽혀도 바닥 마커로 둔갑해 월드 원점이 큐브 자리로 날아간다.
#
# 그래서 큐브1 에만 37 을 둔다 (제 밑면과 거리 4, 나머지 전부와 2).
# 큐브2 에도 넣겠다면 35 가 남아 있다. 큐브3 은 안전한 번호가 없다.
# --cubetop 을 줘야 인쇄에 들어간다. 그리고 web/config.js 도 같이 켜야 한다.
CUBE_TOP_CODES = [37, None, None]
CUBE_TOP = "--cubetop" in sys.argv


def esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def marker_ops(code, x, y, size):
    """마커 한 장. 전체를 어둡게 칠하고 흰 셀만 되돌린다."""
    g = GRIDS[code]
    c = size / 5.0
    out = [f"{INK_G:.4f} g {x*MM:.4f} {y*MM:.4f} {size*MM:.4f} {size*MM:.4f} re f", "1 g"]
    # 맞닿은 흰 셀 사이에 이음선이 보이지 않도록 아주 조금 겹쳐 그린다
    ov = c * 0.004
    for gy in range(5):
        for gx in range(5):
            if g[gy][gx] == 1:
                # PDF 는 아래가 0 이므로 행을 뒤집는다
                cx, cy = x + gx * c - ov, y + (4 - gy) * c - ov
                w = c + ov * 2
                out.append(f"{cx*MM:.4f} {cy*MM:.4f} {w*MM:.4f} {w*MM:.4f} re f")
    return out


def text(s, x, y, size=9, gray=0.2, center_w=None):
    tx = (center_w - len(s) * size * 0.5 / MM) / 2 if center_w else x
    return [f"BT /F1 {size} Tf {gray} g {tx*MM:.4f} {y*MM:.4f} Td ({esc(s)}) Tj ET"]


def text_v(s, x, y, size=8, gray=0.3):
    """90도 돌린 글씨. 옆 띠가 좁아서 가로로는 안 들어간다."""
    return [f"BT /F1 {size} Tf {gray} g 0 1 -1 0 {x*MM:.4f} {y*MM:.4f} Tm "
            f"({esc(s)}) Tj ET"]


def poly(pts, w=0.3, gray=0.2, dash=None, close=False):
    """점들을 잇는 선. 자르는 선은 실선, 접는 선은 점선으로 쓴다."""
    o = [f"{gray} G {w} w"]
    if dash:
        o.append(f"[{dash}] 0 d")
    o.append(f"{pts[0][0]*MM:.4f} {pts[0][1]*MM:.4f} m")
    for q in pts[1:]:
        o.append(f"{q[0]*MM:.4f} {q[1]*MM:.4f} l")
    if close:
        o.append("h")
    o.append("S")
    if dash:
        o.append("[] 0 d")
    return o


def tab_poly(p0, p1, n):
    """p0 에서 p1 로 가는 변에 붙는 날개. 바깥쪽을 45도로 좁혀 모서리에서 안 겹치게.

    n 은 바깥을 향하는 단위 법선이다.
    """
    tx, ty = (p1[0] - p0[0]), (p1[1] - p0[1])
    L = (tx * tx + ty * ty) ** 0.5
    tx, ty = tx / L, ty / L
    d = min(TAB, L / 3)                      # 변이 짧으면 덜 좁힌다
    return [p0,
            (p0[0] + n[0]*TAB + tx*d, p0[1] + n[1]*TAB + ty*d),
            (p1[0] + n[0]*TAB - tx*d, p1[1] + n[1]*TAB - ty*d),
            p1]


def crop(x, y, w, h, t=2.0):
    o = ["0.75 g 0.3 w"]
    for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
        o.append(f"{(cx-t)*MM:.4f} {cy*MM:.4f} m {(cx+t)*MM:.4f} {cy*MM:.4f} l S")
        o.append(f"{cx*MM:.4f} {(cy-t)*MM:.4f} m {cx*MM:.4f} {(cy+t)*MM:.4f} l S")
    return o


def ruler(page_w, y):
    x = (page_w - 100) / 2
    return ["0.2 g 0.35 w",
            f"{x*MM:.4f} {y*MM:.4f} m {(x+100)*MM:.4f} {y*MM:.4f} l S",
            f"{x*MM:.4f} {(y-2)*MM:.4f} m {x*MM:.4f} {(y+2)*MM:.4f} l S",
            f"{(x+100)*MM:.4f} {(y-2)*MM:.4f} m {(x+100)*MM:.4f} {(y+2)*MM:.4f} l S",
            ] + text("this line must measure 100 mm  (print at 100%, no scaling)",
                     0, y - 5, 7.5, 0.35, page_w)


def vruler(x, y, length=100.0):
    """세로 100mm 자. 표지를 뺐으므로 배율 확인은 장마다 이것뿐이다."""
    o = ["0.2 g 0.35 w",
         f"{x*MM:.4f} {y*MM:.4f} m {x*MM:.4f} {(y+length)*MM:.4f} l S",
         f"{(x-2)*MM:.4f} {y*MM:.4f} m {(x+2)*MM:.4f} {y*MM:.4f} l S",
         f"{(x-2)*MM:.4f} {(y+length)*MM:.4f} m {(x+2)*MM:.4f} {(y+length)*MM:.4f} l S"]
    o += text_v(f"this must measure {length:.0f} mm   PRINT AT 100%, NO SCALING",
                x - 3, y + 2, 7.5, 0.35)
    return o


def sheet_page(tiles, page):
    """한 장에 사각형 여러 개를 세로로 쌓는다.

    🔴 사이를 띄우지 않는다. 두 사각형이 맞닿으면 한 번 자를 때 둘이 갈라진다.
       포맥스 재단 때와 같은 원리다. 띄우면 자를 선이 두 배가 되고, 무엇보다
       A4 한 장에 들어가던 짝이 안 들어간다 (150 + 130 = 280, 쓸 수 있는 높이 281).

    🔴 글자는 사각형 오른쪽 띠에 적는다. 위에 적으면 한 장당 10mm 씩 먹어서
       짝이 깨진다 (135 + 9 + 135 + 9 = 288 > 281). 띠는 어차피 남는 자리다.

    tiles: [{"size": mm, "code": 번호 또는 None, "lines": [글자...]}]
    """
    pw, ph = page
    ops = []
    y = ph - MARGIN                      # 위에서부터 쌓는다
    for t in tiles:
        e = t["size"]
        y -= e
        x = MARGIN
        if t.get("code") is not None:
            black = e / (1 + QUIET * 2)
            quiet = black * QUIET
            ops += marker_ops(t["code"], x + quiet, y + quiet, black)
        ops += poly([(x, y), (x + e, y), (x + e, y + e), (x, y + e)], 0.35, 0.35,
                    close=True)
        ops += crop(x, y, e, e)
        # 글자는 띠 안에. 사각형 위쪽에 맞춰 적는다.
        ly = y + e - 5
        for i, line in enumerate(t.get("lines", [])):
            ops += text(line, x + e + 4, ly - i * 4.5, 8 if i == 0 else 7.5,
                        0.1 if i == 0 else 0.35)
    # 세로 자는 장마다 하나. 맨 오른쪽 끝에 둔다.
    ops += vruler(pw - MARGIN - 1, MARGIN + 4)
    return pw, ph, ops


def full_page(code, label, marker_mm, page):
    pw, ph = page
    quiet = marker_mm * QUIET
    block = marker_mm + quiet * 2
    bx, by = (pw - block) / 2, (ph - block) / 2 - 6
    ops = crop(bx, by, block, block)
    ops += marker_ops(code, bx + quiet, by + quiet, marker_mm)
    ops += text(f"{label}   barcode {code}   black square {marker_mm:.0f} mm",
                0, by + block + 8, 10, 0.15, pw)
    ops += ruler(pw, by - 12)
    ops += text("matte paper, do not cut the white margin", 0, 10, 7.5, 0.5, pw)
    return pw, ph, ops


def tile_page(code, label, marker_mm, rows, cols, r, c, page):
    pw, ph = page
    quiet = marker_mm * QUIET
    block = marker_mm + quiet * 2
    tw, th = block / cols, block / rows
    tx, ty = (pw - tw) / 2, (ph - th) / 2 - 4
    # 타일 영역만 보이게 자른다. 마커 전체를 그 안에 맞춰 옮긴다.
    ox = tx - c * tw
    oy = ty - (rows - 1 - r) * th
    ops = [f"q {tx*MM:.4f} {ty*MM:.4f} {tw*MM:.4f} {th*MM:.4f} re W n"]
    ops += marker_ops(code, ox + quiet, oy + quiet, marker_mm)
    ops += ["Q", "0.7 g 0.3 w [2 2] 0 d",
            f"{tx*MM:.4f} {ty*MM:.4f} {tw*MM:.4f} {th*MM:.4f} re S", "[] 0 d"]
    ops += text(f"{label} barcode {code}   row {r+1} / col {c+1}  of {rows}x{cols}",
                0, ty + th + 7, 9.5, 0.15, pw)
    ops += text("print at 100%, butt the dashed edges together", 0, 10, 7.5, 0.5, pw)
    return pw, ph, ops


def write_pdf(pages, path):
    objs, out = [], bytearray(b"%PDF-1.4\n")
    n_pages = len(pages)
    # 1 Catalog, 2 Pages, 3 Font, then page/content pairs
    kids = " ".join(f"{4+i*2} 0 R" for i in range(n_pages))
    objs.append(f"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, (pw, ph, ops) in enumerate(pages):
        stream = "\n".join(ops).encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw*MM:.4f} {ph*MM:.4f}] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5+i*2} 0 R >>")
        objs.append((f"<< /Length {len(stream)} >>\nstream\n", stream, "\nendstream"))

    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode()
        if isinstance(o, tuple):
            out += o[0].encode() + o[1] + o[2].encode()
        else:
            out += o.encode()
        out += b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    with open(path, "wb") as f:
        f.write(bytes(out))
    return len(out)


def cube_page(cube_i, face_i, face_mm, page):
    """큐브 한 면을 한 장에. 기본은 면만 그린다 (--tabs 면 접는 날개까지).

    🔴 큐브를 3mm 포맥스로 다시 만들었으므로 접을 일이 없다. 오려서 면에
       붙이면 된다. 그래서 날개도 접는 선도 안 그린다. 오릴 선 하나뿐이다.

    face_i 0~3 옆면, 4 밑면, 5 윗면
    """
    pw, ph = page
    top_face = face_i == 5
    black = face_mm / (1 + QUIET * 2)
    quiet = black * QUIET
    e = face_mm
    top_code = CUBE_TOP_CODES[cube_i] if (top_face and CUBE_TOP) else None

    # 날개를 안 그리면 글자가 면에 더 붙어도 된다. 그만큼 면을 크게 쓴다.
    pad = TAB if TABS else 4.0
    bx = (pw - e) / 2
    by = (ph - e) / 2 - (12 if TABS else 6)
    P = {"bl": (bx, by), "br": (bx + e, by), "tr": (bx + e, by + e), "tl": (bx, by + e)}
    edges = {
        "bottom": (P["bl"], P["br"], (0, -1)),
        "right":  (P["br"], P["tr"], (1, 0)),
        "top":    (P["tr"], P["tl"], (0, 1)),
        "left":   (P["tl"], P["bl"], (-1, 0)),
    }

    ops = []
    # 마커. 윗면은 --cubetop 을 줬을 때만, 그것도 번호가 있는 큐브만.
    if not top_face:
        code = CUBE_CODES[cube_i][face_i]
        ops += marker_ops(code, bx + quiet, by + quiet, black)
    elif top_code is not None:
        ops += marker_ops(top_code, bx + quiet, by + quiet, black)

    if TABS:
        with_tab = ["bottom", "right", "top", "left"] if face_i >= 4 else ["right"]
        for name in with_tab:
            p0, p1, n = edges[name]
            ops += poly(tab_poly(p0, p1, n), 0.3, 0.45)
            ops += poly([p0, p1], 0.35, 0.55, dash="2.2 1.8")
        for name, (p0, p1, n) in edges.items():
            if name not in with_tab:
                ops += poly([p0, p1], 0.3, 0.45)
    else:
        # 오릴 선 하나. 모서리 표시를 같이 둬서 자를 대기 쉽게 한다.
        ops += poly([P["bl"], P["br"], P["tr"], P["tl"]], 0.35, 0.35, close=True)
        ops += crop(bx, by, e, e)

    # 글자
    direction, floor_code = ("TOP", None) if top_face else CUBE_DIRS[face_i]
    if top_face:
        label = (f"CUBE {cube_i+1}   TOP   barcode {top_code}" if top_code is not None
                 else f"CUBE {cube_i+1}   TOP  (no marker)")
    else:
        label = (f"CUBE {cube_i+1}   face {direction}   barcode "
                 f"{CUBE_CODES[cube_i][face_i]}")
    ops += text(label, 0, by + e + pad + 10, 12, 0.1, pw)

    if top_face:
        note = ("the sheet TOP edge must point the same way as face +Z."
                if top_code is not None
                else "2 holes for the fishing line. reinforce with tape before piercing.")
    else:
        note = ("this face looks straight DOWN (the underside)" if floor_code is None
                else f"this face must look toward FLOOR marker {floor_code}")
    ops += text(note, 0, by + e + pad + 3, 9, 0.3, pw)

    if TABS:
        hint = ("fold the 4 tabs DOWN, tuck inside, glue to the side faces" if top_face
                else "fold the 4 tabs UP, the side faces glue over them" if face_i == 4
                else f"fold the right tab IN, glue it to face "
                     f"{CUBE_DIRS[(face_i+1) % 4][0]}")
    else:
        hint = "cut the solid square and glue it flat on the foam face"
    ops += text(hint, 0, by - pad - 7, 8.5, 0.3, pw)
    ops += text(f"cube edge {e:.0f} mm" +
                ("" if (top_face and top_code is None) else
                 f"   black square {black:.1f} mm"), 0, by - pad - 14, 8, 0.4, pw)
    ops += ruler(pw, by - pad - 23)
    ops += text(("cut the solid line, crease the dashed line. " if TABS else
                 "cut the solid line. ") +
                "100% scale, no fit to page.", 0, 10, 7.5, 0.5, pw)

    # 윗면 낚싯줄 구멍 자리. 둘을 벌려야 큐브가 안 돈다.
    # 🔴 마커를 올렸으면 구멍이 검은 사각형을 물면 안 된다. 흰 여백 안으로
    #    밀어 넣는다. 여백이 좁으면 구멍 표시를 아예 안 그리고 글로 알린다.
    if top_face:
        cy = by + e / 2
        inset = 22.0
        if top_code is not None:
            room = quiet - 3.0            # 구멍 반지름 2mm + 1mm 여유
            inset = min(inset, max(6.0, room))
        if top_code is not None and quiet < 6.0:
            ops += text("quiet zone too narrow for the line holes. "
                        "pierce outside the printed sheet.", 0, cy, 8, 0.3, pw)
        else:
            for sx in (-1, 1):
                cx = bx + e / 2 + sx * (e / 2 - inset)
                r = 2.0
                ops += poly([(cx - r, cy), (cx, cy + r), (cx + r, cy), (cx, cy - r)],
                            0.4, 0.1, close=True)
                ops += poly([(cx - 7, cy), (cx + 7, cy)], 0.25, 0.6)
                ops += poly([(cx, cy - 7), (cx, cy + 7)], 0.25, 0.6)
            # ⚠️ 마커가 있으면 이 글씨가 검은 사각형에 겹쳐 안 보인다.
            #    그때는 면 바깥으로 내린다.
            ty = (by - pad - 20.5) if top_code is not None else (cy - 12)
            ops += text(f"holes {e - inset*2:.0f} mm apart, "
                        f"{inset:.0f} mm in from each edge", 0, ty, 8, 0.4, pw)
    return pw, ph, ops


def write_pdf(pages, path):
    objs, out = [], bytearray(b"%PDF-1.4\n")
    n_pages = len(pages)
    # 1 Catalog, 2 Pages, 3 Font, then page/content pairs
    kids = " ".join(f"{4+i*2} 0 R" for i in range(n_pages))
    objs.append(f"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, (pw, ph, ops) in enumerate(pages):
        stream = "\n".join(ops).encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw*MM:.4f} {ph*MM:.4f}] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5+i*2} 0 R >>")
        objs.append((f"<< /Length {len(stream)} >>\nstream\n", stream, "\nendstream"))

    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode()
        if isinstance(o, tuple):
            out += o[0].encode() + o[1] + o[2].encode()
        else:
            out += o.encode()
        out += b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    with open(path, "wb") as f:
        f.write(bytes(out))
    return len(out)


def cube_sheet(face_mm):
    """그 크기가 들어가는 종이.

    🔴 A4 폭 210mm 에 205mm 면을 올리면 가장자리 2.5mm 밖에 안 남아 프린터가
       잘라 먹거나 제멋대로 줄인다.
    날개를 빼면 큐브3(160mm)도 A4 에 여유 있게 들어간다 (160 + 16 = 176mm).
    """
    need = face_mm + 2 * (TAB if TABS else 0) + 2 * MARGIN
    return A4 if need <= A4[0] else A3


def index_page(items, page):
    """맨 앞 차례. 스물세 장이 다 비슷하게 생겨서 이게 없으면 못 찾는다.

    ⚠️ 본문 글꼴이 Helvetica 라 한글이 안 들어간다. 영문으로 적는다.
       배치도(make_layout.py)가 한글로 된 종이라 그쪽을 같이 들고 보면 된다.
    """
    pw, ph = page
    ops = []
    y = ph - 30
    ops += text("FACETS BETWEEN US", 20, y, 17, 0.1)
    ops += text("marker sheets", 20, y - 9, 11, 0.4)
    y -= 19
    ops += ["0.25 G 0.4 w", f"{20*MM:.4f} {y*MM:.4f} m {(pw-20)*MM:.4f} {y*MM:.4f} l S"]

    y -= 13
    for line in ["PRINT AT 100%.  no fit to page, no scaling.",
                 "MATTE paper.  gloss kills the marker under a spotlight.",
                 "DO NOT CUT the white margin around the black square.",
                 "CHECK the 100 mm ruler on every page with a real ruler."]:
        ops += text(line, 20, y, 9.5, 0.15)
        y -= 10

    y -= 6
    ops += ["0.25 G 0.4 w", f"{20*MM:.4f} {y*MM:.4f} m {(pw-20)*MM:.4f} {y*MM:.4f} l S"]
    y -= 13
    ops += text("page", 20, y, 8, 0.45)
    ops += text("what", 46, y, 8, 0.45)
    ops += text("black square", 120, y, 8, 0.45)
    y -= 4
    ops += ["0.7 G 0.3 w", f"{20*MM:.4f} {y*MM:.4f} m {(pw-20)*MM:.4f} {y*MM:.4f} l S"]
    y -= 11
    for rng, what, blk in items:
        ops += text(rng, 20, y, 9.5, 0.1)
        ops += text(what, 46, y, 9.5, 0.1)
        ops += text(blk, 120, y, 9.5, 0.25)
        y -= 10.5

    y -= 7
    ops += ["0.25 G 0.4 w", f"{20*MM:.4f} {y*MM:.4f} m {(pw-20)*MM:.4f} {y*MM:.4f} l S"]
    y -= 13
    guide = [
        f"FLOOR  put the 4 sheets {MRING_MM:.0f} mm from the pedestal axis,",
        "       all four facing the SAME way (tops toward marker 44).",
    ]
    if TABS:
        guide += [
            "CUBE   4 sides + 1 bottom + 1 top.",
            "       fold the tabs IN so only markers show outside.",
        ]
    else:
        guide += [
            "CUBE   4 sides + 1 bottom + 1 top.  FACES ONLY, no fold tabs.",
            "       cut each square and glue it flat on the foam face.",
            "       the sheet TOP edge goes toward the cube TOP on side faces.",
        ]
    guide += [
        ("TOP    carries a marker. keep the 2 line holes in the white margin."
         if CUBE_TOP else
         "TOP    no marker. only the 2 holes for the fishing line."),
        "CEILING  optional. the cube bottoms already cover that view.",
    ]
    for line in guide:
        ops += text(line, 20, y, 9, 0.2)
        y -= 10
    ops += text("raonsum-chandelier / markers/make_pdf.py", 20, 16, 7.5, 0.55)
    return pw, ph, ops


# =============================================================
#  한 장에 최대한 담는다.
#
#  🔴 사각형 둘을 가로로 못 놓는다. 가장 작은 둘도 130 + 130 = 260 인데
#     쓸 수 있는 폭이 194 다. 그래서 세로 한 줄로만 쌓는다. 높이 하나짜리
#     짐싸기 문제가 된다. 큰 것부터 넣는 FFD 로 푼다 (사각형이 네 종류뿐이라
#     이 크기에서는 최적과 같다).
#
#  🔴 사이를 띄우지 않는다. 맞닿은 두 사각형은 한 번 자르면 둘로 갈라진다.
#     띄우면 150 + 130 = 280 이 281 을 넘어 짝이 깨지고 넉 장이 더 든다.
# =============================================================
USABLE_H = A4[1] - 2 * MARGIN

def pack(tiles):
    bins = []
    for t in sorted(tiles, key=lambda t: -t["size"]):
        for b in bins:
            if sum(x["size"] for x in b) + t["size"] <= USABLE_H:
                b.append(t)
                break
        else:
            bins.append([t])
    return bins


tiles = []
for code, label in FLOOR:
    tiles.append({"size": FLOOR_MM * (1 + QUIET * 2), "code": code, "kind": "floor",
                  "lines": [label, f"barcode {code}",
                            f"{MRING_MM:.0f} mm from axis"]})

for ci in range(len(CUBE_CODES)):
    e = CUBE_FACE_MM[ci]
    for fi in range(6):
        if fi == 5:
            tc = CUBE_TOP_CODES[ci] if CUBE_TOP else None
            # 🔴 윗면 인쇄 안에는 아무것도 안 그린다. 치수도 구멍 표시도 뺀다.
            #    구멍은 현장에서 자리를 보고 뚫는 쪽이 낫다. 종이에 미리
            #    찍어 두면 포맥스에 이미 뚫어 놓은 구멍과 어긋난다.
            tiles.append({"size": e, "code": tc, "kind": "cube",
                          "lines": [f"CUBE {ci+1}  TOP",
                                    f"barcode {tc}" if tc is not None else "no marker"]
                                   + ([ "keep holes in the white margin"]
                                      if tc is not None else [])})
            continue
        direction, floor_code = CUBE_DIRS[fi]
        tiles.append({"size": e, "code": CUBE_CODES[ci][fi], "kind": "cube",
                      "lines": [f"CUBE {ci+1}  {direction}",
                                f"barcode {CUBE_CODES[ci][fi]}",
                                "faces straight down" if floor_code is None
                                else f"toward FLOOR {floor_code}"]})

# --tabs 는 옛 방식이다. 날개를 접어야 하므로 한 면에 한 장을 다 쓴다.
# 그때는 담을 수가 없다.
if TABS:
    sheets = [[t] for t in tiles]
    pages = []
    for c, l in FLOOR:
        pages.append(full_page(c, l, FLOOR_MM, A4))
    for ci in range(len(CUBE_CODES)):
        for fi in range(6):
            pages.append(cube_page(ci, fi, CUBE_FACE_MM[ci], A4))
else:
    sheets = pack(tiles)
    pages = [sheet_page(b, A4) for b in sheets]

# 천장은 흰 여백까지 200mm 라 194mm 안에 안 들어간다. 혼자 한 장을 쓴다.
ccode, clabel = CEILING
pages.append(full_page(ccode, clabel, CEIL_MM, A4))

# 표지는 기본으로 안 넣는다. --index 로 되살린다.
items = []
n = 1
for b in sheets:
    what = ", ".join(t["lines"][0] for t in b)
    items.append((str(n), what, f"{b[0]['size']:.0f} mm" if len(b) == 1
                  else " / ".join(f"{t['size']:.0f}" for t in b) + " mm"))
    n += 1
if TABS:
    items = [(f"1-{len(FLOOR)}", "FLOOR 1-4", f"{FLOOR_MM*(1+QUIET*2):.0f} mm")]
    n = len(FLOOR) + 1
    for ci in range(len(CUBE_CODES)):
        items.append((f"{n}-{n+5}", f"CUBE {ci+1}   6 faces",
                      f"{CUBE_FACE_MM[ci]:.0f} mm"))
        n += 6
items.append((str(n), f"CEILING   barcode {ccode}   (optional)", f"{CEIL_MM:.0f} mm"))
if "--index" in sys.argv:
    pages.insert(0, index_page(items, A4))

name = "RAONSUM_markers_A4_ALL" + ("_tabs" if TABS else "") + \
       ("_top" if CUBE_TOP else "") + ".pdf"
out = os.path.join(OUT, name)
size = write_pdf(pages, out)

cb = ", ".join(f"{v/(1+QUIET*2):.1f}" for v in CUBE_FACE_MM)
print(f"검은 사각형: 바닥 {FLOOR_MM:.0f}mm, 천장 {CEIL_MM:.0f}mm, 큐브 {cb}mm")
print(f"흰 여백 포함: 바닥 {FLOOR_MM*(1+QUIET*2):.0f}mm, 천장 {CEIL_MM*(1+QUIET*2):.0f}mm, "
      f"큐브 {', '.join(f'{v:.0f}' for v in CUBE_FACE_MM)}mm")
print(f"마커 반지름 {MRING_MM:.0f}mm  " +
      ("(현장 보정값 /cal 에서 읽음)" if CAL and CAL.get("mring")
       else "(config.js 계산값. 망이 없어 /cal 을 못 읽었습니다)"))
if CUBE_TOP:
    have = [i+1 for i, c in enumerate(CUBE_TOP_CODES) if c is not None]
    print(f"윗면 마커가 들어간 큐브: {have}  (나머지는 안전한 번호가 없습니다)")
print()
print(f"  {os.path.basename(out)}   A4 {len(pages)}장   {size//1024}KB")
if TABS:
    print("  접는 날개가 있어 한 면에 한 장을 씁니다 (담지 않음)")
else:
    print(f"  사각형 {len(tiles)}개를 {len(sheets)}장에 담았습니다 (천장 1장 별도)")
    # 🔴 A4 로는 이게 최소다. 160 여섯 장은 아래에 121mm 가 남지만 제일 작은
    #    사각형이 130mm 라 아무것도 안 들어간다. 나머지 2190mm 는 281mm 짜리
    #    칸 네 개가 최소이므로 6 + 4 + 4 = 14 장이 하한이다.
for rng, what, blk in items:
    print(f"    {rng:>3}쪽  {what:<42} {blk}")
