// 장면을 조립하고 피드를 붙인다.
// A-Frame 컴포넌트는 <a-scene> 이 붙기 전에 등록되어야 하므로, HTML 에 장면을
// 적어두지 않고 여기서 만든다. 마커도 config.js 의 MARKERS 에서 생성한다.
//
// 쿼리
//   ?preview=1  마커와 카메라 없이 샹들리에만 본다 (개발과 확인용)
//   ?mock=1     Firebase 없이 가짜 크리스탈을 만든다
//   ?fill=1     AR 모드에서도 쌓인 상태로 시작한다 (현장 점검용). ?fill=60 처럼 개수도
//   ?msize=0.06 마커 검은 사각형의 실제 한 변 (m). 화면에 띄워 시험할 때 쓴다
//   ?guide=1    마커 평면에 실측 윤곽과 1m 자를 그린다. 월드가 실물에 맞는지 본다
//   ?debug=1    마커 수, 크리스탈 수, 품질 단계, fps, 월드 원점을 표시한다
//   ?rate=1200  가짜 크리스탈 생성 간격 (ms)

import "./marker_anchor.js";
import { MARKERS, GEOMETRY, PEDESTAL, SCHEDULE, CAL_KEY, AR_SOURCE, ANCHOR,
         MAX_CRYSTALS, DESK, FIREBASE, applyRemoteCal,
         refreshPedestal, refreshMarkers } from "./config.js";
import { Chandelier, RING_GAP, recomputeHeights, ringY } from "./chandelier.js";
import { startFeed, mockData } from "./feed.js";
import { Detector } from "./detect.js";
import { pickCamera, isDesktop } from "./campick.js";
import { loadBlobs } from "./crystal.js";

const VERSION = "build 1101e";   // 고칠 때마다 올린다. 폰이 옛 파일을 쓰고 있는지 이걸로 안다
const params = new URLSearchParams(location.search);
const DEBUG = params.get("debug") === "1";

// AR 모드는 평소 빈 상태로 시작한다. 쌓인 것은 Firebase 에서 받는다.
// 그래서 마커만 비춰 보면 아무것도 안 떠 있어서 맞게 도는지 알 수가 없다.
// 현장 점검 때는 ?fill=1 로 마지막 날 모습을 띄워 놓고 본다.
// ?guide=1 : 월드가 실물에 맞는지 눈으로 보는 자리.
// 마커 평면에 실제 치수의 윤곽을 그린다. 장치 40cm 네모가 실제 알루미늄
// 프레임 위에 딱 겹치면 마커 크기와 배치가 맞은 것이다.
// 작게 나오면 markerSize 가 실제 마커와 다른 것이고, 돌아가 있으면 마커를
// 다른 방향으로 붙인 것이고, 비뚤면 마커 반지름(mring)이 다른 것이다.
const GUIDE = params.get("guide") === "1";

const FILL = params.get("fill");
const WANT_FILL = FILL !== null && FILL !== "0";
const PREVIEW = params.get("preview") === "1";
// 보정 패널은 ?cal=1 이나 ?debug=1 에서만 뜬다. 관객이 여는 주소에는 둘 다 없다.
const CAL = params.get("cal") === "1" || params.get("debug") === "1";

// AR.js 는 getUserMedia 에 facingMode:"environment" 를 넣는다. 맥 내장 카메라는
// 전면이라 그 조건에 안 맞고, 연속성 카메라(아이폰)가 붙었다 떨어지면 스트림이
// 갈아끼워질 수 있다. 어떤 카메라를 쓸지 직접 지정하려면 ?cam=<deviceId>.
// deviceId 는 camtest.html 의 카메라 고르기 화면에서 확인한다.
let CAM = params.get("cam");

// 데스크탑에서 AR 모드를 열고 카메라를 지정하지 않았으면 고르게 한다.
// 맥은 카메라가 여럿이고(내장 + 연속성 카메라) 어느 것을 잡느냐로 결과가 달라진다.
// 터치 기기(관객 폰)에서는 띄우지 않는다. 거기서는 AR.js 가 뒷면 카메라를 고른다.
if (!PREVIEW && !CAM && isDesktop()) {
  CAM = await pickCamera();
}
const CAM_PARAM = CAM ? ` deviceId: ${CAM};` : "";

