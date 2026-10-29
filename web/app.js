// 장면을 조립하고 피드를 붙인다.
// A-Frame 컴포넌트는 <a-scene> 이 붙기 전에 등록되어야 하므로, HTML 에 장면을
// 적어두지 않고 여기서 만든다. 마커도 config.js 의 MARKERS 에서 생성한다.
//
// 쿼리
//   ?preview=1  마커와 카메라 없이 샹들리에만 본다 (개발과 확인용)
//   ?mock=1     Firebase 없이 가짜 크리스탈을 만든다
//   ?debug=1    마커 수, 크리스탈 수, 품질 단계, fps, 월드 원점을 표시한다
//   ?rate=1200  가짜 크리스탈 생성 간격 (ms)

import "./marker_anchor.js";
import { MARKERS, GEOMETRY, PEDESTAL, SCHEDULE, CAL_KEY, AR_SOURCE, ANCHOR,
         refreshPedestal, refreshMarkers } from "./config.js";
import { Chandelier, RING_GAP, recomputeHeights, ringY } from "./chandelier.js";
import { startFeed, mockData } from "./feed.js";
import { Detector } from "./detect.js";
import { pickCamera, isDesktop } from "./campick.js";
import { loadBlobs } from "./crystal.js";

const VERSION = "web_v1";
const params = new URLSearchParams(location.search);
const DEBUG = params.get("debug") === "1";
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

// 🔴 cameraParametersUrl 을 안 주면 AR.js 가 ar-js-org.github.io 에서 직접 받아 온다.
//    못 받으면 ARToolKit 이 초기화되지 않아 마커가 하나도 안 잡힌다. 이틀 동안
//    사람 없이 도는 전시라 바깥에 기대면 안 된다. web/vendor 에 받아 두었다.

const chandelier = new Chandelier();
const ANCHOR_HINT = ANCHOR.hintSeconds;

// 형태 라이브러리와 장면이 둘 다 준비되기 전에 온 크리스탈은 모아둔다.
// 먼저 들어가면 임시 도형으로 만들어져 버린다.
let pending = [];
let libReady = false, sceneReady = false;

function flush() {
  if (!libReady || !sceneReady || !pending) return;
  pending.forEach((d) => chandelier.add(d));
  pending = null;
  if (PREVIEW) chandelier.seed(48, mockData, 6);
}

loadBlobs()
  .then(() => { libReady = true; flush(); })
  .catch((e) => {
    console.warn("[crystal] blobs.json 을 못 불러왔습니다. 임시 도형으로 갑니다.", e);
    libReady = true; flush();
  });

const lights = `
      <a-entity light="type: ambient; intensity: 0.75"></a-entity>
      <a-entity light="type: directional; intensity: 0.55" position="1 3 1"></a-entity>`;

if (PREVIEW) {
  // 링은 chandelier.js 가 날짜별로 그린다. 여기서는 천 위치만 가늠용으로 둔다.
  const guides = `
      <a-plane position="0 0 0" rotation="-90 0 0" width="0.33" height="0.33"
               material="color: #16202c; opacity: 0.7"></a-plane>`;

  document.getElementById("app").innerHTML = `
  <a-scene background="color: #0b0f14" vr-mode-ui="enabled: false"
           renderer="antialias: true; logarithmicDepthBuffer: true">
    <a-entity camera="fov: 55" position="0 ${(GEOMETRY.ceilingHeight / 2).toFixed(2)} 4.2"
              look-controls wasd-controls="fly: true; acceleration: 25"></a-entity>
    <a-entity id="world">${lights}${guides}</a-entity>
  </a-scene>`;
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
                 canvasWidth: ${AR_SOURCE.width}; canvasHeight: ${AR_SOURCE.height};
                 maxDetectionRate: ${AR_SOURCE.maxDetectionRate};
                 cameraParametersUrl: ./vendor/camera_para.dat;${CAM_PARAM}">
    <a-entity camera></a-entity>
    ${markerTags}
    <a-entity id="world" world-anchor>${lights}</a-entity>
  </a-scene>`;
}

const scene = document.querySelector("a-scene");
const status = document.getElementById("status");
const panel = document.getElementById("debug");
if (DEBUG) panel.style.display = "block";

// 렌더 루프는 A-Frame 이 돈다. 직접 setAnimationLoop 을 잡으면 충돌하므로
// 컴포넌트의 tick 에 올린다.
AFRAME.registerComponent("chandelier-driver", {
  init() {
    this.anchor = this.el.components["world-anchor"];
    this.last = 0;
    this.el.object3D.add(chandelier.root);
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
    panel.textContent =
      `${VERSION}${PREVIEW ? "  preview" : ""}\n` +
      (PREVIEW ? "" : `보이는 마커  ${seen} / ${MARKERS.length}${this.anchor && this.anchor.source && this.anchor.source !== "floor" ? ` (${this.anchor.source === "cube" ? "큐브" : "천장"})` : ""}\n`) +
      `크리스탈     ${chandelier.items.length} (cap ${chandelier.cap})\n` +
      `품질 단계    ${chandelier.level}\n` +
      `fps          ${chandelier.fps ? chandelier.fps.toFixed(1) : "재는 중"}\n` +
      (PREVIEW ? "" : `월드 원점    ${p ? `${p.x.toFixed(3)} ${p.y.toFixed(3)} ${p.z.toFixed(3)}` : "아직 없음"}\n`) +
      `겹           ${chandelier.rings.size}개 (그려진 ${SCHEDULE.periodHours}시간마다 1개)\n` +
      `좌대         지름 ${PEDESTAL.diameter.toFixed(2)} m / 높이 ${PEDESTAL.height.toFixed(2)} m\n` +
      `마커 반지름  ${GEOMETRY.markerRing.toFixed(3)} m\n` +
      `천장 높이    ${GEOMETRY.ceilingHeight.toFixed(2)} m (상단면) / ` +
      `${(GEOMETRY.ceilingHeight + PEDESTAL.height).toFixed(2)} m (바닥)\n` +
      `겹 간격      ${RING_GAP.toFixed(3)} m (한 겹 내려오는 높이)\n` +
      `링 반지름    ${GEOMETRY.ringRadiusMin.toFixed(2)}~${GEOMETRY.ringRadiusMax.toFixed(2)} m (개수에 따라)\n` +
      `인식해상도   ${AR_SOURCE.width}x${AR_SOURCE.height} @${AR_SOURCE.maxDetectionRate}/s`;
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

  applyCal({
    floorCeiling: clamp(GEOMETRY.ceilingHeight + PEDESTAL.height, 1.6, 8.0),
    pedH: PEDESTAL.height,
    pedD: PEDESTAL.diameter,
  });
}

startFeed(
  (data) => { if (pending) pending.push(data); else chandelier.add(data); },
  (msg) => { console.log(`[feed] ${msg}`); },
);
