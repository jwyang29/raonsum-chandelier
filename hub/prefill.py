#!/usr/bin/env python3
"""무인 기간에 보여 줄 크리스탈을 Firebase 에 미리 채운다.

11/1 ~ 11/13 과 11/16 ~ 11/25 는 센서부 없이 돈다. DB 가 비어 있으면 관객이
QR 을 찍어도 아무것도 안 뜬다. 그래서 미리 써 넣는다.

🔴 폰마다 따로 만들면 안 된다. 이 작품은 "사람들이 그린 것이 쌓인 기록" 이라
   모든 폰이 같은 샹들리에를 봐야 한다. 그래서 로컬 생성이 아니라 DB 에
   한 번 써 넣는다. 11/14, 11/15 시연 때 허브가 그 위에 얹히는 것도 자동이다.

겹은 시계가 아니라 쌓인 것으로 넘어간다 (chandelier.js 의 nextLayer). 겹마다
다른 주기에 들어가도록 시각을 벌려 적는다. 키도 그 순서로 정렬되게 매긴다.
EventSource 가 키 순서로 넘겨주기 때문이다.

    python3 prefill.py --dry             무엇을 쓸지 보기만 한다
    python3 prefill.py                   쓴다
    python3 prefill.py --wipe            전에 쓴 프리필(pre_)만 지운다

주소와 권한은 hub_v1.py 와 같은 것을 쓴다 (secrets.env).
"""
import json, math, os, random, re, sys, urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_v1  # 주소와 권한, RTDB_PATH 를 그대로 쓴다

# ⚠️ main() 을 거치지 않으므로 secrets.env 를 직접 읽어야 한다.
hub_v1.load_env_file()

CONFIG = os.path.join(HERE, "..", "web", "config.js")
PREFIX = "pre_"          # 이 접두어가 붙은 것만 프리필이다. --wipe 가 이것만 지운다


def arg(name, default, cast=str):
    a = sys.argv[1:]
    return cast(a[a.index(name) + 1]) if name in a else default


LAYERS = arg("--layers", 10, int)
PER    = arg("--per", 15, int)
HOLDS  = arg("--hold", 5, int)
SEED   = arg("--seed", 20261101, int)
DRY    = "--dry" in sys.argv
WIPE   = "--wipe" in sys.argv


def schedule():
    """config.js 의 startISO 와 periodHours 를 그대로 읽는다. 두 군데 적지 않는다."""
    src = open(CONFIG, encoding="utf-8").read()
    iso = re.search(r'startISO:\s*"([^"]+)"', src)
    per = re.search(r'periodHours:\s*num\("period",\s*([\d.]+)\)', src)
    if not iso:
        sys.exit("config.js 에서 startISO 를 못 찾았습니다")
    start = datetime.fromisoformat(iso.group(1))
    hours = float(per.group(1)) if per else 1.0
    return int(start.timestamp() * 1000), hours


# ---------------------------------------------------------------
#  크리스탈 한 덩어리. hub_v1.build_crystal 과 같은 키를 쓴다.
#  값의 분포는 녹화에서 잰 범위 안에서 고르되, 느낌과 어긋나지 않게 묶는다.
#  (빠르게 그은 획이 speed 0.1 로 적히면 모양과 설명이 따로 논다)
# ---------------------------------------------------------------

FEELINGS = [
    #  이름          press        speed
    ("fast_hard",  (0.62, 0.95), (0.60, 0.95)),
    ("fast_soft",  (0.08, 0.40), (0.58, 0.92)),
    ("slow_hard",  (0.60, 0.94), (0.06, 0.38)),
    ("slow_soft",  (0.10, 0.42), (0.08, 0.40)),
    ("varied",     (0.25, 0.80), (0.25, 0.80)),
    ("neutral",    (0.38, 0.62), (0.38, 0.62)),
]


