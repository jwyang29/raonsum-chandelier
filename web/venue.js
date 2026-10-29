// 전시된 모습 미리보기.
// AR 없이, 전시장에 놓인 상태를 통째로 세워 놓고 돌려 본다.
// 설치 전에 좌대 지름과 높이, 천장 높이를 바꿔 가며 비례를 보기 위한 것이다.
//
// 쓰는 것은 전부 실제 값이다. 샹들리에는 app.js 와 같은 Chandelier 를 쓰고,
// 바닥 그림자는 deco/make_shadows.py 가 뽑은 좌표를 그대로 깐다.
// 여기서만 쓰는 수치를 따로 들고 있지 않아야 미리보기와 실물이 어긋나지 않는다.

import { GEOMETRY, PEDESTAL, SCHEDULE, MARKERS, GLASS, MAX_CRYSTALS,
         CUBES, cubeFaceFor, refreshPedestal, refreshMarkers } from "./config.js";
import { Chandelier, recomputeHeights, ringY, RING_GAP, ringRadius } from "./chandelier.js";
import { mockData } from "./feed.js";
import { loadBlobs } from "./crystal.js";

const params = new URLSearchParams(location.search);
// 0 이 뜻이 있는 값은 || 로 받으면 안 된다
const numP = (k, d) => {
  const v = parseFloat(params.get(k));
  return Number.isFinite(v) ? v : d;
};
const state = {
  pedD: parseFloat(params.get("ped")) || PEDESTAL.diameter,
  pedH: parseFloat(params.get("pedh")) || PEDESTAL.height,
  floorCeiling: parseFloat(params.get("floorceiling")) || 3.40,
  // 사진의 좌대는 낮고 넓다. 실측 전까지는 어림값이다.
  layers: parseInt(params.get("layers") || String(SCHEDULE.maxRings), 10),  // 몇 겹까지 쌓였는지
  perLayer: parseInt(params.get("per") || "15", 10),    // 한 겹에 평균 몇 개
  shadows: params.get("shadows") !== "0",
  // 유리의 중심 불투명도. config.js 의 GLASS.alphaCore 가 기본값이다.
  // 이 셰이더는 어두운 카메라 영상 위에서 맞춘 값이라 흰 전시장 벽에서는
  // 거의 안 보인다. 여기서 바로 비교하라고 슬라이더로 뺐다.
  glass: parseFloat(params.get("glass")) || GLASS.alphaCore,

  // 천장에서 낚싯줄로 내려 매단 마커 큐브. 자리와 크기는 config.js 의
  // CUBE_PLAN 이 정한다. 여기서는 몇 개까지 보일지만 고른다.
  cubeN: parseInt(params.get("cuben") || String(CUBES.length), 10),
  cubeFrame: parseInt(params.get("arw") || "1280", 10),
};

const chandelier = new Chandelier();
let grids = {}, shadowData = null;

// ── 마커 한 장을 캔버스로 그린다 ────────────────────────────
// grids.json 은 5x5 다. 바깥 테두리가 검은 테두리이고 가운데 3x3 이 코드다.
// 1 이 흰 칸이다. 흰 여백(quiet zone)까지 그려야 실제로 붙는 크기가 나온다.
function markerTexture(value) {
  const g = grids[String(value)];
  const px = 256, quiet = Math.round(px * 0.25 / 1.5);   // 여백은 블록의 1/6
  const c = document.createElement("canvas");
  c.width = c.height = px;
  const x = c.getContext("2d");
  x.fillStyle = "#fff";
  x.fillRect(0, 0, px, px);
  if (!g) return new THREE.CanvasTexture(c);
  const cell = (px - quiet * 2) / 5;
  for (let r = 0; r < 5; r++) {
    for (let k = 0; k < 5; k++) {
      // 마커는 #333 으로 찍는다 (markers/make_pdf.py 의 INK). 검정이 아니다.
      x.fillStyle = g[r][k] ? "#fff" : "#333";
      x.fillRect(quiet + k * cell, quiet + r * cell, cell + 0.5, cell + 0.5);
    }
  }
  return new THREE.CanvasTexture(c);
}