// ── 캔버스 크기에 맞는 카메라 파라미터를 만든다 ────────────────
//
// 🔴 vendor/camera_para.dat 은 640x480 (가로 4:3) 기준이다. ARToolKit 은 이걸
//    캔버스 크기에 맞출 때 가로와 세로를 따로 늘린다 (arParamChangeSize).
//    캔버스가 960x1280 (세로 3:4) 이면 fx 는 1.5배, fy 는 2.67배가 되어
//    픽셀이 1.78대 1로 찌그러진 카메라 모델이 나온다. 영상은 멀쩡한데 모델이
//    틀어져서 정사각형 마커를 맞추려던 해가 발산한다. 현장에서 마커 셋이
//    보이는데 월드 원점이 12.8m, 마커끼리 25m 어긋났다.
//
//    폰을 돌려도 센서는 그대로다. 그래서 긴 변 기준 초점거리는 변하지 않는다.
//    그 값으로 캔버스 크기에 맞는 정사각 픽셀 모델을 만들어 쓴다.
//    왜곡 계수는 0 으로 둔다. 640x480 용 계수를 다른 크기에 그대로 쓰면
//    중심과 배율이 어긋나 오히려 더 틀어진다.
function cameraParaFor(w, h) {
  try {
    // 긴 변의 화각에서 초점거리를 낸다. 폰마다 다르므로 ?fov= 로 맞춘다.
    const f = (Math.max(w, h) / 2) / Math.tan(AR_SOURCE.fov * Math.PI / 360);
    const buf = new ArrayBuffer(176);         // int32 x2 + double x12 + double x9
    const d = new DataView(buf);
    d.setInt32(0, w); d.setInt32(4, h);
    [f, 0, w / 2, 0,  0, f, h / 2, 0,  0, 0, 1, 0]
      .forEach((v, i) => d.setFloat64(8 + i * 8, v));
    // 🔴 왜곡 계수를 0 으로 지어내면 안 된다.
    //    vertex 는 관측 좌표라 검출은 멀쩡해 보이지만, ARToolKit 은 포즈를 풀
    //    때 이 계수로 보정한 이상 좌표를 쓴다. 지어낸 값을 넣으면 검출은 되는데
    //    포즈만 깨진다. 현장에서 모서리는 80px 로 제대로 집는데 거리가 43m 로
    //    나온 것이 이것이다.
    //    vendor/camera_para.dat 의 실제 계수를 쓰고 배율만 맞춘다.
    //    원본 (640x480): k1 k2 p1 p2 = 0.099172 -0.092120 -0.001883 0.001313
    //                    fx fy = 591.409241 588.648865,  x0 y0 = 323.4479 237.6065
    //                    s = 0.970533
    //    k 와 s 는 정규화 좌표에서 도므로 배율과 무관하다. fx, fy 만 늘리고
    //    중심은 새 캔버스 한가운데로 옮긴다.
    const k = f / 609.3654;                 // 원본 초점거리 대비 배율
    [0.099172, -0.092120, -0.001883, 0.001313,
     591.409241 * k, 588.648865 * k, w / 2, h / 2, 0.970533]
      .forEach((v, i) => d.setFloat64(104 + i * 8, v));
    return URL.createObjectURL(new Blob([buf], { type: "application/octet-stream" }));
  } catch (e) {
    console.warn("[AR] 카메라 파라미터를 못 만들었습니다. 기본 파일로 갑니다.", e);
    return "./vendor/camera_para.dat";
  }
}

// 🔴 AR.js 는 AR 모드일 때만 불러온다. <script> 로 머리에 박으면 안 된다.
//
//    A-Frame 시스템은 씬에 그 속성이 없어도 반드시 init 된다. 그래서 AR.js 가
//    로드되어 있기만 하면 ?preview=1 에서도 제 기본값으로 세션을 연다. 카메라를
//    켜 버리고(권한 창이 뜬다) 렌더러를 640x480 으로 바꾼다.
//    preview 씬은 embedded 가 아니라서 A-Frame 이 html.a-fullscreen 을 붙이고,
//    그 CSS 가 캔버스를 화면 전체로 !important 로 못박는다. 결국 4:3 으로 그린
//    그림이 폰 비율(0.46)로 늘어난다. 세로 1.69배, 가로 0.59배. 2.9배 왜곡이다.
//    폰에서 "멀고 작고 위로 늘어나 보인다" 가 이것이었다 (2026-10-29).
function loadScript(src) {
  return new Promise((ok, no) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => no(new Error(`${src} 를 못 불러왔습니다`));
    document.head.appendChild(s);
  });
}
if (!PREVIEW) await loadScript("./vendor/aframe-ar.js?v=2");

let CAL_NOTE = "안 읽음";

// 🔴 현장 실측값을 먼저 받아 적용한다. 마커 엘리먼트를 만들기 전이어야 한다.
//    설치가 끝나면 마커를 못 옮기므로 숫자로 맞추는 길이 유일한데, QR 은 이미
//    인쇄되어 있고 현장에서 다시 배포하는 것도 불안하다. DB 에 적어 두면
//    모든 폰이 따라온다. 못 받아도 그냥 기본값으로 간다. 멈추면 안 된다.
if (!PREVIEW && FIREBASE.databaseURL && !FIREBASE.databaseURL.includes("PASTE_")) {
  try {
    const url = `${FIREBASE.databaseURL.replace(/\/$/, "")}/cal.json`;
    const ctl = new AbortController();
    const kill = setTimeout(() => ctl.abort(), 4000);   // 망이 느려도 넘어간다
    const cal = await (await fetch(url, { signal: ctl.signal })).json();
    clearTimeout(kill);
    const hit = applyRemoteCal(cal);
    // ⚠️ 셋 다 다른 상태다. 현장에서 값을 넣었는데 아무 기별이 없으면
    //    된 건지 안 된 건지 모른다. 그래서 전부 소리를 낸다.
    CAL_NOTE = !cal ? "DB 에 보정값 없음 (기본값)"
             : hit.length ? `적용 ${hit.join(", ")}`
             : "보정값은 받았지만 쓸 수 있는 항목이 없음";
    console.log(`[cal] ${CAL_NOTE}`);
  } catch (e) {
    CAL_NOTE = `못 받음 (${e.name}). 기본값`;
    console.warn(`[cal] ${CAL_NOTE}`);
  }
}

