#!/usr/bin/env python3
"""
가상 샹들리에 - 허브 업로더 v1

playground_v24.py 의 트래커를 그대로 쓴다. 획이 끝날 때마다 호출되는
Tracker.on_clean 훅에 갠트리 대신 Firebase 업로드를 붙인 것이다.
위치 추정(FabricEstimator, 오차 1.9cm)과 stroke_feeling 은 손대지 않는다.

실행:
    python3 hub_v1.py                   포트를 알아서 찾아 전시용으로 올린다
    python3 hub_v1.py --selftest        센서만 본다. 안 올린다
    python3 hub_v1.py --check           ESP32 없이 Firebase 만 본다
    python3 hub_v1.py --ports           보이는 포트와 ESP32 자리만 찍는다
    python3 hub_v1.py --path crystals_test   시험 자리에 올린다
    python3 hub_v1.py --port /dev/cu.usbserial-0001   포트를 직접 적을 때
    python3 hub_v1.py --mock <csv>              녹화를 재생한다
    python3 hub_v1.py --mock <csv> --dry        업로드 없이 JSON 만 출력

🔴 포트 이름을 외워 치지 않아도 된다. D, 를 보내는 포트를 찾아서 연다.
🔴 끊기면 다시 붙는다. 6초 동안 값이 없어도 끊긴 것으로 보고 다시 연다.
🔴 못 올린 것은 hub/outbox.json 에 받쳐 두고 다음에 켤 때 마저 올린다.

환경변수 (업로드할 때만 필요).
hub/secrets.env 에 적어 두면 알아서 읽는다. export 를 매번 칠 필요 없다:
    RAONSUM_FIREBASE_URL     콘솔 Realtime Database 맨 위에 적힌 주소
                             asia-southeast1 이면 .firebasedatabase.app 로 끝난다

    쓰기 권한은 둘 중 하나. 비밀키가 콘솔에 아직 있으면 그게 제일 간단하다.
    RAONSUM_FIREBASE_SECRET  Realtime Database 비밀키 (저장소에 넣지 말 것)
      또는
    RAONSUM_FIREBASE_APIKEY    웹 API 키 (프로젝트 설정 > 일반)
    RAONSUM_FIREBASE_EMAIL     Authentication 에 만든 허브 계정
    RAONSUM_FIREBASE_PASSWORD  그 계정 비밀번호

연결만 확인:
    python3 hub_v1.py --check
"""

VERSION = "hub_v1"

import argparse, csv, json, math, os, re, sys, time, urllib.request

# playground_v24.py 가 있는 곳. 트래커를 재사용하므로 경로만 잡아준다.
PLAYGROUND_DIR = os.path.expanduser("~/Desktop/playground")
sys.path.insert(0, PLAYGROUND_DIR)

# --check 는 트래커가 필요 없다. playground 가 없는 자리에서도 연결은 봐야 하므로
# 여기서 바로 끝내지 않고 실제로 돌릴 때 끝낸다.
PLAYGROUND_ERR = None


def _stub_pygame():
    """pygame 이 없어도 트래커를 불러올 수 있게 가짜를 끼운다.

    🔴 playground_v24.py 는 원래 화면에 그려 가며 쓰는 도구라 맨 위에서
       pygame 을 불러온다. 그런데 허브는 추적 계산만 쓰고 화면은 안 그린다.
       pygame 을 깔지 않으면 import 에서 바로 막힌다.

       현장에서 이걸로 막히면 설치가 멈춘다. 실제로 여기서 한 번 막혔다.
       그래서 없으면 가짜를 끼워 넣는다. 그리는 함수는 허브가 부르지 않으므로
       아무 일도 하지 않는 껍데기로 충분하다. 진짜 pygame 이 깔려 있으면
       그걸 쓴다.
    """
    try:
        import pygame  # noqa: F401
        return False
    except ImportError:
        pass
    import types

    class _Any(types.ModuleType):
        def __getattr__(self, name):
            if name.isupper():          # 상수 자리
                return 0
            def _noop(*a, **k):
                return _Any(name)
            return _noop

    mod = _Any("pygame")
    for sub in ("draw", "display", "font", "time", "event", "key", "image",
                "mouse", "transform", "surfarray", "locals", "gfxdraw"):
        sys.modules["pygame." + sub] = _Any("pygame." + sub)
    sys.modules["pygame"] = mod
    return True


STUBBED_PYGAME = _stub_pygame()

try:
    from playground_v24 import (Tracker, stroke_feeling, BAUD,
                                SPEED_FAST_CMS, PRESS_HARD_MM, PRESS_VARIED_MM)