// ── 그림자 시트지 ──────────────────────────────────────────
// 시트지는 좌대 상판에서 시작해 옆면을 타고 바닥으로 퍼진다. 세 면이라 세 장이다.
// 26개를 따로 메시로 만들면 드로우콜만 늘고 얻는 게 없다. 어차피 평면이다.
function drawLoops(x, items, place) {
  x.fillStyle = "#1b1f24";
  for (const it of items) {
    const [px, py, k, rot] = place(it);
    x.save();
    x.translate(px, py);
    x.rotate(rot * Math.PI / 180);
    x.scale(it.size * k, it.size * k);
    x.beginPath();
    for (const loop of it.loops) {
      loop.forEach(([lx, ly], i) => (i ? x.lineTo(lx, ly) : x.moveTo(lx, ly)));
      x.closePath();
    }
    x.fill("evenodd");
    x.restore();
  }
}

function canvasOf(px) {
  const c = document.createElement("canvas");
  c.width = c.height = px;
  return c;
}

function texOf(c) {
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 8;
  return t;
}

// 바닥. make_shadows.py 의 pad 와 같은 여백을 둔다.
function floorTexture(d) {
  const W = d.spread + 240, px = 2048, k = px / W;
  const c = canvasOf(px);
  drawLoops(c.getContext("2d"), d.items.filter((i) => i.zone === "floor"),
            (it) => [(W / 2 + it.x) * k, (W / 2 + it.y) * k, k, it.rot]);
  return { tex: texOf(c), size: W / 1000 };
}

// 좌대 상판. 마커와 장치를 피해 놓인 것들이다.
function topTexture(d) {
  const W = d.pedestal, px = 1024, k = px / W;
  const c = canvasOf(px);
  drawLoops(c.getContext("2d"), d.items.filter((i) => i.zone === "top"),
            (it) => [(W / 2 + it.x) * k, (W / 2 + it.y) * k, k, it.rot]);
  return { tex: texOf(c), size: W / 1000 };
}

// 좌대 옆면. 펼치면 가로 pi*지름, 세로 좌대 높이인 띠다.
function sideTexture(d) {
  const W = Math.PI * d.pedestal, H = d.pedh;
  const px = 2048, k = px / W;
  const c = document.createElement("canvas");
  c.width = px;
  c.height = Math.max(8, Math.round(H * k));
  drawLoops(c.getContext("2d"), d.items.filter((i) => i.zone === "side"),
            (it) => [it.u * k, it.v * k, k, it.rot]);
  return { tex: texOf(c) };
}

// ── 장면 ────────────────────────────────────────────────────
// ⚠️ A-Frame 컴포넌트는 <a-scene> 이 붙기 전에 등록되어야 한다. 모듈 스크립트는
//    defer 라서 HTML 에 씬을 적어 두면 등록 전에 초기화되고 컴포넌트가 무시된다.
//    그래서 app.js 와 같이 씬을 여기서 만든다.
const root = new THREE.Object3D();          // 좌대와 장치. 좌대 값이 바뀌면 다시 만든다
const floorGroup = new THREE.Object3D();    // 바닥 그림자
const chandelierPivot = new THREE.Object3D();  // 좌대 상단면에 둔다. 모든 높이의 기준
const cubeGroup = new THREE.Object3D();     // 천장에서 낚싯줄로 내려 매단 마커 큐브
let roomCeiling = null, figure = null, topDecal = null, sideDecal = null;

