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
   python3 setcal.py --smooth 0.08   떨림 줄이기 (낮을수록 안정적)
   python3 setcal.py --clear

⚠️ 적은 것만 바뀐다. 안 적은 것은 그대로 둔다.
"""
import json, os, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_v1
hub_v1.load_env_file()

KEYS = ["ped", "pedh", "floorceiling", "ceiling", "headroom", "msize", "mring", "devh",
        "fov", "gap", "smooth"]


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


def read():
    try:
        with urllib.request.urlopen(f"{up.url}/cal.json", timeout=15) as r:
            return json.loads(r.read().decode() or "null") or {}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            sys.exit("읽기가 막혀 있습니다. 콘솔 규칙 탭에 hub/firebase_rules.json 을\n"
                     "다시 붙여넣고 게시하세요. cal 이 읽기 공개여야 관객 폰이 받습니다.")
        raise


if "--show" in sys.argv:
    print(json.dumps(read(), indent=1, ensure_ascii=False))
    sys.exit(0)

if "--clear" in sys.argv:
    urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=15).read()
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
urllib.request.urlopen(req, timeout=15).read()
print("[setcal] 적었습니다:", json.dumps(patch, ensure_ascii=False))
print("[setcal] 지금 /cal 전체:")
print(json.dumps(read(), indent=1, ensure_ascii=False))
