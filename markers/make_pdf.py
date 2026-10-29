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
FLOOR_MM, CEIL_MM = 100.0, 300.0

# 천장에서 낚싯줄로 매단 큐브. 옆면 넷에 서로 다른 번호를 붙인다.
# 🔴 여기 CUBE_CODES 는 web/config.js 의 것과 같아야 한다. 64개 중에서
#    회전까지 넣은 거리를 보고 고른 조합이다. 함부로 바꾸지 말 것.
CUBE_CODES = [[13, 22, 25, 42], [21, 37, 50, 56], [28, 35, 38, 41]]

# 면이 보는 방향과, 그 방향에 있는 바닥 마커. 붙일 때 이걸 보고 맞춘다.
#   +Z 는 바닥 0번이 있는 쪽, +X 는 63번, -Z 는 44번, -X 는 7번
CUBE_DIRS = [("+Z", 0), ("+X", 63), ("-Z", 44), ("-X", 7)]

# 흰 여백까지 포함한 한 변 (mm). 큐브 한 변이 이 값이다.
# 기본 130 은 중심축에 2.08m 로 매달 때 나온 값이다 (화면 가로 1/16 규칙).
# 더 높이 매달거나 비켜 매달면 커져야 한다. --cube 160 으로 바꾼다.
CUBE_FACE_MM = 130.0
for _i, _a in enumerate(sys.argv):
    if _a == "--cube":
        CUBE_FACE_MM = float(sys.argv[_i + 1])
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
    """큐브 한 면. 어느 큐브의 어느 면인지 크게 적는다. 열두 장이 섞이면 못 찾는다."""
    pw, ph = page
    code = CUBE_CODES[cube_i][face_i]
    direction, floor_code = CUBE_DIRS[face_i]
    black = face_mm / (1 + QUIET * 2)
    quiet = black * QUIET
    bx, by = (pw - face_mm) / 2, (ph - face_mm) / 2 - 10
    ops = crop(bx, by, face_mm, face_mm)
    ops += marker_ops(code, bx + quiet, by + quiet, black)
    ops += text(f"CUBE {cube_i+1}   face {direction}   barcode {code}",
                0, by + face_mm + 12, 12, 0.1, pw)
    ops += text(f"this face must look toward FLOOR marker {floor_code}",
                0, by + face_mm + 5, 9, 0.3, pw)
    ops += text(f"cube edge {face_mm:.0f} mm   black square {black:.1f} mm   "
                f"TOP of this sheet points to the ceiling",
                0, by - 7, 8, 0.35, pw)
    ops += ruler(pw, by - 16)
    ops += text("matte paper, do not cut the white margin", 0, 10, 7.5, 0.5, pw)
    return pw, ph, ops


made = []
p = os.path.join(OUT, "RAONSUM_markers_floor_A4.pdf")
made.append((p, write_pdf([full_page(c, l, FLOOR_MM, A4) for c, l in FLOOR], p), "A4 4장"))

ccode, clabel = CEILING
big = CEIL_MM * (1 + QUIET * 2)
p = os.path.join(OUT, "RAONSUM_marker_ceiling_large.pdf")
made.append((p, write_pdf([full_page(ccode, clabel, CEIL_MM, (big + 20, big + 40))], p),
             f"{big+20:.0f}x{big+40:.0f}mm 1장"))

p = os.path.join(OUT, "RAONSUM_marker_ceiling_tiles_A4.pdf")
tiles = [tile_page(ccode, clabel, CEIL_MM, 3, 3, r, c, A4) for r in range(3) for c in range(3)]
made.append((p, write_pdf(tiles, p), "A4 9장 (3x3)"))

# ⚠️ A4 로 찍는다. 종이 크기를 마커에 맞춰 잘라 놓으면 인쇄 대화상자가
#    용지에 맞춰 줄여 버린다. 마커는 배율이 틀어지면 그대로 못 쓴다.
CUBE_PAGE = A4
for ci in range(len(CUBE_CODES)):
    p = os.path.join(OUT, f"RAONSUM_marker_cube{ci+1}.pdf")
    pages = [cube_page(ci, fi, CUBE_FACE_MM, CUBE_PAGE) for fi in range(4)]
    made.append((p, write_pdf(pages, p),
                 f"{CUBE_PAGE[0]:.0f}x{CUBE_PAGE[1]:.0f}mm 4장"))

print(f"검은 사각형: 바닥 {FLOOR_MM:.0f}mm, 천장 {CEIL_MM:.0f}mm, "
      f"큐브 {CUBE_FACE_MM/(1+QUIET*2):.1f}mm")
print(f"흰 여백 포함: 바닥 {FLOOR_MM*(1+QUIET*2):.0f}mm, 천장 {big:.0f}mm, "
      f"큐브 {CUBE_FACE_MM:.0f}mm")
for path, size, note in made:
    print(f"  {os.path.basename(path)}  {size//1024}KB  {note}")