except ImportError as e:
    PLAYGROUND_ERR = (f"[{VERSION}] playground_v24.py 를 못 불러왔습니다 ({e}).\n"
                      f"  찾은 경로: {PLAYGROUND_DIR}\n"
                      f"  PLAYGROUND_DIR 를 실제 위치로 고치세요.")

# web/config.js 의 DB_PATH 와 같아야 한다.
# 🔴 전시가 돌아가는 동안 센서를 시험할 때는 --path 로 다른 자리에 쓴다.
#    안 그러면 시험용 크리스탈이 관객 화면에 섞인다.
RTDB_PATH = "crystals"
HERE = os.path.dirname(os.path.abspath(__file__))


def db_url_from_config():
    """web/config.js 에 적힌 databaseURL 을 그대로 쓴다.

    주소는 관객 폰이 읽어야 해서 어차피 공개되는 값이다. 비밀이 아니다.
    두 군데 적어 두면 한쪽만 고치는 일이 생기므로 config.js 하나만 본다.
    """
    p = os.path.join(HERE, "..", "web", "config.js")
    try:
        with open(p, encoding="utf-8") as f:
            m = re.search(r'databaseURL:\s*"([^"]+)"', f.read())
    except OSError:
        return ""
    url = (m.group(1) if m else "").strip().rstrip("/")
    return "" if ("PASTE_" in url or not url.isascii()) else url


def load_env_file():
    """hub/secrets.env 가 있으면 읽어서 환경변수로 넣는다.

    전시장에서 노트북을 다시 켤 때마다 export 를 다시 치게 하면 언젠가 빼먹는다.
    빼먹으면 그 시간 관객 것이 통째로 안 올라간다.
    🔴 이 파일은 저장소에 올리지 말 것. .gitignore 에 넣어 뒀다.
    이미 환경변수에 들어 있으면 그쪽을 그대로 둔다.
    """
    path = os.path.join(HERE, "secrets.env")
    if not os.path.exists(path):
        return
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
                n += 1
    print(f"[{VERSION}] secrets.env 에서 {n}개를 읽었습니다")


# ---------------------------------------------------------------
#  크리스탈 형태용 기하 특징
#  v24 의 stroke_feeling 은 속도와 세기를 준다. 형태는 여기서 뽑는다.
#  9센서(오차 1.9cm)라서 모양 정보를 쓸 수 있다. 4센서 안에서는 포기했던 부분이다.
# ---------------------------------------------------------------

def norm(v, lo, hi):
    """lo..hi 를 0..1 로. 범위를 벗어나면 끝값으로 자른다."""
    return round(max(0.0, min(1.0, (v - lo) / (hi - lo))), 3)


# 정규화 범위는 recordings/ 의 녹화 4개에서 획 25개를 재서 정했다 (2026-10-22).
# 여기를 데이터 없이 바꾸지 말 것. 바꿀 땐 probe 를 다시 돌려서 분포를 보고 정한다.
PRESS_MM_RANGE  = (22.0, 46.0)   # 실측 21.7 ~ 46.2, 중앙값 32.6
SPEED_CMS_RANGE = ( 2.0, 36.0)   # 실측 1.8 ~ 36.2, 중앙값 21.3
WIND_RANGE      = ( 1.0,  2.3)   # 실측 1.00 ~ 2.31, 중앙값 1.04 (대부분 직선)


def shape_features(pts):
    """clean 획 [(x, y, press), ...] 에서 형태 특징 세 개를 뽑는다.

    문서의 매핑은 형태를 길쭉함, 면의 수, 비틀림으로 나눈다. 그에 맞춰
      elong = 길쭉함   bbox 종횡비. 직선이면 1, 원이면 0에 가깝다.
      wind  = 면의 수  경로 길이를 bbox 대각선으로 나눈 값. 맴돌면 커진다.
      curl  = 비틀림   부호 있는 총 회전량. 왼쪽으로 감기면 양수.
    9센서(오차 1.9cm)라서 이 값들을 쓸 수 있다. 4센서 안에서는 포기했던 부분이다.
    """
    if len(pts) < 3:
        return {"elong": 0.0, "wind": 0.0, "curl": 0.0, "dir": 0.0}

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    long_side, short_side = max(w, h), min(w, h)

    elong = 1.0 - (short_side / long_side) if long_side > 1e-6 else 0.0

    diag = math.hypot(w, h)
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    wind = (length / diag) if diag > 1e-6 else 1.0

    turn = 0.0
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        turn += math.atan2(v1[0] * v2[1] - v1[1] * v2[0],
                           v1[0] * v2[0] + v1[1] * v2[1])
    curl = max(-1.0, min(1.0, turn / (2 * math.pi)))

    direction = math.atan2(pts[-1][1] - pts[0][1], pts[-1][0] - pts[0][0])

    return {"elong": round(elong, 3), "wind": norm(wind, *WIND_RANGE),
            "curl": round(curl, 3), "dir": round(direction, 3)}