function buildRoom() {
  const g = new THREE.Object3D();
  const wall = new THREE.MeshStandardMaterial({ color: 0xf2f2f0, roughness: 0.95 });

  // 바닥. 사진의 전시장은 광택 있는 회색 바닥이라 거칠기를 낮춘다.
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(16, 16),
    new THREE.MeshStandardMaterial({ color: 0x9a9b98, roughness: 0.28, metalness: 0.08 }));
  floor.rotation.x = -Math.PI / 2;
  g.add(floor);

  for (const [w, h, pos, rot] of [
    [16, 6, [0, 3, -4.2], [0, 0, 0]],
    [16, 6, [-4.6, 3, 0], [0, Math.PI / 2, 0]],
  ]) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), wall);
    m.position.set(...pos);
    m.rotation.set(...rot);
    g.add(m);
  }

  roomCeiling = new THREE.Mesh(new THREE.PlaneGeometry(16, 16),
    new THREE.MeshStandardMaterial({ color: 0xfbfbfa, roughness: 1, side: THREE.DoubleSide }));
  roomCeiling.rotation.x = Math.PI / 2;
  g.add(roomCeiling);

  // 천장 레일 조명. 비례를 가늠하는 데 생각보다 도움이 된다.
  const railMat = new THREE.MeshStandardMaterial({ color: 0x2a2d31, roughness: 0.6 });
  for (const z of [-2.6, 1.4]) {
    const rail = new THREE.Mesh(new THREE.BoxGeometry(9, 0.05, 0.05), railMat);
    rail.position.set(0, 0, z);
    g.add(rail);
    for (let i = -3; i <= 3; i++) {
      const head = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.06, 0.16, 10), railMat);
      head.position.set(i * 1.3, -0.11, z);
      head.rotation.z = 0.35;
      g.add(head);
    }
  }
  g.userData.rails = g.children.slice(-1 * (2 * 8));
  return g;
}
const room = buildRoom();

// 좌대와 장치. 지름이나 높이가 바뀌면 통째로 다시 만든다.
function buildPedestal() {
  root.clear();
  const R = state.pedD / 2, H = state.pedH;

  const ped = new THREE.Mesh(
    new THREE.CylinderGeometry(R, R, H, 64),
    new THREE.MeshStandardMaterial({ color: 0xf6f6f4, roughness: 0.85 }));
  ped.position.y = H / 2;
  root.add(ped);

  // 상판. 아주 살짝 띄워서 옆면과 경계가 보이게 한다.
  const top = new THREE.Mesh(new THREE.CircleGeometry(R, 64),
    new THREE.MeshStandardMaterial({ color: 0xfcfcfa, roughness: 0.8 }));
  top.rotation.x = -Math.PI / 2;
  top.position.y = H + 0.001;
  root.add(top);

  // 센싱 장치. 알루미늄 프로파일 프레임 40x40x20.
  const D = GEOMETRY.deviceSize, DH = GEOMETRY.deviceHeight;
  const alu = new THREE.MeshStandardMaterial({ color: 0x8d9298, roughness: 0.42, metalness: 0.65 });
  const prof = 0.02;
  for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {   // 기둥 4개
    const c = new THREE.Mesh(new THREE.BoxGeometry(prof, DH, prof), alu);
    c.position.set(sx * (D / 2 - prof / 2), H + DH / 2, sz * (D / 2 - prof / 2));
    root.add(c);
  }
  for (const y of [H + prof / 2, H + DH - prof / 2]) {             // 위아래 테두리
    for (const [w, d, ox, oz] of [[D, prof, 0, D / 2 - prof / 2], [D, prof, 0, -(D / 2 - prof / 2)],
                                  [prof, D, D / 2 - prof / 2, 0], [prof, D, -(D / 2 - prof / 2), 0]]) {
      const b = new THREE.Mesh(new THREE.BoxGeometry(w, prof, d), alu);
      b.position.set(ox, y, oz);
      root.add(b);
    }
  }

  // 천. 프레임 위에 씌우고 가운데가 살짝 내려앉는다.
  const C = GEOMETRY.clothSize, seg = 24;
  const cloth = new THREE.PlaneGeometry(C, C, seg, seg);
  const pos = cloth.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), y = pos.getY(i);
    const r = Math.hypot(x, y) / (C / 2);
    pos.setZ(i, -0.012 * Math.cos(Math.min(1, r) * Math.PI / 2));
  }
  cloth.computeVertexNormals();
  const clothMesh = new THREE.Mesh(cloth,
    // 흰 좌대 위의 흰 천이라 그냥 두면 경계가 안 보인다. 한 톤 낮춰 둔다.
    new THREE.MeshStandardMaterial({ color: 0xe6e0d6, roughness: 1, side: THREE.DoubleSide }));
  clothMesh.rotation.x = -Math.PI / 2;
  clothMesh.position.y = H + DH;
  root.add(clothMesh);

  // 마커 4장. 흰 여백 포함 블록이 실제로 붙는 크기다.
  const block = GEOMETRY.markerSize * 1.5;
  for (const m of MARKERS) {
    // ⚠️ 바닥 마커만이다. 천장 마커와 매단 큐브 마커도 MARKERS 에 있다.
    if (m.kind !== "floor") continue;
    const tex = markerTexture(m.value);
    const q = new THREE.Mesh(new THREE.PlaneGeometry(block, block),
      new THREE.MeshBasicMaterial({ map: tex }));
    q.rotation.x = -Math.PI / 2;
    q.position.set(m.pos[0], H + 0.002, m.pos[2]);
    root.add(q);
  }

  // 상판 시트지. 마커보다 살짝 아래에 둬서 마커가 위로 올라오게 한다.
  if (state.shadows && topDecal) {
    const d = new THREE.Mesh(new THREE.CircleGeometry(R, 64),
      new THREE.MeshBasicMaterial({ map: topDecal.tex, transparent: true, opacity: 0.8 }));
    d.rotation.x = -Math.PI / 2;
    d.position.y = H + 0.0015;
    root.add(d);
  }

  // 옆면 시트지. 원통 옆면에 두르면 된다. 한 방향으로만 휘므로 평평한 시트지로 붙는다.
  if (state.shadows && sideDecal) {
    const g = new THREE.CylinderGeometry(R + 0.001, R + 0.001, H, 64, 1, true);
    const d = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      map: sideDecal.tex, transparent: true, opacity: 0.8, side: THREE.DoubleSide }));
    d.position.y = H / 2;
    root.add(d);
  }

  chandelierPivot.position.y = H;
}

