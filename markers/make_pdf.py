#!/usr/bin/env python3
"""인쇄용 마커 PDF를 만든다. 외부 라이브러리 없이 PDF를 직접 쓴다.

SVG를 변환기로 돌리면 인쇄 배율이 틀어질 위험이 있어서, 치수를 직접 잡는다.
마커는 5x5 셀 격자(바깥 한 겹은 검은 테두리)임을 src/ 원본에서 전수 검사로
확인했으므로 벡터 사각형으로 다시 그린다. 그래서 어떤 크기로 찍어도 선이 또렷하다.

    python3 make_pdf.py [출력폴더]
"""
import json, os, sys

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
A4 = (210.0, 297.0)
A3 = (297.0, 420.0)

# 종이로 접어 풀로 붙인다. 날개(풀칠 탭) 폭과 종이 가장자리 여백.
TAB    = 12.0
MARGIN = 8.0


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
    """큐브 한 면을 날개까지 붙여 한 장에. 오려서 접고 풀로 붙인다.

    날개는 큐브 모서리 12개에 정확히 하나씩 가도록 나눠 두었다.
      밑면과 윗면  네 변 전부 (8개)
      옆면 넷      오른쪽 한 변만 (4개)
    옆면의 오른쪽 날개는 다음 번호 옆면에 붙는다. 면 순서가 큐브를 한 바퀴 돈다.

    face_i 0~3 옆면, 4 밑면, 5 윗면(마커 없음, 낚싯줄 구멍)
    """
    pw, ph = page
    top_face = face_i == 5
    black = face_mm / (1 + QUIET * 2)
    quiet = black * QUIET
    e = face_mm

    # 날개가 붙는 변. [(모서리0, 모서리1, 바깥 법선)]
    bx = (pw - e) / 2
    by = (ph - e) / 2 - 12
    P = {"bl": (bx, by), "br": (bx + e, by), "tr": (bx + e, by + e), "tl": (bx, by + e)}
    edges = {
        "bottom": (P["bl"], P["br"], (0, -1)),
        "right":  (P["br"], P["tr"], (1, 0)),
        "top":    (P["tr"], P["tl"], (0, 1)),
        "left":   (P["tl"], P["bl"], (-1, 0)),
    }
    with_tab = (["bottom", "right", "top", "left"] if face_i >= 4 else ["right"])

    ops = []
    # 마커. 윗면은 아무도 못 보므로 비운다.
    if not top_face:
        code = CUBE_CODES[cube_i][face_i]
        ops += marker_ops(code, bx + quiet, by + quiet, black)

    # 날개 (오려낼 선) 와 접는 선
    for name in with_tab:
        p0, p1, n = edges[name]
        ops += poly(tab_poly(p0, p1, n), 0.3, 0.45)
        ops += poly([p0, p1], 0.35, 0.55, dash="2.2 1.8")
    # 날개가 없는 변은 그냥 오리는 선
    for name, (p0, p1, n) in edges.items():
        if name not in with_tab:
            ops += poly([p0, p1], 0.3, 0.45)

    # 글자
    direction, floor_code = ("TOP", None) if top_face else CUBE_DIRS[face_i]
    label = (f"CUBE {cube_i+1}   TOP  (no marker)" if top_face
             else f"CUBE {cube_i+1}   face {direction}   barcode "
                  f"{CUBE_CODES[cube_i][face_i]}")
    ops += text(label, 0, by + e + TAB + 10, 12, 0.1, pw)
    if top_face:
        ops += text("2 holes for the fishing line. reinforce with tape before piercing.",
                    0, by + e + TAB + 3, 9, 0.3, pw)
    else:
        ops += text("this face looks straight DOWN (the underside)" if floor_code is None
                    else f"this face must look toward FLOOR marker {floor_code}",
                    0, by + e + TAB + 3, 9, 0.3, pw)

    hint = ("fold the 4 tabs DOWN, tuck inside, glue to the side faces" if top_face
            else "fold the 4 tabs UP, the side faces glue over them" if face_i == 4
            else f"fold the right tab IN, glue it to face "
                 f"{CUBE_DIRS[(face_i+1) % 4][0]}")
    ops += text(hint, 0, by - TAB - 7, 8.5, 0.3, pw)
    ops += text(f"cube edge {e:.0f} mm" + ("" if top_face else
                f"   black square {black:.1f} mm"), 0, by - TAB - 14, 8, 0.4, pw)
    ops += ruler(pw, by - TAB - 23)
    ops += text("cut the solid line, crease the dashed line. 100% scale, no fit to page.",
                0, 10, 7.5, 0.5, pw)

    # 윗면 낚싯줄 구멍 자리. 둘을 벌려야 큐브가 안 돈다.
    if top_face:
        cy = by + e / 2
        for sx in (-1, 1):
            cx = bx + e / 2 + sx * (e / 2 - 22.0)
            r = 2.0
            ops += poly([(cx - r, cy), (cx, cy + r), (cx + r, cy), (cx, cy - r)],
                        0.4, 0.1, close=True)
            ops += poly([(cx - 7, cy), (cx + 7, cy)], 0.25, 0.6)
            ops += poly([(cx, cy - 7), (cx, cy + 7)], 0.25, 0.6)
        ops += text(f"{e - 44:.0f} mm apart", 0, cy - 12, 8, 0.4, pw)
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
    """그 크기가 들어가는 종이. 날개와 여백까지 보고 고른다.

    🔴 A4 폭 210mm 에 205mm 면을 올리면 가장자리 2.5mm 밖에 안 남아 프린터가
       잘라 먹거나 제멋대로 줄인다. 큐브3 은 A3 으로 간다.
    """
    need = face_mm + 2 * TAB + 2 * MARGIN
    return A4 if need <= A4[0] else A3


made = []
p = os.path.join(OUT, "RAONSUM_markers_floor_A4.pdf")
made.append((p, write_pdf([full_page(c, l, FLOOR_MM, A4) for c, l in FLOOR], p), "A4 4장"))

ccode, clabel = CEILING
big = CEIL_MM * (1 + QUIET * 2)
p = os.path.join(OUT, "RAONSUM_marker_ceiling_A4.pdf")
made.append((p, write_pdf([full_page(ccode, clabel, CEIL_MM, A4)], p),
             f"A4 1장 (선택), 흰 여백 포함 {big:.0f}mm"))

for ci in range(len(CUBE_CODES)):
    face = CUBE_FACE_MM[ci]
    p = os.path.join(OUT, f"RAONSUM_marker_cube{ci+1}.pdf")
    sheet = cube_sheet(face)
    pages = [cube_page(ci, fi, face, sheet) for fi in range(6)]
    made.append((p, write_pdf(pages, p),
                 f"{'A4' if sheet is A4 else 'A3'} 6장 (옆면4 + 밑면 + 윗면), "
                 f"한 변 {face:.0f}mm"))

cb = ", ".join(f"{v/(1+QUIET*2):.1f}" for v in CUBE_FACE_MM)
print(f"검은 사각형: 바닥 {FLOOR_MM:.0f}mm, 천장 {CEIL_MM:.0f}mm, 큐브 {cb}mm")
print(f"흰 여백 포함: 바닥 {FLOOR_MM*(1+QUIET*2):.0f}mm, 천장 {big:.0f}mm, "
      f"큐브 {', '.join(f'{v:.0f}' for v in CUBE_FACE_MM)}mm")
for path, size, note in made:
    print(f"  {os.path.basename(path)}  {size//1024}KB  {note}")