def confidence(feel):
    """느낌 판독이 얼마나 확실한지. 분류를 가른 값이 임계에서 멀수록 확실하다.

    stroke_feeling 은 speed 와 press 를 임계와 비교해 fast/slow, hard/soft 를 고르고
    획 안에서 press 가 많이 변하면 varied 로 본다. 임계 바로 옆이면 애매한 판독이므로
    그 거리를 확신도로 돌려준다. 관객이 크리스탈을 눌렀을 때 함께 보여 준다.
    """
    if feel["spread"] >= PRESS_VARIED_MM:
        margin = (feel["spread"] - PRESS_VARIED_MM) / PRESS_VARIED_MM
    else:
        by_speed = abs(feel["speed"] - SPEED_FAST_CMS) / SPEED_FAST_CMS
        by_press = abs(feel["press"] - PRESS_HARD_MM) / PRESS_HARD_MM
        margin = min(by_speed, by_press)   # 둘 중 더 아슬아슬한 쪽이 판독을 좌우한다
    return round(min(0.99, 0.55 + margin), 2)


def build_crystal(clean, feel, duration):
    """업로드할 JSON 한 덩어리. web/config.js 의 MAPPING 이 이 키들을 읽는다."""
    shape = shape_features(clean)
    return {
        "t":     int(time.time() * 1000),
        "press": norm(feel["press"], *PRESS_MM_RANGE),
        "speed": norm(feel["speed"], *SPEED_CMS_RANGE),
        "dur":   round(duration, 2),
        "elong": shape["elong"],
        "wind":  shape["wind"],
        "curl":  shape["curl"],
        "dir":   shape["dir"],
        "n":     len(clean),
        "feeling": feel["feeling"],
        "conf":    confidence(feel),
    }


# ---------------------------------------------------------------
#  업로드
# ---------------------------------------------------------------

class Auth:
    """쓰기에 붙일 ?auth= 값을 준다.

    비밀키(database secret)는 구글이 deprecated 로 표시해 둔 기능이다. 아직은
    콘솔 프로젝트 설정 > 서비스 계정 > 데이터베이스 비밀번호 에서 발급되지만
    새 프로젝트에서 안 보이는 경우가 있다. 그래서 계정 로그인 쪽도 같이 둔다.

    계정 쪽을 쓰면 토큰이 한 시간짜리라 만료 전에 갱신한다. 갱신이 실패해도
    업로드 한 번을 통째로 날리지 않도록 예외는 호출한 쪽에서 받는다.
    """

    SIGNIN = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
    REFRESH = "https://securetoken.googleapis.com/v1/token?key="

    def __init__(self):
        self.secret = os.environ.get("RAONSUM_FIREBASE_SECRET", "")
        self.key = os.environ.get("RAONSUM_FIREBASE_APIKEY", "")
        self.email = os.environ.get("RAONSUM_FIREBASE_EMAIL", "")
        self.password = os.environ.get("RAONSUM_FIREBASE_PASSWORD", "")
        self.token = ""
        self.refresh_token = ""
        self.expires = 0.0

    @property
    def mode(self):
        if self.secret:
            return "비밀키"
        if self.key and self.email and self.password:
            return "계정"
        return "없음"

    @staticmethod
    def _post(url, payload):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())

    def value(self):
        """지금 쓸 수 있는 auth 값. 권한 설정이 없으면 빈 문자열."""
        if self.secret:
            return self.secret
        if self.mode != "계정":
            return ""
        # 만료 1분 전부터 미리 갱신한다
        if self.token and time.time() < self.expires - 60:
            return self.token
        if self.refresh_token:
            d = self._post(self.REFRESH + self.key,
                           {"grant_type": "refresh_token",
                            "refresh_token": self.refresh_token})
            self.token = d["id_token"]
            self.refresh_token = d["refresh_token"]
            self.expires = time.time() + float(d.get("expires_in", 3600))
        else:
            d = self._post(self.SIGNIN + self.key,
                           {"email": self.email, "password": self.password,
                            "returnSecureToken": True})
            self.token = d["idToken"]
            self.refresh_token = d["refreshToken"]
            self.expires = time.time() + float(d.get("expiresIn", 3600))
            print(f"[{VERSION}] 허브 계정으로 로그인했습니다. uid {d['localId']}")
            print(f"           규칙에 쓸 uid 입니다: \"auth.uid === '{d['localId']}'\"")
        return self.token