// ── 천장에서 매단 마커 큐브 ──────────────────────────────────
// 낚싯줄 두 줄을 천장에서 내리고 작은 정육면체를 꿰어 옆면 넷에 마커를 붙인다.
// 크기는 고르는 게 아니라 올려다보는 거리에서 나온다 (cubeFaceFor, 실측 규칙).

const PHONE_Y = 1.50;     // 폰을 들어 올려다볼 때의 렌즈 높이

// 큐브가 바닥에서 몇 미터에 걸리는지. 천장에서 내려 매다는 것이라 좌대 높이와
// 상관이 없다. config.js 는 좌대 상단면 기준으로 들고 있으므로 되돌린다.
const cubeFloorY = (c) =>
  Number.isFinite(c.floorY) ? c.floorY : c.y + PEDESTAL.height;

// 그 자리에서 관객이 R 만큼 떨어져 올려다볼 때 읽히는 최소 한 변.
const cubeNeeds = (c, R = 2.0) =>
  cubeFaceFor(Math.hypot(R, Math.abs(cubeFloorY(c) - PHONE_Y)), state.cubeFrame);

function buildCubes() {
  cubeGroup.clear();
  const n = Math.max(0, Math.min(CUBES.length, state.cubeN));
  if (!n) return;

  const white = new THREE.MeshStandardMaterial({ color: 0xf7f7f5, roughness: 0.75 });
  // 낚싯줄은 천장에서 맨 아래 큐브까지 한 번에 내려온다. 큐브는 거기 꿰인다.
  // 실제 낚싯줄은 0.3~0.5mm 로 한 픽셀보다 얇아 안 보인다. 굵게 그린다.
  const lineMat = new THREE.MeshBasicMaterial({
    color: 0xd7dbe0, transparent: true, opacity: 0.75 });

  let lowest = Infinity, widest = 0;
  for (let i = 0; i < n; i++) {
    const c = CUBES[i];
    const face = c.face;
    const a = (c.az || 0) * Math.PI / 180;
    const cx = Math.sin(a) * (c.r || 0), cz = Math.cos(a) * (c.r || 0);
    const y = cubeFloorY(c);
    const mat = (v) => new THREE.MeshBasicMaterial({ map: markerTexture(v) });
    // BoxGeometry 면 순서는 +X, -X, +Y, -Y, +Z, -Z 다.
    // codes 는 [+Z, +X, -Z, -X] 순서다 (바닥 0/63/44/7 을 바라보는 쪽).
    const box = new THREE.Mesh(new THREE.BoxGeometry(face, face, face),
      [mat(c.codes[1]), mat(c.codes[3]), white, white,
       mat(c.codes[0]), mat(c.codes[2])]);
    box.position.set(cx, y, cz);
    cubeGroup.add(box);
    lowest = Math.min(lowest, y - face / 2);
    widest = Math.max(widest, face);
  }

  // 줄 둘. 맨 아래 큐브 바닥까지 내려온다.
  const off = Math.max(0.015, widest / 2 - 0.015);
  for (const sx of [-1, 1]) {
    const h = Math.max(0.05, state.floorCeiling - lowest);
    const l = new THREE.Mesh(new THREE.CylinderGeometry(0.0008, 0.0008, h, 6), lineMat);
    l.position.set(sx * off, lowest + h / 2, 0);
    cubeGroup.add(l);
  }
  cubeGroup.userData = { n, lowest };
}

