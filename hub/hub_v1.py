#!/usr/bin/env python3
"""
가상 샹들리에 - 허브 업로더 v1

playground_v24.py 의 트래커를 그대로 쓴다. 획이 끝날 때마다 호출되는
Tracker.on_clean 훅에 갠트리 대신 Firebase 업로드를 붙인 것이다.
위치 추정(FabricEstimator, 오차 1.9cm)과 stroke_feeling 은 손대지 않는다.

실행:
    python3 hub_v1.py --port /dev/cu.usbserial-0001
    python3 hub_v1.py --mock ../../../Desktop/playground/recordings/rec_20261019_133143.csv
    python3 hub_v1.py --mock <csv> --dry        업로드 없이 JSON 만 출력

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
try:
    from playground_v24 import (Tracker, stroke_feeling, BAUD,
                                SPEED_FAST_CMS, PRESS_HARD_MM, PRESS_VARIED_MM)
except ImportError as e:
    PLAYGROUND_ERR = (f"[{VERSION}] playground_v24.py 를 못 불러왔습니다 ({e}).\n"
                      f"  찾은 경로: {PLAYGROUND_DIR}\n"
                      f"  PLAYGROUND_DIR 를 실제 위치로 고치세요.")

RTDB_PATH = "crystals"   # web/config.js 의 DB_PATH 와 같아야 한다
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
        self.queue = []
        if not dry and not self.url:
            sys.exit(f"[{VERSION}] 주소가 없습니다. web/config.js 의 databaseURL 을 채우거나 "
                     f"RAONSUM_FIREBASE_URL 을 넣으세요.")
        if not dry and self.auth.mode == "없음":
            print(f"[{VERSION}] ⚠️ 쓰기 권한이 없습니다. 규칙이 잠겨 있으면 전부 실패합니다.")

    def _endpoint(self, path=RTDB_PATH):
        url = f"{self.url}/{path}.json"
        a = self.auth.value()
        return url + (f"?auth={a}" if a else "")

    def _put(self, crystal):
        line = json.dumps(crystal, ensure_ascii=False).encode()
        req = urllib.request.Request(self._endpoint(), data=line, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())

    def send(self, crystal):
        line = json.dumps(crystal, ensure_ascii=False)
        if self.dry:
            print(f"  [dry] {line}")
            self.sent += 1
            return

        self.queue.append(crystal)
        while self.queue:
            item = self.queue[0]
            try:
                self._put(item)
            except Exception as e:
                self.failed += 1
                print(f"  업로드 실패 ({e}). {len(self.queue)}개를 들고 다음 획 때 다시 시도합니다.")
                return
            self.queue.pop(0)
            self.sent += 1
            print(f"  올림 {self.sent}번째  {item['feeling']}  "
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

def frames_from_serial(port):
    import serial
    ser = serial.Serial(port, BAUD, timeout=1)
    print(f"[{VERSION}] {port} 열었습니다. 처음 2초는 천에서 손을 떼 주세요 (기준 거리 측정).")
    while True:
        raw = ser.readline().decode(errors="ignore").strip()
        if not raw or raw.startswith("#"):
            if raw:
                print(f"  esp32: {raw}")
            continue
        if not raw.startswith("D,"):
            continue
        try:
            dist = [int(v) for v in raw.split(",")[1:]]
        except ValueError:
            continue
        yield dist, time.time()


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
    ap.add_argument("--fast", action="store_true", help="mock 을 실시간 대기 없이 빠르게")
    ap.add_argument("--check", action="store_true",
                    help="ESP32 없이 Firebase 읽기/쓰기/지우기만 확인")
    args = ap.parse_args()
    load_env_file()

    if args.check:
        print(f"=== {VERSION} 연결 확인 ===")
        return Uploader().check()

    if not args.port and not args.mock:
        ap.error("--port 또는 --mock 또는 --check 중 하나가 필요합니다")
    if PLAYGROUND_ERR:
        sys.exit(PLAYGROUND_ERR)

    print(f"=== {VERSION} ===")
    up = Uploader(dry=args.dry)
    tracker = Tracker()

    def on_clean(clean, feel):
        dur = (tracker.stroke_t1 - tracker.stroke_t0) if tracker.stroke_t0 else 0.0
        up.send(build_crystal(clean, feel, dur))

    tracker.on_clean = on_clean

    frames = (frames_from_csv(args.mock, realtime=not args.fast)
              if args.mock else frames_from_serial(args.port))
    try:
        for dist, t in frames:
            tracker.feed(dist, t)
    except KeyboardInterrupt:
        pass
    finally:
        tracker.finish_now()
        print(f"\n끝. 올린 크리스탈 {up.sent}개, 실패 {up.failed}개")


if __name__ == "__main__":
    sys.exit(main() or 0)
