#!/usr/bin/env python3
"""인쇄용 마커 시트를 만든다.

AR.js 바코드 마커(ARToolKit 3x3 matrix code) 원본은
nicolocarpignoli/artoolkit-barcode-markers-collection 에서 받았다. src/ 에 있다.
원본에는 흰 여백이 없어서 여기서 붙인다. 검은 테두리 바깥에 흰 여백이 없으면
ARToolKit 이 사각형을 못 찾는다.

    python3 make_sheets.py
"""
import base64, os, sys


def arg(n, d, c=str):
    a = sys.argv[1:]
    return c(a[a.index(n) + 1]) if n in a else d

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
OUT = os.path.dirname(os.path.abspath(__file__))

FLOOR = [(0, "바닥 1"), (7, "바닥 2"), (44, "바닥 3"), (63, "바닥 4")]
CEILING = (26, "천장")

FLOOR_MM = 100.0     # 검은 사각형 한 변. config.js 의 markerSize 와 같아야 한다
CEIL_MM  = 300.0
QUIET_RATIO = 0.25   # 여백은 마커 한 변의 25%. 셀 하나보다 넓어야 한다

# 🔴 검은 칸의 밝기 (0 이 검정, 255 가 흰색). 회색으로 찍고 싶을 때 쓴다.
# AR.js 3.4.5 는 영상을 고정 문턱 100 으로 흑백 두 값으로 자른다.
# 카메라가 본 밝기가 100 을 넘으면 그 마커는 통째로 사라진다.
# 실제 검출기(ARToolKit)에 그림을 넣어 재 보면, 카메라가 밝게 찍었을 때 버티는 정도가 이렇다.
#   0  검정  2.0배까지 읽힘
#   40        2.0배까지
#   60        1.6배까지
#   80        1.2배까지
#   90        1.0배 (여유 없음)
# 전시장은 흰 좌대와 흰 바닥이라 카메라가 오히려 어둡게 찍지만, 여유는 남겨 둔다.
# 기본을 51(#333)로 둔다. 2.0배 밝게 찍어도 읽히는 40 과 1.6배인 60 사이다.
# 검정으로 되돌리려면 --ink 0.
INK = arg('--ink', 51, int)
if INK > 60:
    print(f'⚠️ 검은 칸 밝기 {INK} 는 여유가 거의 없습니다. 60 이하를 권합니다')


def png_b64(code):
    with open(os.path.join(SRC, f'{code}.png'), 'rb') as f:
        return base64.b64encode(f.read()).decode()


def ink_filter():
    """검은 칸만 INK 밝기로 올린다. 흰 칸과 여백은 그대로 둔다.

    0 -> INK, 255 -> 255 인 일차식이라, 중간값이 없는 마커 그림에서는
    검은 칸만 정확히 그 값이 된다.
    ⚠️ color-interpolation-filters 를 sRGB 로 박아야 한다. SVG 기본값인
    linearRGB 로 두면 값이 그대로 안 나온다.
    """
    if INK <= 0:
        return '', ''
    k = INK / 255.0
    f = ('<filter id="ink" color-interpolation-filters="sRGB">'
         '<feComponentTransfer>'
         + ''.join(f'<feFunc{c} type="linear" slope="{1-k:.4f}" intercept="{k:.4f}"/>'
                   for c in 'RGB')
         + '</feComponentTransfer></filter>')
    return f, ' filter="url(#ink)"'