// 관객 비례. 샹들리에 맨 아래가 머리 위를 지나는지 보려고 둔다.
function buildFigure() {
  const g = new THREE.Object3D();
  const skin = new THREE.MeshStandardMaterial({
    color: 0x6f7a86, roughness: 1, transparent: true, opacity: 0.5 });
  // ⚠️ three.js r137 에는 CapsuleGeometry 가 없다 (r141 에 들어왔다).
  //    A-Frame 1.3.0 이 r137 을 쓰므로 원기둥과 구로 만든다.
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.15, 0.62, 14), skin);
  body.position.y = 1.18;
  const shoulder = new THREE.Mesh(new THREE.SphereGeometry(0.17, 14, 10), skin);
  shoulder.position.y = 1.47;
  shoulder.scale.set(1, 0.55, 0.8);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.105, 16, 12), skin);
  head.position.y = 1.64;
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.1, 10), skin);
  neck.position.y = 1.53;
  const legs = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.12, 0.88, 14), skin);
  legs.position.y = 0.44;
  g.add(body, shoulder, neck, head, legs);
  return g;
}

function layout() {
  // 좌대 바깥에 서서 보는 자리. 기본 시점에서 좌대를 가리지 않게 옆으로 비킨다.
  const fr = state.pedD / 2 + 0.34, fa = 1.75;
  figure.position.set(Math.sin(fa) * fr, 0, Math.cos(fa) * fr);
  roomCeiling.position.y = state.floorCeiling;
  room.userData.rails.forEach((r) => { r.position.y = 0; });
  room.children.forEach((c) => {
    if (c.geometry && c.geometry.type === "BoxGeometry" && c.geometry.parameters.width === 9) {
      c.position.y = state.floorCeiling - 0.03;
    }
  });
  // 레일 조명 머리는 레일 아래에 매달린다
  room.children.forEach((c) => {
    if (c.geometry && c.geometry.type === "CylinderGeometry" && c.geometry.parameters.height === 0.16) {
      c.position.y = state.floorCeiling - 0.14;
    }
  });
  floorGroup.visible = state.shadows;
}

// ── 좌대 값이 바뀌면 전부 다시 잡는다 ───────────────────────
function apply() {
  PEDESTAL.diameter = state.pedD;
  PEDESTAL.height = state.pedH;
  GEOMETRY.ceilingHeight = Math.max(0.8, state.floorCeiling - state.pedH);
  refreshPedestal();
  refreshMarkers();
  recomputeHeights(chandelier);
  buildPedestal();
  buildCubes();
  layout();
  report();
}

// 이미 만들어진 크리스탈의 유니폼까지 바꾼다. 재질은 크리스탈마다 따로 있다.
function applyGlass() {
  GLASS.alphaCore = state.glass;
  for (const it of chandelier.items) {
    it.mesh.traverse((o) => {
      const u = o.material && o.material.uniforms;
      if (!u || !u.uAlphaCore) return;
      u.uAlphaCore.value = state.glass;
      // 흡수를 같이 올려야 흰 벽에서 대비가 생긴다. 투명도만 올리면 더 희어질 뿐이다.
      u.uAbsorb.value = Math.min(0.75, 0.42 + (state.glass - 0.22) * 1.3);
    });
  }
}