// 🔴 cameraParametersUrl 을 안 주면 AR.js 가 ar-js-org.github.io 에서 직접 받아 온다.
//    못 받으면 ARToolKit 이 초기화되지 않아 마커가 하나도 안 잡힌다. 이틀 동안
//    사람 없이 도는 전시라 바깥에 기대면 안 된다. web/vendor 에 받아 두었다.

const chandelier = new Chandelier();
// 폰이 실제로 내준 영상 크기. 요청한 것과 다르면 포즈가 통째로 틀어진다.
function videoSize() {
  try {
    const v = document.querySelector("video");
    if (v && v.videoWidth) return `${v.videoWidth}x${v.videoHeight}`;
  } catch (e) {}
  return "아직 모름";
}

const ANCHOR_HINT = ANCHOR.hintSeconds;

// 형태 라이브러리와 장면이 둘 다 준비되기 전에 온 크리스탈은 모아둔다.
// 먼저 들어가면 임시 도형으로 만들어져 버린다.
let pending = [];
let libReady = false, sceneReady = false;

function flush() {
  if (!libReady || !sceneReady || !pending) return;
  pending.forEach((d) => chandelier.add(d));
  pending = null;
  // 전시 마지막 날 모습으로 채운다. 48개로 띄우면 성글어서 폰이 실제로
  // 버티는지도, 비례가 맞는지도 알 수 없다.
  if (PREVIEW || WANT_FILL) {
    const layers = SCHEDULE.maxRings;
    const n = Number(FILL) > 1 ? Number(FILL) : Math.min(MAX_CRYSTALS, layers * 15);
    chandelier.seed(n, mockData, layers);
  }
  if (PREVIEW) {
    framePreview();
    setTimeout(framePreview, 2500);   // 올라오던 것들이 자리 잡은 뒤 한 번 더
  }
}

loadBlobs()
  .then(() => { libReady = true; flush(); })
  .catch((e) => {
    console.warn("[crystal] blobs.json 을 못 불러왔습니다. 임시 도형으로 갑니다.", e);
    libReady = true; flush();
  });

// 실측 윤곽. 마커 평면(y=0)이 좌대 상단면이다.
function buildGuide() {
  const g = new THREE.Object3D();
  const mat = (c) => new THREE.LineBasicMaterial({ color: c, depthTest: false });
  const line = (pts, c) => {
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat(c));
    l.renderOrder = 999;
    return l;
  };
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const rect = (s, y, c) => line([V(-s/2, y, -s/2), V(s/2, y, -s/2),
                                  V(s/2, y, s/2), V(-s/2, y, s/2),
                                  V(-s/2, y, -s/2)], c);
  const circle = (r, y, c) => {
    const pts = [];
    for (let i = 0; i <= 72; i++) {
      const a = (i / 72) * Math.PI * 2;
      pts.push(V(Math.cos(a) * r, y, Math.sin(a) * r));
    }
    return line(pts, c);
  };

  g.add(rect(GEOMETRY.deviceSize, 0.002, 0x2bff88));            // 장치 40cm 각
  g.add(rect(GEOMETRY.clothSize, GEOMETRY.deviceHeight, 0xffd23f));  // 천 (장치 위 20cm)
  g.add(circle(PEDESTAL.diameter / 2, 0.001, 0x4aa8ff));        // 좌대 테두리
  g.add(circle(GEOMETRY.markerRing, 0.003, 0xff4f8b));          // 마커 네 개가 놓인 원

  // 마커 자리마다 실제 크기의 네모. 인쇄물 검은 사각형 위에 겹쳐야 한다.
  for (const m of MARKERS) {
    if (m.kind !== "floor") continue;
    const q = rect(m.size, 0.004, 0xffffff);
    q.position.set(m.pos[0], 0, m.pos[2]);
    g.add(q);
  }

  // 세로 자 1m. 10cm 마다 눈금을 친다. 크기가 틀리면 여기서 바로 보인다.
  const rod = new THREE.Mesh(
    new THREE.CylinderGeometry(0.004, 0.004, 1, 8),
    new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }));
  rod.position.y = 0.5;
  rod.renderOrder = 999;
  g.add(rod);
  for (let i = 1; i <= 10; i++) {
    const w = i % 5 === 0 ? 0.10 : 0.05;
    const t = new THREE.Mesh(
      new THREE.BoxGeometry(w, 0.006, 0.006),
      new THREE.MeshBasicMaterial({ color: i % 5 === 0 ? 0xff4f8b : 0xffffff,
                                    depthTest: false }));
    t.position.set(w / 2, i * 0.1, 0);
    t.renderOrder = 999;
    g.add(t);
  }
  return g;
}

// 미리보기 카메라. 샹들리에를 세워 놓고 재서 화면에 꽉 차게 둔다.
//
// ⚠️ 이론상 최대 링 반지름(0.60m)으로 잡으면 안 된다. 실제 링은 그 겹에 걸린
//    개수에서 나오므로 0.10~0.35m 쯤이다. 최대치로 잡으면 실물보다 두 배 멀어져
//    아주 작게 보인다.
// ⚠️ fov 는 세로 기준이다. 세로로 긴 폰에서는 가로 화각이
//    tan(fov/2) * (가로/세로) 로 확 좁아진다. 그쪽이 거리를 지배한다.
const PREVIEW_FOV = 55;