# ---------------------------------------------------------------
#  현장에서 보이는 한 줄
#
#  🔴 지금까지는 획이 끝날 때만 출력이 나왔다. 그래서 아무 일도 안 일어나면
#     센서가 죽은 건지, 기준 거리를 아직 잡는 중인지, 망이 끊긴 건지,
#     아니면 그냥 아무도 안 그린 건지 구분할 수가 없었다. 세 시간짜리
#     시연에서 그 상태로 서 있으면 고칠 방법이 없다.
#     그래서 한 줄을 계속 덮어쓰며 보여 준다.
# ---------------------------------------------------------------
WIDTH = 92


class Status:
    def __init__(self):
        # 파이프로 넘길 때는 끄다. \r 이 로그 파일을 쓰레기로 만든다.
        self.on = sys.stdout.isatty()
        self.drawn = False
        self.at = 0.0

    def show(self, text, every=0.4):
        if not self.on:
            return
        now = time.time()
        if now - self.at < every:
            return
        self.at = now
        sys.stdout.write("\r" + text[:WIDTH].ljust(WIDTH))
        sys.stdout.flush()
        self.drawn = True

    def clear(self):
        if self.on and self.drawn:
            sys.stdout.write("\r" + " " * WIDTH + "\r")
            sys.stdout.flush()
            self.drawn = False


STATUS = Status()


def say(*a):
    """상태 줄을 지우고 보통 출력을 한 뒤, 다음 show 가 다시 그리게 둔다."""
    STATUS.clear()
    print(*a)


def status_line(tracker, up, strokes):
    """센서, 기준 거리, 손, 업로드를 한 줄에."""
    try:
        snap = tracker.snapshot()
    except Exception:
        return "..."
    alive = sum(1 for b in snap["baseline"] if b is not None)
    if snap["calibrating"]:
        base = f"기준 잡는 중 {snap['calib_n']}"
    elif alive == 0:
        base = "기준 없음"
    else:
        base = "기준 OK"
    hand = "손 ●" if snap.get("finger") else "손 ·"
    rate = snap.get("rate") or 0
    q = f"  대기 {len(up.queue)}" if up.queue else ""
    fail = f"  실패 {up.failed}" if up.failed else ""
    return (f"{rate:5.1f} fps   센서 {alive}/9   {base}   {hand}   "
            f"획 {strokes}   올림 {up.sent}{q}{fail}")


def sensor_line(tracker):
    """센서 아홉 개의 지금 거리. 하나가 죽으면 여기서 바로 보인다."""
    try:
        snap = tracker.snapshot()
    except Exception:
        return "..."
    cells, dead = [], []
    for i, (d, b) in enumerate(zip(snap["dist"], snap["baseline"])):
        if b is None or d is None or d < 0:
            cells.append("  --")
            dead.append(i)
        else:
            cells.append(f"{d:4.0f}")
    tail = f"   ✗ {','.join(str(i) for i in dead)}번 안 읽힘" if dead else "   전부 읽힘"
    return f"{(snap.get('rate') or 0):5.1f} fps  " + " ".join(cells) + tail