function report() {
  const n = Math.min(state.layers, SCHEDULE.maxRings);
  const last = ringY(n - 1);
  const used = [...chandelier.rings.values()].map((r) => r.used);
  const rs = used.length ? used.map(ringRadius) : [0];
  const made = used.reduce((a, b) => a + b, 0);
  // 겹은 그려진 주기에만 열리므로 시계와 1:1 이 아니다. 날짜를 적으면 틀린다.
  // n 겹은 그려진 n 주기이고, 운영 시간으로 나눠야 며칠치인지 나온다.
  const drawnH = n * SCHEDULE.periodHours;
  const [oh0, oh1] = SCHEDULE.openHours || [0, 24];
  const days = drawnH / Math.max(1, oh1 - oh0);

  document.getElementById("info").innerHTML =
    `<b>${n}겹</b> 그린 시간 ${drawnH}시간 ` +
    `(운영 ${oh0}~${oh1}시면 ${days.toFixed(1)}일치)<br>` +
    `지금까지 ${made}개 중 ${chandelier.items.length}개 보임 ` +
    `(상한 ${MAX_CRYSTALS})<br>` +
    `링 반지름 ${Math.min(...rs).toFixed(2)}~${Math.max(...rs).toFixed(2)}m (걸린 개수에서)<br>` +
    `그려진 ${SCHEDULE.periodHours}시간마다 ${(RING_GAP * 100).toFixed(1)}cm 내려옴<br>` +
    `샹들리에 바닥 기준 ${(GEOMETRY.ceilingHeight + state.pedH).toFixed(2)}m ~ ${(last + state.pedH).toFixed(2)}m<br>` +
    `마커 반지름 ${GEOMETRY.markerRing.toFixed(3)}m / 장치 ${GEOMETRY.deviceSize}m 각<br>` +
    `천 높이 바닥에서 ${(state.pedH + GEOMETRY.deviceHeight).toFixed(2)}m` +
    (state.pedH + GEOMETRY.deviceHeight < 0.75
      ? `<br><span style="color:#e8b36b">천이 낮아 관객이 쪼그려야 그립니다</span>` : "") +
    (state.glass < 0.15
      ? `<br><span style="color:#e8b36b">흰 벽에서는 이 값이면 크리스탈이 거의 안 보입니다</span>`
      : "") +
    cubeReport();
}

// 매단 큐브. 크기는 고른 값이 아니라 그 높이에서 나온 값이라 같이 적어 준다.
function cubeReport() {
  const u = cubeGroup.userData;
  if (!u || !u.n) return "";
  let out = `<br><br><b>매단 큐브 ${u.n}개</b> (중심축, 낚싯줄 두 줄)`;
  for (let i = 0; i < u.n; i++) {
    const c = CUBES[i];
    const y = cubeFloorY(c);
    const need = cubeNeeds(c);
    const tight = c.face < need - 0.001;
    out += `<br>바닥 ${y.toFixed(2)}m / 한 변 ${(c.face * 100).toFixed(1)}cm ` +
           `(검은 ${(c.face / 1.5 * 100).toFixed(1)}cm)` +
           (tight ? `<span style="color:#e8b36b"> 2m 에서 읽히려면 ` +
                    `${(need * 100).toFixed(1)}cm 필요</span>` : "");
  }
  const bottom = cubeFloorY(CUBES[0]) - CUBES[0].face / 2;
  if (bottom < 1.15) {
    out += `<br><span style="color:#e8b36b">맨 아래 큐브가 ${bottom.toFixed(2)}m 라 ` +
           `그리는 사람 머리에 닿을 수 있습니다</span>`;
  }
  return out;
}

// ── 공전 카메라 ─────────────────────────────────────────────
// A-Frame 1.3 에는 orbit 이 없다. 작품을 가운데 두고 도는 게 맞는 장면이라
// look-controls 대신 직접 만든다.
const UP = new THREE.Vector3(0, 1, 0);