function framePreview() {
  const camEl = document.querySelector("[camera]");
  if (!camEl || !chandelier.rings.size) return;

  // ⚠️ Box3.setFromObject 으로 재면 안 된다. 크리스탈은 셰이더에서 부풀리므로
  //    geometry 의 bounding box 가 실제로 보이는 크기보다 작다. 실제로 재 보니
  //    링 위치만 잡혀서 (높이 1.36m) 가로로 돌렸을 때 위아래가 잘렸다.
  //    링 높이와 반지름은 아는 값이다. 거기에 크리스탈이 삐져나오는 만큼만 더한다.
  const PAD = 0.20;
  let rmax = GEOMETRY.ringRadiusMin, top = -Infinity, bot = Infinity;
  for (const [layer, ring] of chandelier.rings) {
    rmax = Math.max(rmax, ring.radius || 0);
    const y = ringY(layer);
    top = Math.max(top, y);
    bot = Math.min(bot, y);
  }
  const H = (top + PAD) - (bot - PAD);
  const W = rmax * 2 + PAD * 2;
  const tanV = Math.tan(PREVIEW_FOV * Math.PI / 360);
  const aspect = Math.max(0.3, window.innerWidth / window.innerHeight);
  // 여유 10%. 미리보기는 가짜 크리스탈이 계속 붙어서 링이 조금씩 넓어진다.
  const dist = Math.max(H / 2 / tanV, W / 2 / (tanV * aspect)) * 1.1;
  camEl.setAttribute("position", { x: 0, y: (top + bot) / 2, z: dist });
}


// 폰을 돌리면 비율이 뒤집힌다. 그때 다시 잡는다.
if (PREVIEW) window.addEventListener("resize", () => setTimeout(framePreview, 120));

const lights = `
      <a-entity light="type: ambient; intensity: 0.75"></a-entity>
      <a-entity light="type: directional; intensity: 0.55" position="1 3 1"></a-entity>`;

if (PREVIEW) {
  // 링은 chandelier.js 가 날짜별로 그린다. 여기서는 천 위치만 가늠용으로 둔다.
  const guides = `
      <a-plane position="0 0 0" rotation="-90 0 0" width="0.33" height="0.33"
               material="color: #16202c; opacity: 0.7"></a-plane>`;

  // 거리는 띄워 놓고 재서 맞춘다 (framePreview). 여기 값은 첫 프레임용 어림이다.
  const midY = (GEOMETRY.ringMinY + GEOMETRY.ceilingHeight) / 2;

  document.getElementById("app").innerHTML = `
  <a-scene background="color: #0b0f14" vr-mode-ui="enabled: false"
           renderer="antialias: true; logarithmicDepthBuffer: true">
    <a-entity camera="fov: ${PREVIEW_FOV}" position="0 ${midY.toFixed(2)} 3.5"
              look-controls wasd-controls="fly: true; acceleration: 25"></a-entity>
    <a-entity id="world">${lights}${guides}</a-entity>
  </a-scene>`;
  // 미리보기는 카메라를 안 쓴다. 기본 문구를 그대로 두면 폰에서 한참 동안
  // 카메라를 기다리는 것처럼 보인다.
  document.getElementById("status").textContent =
    "미리보기입니다. 폰을 돌리면 같이 돕니다";
} else {
  const markerTags = MARKERS.map((m) => `
    <a-marker id="marker-${m.value}" type="barcode" value="${m.value}"
              size="${m.size}" smooth="true" smoothCount="5"
              smoothTolerance="0.01" smoothThreshold="2"></a-marker>`).join("");

  document.getElementById("app").innerHTML = `
  <a-scene embedded vr-mode-ui="enabled: false"
           renderer="antialias: true; alpha: true; logarithmicDepthBuffer: true"
           arjs="sourceType: webcam; detectionMode: mono_and_matrix; matrixCodeType: 3x3; trackingMethod: best;
                 sourceWidth: ${AR_SOURCE.width}; sourceHeight: ${AR_SOURCE.height};
                 canvasWidth: ${AR_SOURCE.canvasW || AR_SOURCE.width};
                 canvasHeight: ${AR_SOURCE.canvasH || AR_SOURCE.height};
                 maxDetectionRate: ${AR_SOURCE.maxDetectionRate};
                 cameraParametersUrl: ${cameraParaFor(
                   AR_SOURCE.canvasW || AR_SOURCE.width,
                   AR_SOURCE.canvasH || AR_SOURCE.height)};${CAM_PARAM}">
    <a-entity camera></a-entity>
    ${markerTags}
    <a-entity id="world" world-anchor>${lights}</a-entity>
  </a-scene>`;

  // 🔴 폰이 실제로 내주는 영상 크기로 AR.js 를 띄워야 한다.
  //
  //    세로로 든 폰은 카메라가 960x1280 을 준다. 그런데 1280x960 을 요청해
  //    두면 AR.js 가 세로 영상을 가로 캔버스에 욱여넣는다. 정사각형 마커가
  //    직사각형으로 찌그러지고 포즈가 통째로 깨진다. 현장에서 월드 원점이
  //    25m 밖으로 날아갔고 마커끼리 10m 씩 어긋났다.
  //
  //    카메라를 먼저 열어 재고 끄는 방법도 있지만, 폰이 카메라를 놓아주기
  //    전에 AR.js 가 다시 열다 실패하면 화면이 아예 안 뜬다. 그래서 일단
  //    띄워 놓고, 영상 크기가 요청과 다르면 그 크기를 붙여 한 번만 다시 연다.
  //    ?arw 를 직접 준 경우에는 사람이 고른 값이므로 건드리지 않는다.
  {
    let tries = 0;
    const fit = setInterval(() => {
      const v = document.querySelector("video");
      if (!v || !v.videoWidth) { if (++tries > 60) clearInterval(fit); return; }
      clearInterval(fit);
      const w = v.videoWidth, h = v.videoHeight;
      const cw = AR_SOURCE.canvasW || AR_SOURCE.width;
      const ch = AR_SOURCE.canvasH || AR_SOURCE.height;
      if (w === cw && h === ch) return;                 // 이미 맞는다
      // 같은 크기로 또 열지 않는다. 폰을 돌리면 영상이 바뀌므로 크기로 적는다.
      let last = "";
      try { last = sessionStorage.getItem("arfit") || ""; } catch (e) {}
      if (last === `${w}x${h}`) return;
      try { sessionStorage.setItem("arfit", `${w}x${h}`); } catch (e) {}
      console.warn(`[AR] 영상 ${w}x${h}, 캔버스 ${cw}x${ch}. 캔버스를 영상에 맞춰 다시 엽니다.`);
      const u = new URL(location.href);
      u.searchParams.set("cw", String(w));              // 요청(arw)은 건드리지 않는다
      u.searchParams.set("ch", String(h));
      location.replace(u.toString());
    }, 250);
  }
}

