#!/usr/bin/env python3
"""마커 배치도 한 장을 만든다 (A4 SVG).

현장에서 들고 보는 종이다. 평면도 하나, 옆면도 하나, 그리고 지켜야 하는 것들.

치수는 손으로 적지 않고 web/config.js 에서 읽어 온다. 두 군데 적어 두면
한쪽만 고치는 일이 생기고, 그러면 종이가 틀린 자리로 사람을 보낸다.

    python3 make_layout.py [출력폴더]
"""
import math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "web", "config.js")
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = _pos[0] if _pos else os.path.join(HERE, "print")

CUBE_FACE_MM = 130.0      # markers/make_pdf.py 의 CUBE_FACE_MM 과 같아야 한다


def cfg(pattern, default=None):
    """config.js 에서 숫자 하나를 읽는다. num("key", 0.1) 꼴도 받는다."""
    src = open(CONFIG, encoding="utf-8").read()
    m = re.search(pattern, src)
    if not m:
        if default is None:
            sys.exit(f"config.js 에서 못 찾음: {pattern}")
        return default
    return float(m.group(1))


PED_D   = cfg(r'diameter:\s*num\("ped",\s*([\d.]+)\)')
PED_H   = cfg(r'height:\s*num\("pedh",\s*([\d.]+)\)')
MARKER  = cfg(r'markerSize:\s*num\("msize",\s*([\d.]+)\)')
DEVICE  = cfg(r'deviceSize:\s*([\d.]+)')
DEV_H   = cfg(r'deviceHeight:\s*([\d.]+)')
CLOTH   = cfg(r'clothSize:\s*([\d.]+)')
CEIL_M  = cfg(r'ceilingMarkerSize:\s*([\d.]+)')
CEIL_H  = cfg(r'ceilingHeight:\s*deskNum\("ceiling",\s*[\d.]+,\s*floorCeiling[^:]*:\s*([\d.]+)\)',
              3.08)
RIM     = cfg(r'rimMargin:\s*([\d.]+)')
HEADROOM = cfg(r'headroom:\s*deskNum\("headroom",\s*[\d.]+,\s*([\d.]+)\)', 2.05)

# refreshPedestal 과 같은 계산. 여기서 어긋나면 종이가 틀린 자리를 가리킨다.
half = MARKER / 2
pedR = PED_D / 2 - RIM
outer = math.sqrt(max(0.0, pedR * pedR - half * half)) - half
inner = DEVICE / 2 + half + 0.005
MRING = math.floor(outer * 200) / 200 if outer >= inner else inner

FLOOR_DIRS = [(0, 0, 1, "+Z"), (7, -1, 0, "-X"), (44, 0, -1, "-Z"), (63, 1, 0, "+X")]
CUBE_CODES = [[13, 22, 25, 42], [21, 37, 50, 56], [28, 35, 38, 41]]
CUBE_FACES = [("+Z", 0), ("+X", 63), ("-Z", 44), ("-X", 7)]

W, H = 210.0, 297.0
INK = "#1b1f24"
MUTE = "#6b7784"
HOT = "#c2185b"
o = []
a = o.append


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(x, y, s, size=3.4, fill=INK, weight=400, anchor="start", mono=False):
    fam = ("ui-monospace, SFMono-Regular, Menlo, monospace" if mono
           else "-apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif")
    a(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" '
      f'font-weight="{weight}" text-anchor="{anchor}" '
      f'font-family="{fam}">{esc(s)}</text>')


def rule(y, x0=14, x1=W - 14, c="#d6dbe0"):
    a(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{c}" stroke-width="0.3"/>')


a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" '
  f'viewBox="0 0 {W} {H}">')
a(f'<rect width="{W}" height="{H}" fill="#fff"/>')

# ── 머리 ────────────────────────────────────────────────────
t(14, 18, "라온숨 가상 샹들리에   마커 배치", 6.2, INK, 700)
t(W - 14, 18, "A4 / 축척 약 1:22", 3.2, MUTE, 400, "end")
t(14, 24.5, "모든 치수는 web/config.js 에서 읽어 왔습니다. 설치 후 이 종이와 다르면 "
            "config.js 를 고쳐야 합니다.", 3.1, MUTE)
rule(28)

# ── 평면도 ──────────────────────────────────────────────────
t(14, 36, "1. 좌대 위 (평면도)", 4.4, INK, 700)
CX, CY, K = 66.0, 92.0, 48.0      # 중심과 1m 당 mm (1/10 보다 작게)

a(f'<circle cx="{CX}" cy="{CY}" r="{PED_D/2*K:.2f}" fill="#f4f6f8" '
  f'stroke="#aab4bf" stroke-width="0.4"/>')