class Uploader:
    def __init__(self, dry=False):
        self.dry = dry
        env_url = os.environ.get("RAONSUM_FIREBASE_URL", "").strip().rstrip("/")
        # 예시 파일의 "프로젝트이름" 을 그대로 두면 urllib 이 latin-1 로 못 바꿔
        # 뜬금없는 codec 오류를 낸다. 여기서 먼저 걸러 준다.
        if env_url and not env_url.isascii():
            print(f"[{VERSION}] ⚠️ RAONSUM_FIREBASE_URL 에 한글이 들어 있습니다. "
                  f"예시를 안 고치신 것 같아 무시합니다.")
            env_url = ""
        self.url = env_url or db_url_from_config()
        self.from_config = not env_url and bool(self.url)
        self.auth = Auth()
        self.sent = 0
        self.failed = 0
        # 🔴 올리지 못한 크리스탈은 버리지 않는다. 관객이 방금 그린 획이다.
        #    전시장 와이파이가 한 번 끊겼다고 그 사람 것만 사라지면 안 된다.
        #    🔴 메모리에만 두면 허브를 닫는 순간 같이 사라진다. 와이파이가
        #       끊긴 채로 시연이 끝나면 그 시간 관객 것이 통째로 없어진다.
        #       파일에 받쳐 두고, 다음에 켤 때 마저 올린다.
        self.queue = []
        self.spool = os.path.join(HERE, "outbox.json")
        if not dry:
            self._load_spool()
        if not dry and not self.url:
            sys.exit(f"[{VERSION}] 주소가 없습니다. web/config.js 의 databaseURL 을 채우거나 "
                     f"RAONSUM_FIREBASE_URL 을 넣으세요.")
        if not dry and self.auth.mode == "없음":
            print(f"[{VERSION}] ⚠️ 쓰기 권한이 없습니다. 규칙이 잠겨 있으면 전부 실패합니다.")

    def _load_spool(self):
        """지난번에 못 올리고 남은 것을 다시 집어 든다."""
        try:
            with open(self.spool, encoding="utf-8") as f:
                left = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(left, list) and left:
            self.queue = left
            print(f"[{VERSION}] 지난번에 못 올린 {len(left)}개를 들고 시작합니다")

    def _save_spool(self):
        try:
            if self.queue:
                with open(self.spool, "w", encoding="utf-8") as f:
                    json.dump(self.queue, f, ensure_ascii=False)
            elif os.path.exists(self.spool):
                os.remove(self.spool)
        except OSError as e:
            say(f"  ⚠️ 대기 목록을 파일에 못 적었습니다 ({e})")

    def _endpoint(self, path=None):
        # 🔴 기본값에 RTDB_PATH 를 바로 쓰면 안 된다. 파이썬은 기본값을 함수를
        #    만들 때 한 번만 묶는다. 그래서 --path 로 전역을 바꿔도 여기는
        #    예전 값("crystals")을 계속 쓴다. 실제로 그 바람에 시험용 크리스탈
        #    6개가 전시용 자리에 들어갔다. 부를 때마다 읽는다.
        if path is None:
            path = RTDB_PATH
        url = f"{self.url}/{path}.json"
        a = self.auth.value()
        return url + (f"?auth={a}" if a else "")

    def _put(self, crystal):
        line = json.dumps(crystal, ensure_ascii=False).encode()
        req = urllib.request.Request(self._endpoint(), data=line, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())

    def flush(self):
        """받쳐 둔 것을 지금 올려 본다.

        🔴 send 안에서만 털면, 허브를 다시 켠 뒤 아무도 안 그리는 동안
           지난번 것이 그대로 앉아 있는다. 켜자마자 한 번 턴다.
        """
        if self.dry or not self.queue:
            return
        n0 = len(self.queue)
        while self.queue:
            try:
                self._put(self.queue[0])
            except Exception as e:
                print(f"[{VERSION}] 받쳐 둔 {len(self.queue)}개를 아직 못 올립니다 ({e})")
                return
            self.queue.pop(0)
            self.sent += 1
            self._save_spool()
        print(f"[{VERSION}] 받쳐 둔 {n0}개를 마저 올렸습니다")

    def send(self, crystal):
        line = json.dumps(crystal, ensure_ascii=False)
        if self.dry:
            say(f"  [dry] {line}")
            self.sent += 1
            return

        self.queue.append(crystal)
        self._save_spool()
        while self.queue:
            item = self.queue[0]
            try:
                self._put(item)
            except Exception as e:
                self.failed += 1
                say(f"  업로드 실패 ({e}). {len(self.queue)}개를 들고 "
                    f"다음 획 때 다시 시도합니다 (hub/outbox.json 에 받쳐 뒀습니다).")
                return
            self.queue.pop(0)
            self._save_spool()
            self.sent += 1
            say(f"  올림 {self.sent}번째  {item['feeling']}  "
                f"press {item['press']}  speed {item['speed']}  "
                f"elong {item['elong']}  conf {item['conf']}")

    def check(self):
        """ESP32 없이 연결만 본다. 읽기, 쓰기, 지우기를 차례로 해 본다."""
        print(f"[{VERSION}] 주소   {self.url or '(없음)'}"
              f"{' (web/config.js 에서)' if self.from_config else ''}")
        print(f"[{VERSION}] 권한   {self.auth.mode}")
        if not self.url:
            return 1

        try:
            self.auth.value()
        except Exception as e:
            print(f"  ✗ 로그인 실패 ({e})")
            return 1

        # 읽기. 관객 폰이 하는 것과 같은 요청이다.
        try:
            with urllib.request.urlopen(f"{self.url}/{RTDB_PATH}.json", timeout=8) as r:
                data = json.loads(r.read().decode() or "null")
            n = len(data) if isinstance(data, dict) else 0
            print(f"  ✓ 읽기  지금 {n}개 올라와 있습니다 (권한 없이 읽혔습니다)")
        except Exception as e:
            code = getattr(e, "code", None)
            why = {404: "주소가 틀렸거나 Realtime Database 를 아직 안 만들었습니다",
                   401: "규칙의 .read 가 true 가 아닙니다",
                   403: "규칙의 .read 가 true 가 아닙니다"}.get(code, "")
            # 망이 끊긴 것과 규칙 문제는 고치는 방법이 전혀 다르다. 갈라서 알려 준다.
            if isinstance(e, urllib.error.URLError) and not code:
                why = "인터넷에 못 닿습니다. 와이파이를 확인하세요"
            print(f"  ✗ 읽기 실패 ({e}). {why}")
            return 1

        # 쓰기
        probe = {"t": int(time.time() * 1000), "press": 0.5, "speed": 0.5,
                 "dur": 1.0, "elong": 0.5, "wind": 0.0, "curl": 0.0, "dir": 0.0,
                 "n": 3, "feeling": "selftest", "conf": 0.55}
        try:
            name = self._put(probe)["name"]
            print(f"  ✓ 쓰기  {name}")
        except Exception as e:
            code = getattr(e, "code", None)
            why = ("권한 설정(비밀키 또는 계정)과 규칙의 .write 를 보세요"
                   if code in (401, 403) else "")
            print(f"  ✗ 쓰기 실패 ({e}). {why}")
            return 1

        # 지우기. 남으면 전시 화면에 가짜 크리스탈이 하나 뜬다.
        try:
            req = urllib.request.Request(self._endpoint(f"{RTDB_PATH}/{name}"),
                                         method="DELETE")
            urllib.request.urlopen(req, timeout=5).read()
            print("  ✓ 지우기  시험용 한 개를 치웠습니다")
        except Exception as e:
            print(f"  ⚠️ 시험용 크리스탈 {name} 이 남았습니다 ({e}). 콘솔에서 지우세요")
        print(f"[{VERSION}] 전부 통과했습니다. --port 로 실제 운영을 돌리면 됩니다.")
        return 0