const scene = document.querySelector("a-scene");
// ── jsartoolkit 의 두 가지 결함을 바로잡는다 ──────────────────
//
// 둘 다 markers/pose_test.html 의 닫힌 고리 시험으로 확인했다. 알려진 거리에
// 마커를 띄워 그림을 만들고 실제 검출기에 넣어 돌아오는 거리를 재는 시험이다.
//
// 🔴 (1) 세로 캔버스에서 그림을 가로로 늘려 복사한다.
//        ARController 의 그림 복사 코드가 orientation === "portrait" 일 때
//          g = canvas.height / canvas.width
//          drawImage(img, (w - h*g)/2, 0, h*g, w*g)
//        로 그린다. 캔버스가 960x1280 이면 가로를 1706px 로 늘린다. 비율로
//        (세로/가로)^2 = 1.78 배다. 세로로 든 폰은 영상이 960x1280 이라 반드시
//        이 분기를 탄다. 정사각형 마커가 가로로 1.78배 뭉개지고, ARToolKit 이
//        정사각형을 거기 끼워 맞추려다 해가 발산한다. 현장에서 월드 원점이
//        12m, 71m, 196km 로 튀고 NaN 까지 나온 것이 이것이다.
//        시험에서 120x120 을 넣으면 212x118 로 들어갔고, landscape 로 두면
//        118x118 로 제대로 들어갔다.
//
// 🔴 (2) 마커 폭이 1.0 으로 굳는다.
//        trackBarcodeMarkerId 는 if (!this.barcodeMarkers[id]) 로 막혀 있어서
//        이미 등록된 번호의 폭을 안 바꾼다. 그런데 검출 루프가 마커를 처음 본
//        순간 폭 없이 먼저 등록해 버린다. 그러면 기본값 1.0 으로 굳고, 나중에
//        AR.js 가 주는 진짜 크기(0.10)는 버려진다. 거리가 정확히 10배가 된다.
//
// 매 프레임 싸게 확인해서 틀어져 있으면 되돌린다. 마커가 새로 보일 때마다
// 다시 굳을 수 있으므로 한 번만 고쳐서는 안 된다.
// 🔴 (3) 틀린 상태로 들어간 포즈가 계속 남는다.
//        검출 루프는 마커를 전에도 봤으면 getTransMatSquareCont 로 이전 행렬에서
//        이어서 푼다. 페이지가 뜨고 (1)(2)를 고치기 전까지의 몇 프레임 동안
//        뭉개진 그림과 폭 1.0 으로 푼 쓰레기 포즈가 o.matrix 에 박히고, 그 뒤로는
//        계속 그 근처에서만 맴돈다. 새로고침해도 매번 똑같이 재발한다.
//        그래서 고칠 때 쌓인 행렬을 버리고 처음부터 다시 풀게 한다.
let arFixed = false;
function fixArController() {
  const sys = scene && scene.systems && scene.systems.arjs;
  const ctrl = sys && sys._arSession && sys._arSession.arContext
    && sys._arSession.arContext.arController;
  if (!ctrl) return;
  let changed = false;
  if (ctrl.orientation !== "landscape") { ctrl.orientation = "landscape"; changed = true; }
  const bm = ctrl.barcodeMarkers;
  if (bm) {
    for (const m of MARKERS) {
      const e = bm[m.value];
      if (e && e.markerWidth !== m.size) { e.markerWidth = m.size; changed = true; }
    }
    // ⚠️ 행렬을 0 으로 비우면 안 된다. getTransMatSquareCont 가 그 0 을 초기값으로
    //    받아 영원히 0 을 내놓는다. 이어 풀지 말라고만 한다.
    //    (이제 포즈는 marker_anchor 가 직접 푸니 이 경로는 쓰이지 않지만,
    //     AR.js 가 자기 요소를 갱신하는 데 여전히 돈다.)
    if (changed) for (const k in bm) bm[k].inPrevious = false;
  }
  if (changed && !arFixed) {
    arFixed = true;
    console.info("[AR] 검출기 보정: orientation=landscape, 마커 폭 복구, 쌓인 포즈 버림");
  }
}