d = DEVICE * K
a(f'<rect x="{CX-d/2:.2f}" y="{CY-d/2:.2f}" width="{d:.2f}" height="{d:.2f}" '
  f'fill="none" stroke="#2bff88" stroke-width="0.6"/>')
a(f'<rect x="{CX-d/2:.2f}" y="{CY-d/2:.2f}" width="{d:.2f}" height="{d:.2f}" '
  f'fill="#e9f7ef" opacity="0.7"/>')
c = CLOTH * K
a(f'<rect x="{CX-c/2:.2f}" y="{CY-c/2:.2f}" width="{c:.2f}" height="{c:.2f}" '
  f'fill="none" stroke="#f0ad22" stroke-width="0.5" stroke-dasharray="1.6 1.2"/>')
a(f'<circle cx="{CX}" cy="{CY}" r="{MRING*K:.2f}" fill="none" stroke="{HOT}" '
  f'stroke-width="0.35" stroke-dasharray="2 1.6"/>')

# 마커 네 장.
# 🔴 위에서 내려다본 그림이다. 종이 위쪽이 -Z, 오른쪽이 +X 여야 손이 맞는다.
#    (+Z 를 위로 그리면 좌우가 뒤집혀서 7번과 63번 자리가 바뀐다. 네 장이
#     원 위에 도는 순서가 반대가 되므로 설치가 통째로 틀어진다.)
blk = MARKER * 1.5 * K
for code, dx, dz, name in FLOOR_DIRS:
    mx, my = CX + dx * MRING * K, CY + dz * MRING * K
    a(f'<rect x="{mx-blk/2:.2f}" y="{my-blk/2:.2f}" width="{blk:.2f}" height="{blk:.2f}" '
      f'fill="#fff" stroke="{INK}" stroke-width="0.35"/>')
    s = MARKER * K
    a(f'<rect x="{mx-s/2:.2f}" y="{my-s/2:.2f}" width="{s:.2f}" height="{s:.2f}" '
      f'fill="#333"/>')
    t(mx, my + 1.2, str(code), 3.6, "#fff", 700, "middle", True)
    t(mx, my + blk / 2 + 3.6, name, 2.6, MUTE, 400, "middle", True)

# 방향 표시. 인쇄물 위쪽이 전부 같은 쪽을 봐야 한다.
ay = CY - PED_D / 2 * K - 7
a(f'<line x1="{CX}" y1="{ay+5:.2f}" x2="{CX}" y2="{ay:.2f}" stroke="{HOT}" '
  f'stroke-width="0.5"/>')
a(f'<path d="M {CX-1.4:.2f} {ay+1.6:.2f} L {CX:.2f} {ay-0.6:.2f} '
  f'L {CX+1.4:.2f} {ay+1.6:.2f} Z" fill="{HOT}"/>')
t(CX + 2.5, ay + 1.2, "네 장 모두 인쇄물 위쪽을 44번 쪽으로", 2.8, HOT, 600)

# 치수선
def dim(x0, x1, y, label):
    a(f'<line x1="{x0:.2f}" y1="{y:.2f}" x2="{x1:.2f}" y2="{y:.2f}" '
      f'stroke="{MUTE}" stroke-width="0.3"/>')
    for x in (x0, x1):
        a(f'<line x1="{x:.2f}" y1="{y-1.2:.2f}" x2="{x:.2f}" y2="{y+1.2:.2f}" '
          f'stroke="{MUTE}" stroke-width="0.3"/>')
    t((x0 + x1) / 2, y - 1.8, label, 2.8, MUTE, 400, "middle", True)

dim(CX, CX + MRING * K, CY + PED_D / 2 * K + 9, f"{MRING*100:.1f} cm")
dim(CX - PED_D / 2 * K, CX + PED_D / 2 * K, CY + PED_D / 2 * K + 16,
    f"좌대 지름 {PED_D*100:.0f} cm")