# ---------------------------------------------------------------
#  입력: 시리얼 또는 녹화 재생
# ---------------------------------------------------------------

# 시리얼이 붙었나 끊겼나를 감시 창에 알린다. 없으면 아무 일도 안 한다.
SERIAL_CB = None


def _serial(text):
    if SERIAL_CB:
        try:
            SERIAL_CB(text)
        except Exception:
            pass


# 블루투스 가상 포트. ESP32 를 찾을 때 건너뛴다. 열면 몇 초씩 걸린다.
SKIP_PORTS = ("Bluetooth", "debug-console", "BeoplayH9", "Earbuds", "AirPods")


def list_ports():
    """꽂혀 있는 시리얼 포트. 블루투스는 뺀다."""
    try:
        from serial.tools import list_ports as lp
    except ImportError:
        return []
    out = []
    for p in lp.comports():
        if any(k.lower() in p.device.lower() for k in SKIP_PORTS):
            continue
        out.append(p.device)
    return out


def find_esp32(seconds=2.0):
    """ESP32 를 스스로 찾는다. D, 로 시작하는 줄을 보내는 포트가 그것이다.

    🔴 포트 이름을 외워서 치게 하면 안 된다. 케이블이나 칩이 바뀌면
       /dev/cu.usbserial-0001 이 wchusbserial 이나 SLAB_USBtoUART 가 된다.
       현장에서 이걸로 막히면 시연이 멈춘다. 그냥 찾아서 연다.
    """
    import serial
    ports = list_ports()
    if not ports:
        return None
    print(f"[{VERSION}] 포트를 찾는 중: {', '.join(ports)}")
    for dev in ports:
        try:
            with serial.Serial(dev, BAUD, timeout=0.3) as ser:
                end = time.time() + seconds
                while time.time() < end:
                    raw = ser.readline().decode(errors="ignore").strip()
                    if raw.startswith("D,"):
                        print(f"[{VERSION}] ESP32 를 찾았습니다: {dev}")
                        return dev
        except Exception:
            continue
    return None