const status = document.getElementById("status");
const panel = document.getElementById("debug");
if (DEBUG) panel.style.display = "block";

// 패널을 누르면 자세히 보기를 켜고 끈다. 그 폰에 남는다.
let DETAIL = false;
try { DETAIL = localStorage.getItem("dbgdetail") === "1"; } catch (e) {}
if (DEBUG && panel) {
  panel.style.cursor = "pointer";
  panel.addEventListener("click", () => {
    DETAIL = !DETAIL;
    try { localStorage.setItem("dbgdetail", DETAIL ? "1" : "0"); } catch (e) {}
  });
}

// 렌더 루프는 A-Frame 이 돈다. 직접 setAnimationLoop 을 잡으면 충돌하므로
// 컴포넌트의 tick 에 올린다.
// 🔴 뜨자마자 잡아야 한다. 늦으면 그 사이 프레임의 쓰레기 포즈가 박힌다.
//    19개를 훑는 가벼운 반복이라 매 프레임 돌려도 괜찮다.
if (!PREVIEW) setInterval(fixArController, 16);

AFRAME.registerComponent("chandelier-driver", {
  init() {
    this.anchor = this.el.components["world-anchor"];
    this.last = 0;
    this.el.object3D.add(chandelier.root);
    if (GUIDE) this.el.object3D.add(buildGuide());
    sceneReady = true;
    flush();

    // 방향 센서를 켠다. 마커를 놓쳤을 때 샹들리에를 제자리에 붙잡는 데 쓴다.
    // 아이폰(iOS 13+)은 사용자 제스처 안에서만 권한을 받을 수 있어서 첫 탭에 묶는다.
    const gyro = this.anchor && this.anchor.gyro;
    if (gyro) {
      const hint = document.getElementById("gyro-hint");
      const begin = async () => {
        const ok = await gyro.start();
        if (hint) hint.style.display = "none";
        console.log(`[gyro] ${ok ? "켜짐" : "거부됨. 마커 밖에서는 화면에 고정됩니다"}`);
      };
      if (gyro.needsPermission) {
        if (hint) hint.style.display = "block";
        document.addEventListener("click", begin, { once: true });
        document.addEventListener("touchend", begin, { once: true, passive: true });
      } else {
        begin();
      }
    }

    // 크리스탈을 누르면 기계가 그 선을 어떻게 읽었는지 띄운다
    this.detector = new Detector({
      sceneEl: scene,
      boxEl: document.getElementById("det-box"),
      labelEl: document.getElementById("det-label"),
      getMeshes: () => chandelier.items.map((it) => it.mesh),
    });
  },
  tick(time) {
    const now = time / 1000;
    chandelier.update(now);
    if (this.detector) this.detector.update();   // 올라가는 동안 박스가 따라붙는다

    if (now - this.last < 0.25) return;
    this.last = now;

    const seen = this.anchor ? this.anchor.visibleCount : 0;
    // 샹들리에는 머리 위, 마커는 발밑 좌대에 있어서 보는 자세에서는 마커가
    // 화면에 없는 게 정상이다. 그래서 마커를 놓쳤다고 바로 재촉하지 않는다.
    // 자이로는 돌아간 각도만 알고 걸어간 거리는 모르므로, 오래 버티면
    // 조금씩 어긋난다. 그때만 좌대를 다시 비춰 달라고 한다.
    const held = this.anchor ? this.anchor.heldSeconds : 0;
    status.textContent = PREVIEW
      ? "미리보기입니다. 드래그로 둘러보고 WASD 로 움직이세요"
      : !this.anchor || !this.anchor.started ? "좌대의 마커를 화면에 담아 주세요"
      : held > ANCHOR_HINT ? "좌대를 한 번 비추면 위치가 다시 맞습니다"
      : "";
    if (!DEBUG) return;

    const p = this.anchor && this.anchor.started ? this.anchor.pos : null;
    // 🔴 검출기가 진짜로 쓰는 캔버스 크기와 투영 행렬을 읽는다.
    const ar = PREVIEW ? null : (() => {
      try {
        const sys = scene.systems.arjs;
        const c = sys && sys._arSession && sys._arSession.arContext
          && sys._arSession.arContext.arController;
        if (!c || !c.canvas) return null;
        const o = { cw: c.canvas.width, ch: c.canvas.height, fx: "?", fy: "?", corners: "" };
        // 🔴 검출기가 실제로 집은 네 모서리. 여기가 작으면 엉뚱한 것을 마커로
        //    본 것이고, 크면 모서리는 맞는데 포즈 계산이 틀어진 것이다.
        try {
          const n = c.getMarkerNum ? c.getMarkerNum() : 0;
          const parts = [];
          for (let i = 0; i < n && parts.length < 3; i++) {
            const mk = c.getMarker(i);
            if (!mk || mk.idMatrix < 0 || !mk.vertex) continue;
            const v = mk.vertex;
            const w = Math.round(Math.max(Math.abs(v[0][0]-v[1][0]), Math.abs(v[1][0]-v[2][0])));
            const h = Math.round(Math.max(Math.abs(v[0][1]-v[1][1]), Math.abs(v[1][1]-v[2][1])));
            parts.push(`${mk.idMatrix}:${w}x${h}`);
          }
          o.corners = parts.join("  ");
        } catch (e) {}
        const m = c.getCameraMatrix && c.getCameraMatrix();
        if (m) {                      // OpenGL 투영: m[0] = 2fx/W, m[5] = 2fy/H
          o.fx = Math.round(m[0] * o.cw / 2);
          o.fy = Math.round(m[5] * o.ch / 2);
        }
        return o;
      } catch (e) {}
      return null;
    })();
    // 🔴 설정값이 아니라 검출기가 실제로 쥐고 있는 마커 폭을 읽는다.
    const aw = PREVIEW ? null : (() => {
      try {
        const sys = scene.systems.arjs;
        const c = sys && sys._arSession && sys._arSession.arContext
          && sys._arSession.arContext.arController;
        if (!c || !c.barcodeMarkers) return null;
        for (const m of MARKERS) {
          const e = c.barcodeMarkers[m.value];
          if (e) return { v: m.value, w: e.markerWidth, want: m.size, ori: c.orientation };
        }
      } catch (e) {}
      return null;
    })();
    const vs = PREVIEW ? null : videoSize();
    // 🔴 현장에서는 줄이 많으면 오히려 못 읽는다. 꼭 필요한 여섯 줄만 두고
    //    나머지는 패널을 눌러 펼친다. 접힘 여부는 그 폰에 남는다.
    const d2 = (v) => v.toFixed(2);
    const head =
      `${VERSION}${PREVIEW ? "  preview" : ""}${DETAIL ? "" : "   (눌러서 자세히)"}\n` +
      (PREVIEW ? "" : `원점까지     ${p ? d2(p.length()) + " m" : "-"}\n`) +
      (PREVIEW ? "" : `서로 어긋남  ${this.anchor ? (this.anchor.spread * 100).toFixed(1) : "0"} cm` +
        `${this.anchor && this.anchor.spread > 0.08 ? "  틀림" : ""}` +
        `${this.anchor && this.anchor.rejected ? "  버림" : ""}\n`) +
      (PREVIEW ? "" : `번호         ${this.anchor && this.anchor.seenValues.length
          ? this.anchor.seenValues.join(" ") : "없음"}\n`) +
      (PREVIEW ? "" : `검출기 내부  ${ar ? `${ar.cw}x${ar.ch}  fx ${ar.fx} fy ${ar.fy}` : "아직 모름"}` +
        `${ar && Math.abs(ar.fx - ar.fy) > 20 ? "  찌그러짐" : ""}\n`) +
      (PREVIEW ? "" : `검출기 한 변 ${aw ? `${(aw.w * 100).toFixed(1)} cm (준 값 ${(aw.want * 100).toFixed(1)})` : "아직 모름"}` +
        `${aw && Math.abs(aw.w - aw.want) > 0.002 ? "  안 먹음" : ""}  ${aw ? aw.ori : ""}\n`) +
      // 🔴 집은 네 모서리의 픽셀 크기. 150 쯤이면 검출은 맞고 포즈만 틀린 것이다.
      (PREVIEW ? "" : `모서리 px    ${ar && ar.corners ? ar.corners : "없음"}\n`) +
      // 정사각형의 네 돌림 중 어느 것을 골랐나. 같은 묶음이 얼마나 모였나.
      (PREVIEW ? "" : `돌림         ${this.anchor ? (this.anchor.rot | 0) * 90 + "도" : "-"}` +
        `${this.anchor && this.anchor.rotSpread !== undefined
            ? `  (모임 ${(this.anchor.rotSpread * 100).toFixed(1)} cm)` : "  (마커 하나라 못 고름)"}\n`) +
      `fps ${chandelier.fps ? chandelier.fps.toFixed(0) : "-"}  크리스탈 ${chandelier.items.length}  겹 ${chandelier.rings.size}`;

    panel.textContent = !DETAIL ? head : head + "\n\n" +
      (PREVIEW ? "" : `요청 영상    ${AR_SOURCE.width}x${AR_SOURCE.height} @${AR_SOURCE.maxDetectionRate}/s\n`) +
      (PREVIEW ? "" : `실제 영상    ${vs}` +
        `${vs && ar && vs !== `${ar.cw}x${ar.ch}` ? "  <- 캔버스와 다름" : "  OK"}\n`) +
      (PREVIEW ? "" : `보이는 마커  ${seen} / ${MARKERS.length}` +
        `${this.anchor && this.anchor.source && this.anchor.source !== "floor" ? ` (${this.anchor.source === "cube" ? "큐브" : "천장"})` : ""}\n`) +
      (PREVIEW ? "" : `월드 원점    ${p ? `${p.x.toFixed(2)} ${p.y.toFixed(2)} ${p.z.toFixed(2)}` : "아직 없음"}\n`) +
      `화각         ${AR_SOURCE.fov.toFixed(1)} 도\n` +
      `좌대         지름 ${d2(PEDESTAL.diameter)} / 높이 ${d2(PEDESTAL.height)} m\n` +
      `마커 반지름  ${GEOMETRY.markerRing.toFixed(3)} m   한 변 ${(GEOMETRY.markerSize * 100).toFixed(1)} cm\n` +
      `천장         ${d2(GEOMETRY.ceilingHeight)} m (상단면) / ${d2(GEOMETRY.ceilingHeight + PEDESTAL.height)} m (바닥)\n` +
      `겹 간격      ${RING_GAP.toFixed(3)} m\n` +
      `품질 ${chandelier.level}   현장 보정    ${CAL_NOTE}`;
  },
});