AFRAME.registerComponent("orbit", {
  init() {
    this.az = -0.45; this.el_ = 0.22; this.dist = 4.6;
    this.target = new THREE.Vector3(0, 1.5, 0);
    this._m = new THREE.Matrix4();
    const cv = this.el.sceneEl.canvas;
    let down = false, px = 0, py = 0;

    const start = (e) => { down = true; px = e.clientX; py = e.clientY; };
    const move = (e) => {
      if (!down) return;
      this.az -= (e.clientX - px) * 0.006;
      this.el_ = Math.max(-1.25, Math.min(1.15, this.el_ + (e.clientY - py) * 0.005));
      px = e.clientX; py = e.clientY;
    };
    const end = () => { down = false; };
    cv.addEventListener("pointerdown", start);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    cv.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.dist = Math.max(0.9, Math.min(11, this.dist * (1 + e.deltaY * 0.0012)));
    }, { passive: false });

    // 두 손가락 벌리기
    let pinch = 0;
    cv.addEventListener("touchmove", (e) => {
      if (e.touches.length !== 2) return;
      const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                           e.touches[0].clientY - e.touches[1].clientY);
      if (pinch) this.dist = Math.max(0.9, Math.min(11, this.dist * pinch / d));
      pinch = d;
    }, { passive: true });
    cv.addEventListener("touchend", () => { pinch = 0; });

    this.goVisitor = () => {
      // 관객 눈높이. 좌대에서 한 걸음 떨어져 서서 올려다보는 자리.
      // 공전 카메라는 목표를 중심으로 구면을 도는 방식이라, 눈높이를 그대로 넣으려면
      // 원하는 카메라 위치에서 거꾸로 거리와 고도를 푼다.
      const EYE = 1.55;
      const r = state.pedD / 2 + 0.9;
      const ty = state.pedH + (GEOMETRY.ceilingHeight + GEOMETRY.ringMinY) / 2;
      const dy = EYE - ty;                       // 올려다보므로 음수
      this.target.set(0, ty, 0);
      this.dist = Math.hypot(r, dy);
      this.el_ = Math.asin(dy / this.dist);
    };
    this.goWhole = () => {
      // 바닥부터 천장까지 한 화면에 들어오는 거리. fov 42 기준.
      this.dist = Math.max(4.4, state.floorCeiling / (2 * Math.tan(21 * Math.PI / 180)) + 0.9);
      this.el_ = 0.12;
      this.target.set(0, state.floorCeiling * 0.52, 0);
    };
    this.goWhole();
  },
  tick() {
    const o = this.el.object3D;
    const ce = Math.cos(this.el_), se = Math.sin(this.el_);
    o.position.set(
      this.target.x + Math.sin(this.az) * ce * this.dist,
      this.target.y + se * this.dist,
      this.target.z + Math.cos(this.az) * ce * this.dist);

    // ⚠️ Object3D.lookAt 은 카메라와 조명일 때만 -Z 를 목표로 돌린다. 여기 object3D 는
    //    카메라를 자식으로 가진 Group 이라 +Z 가 목표를 보게 되어 정반대를 본다.
    //    Matrix4.lookAt 은 카메라 규약(-Z)이라 이걸로 직접 만든다.
    this._m.lookAt(o.position, this.target, UP);
    o.quaternion.setFromRotationMatrix(this._m);
  },
});

AFRAME.registerComponent("venue", {
  init() {
    const o = this.el.object3D;
    o.add(room, root, floorGroup, chandelierPivot, cubeGroup);
    chandelierPivot.add(chandelier.root);
    figure = buildFigure();
    o.add(figure);

    Promise.all([
      fetch("./shadows.json").then((r) => r.json()).catch(() => null),
      fetch("./grids.json").then((r) => r.json()).catch(() => ({})),
      loadBlobs().catch(() => {}),
    ]).then(([sd, gr]) => {
      grids = gr || {};
      if (sd) {
        shadowData = sd;
        const f = floorTexture(sd);
        const p = new THREE.Mesh(new THREE.PlaneGeometry(f.size, f.size),
          new THREE.MeshBasicMaterial({ map: f.tex, transparent: true, opacity: 0.8 }));
        p.rotation.x = -Math.PI / 2;
        p.position.y = 0.003;
        floorGroup.add(p);

        // 상판과 옆면은 좌대에 붙으므로 좌대가 다시 세워질 때 같이 올린다
        topDecal = topTexture(sd);
        sideDecal = sideTexture(sd);
      }
      apply();
      // 며칠치가 쌓인 모습. 하루 약 18개로 잡는다.
      chandelier.seed(state.layers * state.perLayer, mockData, state.layers);
      applyGlass();
      report();
      document.getElementById("load").style.display = "none";

      // 올라가는 장면도 보이게 가끔 하나씩 띄운다. 전시에서는 관객이 그릴 때마다다.
      // 오늘 날짜로 넣으면 안 된다. 미리보기는 "며칠째"를 고른 상태라 그날 링에 걸려야 한다.
      const startMs = new Date(SCHEDULE.startISO).getTime();
      setInterval(() => {
        const d = mockData();
        d.t = startMs + (state.layers - 1) * SCHEDULE.periodHours * 3600000
            + SCHEDULE.periodHours * 3600000 * 0.4;
        chandelier.add(d);
        applyGlass();
        report();
      }, 9000);
    });
  },
  tick(t) { chandelier.update(t / 1000); },
});