def frames_from_serial(port=None, tracker=None, reconnect=True, stall=6.0):
    """ESP32 에서 거리 아홉 개를 계속 받는다.

    🔴 끊기면 다시 붙는다. 세 시간짜리 시연이라 USB 가 한 번 건드려지거나
       ESP32 가 한 번 리셋되면 그것으로 끝나면 안 된다. 예전에는 예외가
       그대로 올라와 허브가 죽었다.

    🔴 열려 있는데 조용한 경우도 끊긴 것으로 본다. USB 는 멀쩡한데 ESP32 만
       멎으면 포트는 계속 열려 있고 readline 이 빈 줄만 준다. 그 상태로
       가만히 있으면 아무도 뭐가 잘못됐는지 모른다. stall 초 동안 D, 줄이
       하나도 안 오면 닫고 다시 연다.
    """
    import serial
    first = True
    while True:
        dev = port or find_esp32()
        if not dev:
            if not reconnect:
                raise SystemExit(
                    f"[{VERSION}] ESP32 를 못 찾았습니다.\n"
                    f"  보이는 포트: {', '.join(list_ports()) or '없음'}\n"
                    f"  USB 를 꽂고 다시 돌리거나 --port 로 직접 적어 주세요.")
            print(f"[{VERSION}] ESP32 가 안 보입니다. 2초 뒤 다시 찾습니다.")
            time.sleep(2)
            continue

        try:
            ser = serial.Serial(dev, BAUD, timeout=1)
        except Exception as e:
            if not reconnect:
                raise
            print(f"[{VERSION}] {dev} 를 못 열었습니다 ({e}). 2초 뒤 다시.")
            time.sleep(2)
            continue

        _serial("연결됨 " + os.path.basename(dev))
        if first:
            print(f"[{VERSION}] {dev} 열었습니다. "
                  f"처음 2초는 천에서 손을 떼 주세요 (기준 거리 측정).")
            first = False
        else:
            print(f"\n[{VERSION}] {dev} 에 다시 붙었습니다. "
                  f"기준 거리를 다시 잽니다. 천에서 손을 떼 주세요.")
            if tracker is not None:
                tracker.recalibrate()

        last = time.time()
        try:
            while True:
                raw = ser.readline().decode(errors="ignore").strip()
                if time.time() - last > stall:
                    _serial("값 없음")
                    print(f"\n[{VERSION}] {stall:.0f}초 동안 센서 값이 없습니다. "
                          f"다시 연결합니다.")
                    break
                if not raw:
                    continue
                if raw.startswith("#"):
                    print(f"  esp32: {raw}")
                    continue
                if not raw.startswith("D,"):
                    continue
                try:
                    dist = [int(v) for v in raw.split(",")[1:]]
                except ValueError:
                    continue
                last = time.time()
                yield dist, time.time()
        except Exception as e:
            _serial("끊김")
            print(f"\n[{VERSION}] 시리얼이 끊겼습니다 ({e}).")
        finally:
            try:
                ser.close()
            except Exception:
                pass
        if not reconnect:
            return
        time.sleep(1)