document.querySelector("#world").setAttribute("chandelier-driver", "");

// ── 현장 보정 ───────────────────────────────────────────────
// 현장에서 재는 값은 셋이다. 바닥에서 천장까지, 좌대 높이, 좌대 지름.
// 코드가 쓰는 높이는 전부 좌대 상단면 기준이라 좌대 높이를 빼서 넘긴다.
// 값은 이 기기에만 저장되므로, 정해지면 config.js 의 기본값에 적어 넣는다.
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v * 100) / 100));

function readCal() {
  const g = (id, lo, hi, dflt) => {
    const el = document.getElementById(id);
    const v = el ? parseFloat(el.value) : NaN;
    return Number.isFinite(v) ? clamp(v, lo, hi) : dflt;
  };
  return {
    floorCeiling: g("cal-ceil", 1.6, 8.0, GEOMETRY.ceilingHeight + PEDESTAL.height),
    pedH: g("cal-pedh", 0.0, 1.5, PEDESTAL.height),
    pedD: g("cal-pedd", 0.3, 2.0, PEDESTAL.diameter),
  };
}

function applyCal(v) {
  PEDESTAL.height = v.pedH;
  PEDESTAL.diameter = v.pedD;
  GEOMETRY.ceilingHeight = Math.max(0.8, clamp(v.floorCeiling - v.pedH, 0.8, 8));

  refreshPedestal();   // 좌대 지름 -> 마커 반지름, 좌대 높이 -> 링 하한
  refreshMarkers();    // 마커 네 개의 위치와 천장 마커 높이

  // 첫 호출은 A-Frame 이 엔티티를 초기화하기 전이라 components 가 아직 없다.
  const world = document.querySelector("#world");
  const anchor = world && world.components && world.components["world-anchor"];
  if (anchor && anchor.rebuildInverses) anchor.rebuildInverses();

  recomputeHeights(chandelier);

  try {
    localStorage.setItem(CAL_KEY, JSON.stringify({
      floorceiling: v.floorCeiling, pedh: v.pedH, ped: v.pedD,
    }));
  } catch {}

  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) el.value = val;
  };
  set("cal-ceil", v.floorCeiling.toFixed(2));
  set("cal-pedh", v.pedH.toFixed(2));
  set("cal-pedd", v.pedD.toFixed(2));

  const hint = document.getElementById("cal-hint");
  if (!hint) return;
  const fit = refreshPedestal();
  const lastY = ringY(SCHEDULE.maxRings - 1);
  // 하루에 내려오는 높이가 이 작품의 핵심 수치다. 좌대가 높으면 그만큼 줄어든다.
  hint.innerHTML =
    `<b>그려진 ${SCHEDULE.periodHours}시간마다 ${(RING_GAP * 100).toFixed(1)}cm 내려옴</b><br>` +
    `샹들리에 ${GEOMETRY.ceilingHeight.toFixed(2)}m ~ ${lastY.toFixed(2)}m (상단면 기준)<br>` +
    `바닥 기준 ${(GEOMETRY.ceilingHeight + v.pedH).toFixed(2)}m ~ ${(lastY + v.pedH).toFixed(2)}m<br>` +
    `마커 반지름 ${GEOMETRY.markerRing.toFixed(3)}m` +
    (fit.fits ? "" : `<br>⚠️ 좌대가 좁습니다. ${fit.needD.toFixed(2)}m 이상 필요`) +
    `<br>확정되면 config.js 에<br>` +
    `<code>height: num("pedh", ${v.pedH.toFixed(2)})</code><br>` +
    `<code>diameter: num("ped", ${v.pedD.toFixed(2)})</code><br>` +
    `<code>ceilingHeight: num("ceiling", ${GEOMETRY.ceilingHeight.toFixed(2)})</code>`;
}