// ── 조작 패널 ───────────────────────────────────────────────
const bind = (id, key, fmt) => {
  const el = document.getElementById(id);
  const out = document.getElementById(id + "-v");
  const sync = () => {
    state[key] = parseFloat(el.value);
    out.textContent = fmt(state[key]);
    apply();
  };
  el.addEventListener("input", sync);
  el.value = state[key];
  out.textContent = fmt(state[key]);
};

document.getElementById("app").innerHTML = `
  <a-scene background="color: #141922" vr-mode-ui="enabled: false"
           renderer="antialias: true; logarithmicDepthBuffer: true; colorManagement: true">
    <a-entity light="type: hemisphere; color: #ffffff; groundColor: #9a9b98; intensity: 0.85"></a-entity>
    <a-entity light="type: directional; intensity: 0.5" position="2 5 3"></a-entity>
    <a-entity light="type: point; intensity: 0.45; distance: 7" position="0 2.9 0.6"></a-entity>
    <a-entity id="cam" camera="fov: 42" orbit></a-entity>
    <a-entity venue></a-entity>
  </a-scene>`;

const scene = document.querySelector("a-scene");
scene.addEventListener("loaded", () => {
  bind("ped", "pedD", (v) => v.toFixed(2) + "m");
  bind("pedh", "pedH", (v) => v.toFixed(2) + "m");
  bind("ceil", "floorCeiling", (v) => v.toFixed(2) + "m");
  // 높이와 크기는 슬라이더가 없다. config.js 의 CUBE_PLAN 이 정하고
  // 여기서는 몇 개까지 걸지만 본다.
  bind("cuben", "cubeN", (v) => (v ? `${v}개` : "없음"));

  // 겹 수와 겹당 개수. 둘 다 바뀌면 쌓인 모습이 달라지므로 비우고 다시 채운다.
  const refill = () => {
    while (chandelier.items.length) chandelier.evictOne();
    chandelier.rings.forEach((r) => {
      if (!r.mesh) return;
      chandelier.root.remove(r.mesh);
      r.mesh.geometry.dispose();
    });
    chandelier.rings.clear();
    chandelier.resetLayers();      // 링을 비웠으니 겹 커서도 되돌린다
    apply();
    chandelier.seed(state.layers * state.perLayer, mockData, state.layers);
    applyGlass();
    report();
  };

  [["layer", "layers", (v) => `${v}겹`], ["per", "perLayer", (v) => `겹당 ${v}개`]]
    .forEach(([id, key, fmt]) => {
      const el = document.getElementById(id);
      if (id === "layer") el.max = SCHEDULE.maxRings;
      el.value = state[key];
      document.getElementById(id + "-v").textContent = fmt(state[key]);
      el.addEventListener("input", () => {
        state[key] = parseInt(el.value, 10);
        document.getElementById(id + "-v").textContent = fmt(state[key]);
        refill();
      });
    });

  const gl = document.getElementById("glass");
  gl.value = state.glass;
  document.getElementById("glass-v").textContent = state.glass.toFixed(2);
  gl.addEventListener("input", () => {
    state.glass = parseFloat(gl.value);
    document.getElementById("glass-v").textContent = state.glass.toFixed(2);
    applyGlass();
    report();
  });

  const cam = document.querySelector("#cam").components.orbit;
  document.getElementById("v-whole").addEventListener("click", () => cam.goWhole());
  document.getElementById("v-eye").addEventListener("click", () => cam.goVisitor());
  document.getElementById("v-shadow").addEventListener("click", () => {
    state.shadows = !state.shadows;
    buildPedestal();   // 상판과 옆면 시트지는 좌대에 붙어 있다
    layout();
  });
});
