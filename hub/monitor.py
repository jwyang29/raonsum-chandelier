#!/usr/bin/env python3
"""노트북에서 사슬 전체를 눈으로 보는 창.

    python3 hub/hub_v1.py --monitor

브라우저에 http://localhost:8700 이 열린다. 네 칸이 보인다.

    1 센서      아홉 개 거리와 눌린 정도. 죽은 센서가 빨갛게 뜬다
    2 그림      천 위에서 읽힌 궤적. 지금 긋는 선과 방금 끝난 획
    3 입체      그 획으로 태어난 크리스탈. 관객이 보는 것과 같은 코드로 그린다
    4 전송      올라간 것, 실패한 것, 망이 끊겨 들고 있는 것

🔴 왜 pygame 이 아니라 브라우저인가.
   playground_v24 가 pygame 을 쓰지만 이 노트북에는 안 깔려 있다 (그래서
   hub_v1 이 가짜를 끼워 넣는다). 현장에서 pip 를 돌리다 막히면 안 된다.
   파이썬 기본 라이브러리만으로 띄우고, 크리스탈은 web/crystal.js 를 그대로
   불러 그린다. 디버그 화면과 관객 화면이 다른 코드면 디버그가 거짓말을 한다.

🔴 창을 닫아도 허브는 계속 돈다. 보는 자리일 뿐이고 업로드를 막지 않는다.
   HTTP 는 따로 도는 실 위에서 돌고, 전부 daemon 이라 Ctrl+C 로 같이 끝난다.
"""
import json
import os
import threading
import time
from collections import deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

# 천은 한 변 33cm 이고 좌표는 ±150 단위다 (playground_v24 의 UNIT=100, LIMIT=1.5).
FIELD = 150.0
FABRIC_CM = 33.0

# 최근 것만 들고 있는다. 세 시간 동안 다 쌓으면 브라우저가 느려진다.
RECENT = 12


class Feed:
    """허브가 여기에 적고, 브라우저가 여기서 읽는다."""

    def __init__(self, tracker, up, path, port):
        self.tracker = tracker
        self.up = up
        self.path = path
        self.port = port
        self.lock = threading.Lock()
        self.crystals = deque(maxlen=RECENT)
        self.notes = deque(maxlen=6)     # ESP32 가 스스로 하는 말
        self.serial = "여는 중"
        self.started = time.time()

    def add_crystal(self, c, ok):
        with self.lock:
            self.crystals.appendleft({
                "at": time.strftime("%H:%M:%S"),
                "ok": bool(ok),
                "data": c,
            })

    def add_note(self, text):
        """ESP32 의 # 줄. 배선이 틀렸을 때 여기에만 단서가 있다."""
        with self.lock:
            if not self.notes or self.notes[0]["t"] != text:
                self.notes.appendleft({"t": text, "at": time.strftime("%H:%M:%S")})

    def set_serial(self, text):
        with self.lock:
            self.serial = text

    def state(self):
        try:
            s = self.tracker.snapshot()
        except Exception as e:
            return {"error": str(e)}
        up = self.up
        with self.lock:
            crystals = list(self.crystals)
            notes = list(self.notes)
            serial = self.serial
        return {
            "rate": round(s.get("rate") or 0, 1),
            "calibrating": s["calibrating"],
            "calib_n": s["calib_n"],
            "dist": s["dist"],
            "baseline": s["baseline"],
            "press": s["press"],
            "finger": s["finger"],
            "current": s["current"] or [],
            "clean": s["clean"][-4:],
            "field": FIELD,
            "fabric_cm": FABRIC_CM,
            "sent": up.sent,
            "failed": up.failed,
            "queued": len(up.queue),
            "dry": up.dry,
            "path": self.path,
            "serial": serial,
            "crystals": crystals,
            "notes": notes,
            "uptime": int(time.time() - self.started),
        }


def start(feed, port=8700):
    """HTTP 를 따로 도는 실에서 연다. 주소를 돌려준다."""

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=ROOT, **k)

        def log_message(self, *a):
            pass                      # 폴링마다 한 줄씩 찍으면 상태 줄이 묻힌다

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if self.path.startswith("/state"):
                body = json.dumps(feed.state(), ensure_ascii=False).encode("utf-8")
                return self._send(body, "application/json; charset=utf-8")
            return super().do_GET()

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return f"http://localhost:{port}"


