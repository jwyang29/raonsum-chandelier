#!/usr/bin/env python3
"""현장에서 잰 값을 Firebase 에 적어 둔다. 모든 관객 폰이 그걸 읽어 간다.

🔴 설치를 마치면 마커를 옮기거나 다시 찍을 수 없다. 숫자로 맞추는 길이
   유일하다. 그런데 QR 은 이미 인쇄되어 있고 현장에서 다시 배포하는 것도
   불안하다. 그래서 여기에 적는다. 앱이 뜰 때 /cal 을 한 번 읽는다.

   python3 setcal.py --show
   python3 setcal.py --ped 1.10 --pedh 0.35 --floorceiling 3.25
   python3 setcal.py --msize 0.098 --mring 0.415 --devh 0.22
   python3 setcal.py --fm 0,0.42,0 -0.41,0,2 0,-0.43,0 0.42,0,-1
   python3 setcal.py --cubey 1.22 2.10 3.00
   python3 setcal.py --cuberot 90 0 0
   python3 setcal.py --fov 65        렌즈 화각 (긴 변 기준, 도)
   python3 setcal.py --gap 0.24      겹 사이 간격 (m)
   python3 setcal.py --smooth 0.02   마커 포즈를 따라가는 비율 (낮을수록 안정적)
   python3 setcal.py --dead 0.12     이만큼(m) 안 움직이면 아예 안 따라간다
   python3 setcal.py --deadrot 7     이만큼(도) 안 돌면 아예 안 따라간다
   python3 setcal.py --gyrosmooth 0.12  자이로를 따라가는 비율
   python3 setcal.py --gyrodead 0.6     자이로가 이만큼(도) 안 돌면 무시
   python3 setcal.py --scatter 1     흩뿌리기 켜기 (0 이면 샹들리에)
   python3 setcal.py --cubes 0       매단 큐브를 끄고 바닥 네 장만 쓴다
   python3 setcal.py --keep 0.25     띄울 크리스탈 비율 (낮출수록 성기다)
   python3 setcal.py --lock 8        고정 카메라: 8초 뒤 자세를 얼린다 (0 이면 끔)
   python3 setcal.py --cscale 1.3    크리스탈 크기 배수
   python3 setcal.py --clear

⚠️ 적은 것만 바뀐다. 안 적은 것은 그대로 둔다.
"""
import json, os, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_v1
hub_v1.load_env_file()

KEYS = ["ped", "pedh", "floorceiling", "ceiling", "headroom", "msize", "mring", "devh",
        "fov", "gap", "smooth",
        # 떨림 관련. 전부 배포 없이 현장에서 맞춘다.
        "dead", "deadrot", "gyrosmooth", "gyrodead",
        # 매단 큐브를 통째로 끈다 (0 이면 바닥 네 장만 쓴다)
        "cubes", "keep", "cscale", "lock"]


def take(name, cast=float, many=False):
    a = sys.argv[1:]
    if name not in a:
        return None
    i = a.index(name) + 1
    if not many:
        return cast(a[i])
    out = []
    while i < len(a) and not a[i].startswith("--"):
        out.append(a[i]); i += 1
    return out


up = hub_v1.Uploader()
url = up._endpoint("cal")
print(f"[setcal] {up.url}/cal.json   권한 {up.auth.mode}")


def offline(e):
    """🔴 망이 끊겼을 때 파이썬 역추적을 통째로 쏟지 않는다.

    현장에서 와이파이가 흔들릴 때 이 화면을 보면 무엇이 잘못됐는지 알 수가
    없다. 고칠 수 있는 것인지 아닌지만 한 줄로 알려 준다.
    """
    sys.exit("\n[setcal] 인터넷에 못 닿습니다. 보정값은 그대로 있습니다.\n"
             "  와이파이를 확인하고 다시 돌리세요.\n"
             f"  ({e.reason if hasattr(e, 'reason') else e})")


def read():
    try:
        with urllib.request.urlopen(f"{up.url}/cal.json", timeout=15) as r:
            return json.loads(r.read().decode() or "null") or {}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            sys.exit("읽기가 막혀 있습니다. 콘솔 규칙 탭에 hub/firebase_rules.json 을\n"
                     "다시 붙여넣고 게시하세요. cal 이 읽기 공개여야 관객 폰이 받습니다.")
        raise
    except urllib.error.URLError as e:
        offline(e)


if "--show" in sys.argv:
    print(json.dumps(read(), indent=1, ensure_ascii=False))
    sys.exit(0)

if "--clear" in sys.argv:
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=15).read()
    except urllib.error.URLError as e:
        offline(e)
    print("[setcal] 지웠습니다. 앱이 코드의 기본값으로 돌아갑니다.")
    sys.exit(0)

patch = {}
for k in KEYS:
    v = take("--" + k)
    if v is not None:
        patch[k] = v

fm = take("--fm", str, many=True)
if fm:
    if len(fm) != 4:
        sys.exit("--fm 은 네 장을 전부 적어야 합니다. 0,7,44,63 순서입니다.")
    patch["fm"] = [[float(x) for x in t.split(",")] for t in fm]

# 흩뿌리기 (1 켜기 / 0 끄기). 무인 기간의 예비 모양.
# ⚠️ take 의 기본 변환은 float 다. 그대로 쓰면 "1" 이 1.0 -> "1.0" 이 되어
#    문자열 비교에서 떨어진다. 숫자로 받아 0 이 아니면 켠 것으로 본다.
sv = take("--scatter")
if sv is not None:
    patch["scatter"] = 1 if float(sv) != 0 else 0

cy = take("--cubey", str, many=True)
if cy:
    patch["cubeY"] = [float(v) for v in cy]

# 큐브가 Y축으로 돌아가 달렸을 때. 세 개를 전부 적는다 (안 돌아갔으면 0).
cr = take("--cuberot", str, many=True)
if cr:
    patch["cubeRot"] = [float(v) for v in cr]

if not patch:
    sys.exit(__doc__)

req = urllib.request.Request(url, data=json.dumps(patch).encode(), method="PATCH",
                             headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=15).read()
except urllib.error.URLError as e:
    offline(e)
print("[setcal] 적었습니다:", json.dumps(patch, ensure_ascii=False))
print("[setcal] 지금 /cal 전체:")
print(json.dumps(read(), indent=1, ensure_ascii=False))