if (CAL) {
  const panel = document.getElementById("cal");
  panel.style.display = "block";

  // +- 버튼은 천장 높이에만 붙는다. 현장에서 가장 자주 더듬는 값이다.
  panel.querySelectorAll("button[data-d]").forEach((b) => {
    b.addEventListener("click", () => {
      const v = readCal();
      v.floorCeiling = clamp(v.floorCeiling + parseFloat(b.dataset.d), 1.6, 8.0);
      applyCal(v);
    });
  });

  ["cal-ceil", "cal-pedh", "cal-pedd"].forEach((id) => {
    document.getElementById(id).addEventListener("input", () => applyCal(readCal()));
  });

  // 이 기기에 남은 보정값을 지운다. 테스트하다 남은 값 때문에 헷갈리는 일이 잦다.
  document.getElementById("cal-reset").addEventListener("click", () => {
    try { localStorage.removeItem(CAL_KEY); } catch {}
    location.reload();
  });

  // ⚠️ 책상 모드에서는 돌리지 않는다. applyCal 의 천장 하한이 0.8m 라
  //    책상용 0.70m 를 도로 밀어 올린다.
  if (!DESK) applyCal({
    floorCeiling: clamp(GEOMETRY.ceilingHeight + PEDESTAL.height, 1.6, 8.0),
    pedH: PEDESTAL.height,
    pedD: PEDESTAL.diameter,
  });
}

startFeed(
  (data) => { if (pending) pending.push(data); else chandelier.add(data); },
  (msg) => { console.log(`[feed] ${msg}`); },
);