def sheet(code, label, marker_mm, page_w, page_h, path, ruler=True):
    quiet = marker_mm * QUIET_RATIO
    block = marker_mm + quiet * 2
    x = (page_w - block) / 2
    y = (page_h - block) / 2 - 8
    mx, my = x + quiet, y + quiet

    tick = 6
    marks = []
    for cx, cy in ((x, y), (x + block, y), (x, y + block), (x + block, y + block)):
        marks.append(f'<path d="M{cx-tick} {cy}H{cx+tick}M{cx} {cy-tick}V{cy+tick}" '
                     f'stroke="#bbb" stroke-width="0.2"/>')

    rule = ""
    if ruler:
        ry = y + block + 16
        rx = (page_w - 100) / 2
        rule = (f'<g stroke="#333" stroke-width="0.3" fill="none">'
                f'<path d="M{rx} {ry}h100M{rx} {ry-2.5}v5M{rx+100} {ry-2.5}v5"/></g>'
                f'<text x="{page_w/2}" y="{ry+6}" font-size="3.4" fill="#333" '
                f'text-anchor="middle" font-family="sans-serif">'
                f'이 선이 정확히 100mm 여야 합니다 (인쇄 배율 100%)</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{page_w}mm" height="{page_h}mm"
     viewBox="0 0 {page_w} {page_h}">
  <rect width="{page_w}" height="{page_h}" fill="#fff"/>
  {ink_filter()[0]}
  <rect x="{x}" y="{y}" width="{block}" height="{block}" fill="#fff"/>
  <image x="{mx}" y="{my}" width="{marker_mm}" height="{marker_mm}"
         image-rendering="pixelated" style="image-rendering:pixelated;image-rendering:crisp-edges"
         href="data:image/png;base64,{png_b64(code)}"{ink_filter()[1]}/>
  {''.join(marks)}
  <text x="{page_w/2}" y="{y-6}" font-size="5" fill="#333" text-anchor="middle"
        font-family="sans-serif">{label}  ·  barcode {code}  ·  검은 사각형 {marker_mm:.0f}mm</text>
  {rule}
  <text x="{page_w/2}" y="{page_h-8}" font-size="3" fill="#888" text-anchor="middle"
        font-family="sans-serif">무광 용지에 100% 배율로 인쇄. 흰 여백을 자르지 말 것.</text>
</svg>'''
    with open(path, "w") as f:
        f.write(svg)
    return block


def tiles(code, label, marker_mm, cols, rows, page_w, page_h, prefix):
    """큰 마커를 A4 여러 장에 나눠 찍는다."""
    quiet = marker_mm * QUIET_RATIO
    block = marker_mm + quiet * 2
    tw, th = block / cols, block / rows
    made = []
    for r in range(rows):
        for c in range(cols):
            ox = (page_w - tw) / 2 - c * tw
            oy = (page_h - th) / 2 - r * th
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{page_w}mm" height="{page_h}mm"
     viewBox="0 0 {page_w} {page_h}">
  <rect width="{page_w}" height="{page_h}" fill="#fff"/>
  <clipPath id="c"><rect x="{(page_w-tw)/2}" y="{(page_h-th)/2}" width="{tw}" height="{th}"/></clipPath>
  <g clip-path="url(#c)">
    {ink_filter()[0]}
    <rect x="{ox}" y="{oy}" width="{block}" height="{block}" fill="#fff"/>
    <image x="{ox+quiet}" y="{oy+quiet}" width="{marker_mm}" height="{marker_mm}"
           image-rendering="pixelated" style="image-rendering:pixelated;image-rendering:crisp-edges"
           href="data:image/png;base64,{png_b64(code)}"{ink_filter()[1]}/>
  </g>
  <rect x="{(page_w-tw)/2}" y="{(page_h-th)/2}" width="{tw}" height="{th}"
        fill="none" stroke="#ccc" stroke-width="0.2" stroke-dasharray="2 2"/>
  <text x="{page_w/2}" y="{(page_h-th)/2-5}" font-size="4.5" fill="#333" text-anchor="middle"
        font-family="sans-serif">{label} barcode {code} · {r+1}행 {c+1}열 / {rows}x{cols}</text>
  <text x="{page_w/2}" y="{page_h-8}" font-size="3" fill="#888" text-anchor="middle"
        font-family="sans-serif">점선끼리 맞대어 붙이면 {marker_mm:.0f}mm 마커가 됩니다. 100% 배율 인쇄.</text>
</svg>'''
            path = os.path.join(OUT, f"{prefix}_{r+1}{c+1}.svg")
            with open(path, "w") as f:
                f.write(svg)
            made.append(os.path.basename(path))
    return made


made = []
for i, (code, label) in enumerate(FLOOR, 1):
    name = f"floor_{i}_barcode{code}_100mm.svg"
    sheet(code, label, FLOOR_MM, 210, 297, os.path.join(OUT, name))
    made.append(name)

ccode, clabel = CEILING
big = f"ceiling_barcode{ccode}_300mm.svg"
block = sheet(ccode, clabel, CEIL_MM, CEIL_MM * 1.5 + 20, CEIL_MM * 1.5 + 40,
              os.path.join(OUT, big), ruler=False)
made.append(big)
made += tiles(ccode, clabel, CEIL_MM, 2, 2, 210, 297, "ceiling_tile")

print(f"검은 사각형: 바닥 {FLOOR_MM:.0f}mm, 천장 {CEIL_MM:.0f}mm")
print(f"흰 여백 포함 블록: 바닥 {FLOOR_MM*1.5:.0f}mm, 천장 {block:.0f}mm")
for m in made:
    print("  ", m)