PAGE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>허브 감시</title>
<style>
  :root { --bg:#0b0e12; --card:#141922; --line:#232c38; --fg:#d8e0ea;
          --mute:#7f8b99; --ok:#7fd4c1; --bad:#e2766b; --warn:#d8b36b; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; background:var(--bg); color:var(--fg);
    font:13px/1.5 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }
  /* ESP32 가 스스로 하는 말. 배선이 틀렸을 때 여기에만 단서가 있다. */
  #esp { margin:10px 14px 0; padding:9px 12px; border-radius:6px;
         background:#3d201c; border:1px solid #6b3a33; color:#f0b9b1;
         font:12px/1.6 ui-monospace, Menlo, monospace; white-space:pre-wrap; }
  #esp b { color:#fff; display:block; margin-bottom:3px; font-family:inherit; }
  #top { display:flex; gap:14px; align-items:baseline; padding:10px 14px;
         border-bottom:1px solid var(--line); flex-wrap:wrap; }
  #top b { font-size:15px; letter-spacing:-.01em; }
  .pill { font:600 11px/1 ui-monospace, Menlo, monospace; padding:4px 8px;
          border-radius:3px; background:#1d2530; color:var(--mute); }
  .pill.ok { background:#133a33; color:var(--ok); }
  .pill.bad { background:#3d201c; color:var(--bad); }
  .pill.warn { background:#3a3120; color:var(--warn); }
  /* 🔴 minmax(0,1fr) 이어야 한다. 그냥 1fr 은 minmax(auto,1fr) 이라 칸이
     내용보다 작아지지 못한다. 캔버스가 커지면 칸이 따라 커지고 캔버스가
     또 커지는 되먹임이 생긴다. 실제로 4800px 까지 부풀어 다른 칸을 밀어냈다. */
  /* 🔴 읽힌 그림과 태어난 입체가 주인공이다. 그 둘을 보려고 띄우는 창이다.
     센서와 전송은 숫자만 확인하면 되므로 옆 기둥으로 보낸다. */
  #grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr) 250px;
          gap:12px; padding:12px; height:calc(100% - 46px); }
  #side { display:grid; grid-template-rows:auto 1fr; gap:12px; min-height:0; }
  @media (max-width:1000px) { #grid { grid-template-columns:minmax(0,1fr);
                                      height:auto; }
                              #side { grid-template-rows:auto auto; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:8px;
          padding:11px 12px; display:flex; flex-direction:column;
          min-height:0; min-width:0; overflow:hidden; }
  .card.big h2 { font-size:12px; letter-spacing:.2em; }
  .card h2 { margin:0 0 9px; font:600 11px/1 ui-monospace, Menlo, monospace;
             letter-spacing:.16em; color:var(--mute); text-transform:uppercase; }
  .card .sub { font-size:11px; color:var(--mute); margin:-5px 0 9px; }

  /* 1 센서 */
  #sensors { display:grid; grid-template-columns:repeat(3,1fr); gap:5px; }
  .s { background:#0e1319; border:1px solid var(--line); border-radius:5px;
       padding:7px 6px; text-align:center; }
  .s.dead { border-color:#5a2a24; background:#1d1210; }
  .s .n { font:600 9px/1 ui-monospace,Menlo,monospace; color:var(--mute); }
  .s .d { font:600 15px/1.2 ui-monospace,Menlo,monospace; font-variant-numeric:tabular-nums; }
  .s.dead .d { color:var(--bad); font-size:14px; }
  .s .bar { height:4px; background:#1b2029; border-radius:2px; margin-top:5px; }
  .s .bar i { display:block; height:100%; background:var(--ok); border-radius:2px; width:0; }

  /* 2 그림 */
  #fabricWrap { position:relative; flex:1; min-height:320px; display:grid; place-items:center; }
  #fabric { background:#0e1319; border:1px solid var(--line); border-radius:4px; }

  /* 3 입체 */
  #stage { flex:1; min-height:320px; background:#0e1319; border:1px solid var(--line);
           border-radius:4px; position:relative; overflow:hidden; }
  /* 캔버스 크기는 CSS 가 쥔다. three 가 style 을 건드리면 위의 되먹임이 돈다. */
  #stage canvas { display:block; width:100% !important; height:100% !important; }
  #noxtal { position:absolute; inset:0; display:grid; place-items:center;
            color:var(--mute); font-size:12px; text-align:center; padding:0 14px; }
  #feat { margin-top:9px; font:11px/1.7 ui-monospace,Menlo,monospace; color:var(--mute); }
  #feat b { color:var(--fg); font-weight:600; }

  /* 4 전송 */
  #log { flex:1; overflow:auto; margin:0; font:11px/1.6 ui-monospace,Menlo,monospace; }
  #log .row { display:flex; gap:7px; padding:5px 0; border-bottom:1px solid #1b222c; }
  #log .row .t { color:var(--mute); }
  #log .row .m { flex:1; }
  #log .row.bad .m { color:var(--bad); }
  #log .row.ok .m { color:var(--ok); }
  #counts { display:flex; gap:7px; margin-top:9px; flex-wrap:wrap; }
</style>
</head>
<body>
<div id="top">
  <b>허브 감시</b>
  <span class="pill" id="p-serial">시리얼</span>
  <span class="pill" id="p-rate">0 fps</span>
  <span class="pill" id="p-base">기준</span>
  <span class="pill" id="p-path">자리</span>
  <span class="pill" id="p-conn">창 연결</span>
</div>

<div id="esp" style="display:none"></div>
<div id="grid">
  <div class="card big">
    <h2>읽힌 그림</h2>
    <div class="sub" id="fabsub">천 33cm</div>
    <div id="fabricWrap"><canvas id="fabric" width="480" height="480"></canvas></div>
  </div>

  <div class="card big">
    <h2>태어난 입체</h2>
    <div class="sub">관객 화면과 같은 코드로 그립니다</div>
    <div id="stage"><div id="noxtal">아직 없습니다.<br>천에 한 번 그어 보세요.</div></div>
    <div id="feat"></div>
  </div>

  <div id="side">
    <div class="card">
      <h2>센서</h2>
      <div class="sub">손을 떼면 기준에 가까워집니다</div>
      <div id="sensors"></div>
    </div>
    <div class="card">
      <h2>웹 전송</h2>
      <div class="sub" id="dest"></div>
      <div id="log"></div>
      <div id="counts"></div>
    </div>
  </div>
</div>

<script src="/web/vendor/aframe.min.js?v=2"></script>
<script type="module">
// 🔴 크리스탈은 관객이 보는 것과 같은 코드로 그린다. 디버그 화면이 따로
//    그리면, 여기서 멀쩡해 보여도 전시장에서 다르게 나올 수 있다.
let makeCrystal = null, blobsReady = false, glassTime = null;
try {
  const c = await import("/web/crystal.js");
  await c.loadBlobs("/web/blobs.json");
  makeCrystal = c.makeCrystal;
  try { glassTime = (await import("/web/glass_material.js")).glassTime; } catch (e) {}
  blobsReady = true;
} catch (e) {
  document.getElementById("noxtal").textContent =
    "크리스탈 코드를 못 불러왔습니다: " + e.message;
}

// ── 3 입체 ────────────────────────────────────────────────
let renderer, scene, camera, pivot, mesh;
function initStage() {
  const host = document.getElementById("stage");
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio));
  host.appendChild(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(40, 1, 0.01, 50);
  camera.position.set(0, 0, 2.4);
  pivot = new THREE.Object3D();
  scene.add(pivot);
  const fit = () => {
    const w = host.clientWidth, h = host.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  };
  fit();
  addEventListener("resize", fit);
  try { new ResizeObserver(fit).observe(host); } catch (e) {}
  (function spin() {
    requestAnimationFrame(spin);
    if (glassTime) glassTime.value = performance.now() / 1000;
    pivot.rotation.y += 0.012;
    pivot.rotation.x = 0.25;
    renderer.render(scene, camera);
  })();
}
if (blobsReady) initStage();

function showCrystal(d) {
  if (!blobsReady || !pivot) return;
  if (mesh) { pivot.remove(mesh); mesh = null; }
  try {
    mesh = makeCrystal(d, "high");
  } catch (e) { return; }
  // 가운데를 집어서 돌린다. 구운 형태는 원점에 맞춰져 있지 않다.
  mesh.geometry.computeBoundingSphere();
  const r = mesh.geometry.boundingSphere.radius || 0.5;
  const s = 0.85 / (r * Math.max(mesh.scale.x, mesh.scale.y, mesh.scale.z));
  mesh.scale.multiplyScalar(s);
  pivot.add(mesh);
  document.getElementById("noxtal").style.display = "none";
}

const KIND = (d) => (d.wind ?? 0) > 0.42 ? "loop"
                  : (d.elong ?? .5) > 0.5 ? "arc" : "ribbon";

function showFeatures(d) {
  const f = document.getElementById("feat");
  if (!d) { f.textContent = ""; return; }
  const bar = (v) => "▇".repeat(Math.round(Math.max(0, Math.min(1, v)) * 10))
                     .padEnd(10, "·");
  f.innerHTML =
    `형태  <b>${KIND(d)}</b>   느낌 <b>${d.feeling}</b>   확신 ${d.conf}<br>` +
    `세기  ${bar(d.press)} ${d.press}<br>` +
    `속도  ${bar(d.speed)} ${d.speed}<br>` +
    `길쭉  ${bar(d.elong)} ${d.elong}<br>` +
    `맴돎  ${bar(d.wind)} ${d.wind}   비틀림 ${d.curl}<br>` +
    `점 ${d.n}개   ${d.dur}초`;
}

// ── 2 그림 ────────────────────────────────────────────────
const cv = document.getElementById("fabric");
const ctx = cv.getContext("2d");
// 🔴 캔버스 크기를 CSS 로만 늘리면 흐려진다. 픽셀 수를 같이 올린다.
function fitFabric() {
  const host = document.getElementById("fabricWrap");
  const d = Math.max(240, Math.min(host.clientWidth, host.clientHeight));
  const r = Math.min(2, devicePixelRatio || 1);
  if (cv.width === Math.round(d * r)) return;
  cv.width = cv.height = Math.round(d * r);
  cv.style.width = cv.style.height = d + "px";
}
addEventListener("resize", fitFabric);
try { new ResizeObserver(fitFabric).observe(document.getElementById("fabricWrap")); } catch (e) {}
fitFabric();
function drawFabric(s) {
  fitFabric();
  const W = cv.width, H = cv.height, F = s.field || 150;
  const px = (v) => (v / F * 0.5 + 0.5) * W;
  const py = (v) => (0.5 - v / F * 0.5) * H;
  ctx.clearRect(0, 0, W, H);

  // 센서 아홉 자리 (-100, 0, +100)
  ctx.fillStyle = "#1e2732";
  for (const gx of [-100, 0, 100]) for (const gy of [-100, 0, 100]) {
    ctx.beginPath(); ctx.arc(px(gx), py(gy), W / 140, 0, 7); ctx.fill();
  }
  ctx.strokeStyle = "#1b2029"; ctx.lineWidth = 1;
  ctx.strokeRect(px(-100), py(100), px(100) - px(-100), py(-100) - py(100));

  // 방금 끝난 획들. 오래된 것일수록 흐리게.
  const cl = s.clean || [];
  cl.forEach((line, i) => {
    const a = 0.18 + 0.2 * (i / Math.max(1, cl.length - 1));
    ctx.strokeStyle = `rgba(127,212,193,${a})`;
    ctx.lineWidth = W / 150; stroke(line);
  });

  // 지금 긋는 선
  if (s.current && s.current.length > 1) {
    ctx.strokeStyle = "#7fd4c1"; ctx.lineWidth = W / 90; stroke(s.current);
  }
  // 손가락
  if (s.finger) {
    const [x, y, d] = s.finger;
    ctx.fillStyle = "#e9f6f2";
    ctx.beginPath(); ctx.arc(px(x), py(y), (W / 100) + Math.min(W / 36, (d || 0) * W / 1000), 0, 7);
    ctx.fill();
  }
  function stroke(pts) {
    ctx.beginPath();
    pts.forEach((p, i) => i ? ctx.lineTo(px(p[0]), py(p[1]))
                            : ctx.moveTo(px(p[0]), py(p[1])));
    ctx.stroke();
  }
}

// ── 1 센서 ────────────────────────────────────────────────
// 화면 배치는 천을 위에서 내려다본 모양에 맞춘다 (위가 +y).
const ORDER = [6, 7, 8, 3, 4, 5, 0, 1, 2];
function drawSensors(s) {
  const host = document.getElementById("sensors");
  if (host.children.length !== 9) {
    host.innerHTML = ORDER.map((i) =>
      `<div class="s" id="s${i}"><div class="n">${i}</div>` +
      `<div class="d">--</div><div class="bar"><i></i></div></div>`).join("");
  }
  for (let i = 0; i < 9; i++) {
    const el = document.getElementById("s" + i);
    if (!el) continue;
    const d = s.dist[i], b = s.baseline[i], p = s.press[i] || 0;
    const dead = b === null || d === null || d < 0;
    el.classList.toggle("dead", dead);
    el.querySelector(".d").textContent = dead ? "--" : Math.round(d);
    el.querySelector(".bar i").style.width =
      Math.min(100, Math.max(0, p / 40 * 100)) + "%";
  }
}

// ── 4 전송 ────────────────────────────────────────────────
let lastKey = "";
function drawLog(s) {
  document.getElementById("dest").textContent =
    s.dry ? "시험 모드입니다. 올리지 않습니다"
          : `올리는 자리: ${s.path}`;
  const log = document.getElementById("log");
  log.innerHTML = (s.crystals || []).map((c) =>
    `<div class="row ${c.ok ? "ok" : "bad"}"><span class="t">${c.at}</span>` +
    `<span class="m">${c.ok ? "올림" : "실패"}  ${c.data.feeling}  ` +
    `press ${c.data.press}  speed ${c.data.speed}</span></div>`).join("")
    || `<div style="color:var(--mute)">아직 없습니다</div>`;

  const pill = (t, cls) => `<span class="pill ${cls || ""}">${t}</span>`;
  document.getElementById("counts").innerHTML =
    pill("올림 " + s.sent, s.sent ? "ok" : "") +
    pill("실패 " + s.failed, s.failed ? "bad" : "") +
    pill("대기 " + s.queued, s.queued ? "warn" : "");

  // 맨 위 것이 바뀌면 입체를 새로 그린다
  const top = s.crystals && s.crystals[0];
  const key = top ? top.at + "|" + top.data.t : "";
  if (top && key !== lastKey) {
    lastKey = key;
    showCrystal(top.data);
    showFeatures(top.data);
  }
}

// ── 폴링 ──────────────────────────────────────────────────
const setPill = (id, text, cls) => {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = "pill " + (cls || "");
};

async function tick() {
  try {
    const s = await (await fetch("/state", { cache: "no-store" })).json();
    if (s.error) { setPill("p-conn", "트래커 오류", "bad"); return; }
    setPill("p-conn", "연결됨", "ok");
    setPill("p-rate", s.rate.toFixed(1) + " fps", s.rate > 10 ? "ok" : "bad");
    setPill("p-serial", "시리얼 " + s.serial,
            s.serial.indexOf("연결") === 0 ? "ok" : "bad");
    const alive = s.baseline.filter((b) => b !== null).length;
    setPill("p-base", s.calibrating ? `기준 잡는 중 ${s.calib_n}`
                                    : `센서 ${alive}/9`,
            s.calibrating ? "warn" : alive === 9 ? "ok" : "bad");
    setPill("p-path", s.dry ? "올리지 않음" : s.path,
            s.dry ? "warn" : s.path === "crystals" ? "ok" : "warn");
    document.getElementById("fabsub").textContent =
      `천 ${s.fabric_cm}cm   점 ${(s.current || []).length}개`;
    drawSensors(s); drawFabric(s); drawLog(s);
    const esp = document.getElementById("esp");
    const notes = s.notes || [];
    if (notes.length) {
      esp.style.display = "";
      esp.innerHTML = "<b>ESP32 가 보내는 말 (배선 문제는 여기에 나옵니다)</b>" +
        notes.map(n => n.at + "  " + n.t).join("\n");
    } else { esp.style.display = "none"; }
  } catch (e) {
    setPill("p-conn", "허브와 끊김", "bad");
  }
}
tick();
setInterval(tick, 120);
</script>
</body>
</html>
"""