bx = 124
t(bx, 40, "확인할 것", 3.4, INK, 700)
lines = [
    (f"중심에서 {MRING*100:.1f} cm", "네 장 모두 같은 거리. 줄자로 잰다"),
    ("축과 나란히", "둥근 좌대에는 맞출 모서리가 없다."),
    ("", "테이프로 기준선 하나 긋고 그 선에 맞춘다"),
    ("인쇄물 위쪽 한 방향", "네 장을 같은 방향으로 (44번 쪽). 돌려 붙이면 안 된다"),
    ("", "방향이 맞는지는 ?guide=1 로 본다. 월드가 90도 돌아가 있으면"),
    ("", "네 장을 한꺼번에 90도 돌려 다시 본다. 네 번 안에 맞는다"),
    (f"검은 사각형 {MARKER*100:.0f} cm", "찍고 나서 자로 잰다. 틀리면 월드가 틀어진다"),
    ("흰 여백 자르지 말 것", "여백이 없으면 사각형을 못 찾는다"),
    ("장치 바깥으로", f"장치 {DEVICE*100:.0f} cm 각. 천을 밟으면 안 된다"),
]
yy = 46
for head, body in lines:
    if head:
        t(bx, yy, "•  " + head, 3.1, INK, 600)
        yy += 3.9
    if body:
        t(bx + 3.4, yy, body, 2.7, MUTE)
        yy += 3.9

rule(136)

# ── 옆면도 ──────────────────────────────────────────────────
t(14, 145, "2. 높이 (옆면도)", 4.4, INK, 700)
SX, SY, SK = 52.0, 258.0, 28.0     # 바닥 y 와 1m 당 mm
FLOOR_CEIL = CEIL_H + PED_H

a(f'<line x1="18" y1="{SY}" x2="{W-80}" y2="{SY}" stroke="#aab4bf" stroke-width="0.5"/>')

# 좌대와 장치
pw = PED_D * SK
a(f'<rect x="{SX-pw/2:.2f}" y="{SY-PED_H*SK:.2f}" width="{pw:.2f}" '
  f'height="{PED_H*SK:.2f}" fill="#f4f6f8" stroke="#aab4bf" stroke-width="0.4"/>')
dw = DEVICE * SK
a(f'<rect x="{SX-dw/2:.2f}" y="{SY-(PED_H+DEV_H)*SK:.2f}" width="{dw:.2f}" '
  f'height="{DEV_H*SK:.2f}" fill="none" stroke="#2bff88" stroke-width="0.6"/>')

# 천장 마커
cm = CEIL_M * SK
a(f'<line x1="18" y1="{SY-FLOOR_CEIL*SK:.2f}" x2="{W-80}" y2="{SY-FLOOR_CEIL*SK:.2f}" '
  f'stroke="#aab4bf" stroke-width="0.5"/>')
a(f'<rect x="{SX-cm/2:.2f}" y="{SY-FLOOR_CEIL*SK:.2f}" width="{cm:.2f}" height="1.6" '
  f'fill="#333"/>')
t(SX + 22, SY - FLOOR_CEIL * SK + 3.2,
  f"천장 마커 26 / {CEIL_M*100:.0f} cm / 아래를 보게", 2.8, INK, 600)

# 샹들리에가 차지하는 높이
top, bot = FLOOR_CEIL, HEADROOM
a(f'<rect x="{SX-18:.2f}" y="{SY-top*SK:.2f}" width="36" '
  f'height="{(top-bot)*SK:.2f}" fill="#eef3fb" stroke="#9fb6d4" '
  f'stroke-width="0.3" stroke-dasharray="1.6 1.2"/>')
t(SX, SY - (top + bot) / 2 * SK, "가상 샹들리에", 3.0, "#5b7ca6", 600, "middle")
t(SX, SY - (top + bot) / 2 * SK + 4, f"{bot:.2f} ~ {top:.2f} m", 2.7, "#5b7ca6",
  400, "middle", True)

# 천과 샹들리에 사이. 비어 보이는 게 그림이 틀린 게 아니라 설계가 그렇다.
void_top, void_bot = HEADROOM, PED_H + DEV_H
a(f'<line x1="{SX:.2f}" y1="{SY-void_top*SK:.2f}" x2="{SX:.2f}" '
  f'y2="{SY-void_bot*SK:.2f}" stroke="{MUTE}" stroke-width="0.25" '
  f'stroke-dasharray="1.2 1.2"/>')
t(SX + 2.5, SY - (void_top + void_bot) / 2 * SK,
  f"빈 공간 {void_top-void_bot:.2f} m", 2.7, MUTE)
t(SX + 2.5, SY - (void_top + void_bot) / 2 * SK + 3.4,
  "천 위에서 샹들리에 아래까지", 2.5, MUTE)

# 매단 큐브
cube_y = 2.08
cs = CUBE_FACE_MM / 1000 * SK
a(f'<line x1="{SX+34:.2f}" y1="{SY-FLOOR_CEIL*SK:.2f}" x2="{SX+34:.2f}" '
  f'y2="{SY-cube_y*SK:.2f}" stroke="{MUTE}" stroke-width="0.25"/>')