def crystal(rng, t_ms, hold=None):
    name, pr, sp = rng.choice(FEELINGS)
    press = round(rng.uniform(*pr), 3)
    speed = round(rng.uniform(*sp), 3)
    d = {
        "t":       t_ms,
        "press":   press,
        "speed":   speed,
        "dur":     round(rng.uniform(0.7, 4.2), 2),
        "elong":   round(rng.uniform(0.05, 0.95), 3),
        "wind":    round(rng.uniform(0.0, 0.62), 3),
        "curl":    round(rng.uniform(-1.0, 1.0), 3),
        "dir":     round(rng.uniform(0, math.pi * 2), 3),
        "n":       rng.randint(9, 180),
        "feeling": name,
        "conf":    round(rng.uniform(0.56, 0.98), 2),
    }
    if hold is not None:
        d["hold"] = round(hold, 3)
    return d


def build():
    start_ms, period_h = schedule()
    rng = random.Random(SEED)
    out = {}
    i = 0

    # 겹마다 개수를 다르게 준다. 한산한 시간과 붐비는 시간이 번갈아 오는 모습이고,
    # 그래야 개수에 따라 링이 넓어지는 게 샹들리에 옆모습에 보인다.
    plan = []
    for L in range(LAYERS):
        w = 0.42 + 0.58 * (1 + math.sin(L * 0.9 + 0.6)) / 2
        plan.append(max(4, round(PER * w)))

    for L, n in enumerate(plan):
        # 겹 하나는 한 주기 안에 들어가야 한다. 날을 벌려 적어 둔다.
        day = L
        hour = 3 + (L * 2) % 6          # 운영 시간 안쪽
        base = start_ms + ((day * 24 + hour) * 3600_000)
        span = int(period_h * 3600_000) - 60_000
        for k in range(n):
            t = base + int(span * (k + 0.5) / n)
            out[f"{PREFIX}{i:04d}"] = crystal(rng, t)
            i += 1

    # 올라가다 멈춘 것들. 마지막 겹과 같은 주기에 둔다. 그 겹으로 올라가는 중이다.
    # 0.35~0.84 면 바닥 기준 약 0.97m 에서 2.45m 사이에 선다. 천과 샹들리에
    # 사이의 빈 구간이 바로 거기다.
    if HOLDS > 0:
        L = LAYERS - 1
        base = start_ms + (((L * 24) + 3 + (L * 2) % 6) * 3600_000)
        for k in range(HOLDS):
            h = 0.35 + (0.84 - 0.35) * (k / max(1, HOLDS - 1))
            t = base + int(period_h * 3600_000) - 40_000 + k
            out[f"{PREFIX}{i:04d}"] = crystal(rng, t, hold=h)
            i += 1
    return out, plan


def req(method, path, body=None):
    url = up._endpoint(path)
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as res:
        return res.read().decode()


up = hub_v1.Uploader()
print(f"[prefill] 주소 {up.url}")
print(f"[prefill] 권한 {up.auth.mode}")

if WIPE:
    with urllib.request.urlopen(f"{up.url}/{hub_v1.RTDB_PATH}.json?shallow=true",
                                timeout=20) as r:
        keys = json.loads(r.read().decode() or "{}") or {}
    mine = [k for k in keys if k.startswith(PREFIX)]
    print(f"[prefill] 프리필 {len(mine)}개 발견 (전체 {len(keys)}개)")
    if not mine:
        sys.exit(0)
    if DRY:
        print("[prefill] --dry 라 지우지 않습니다")
        sys.exit(0)
    req("PATCH", hub_v1.RTDB_PATH, {k: None for k in mine})
    print(f"[prefill] {len(mine)}개 지웠습니다. 관객이 그린 것은 건드리지 않았습니다.")
    sys.exit(0)

rows, plan = build()
held = [v for v in rows.values() if "hold" in v]
print(f"[prefill] {LAYERS}겹 / 겹당 {plan} / 모두 {len(rows)}개 "
      f"(그중 올라가다 멈춘 것 {len(held)}개)")
for v in held:
    print(f"            hold {v['hold']}")

if DRY:
    k = sorted(rows)[0]
    print(f"[prefill] --dry 입니다. 첫 덩어리:\n  {k} {json.dumps(rows[k], ensure_ascii=False)}")
    sys.exit(0)

req("PATCH", hub_v1.RTDB_PATH, rows)
with urllib.request.urlopen(f"{up.url}/{hub_v1.RTDB_PATH}.json?shallow=true",
                            timeout=20) as r:
    now = json.loads(r.read().decode() or "{}") or {}
print(f"[prefill] 썼습니다. DB 에 지금 {len(now)}개 있습니다.")