def frames_from_csv(path, realtime=True):
    """recordings/rec_*.csv 재생. 헤더는 t,d0..d8."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in rows[0].keys() if c.startswith("d")]
    print(f"[{VERSION}] {os.path.basename(path)} 재생, {len(rows)}프레임, 센서 {len(cols)}개")
    t0 = time.time()
    for row in rows:
        stamp = float(row["t"])
        if realtime:
            wait = t0 + stamp - time.time()
            if wait > 0:
                time.sleep(wait)
        yield [int(row[c]) for c in cols], t0 + stamp


# ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="ESP32 시리얼 포트")
    ap.add_argument("--mock", help="재생할 recordings CSV")
    ap.add_argument("--dry", action="store_true", help="업로드 없이 출력만")
    ap.add_argument("--path", default=None,
                    help="쓸 자리. 시험할 때는 crystals_test 처럼 따로 둔다")
    ap.add_argument("--fast", action="store_true", help="mock 을 실시간 대기 없이 빠르게")
    ap.add_argument("--check", action="store_true",
                    help="ESP32 없이 Firebase 읽기/쓰기/지우기만 확인")
    ap.add_argument("--selftest", action="store_true",
                    help="센서만 본다. 아홉 개 거리를 실시간으로 찍고 올리지 않는다")
    ap.add_argument("--ports", action="store_true", help="보이는 시리얼 포트만 찍고 끝")
    ap.add_argument("--monitor", action="store_true",
                    help="노트북 브라우저에 감시 창을 띄운다 (센서 / 그림 / 입체 / 전송)")
    ap.add_argument("--mport", type=int, default=8700, help="감시 창 포트")
    args = ap.parse_args()
    # 🔴 --path 는 모듈 전역을 갈아끼운다. _endpoint 와 --check 가 전부 이걸
    #    본다. 시험용 자리를 쓰면 화면에 크게 알린다. 전시용에 섞어 쓰면
    #    되돌리기 어렵기 때문이다.
    if args.path:
        global RTDB_PATH
        RTDB_PATH = args.path
        print(f"[{VERSION}] 🔴 시험용 자리에 씁니다: {RTDB_PATH}")
        print(f"[{VERSION}]    관객이 보는 crystals 는 건드리지 않습니다")
        print(f"[{VERSION}]    웹에서는 ?dbpath={RTDB_PATH}&feed=live 로 봅니다")
    load_env_file()

    if args.ports:
        found = list_ports()
        print("보이는 포트: " + (", ".join(found) if found else "없음"))
        if found:
            dev = find_esp32()
            print("ESP32: " + (dev or "D, 를 보내는 포트가 없습니다"))
        return 0

    if args.check:
        print(f"=== {VERSION} 연결 확인 ===")
        return Uploader().check()

    # 🔴 포트를 안 적으면 찾아 준다. 이름을 외워 치게 하면 현장에서 막힌다.
    #    케이블이나 칩이 바뀌면 usbserial 이 wchusbserial 이 된다.
    if PLAYGROUND_ERR:
        sys.exit(PLAYGROUND_ERR)

    selftest = args.selftest
    print(f"=== {VERSION}{' 센서 점검' if selftest else ''} ===")
    if selftest:
        print("올리지 않습니다. 천을 눌러 보면서 아래 숫자가 움직이는지 보세요.")
        print("  --  은 그 센서가 안 읽히는 것입니다. 배선을 보세요.\n")

    up = Uploader(dry=args.dry or selftest)
    up.flush()                      # 지난번에 못 올린 것부터 턴다
    tracker = Tracker()
    strokes = 0

    feed = None

    def on_clean(clean, feel):
        nonlocal strokes
        strokes += 1
        dur = (tracker.stroke_t1 - tracker.stroke_t0) if tracker.stroke_t0 else 0.0
        c = build_crystal(clean, feel, dur)
        up.send(c)
        if feed is not None:
            # 보내고 나서도 줄에 남아 있으면 못 올라간 것이다.
            feed.add_crystal(c, c not in up.queue)

    tracker.on_clean = on_clean

    if args.monitor:
        # 🔴 감시 창은 보는 자리일 뿐이다. 못 띄워도 허브는 계속 돌아야 한다.
        try:
            import monitor
            feed = monitor.Feed(tracker, up, RTDB_PATH, args.mport)   # noqa: F841
            url = monitor.start(feed, args.mport)
            global SERIAL_CB
            SERIAL_CB = feed.set_serial
            print(f"[{VERSION}] 감시 창: {url}")
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass
        except Exception as e:
            print(f"[{VERSION}] ⚠️ 감시 창을 못 띄웠습니다 ({e}). 허브는 계속 갑니다.")

    frames = (frames_from_csv(args.mock, realtime=not args.fast) if args.mock
              else frames_from_serial(args.port, tracker=tracker))
    try:
        for dist, t in frames:
            tracker.feed(dist, t)
            STATUS.show(sensor_line(tracker) if selftest
                        else status_line(tracker, up, strokes))
    except KeyboardInterrupt:
        pass
    finally:
        STATUS.clear()
        tracker.finish_now()
        if selftest:
            snap = tracker.snapshot()
            alive = sum(1 for b in snap["baseline"] if b is not None)
            print(f"\n끝. 센서 {alive}/9 가 읽혔고 획 {strokes}개를 잡았습니다.")
            if alive < 9:
                dead = [i for i, b in enumerate(snap["baseline"]) if b is None]
                print(f"  🔴 {dead} 번 센서가 안 읽힙니다. 배선이나 I2C 주소를 보세요.")
            elif strokes == 0:
                print("  ⚠️ 획이 하나도 안 잡혔습니다. 천을 더 깊게 눌러 보세요.")
            else:
                print("  좋습니다. 이제 --path crystals_test 로 올려 보세요.")
        else:
            print(f"\n끝. 올린 크리스탈 {up.sent}개, 실패 {up.failed}개"
                  + (f", 못 올리고 남은 것 {len(up.queue)}개" if up.queue else ""))


if __name__ == "__main__":
    sys.exit(main() or 0)