a(f'<line x1="{SX+37:.2f}" y1="{SY-FLOOR_CEIL*SK:.2f}" x2="{SX+37:.2f}" '
  f'y2="{SY-cube_y*SK:.2f}" stroke="{MUTE}" stroke-width="0.25"/>')
for i in range(2):
    yy = SY - (cube_y + i * (CUBE_FACE_MM / 1000 + 0.10)) * SK
    a(f'<rect x="{SX+35.5-cs/2:.2f}" y="{yy-cs/2:.2f}" width="{cs:.2f}" '
      f'height="{cs:.2f}" fill="#fff" stroke="{INK}" stroke-width="0.35"/>')
t(SX + 35.5 + cs / 2 + 2.5, SY - cube_y * SK,
  f"매단 큐브 / 한 변 {CUBE_FACE_MM:.0f} cm", 2.8, INK, 600)
t(SX + 35.5 + cs / 2 + 2.5, SY - cube_y * SK + 3.6,
  "낚싯줄 두 줄 (한 줄이면 돈다)", 2.7, HOT, 600)

# 높이 치수
for y, lab in [(PED_H, f"좌대 {PED_H*100:.0f} cm"),
               (PED_H + DEV_H, f"천 {(PED_H+DEV_H)*100:.0f} cm"),
               (HEADROOM, f"샹들리에 아래 {HEADROOM:.2f} m"),
               (FLOOR_CEIL, f"천장 {FLOOR_CEIL:.2f} m")]:
    a(f'<line x1="{SX-pw/2-4:.2f}" y1="{SY-y*SK:.2f}" x2="{SX-pw/2-1:.2f}" '
      f'y2="{SY-y*SK:.2f}" stroke="{MUTE}" stroke-width="0.3"/>')
    t(SX - pw / 2 - 5, SY - y * SK + 1, lab, 2.6, MUTE, 400, "end")

# 큐브 면 배치표
bx2 = 128
t(bx2, 149, "매단 큐브 면 번호", 3.4, INK, 700)
t(bx2, 153.5, "옆면 넷에 붙인다. 윗면 아랫면은 비운다.", 2.7, MUTE)
t(bx2, 157.5, "각 면이 바닥 마커 한 장을 바라보게 맞춘다.", 2.7, MUTE)
hy = 164
t(bx2, hy, "면", 2.7, MUTE, 600)
t(bx2 + 14, hy, "보는 쪽", 2.7, MUTE, 600)
t(bx2 + 36, hy, "큐브1", 2.7, MUTE, 600)
t(bx2 + 50, hy, "큐브2", 2.7, MUTE, 600)
t(bx2 + 64, hy, "큐브3", 2.7, MUTE, 600)
a(f'<line x1="{bx2}" y1="{hy+1.4}" x2="{bx2+72}" y2="{hy+1.4}" '
  f'stroke="#d6dbe0" stroke-width="0.3"/>')
for i, (name, floor_code) in enumerate(CUBE_FACES):
    y = hy + 5.2 + i * 4.6
    t(bx2, y, name, 2.9, INK, 600, "start", True)
    t(bx2 + 14, y, f"바닥 {floor_code}", 2.8, INK)
    for ci in range(3):
        t(bx2 + 36 + ci * 14, y, str(CUBE_CODES[ci][i]), 2.9, INK, 600, "start", True)
t(bx2, hy + 28, "인쇄물 위쪽이 전부 천장을 향하게.", 2.7, HOT, 600)

rule(268)

# ── 꼭 지킬 것 ───────────────────────────────────────────────
t(14, 276, "인쇄", 3.6, INK, 700)
t(26, 276, "markers/print/ 의 PDF 를 100% 배율로. 무광. 흰 여백 자르지 말 것. "
           "찍은 뒤 자로 검은 사각형을 재서 맞는지 확인.", 3.0, INK)
t(14, 282, "확인", 3.6, INK, 700)
t(26, 282, "폰에서 ?guide=1 로 열면 실측 윤곽이 겹쳐 보입니다. "
           "초록 네모가 장치 위에 딱 맞으면 된 것입니다.", 3.0, INK)
t(14, 289.5, "raonsum-chandelier / markers/make_layout.py 가 config.js 에서 읽어 만든 "
             "종이입니다", 2.6, MUTE)

a("</svg>")

os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "RAONSUM_marker_layout_A4.svg")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(o))

print(f"마커 반지름 {MRING*100:.1f}cm / 좌대 {PED_D*100:.0f}cm / "
      f"바닥에서 천장 {FLOOR_CEIL:.2f}m")
print(f"  {os.path.basename(path)}  {os.path.getsize(path)//1024}KB")
