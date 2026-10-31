// 여러 마커에서 하나의 월드 좌표계를 만든다.
//
// AR.js 의 <a-marker> 는 자기 자식만 마커 위에 올려준다. 그런데 이 작품은
// 어느 마커가 보이든 같은 공간에 같은 샹들리에가 있어야 하므로, 마커를 포즈
// 측정에만 쓰고 장면은 마커 밖의 #world 에 두고 그 포즈를 매 프레임 갱신한다.
// 보이는 마커가 둘 이상이면 평균을 낸다 (문서의 "2개 이상 보이면 평균").

import { MARKERS, ANCHOR, AR_SOURCE } from "./config.js";
import { solveMarkerAll, solvePlane, CV_TO_THREE } from "./pose.js";
import { Gyro } from "./gyro.js";

const DEG = Math.PI / 180;

// ?rot=0..3 으로 돌림을 직접 못박는다. 자동으로 고른 것이 틀릴 때 쓴다.
const ROT_Q = parseInt(new URLSearchParams(location.search).get("rot"), 10);
const ROT_FIXED = Number.isFinite(ROT_Q) ? (ROT_Q & 3) : null;

// 마커 로컬 좌표계에서 우리 월드 좌표계로 가는 변환을 미리 만들어 역행렬을 둔다.
// AR.js 에서 마커 자식은 마커 면 위에 서고 +Y 가 면 바깥을 향한다.
//
// tilt 가 면이 어느 쪽을 보는지다 (도).
//   0    위를 본다. 바닥에 눕힌 마커
//   180  아래를 본다. 천장에 붙인 마커 (flip: true 와 같다)
//   90   옆을 본다. 매단 큐브의 옆면
// YXZ 라 R = Ry(yaw) * Rx(tilt) * Rz(roll) 이고, 먼저 면을 세운 다음
// 월드 Y 축으로 yaw 만큼 돌린다. roll 은 그 면에서 어느 쪽이 위인지다.
function buildInverse(m) {
  const T = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const tilt = m.tilt !== undefined ? m.tilt : (m.flip ? 180 : 0);
  const e = new THREE.Euler(tilt * DEG, (m.yaw || 0) * DEG, (m.roll || 0) * DEG, "YXZ");
  q.setFromEuler(e);
  T.compose(new THREE.Vector3(...m.pos), q, new THREE.Vector3(1, 1, 1));
  return T.invert();
}

// ── 포즈를 직접 푼다 ──────────────────────────────────────────
//
// 🔴 AR.js 가 넣어 주는 마커 행렬을 쓰지 않는다. 검출(번호와 모서리)은 믿을
//    만한데 포즈만 모서리와 모순되기 때문이다. 현장에서 모서리를 80px 로
//    제대로 집으면서 거리를 43m 라고 했다. 모서리와 마커 크기와 초점거리가
//    있으면 포즈는 우리가 푼다 (pose.js, 합성 그림으로 오차 0.00% 확인).
//
//    마커 로컬 축 규약이 둘이 다르다.
//      pose.js   면이 XY 평면, +Z 가 면 바깥
//      AR.js     면이 XZ 평면, +Y 가 면 바깥 (buildInverse 가 쓰는 규약)
//    그래서 B 로 갈아탄다.  marker_local = B * pose_local
//      B = [1 0 0 / 0 0 1 / 0 -1 0]   (회전이므로 역은 전치)
const B_INV = new THREE.Matrix4().set(
  1, 0, 0, 0,
  0, 0, 1, 0,
  0, -1, 0, 0,
  0, 0, 0, 1,
);
// OpenCV 카메라( +Y 아래, +Z 앞 )를 three.js 카메라( +Y 위, -Z 앞 )로.
const CV_FIX = new THREE.Matrix4().makeScale(
  CV_TO_THREE[0], CV_TO_THREE[1], CV_TO_THREE[2]);

function controllerOf(el) {
  const sys = el.sceneEl && el.sceneEl.systems && el.sceneEl.systems.arjs;
  const ctx = sys && sys._arSession && sys._arSession.arContext;
  return (ctx && ctx.arController) || null;
}

AFRAME.registerComponent("world-anchor", {
  init() {
    this.slots = MARKERS.map((m) => ({
      conf: m,
      inv: buildInverse(m),
      el: document.querySelector(`#marker-${m.value}`),
      seen: false,
    }));
    this.slots.forEach((s) => {
      if (!s.el) return;
      s.el.addEventListener("markerFound", () => { s.seen = true; });
      s.el.addEventListener("markerLost", () => { s.seen = false; });
    });

    // 천장 높이를 고치면 천장 마커의 변환이 달라진다. 다시 만들 수 있게 열어둔다.
    this.rebuildInverses = () => {
      this.slots.forEach((s) => { s.inv = buildInverse(s.conf); });
      this.started = false;
    };

    // 마커를 놓친 사이 기기가 얼마나 돌았는지로 월드를 되돌린다
    this.gyro = ANCHOR.gyroHold ? new Gyro() : null;
    this.holdDevice = new THREE.Quaternion();   // 놓친 순간의 기기 방향
    this.holdPos = new THREE.Vector3();         // 놓친 순간의 월드 포즈
    this.holdQuat = new THREE.Quaternion();
    this.holding = false;
    this.gyroDelta = new THREE.Quaternion();
    this.heldSeconds = 0;       // 마커 없이 자이로만으로 버틴 시간

    this.pos = new THREE.Vector3();
    this.quat = new THREE.Quaternion();
    this.started = false;
    this.visibleCount = 0;
    this.seenValues = [];
    this.spread = 0;
    this.rejected = false;   // 둘만 보이는데 서로 어긋나 버린 프레임인가

    this.tmpM = new THREE.Matrix4();
    this.tmpQ = new THREE.Quaternion();
    this.byValue = new Map(this.slots.map((k) => [k.conf.value, k]));
    this.rot = 0;                 // 정사각형의 네 돌림 중 고른 것
    this.rotBy = new Map();       // 묶음(바닥/큐브/천장)마다 따로 기억한다
    this.tmpS = new THREE.Vector3();
  },

  // 검출기가 집은 모서리로 마커마다 포즈를 푼다. 번호 -> 카메라 좌표 행렬.
  solvePoses() {
    const out = new Map();
    const ctrl = this.ctrl || (this.ctrl = controllerOf(this.el));
    if (!ctrl || !ctrl.canvas || !ctrl.getMarkerNum) return out;
    const w = ctrl.canvas.width, h = ctrl.canvas.height;
    if (!w || !h) return out;
    // 초점거리는 긴 변의 화각에서 낸다. app.js 가 만드는 카메라 파라미터와 같은 식.
    const f = (Math.max(w, h) / 2) / Math.tan(AR_SOURCE.fov * Math.PI / 360);
    const K = { fx: f, fy: f, cx: w / 2, cy: h / 2 };
    let n = 0;
    try { n = ctrl.getMarkerNum(); } catch (e) { return out; }
    // 1단계. 마커마다 네 돌림의 포즈를 모두 만든다.
    const cand = [];                 // [{slot, mats:[Matrix4 x4]}]
    for (let i = 0; i < n; i++) {
      let mk;
      try { mk = ctrl.getMarker(i); } catch (e) { continue; }
      if (!mk || mk.idMatrix < 0 || !mk.vertex) continue;
      const slot = this.byValue.get(mk.idMatrix);
      if (!slot) continue;                          // 작품이 안 쓰는 번호
      const all = solveMarkerAll(mk.vertex, slot.conf.size, K);
      if (!all || !(all[0].err < 6)) continue;      // 너무 안 맞으면 버린다
      const mats = all.map((g) => {
        const P = new THREE.Matrix4().set(
          g.R[0], g.R[1], g.R[2], g.t[0],
          g.R[3], g.R[4], g.R[5], g.t[1],
          g.R[6], g.R[7], g.R[8], g.t[2],
          0, 0, 0, 1,
        );
        return new THREE.Matrix4().multiplyMatrices(CV_FIX, P).multiply(B_INV);
      });
      cand.push({ slot, mats, vertex: mk.vertex });
    }
    if (!cand.length) return out;

    // 2단계. 🔴 돌림을 고른다.
    //   정사각형이라 마커 혼자서는 네 방향을 구분 못 한다. 그런데 같은 묶음에
    //   속한 마커들은 설치물에 함께 고정되어 있으므로, 맞는 돌림이면 모두가
    //   같은 월드 원점을 가리킨다. 네 가지를 다 넣어 보고 가장 모이는 것을 고른다.
    //
    //   ⚠️ 반드시 묶음 안에서만 비교해야 한다. 바닥 넷과 매단 큐브는 서로 다른
    //      물체라 섞어 놓고 비교하면 네 방향 어느 것도 모이지 않는다. 그러면
    //      엉뚱한 값이 뽑혀 월드가 통째로 돌아간다.
    //   ⚠️ 한 장만 보이는 묶음은 가릴 수 없다. 그 묶음에서 전에 고른 것을 쓰고,
    //      그것도 없으면 가장 최근에 확정된 값을 쓴다. 0 으로 두면 안 된다.
    const byKind = new Map();
    for (const c of cand) {
      const k = c.slot.conf.kind || "floor";
      if (!byKind.has(k)) byKind.set(k, []);
      byKind.get(k).push(c);
    }
    const spreadOf = (list, rot) => {
      const ps = list.map((c) =>
        new THREE.Vector3().setFromMatrixPosition(
          new THREE.Matrix4().multiplyMatrices(c.mats[rot], c.slot.inv)));
      let sp = 0;
      for (let i = 0; i < ps.length; i++)
        for (let j = i + 1; j < ps.length; j++)
          sp = Math.max(sp, ps[i].distanceTo(ps[j]));
      return sp;
    };
    // 🔴 한 평면에 놓인 마커들은 통째로 푼다.
    //
    //    사각형 한 장은 정면에 가까울수록 서로 다른 두 자세가 똑같이 잘
    //    들어맞는다 (평면 표적의 고질적인 모호성). 그래서 프레임마다 둘
    //    사이를 오가고, 월드의 중심이 기울어지며 흔들린다. 장당 풀어 평균내도
    //    각자 흔들리므로 안 없어진다.
    //
    //    바닥 네 장은 1m 에 걸쳐 흩어져 있다. 열여섯 점을 한 호모그래피로
    //    풀면 자세가 하나로 결정된다. 덤으로 돌림도 저절로 정해진다. 번호마다
    //    자리가 다르므로 90도 돌린 대응은 아예 안 맞기 때문이다.
    const flat = byKind.get("floor");
    if (flat && flat.length >= 2) {
      const w = this.solveFloorPlane(flat, K);
      if (w) { out.set("__world_floor", w); this.rotSpread = 0; }
    }

    for (const [kind, list] of byKind) {
      let rot = ROT_FIXED !== null ? ROT_FIXED
        : (this.rotBy.has(kind) ? this.rotBy.get(kind) : (this.rot | 0));
      if (ROT_FIXED === null && list.length >= 2) {
        let best = Infinity, bestR = rot;
        for (let r = 0; r < 4; r++) {
          const sp = spreadOf(list, r);
          if (sp < best) { best = sp; bestR = r; }
        }
        rot = bestR;
        if (best < 0.20) { this.rotBy.set(kind, rot); this.rot = rot; }
        this.rotSpread = best;
      }
      for (const c of list) out.set(c.slot.conf.value, c.mats[rot]);
    }
    return out;
  },

  // 바닥 마커들의 모서리를 한 평면(월드 y=0)에 모아 한 번에 푼다.
  // 반환: 월드 -> 카메라 (three.js 규약) 행렬
  solveFloorPlane(list, K) {
    // 한 장의 네 모서리를 (돌림 r, 뒤집기 f) 로 짝지어 평면 점으로 만든다.
    const ptsOf = (c, r, f) => {
      const m = c.slot.conf;
      const hh = m.size / 2;
      const L = [[-hh, -hh], [hh, -hh], [hh, hh], [-hh, hh]];
      const yaw = (m.yaw || 0) * DEG;
      const cs = Math.cos(yaw), sn = Math.sin(yaw);
      const out = [];
      for (let i = 0; i < 4; i++) {
        // pose.js 의 평면 좌표 (a, b) 는 마커 로컬 (a, 0, -b) 다.
        const a = L[i][0], b = L[i][1];
        const X = m.pos[0] + a * cs + (-b) * sn;
        const Z = m.pos[2] - a * sn + (-b) * cs;
        const j = f ? (r + 3 - i) % 4 : (r + i) % 4;
        out.push({ X, Y: Z, u: c.vertex[j][0], v: c.vertex[j][1] });
      }
      return out;
    };
    const tryAll = (rots, flip) => {
      const pts = [];
      for (let k = 0; k < list.length; k++) pts.push(...ptsOf(list[k], rots[k], flip));
      return solvePlane(pts, K);
    };

    let best = null, bestRots = null, bestFlip = 0;
    for (let flip = 0; flip < 2; flip++) {
      for (let r = 0; r < 4; r++) {
        const rots = new Array(list.length).fill(r);
        const p = tryAll(rots, flip);
        if (p && (!best || p.err < best.err)) { best = p; bestRots = rots; bestFlip = flip; }
      }
    }
    // 🔴 네 장이 같은 방향으로 붙어 있지 않을 수 있다. 종이를 손으로 붙이면
    //    한 장쯤 90도 돌아가기 쉽다. 그러면 모두 같은 돌림으로는 절대 안 맞는다.
    //    한 장씩 돌려 보며 더 잘 맞는 쪽으로 옮긴다. 몇 번만 돌면 수렴한다.
    if (best && bestRots) {
      for (let pass = 0; pass < 3; pass++) {
        let moved = false;
        for (let k = 0; k < list.length; k++) {
          for (let r = 0; r < 4; r++) {
            if (r === bestRots[k]) continue;
            const t = bestRots.slice(); t[k] = r;
            const p = tryAll(t, bestFlip);
            if (p && p.err < best.err - 1e-6) { best = p; bestRots = t; moved = true; }
          }
        }
        if (!moved) break;
      }
    }
    // 실패해도 어긋남은 남긴다. 안 남기면 왜 안 되는지 볼 수가 없다.
    this.floorErr = best ? best.err : null;
    this.floorN = list.length;
    this.floorRots = bestRots ? bestRots.join("") : "";
    if (!best || !(best.err < 8)) return null;

    // 평면 기저 e1=+X, e2=+Z, e3=e1 x e2 = -Y 이므로
    // 월드 회전의 열은 x:r1, y:-r3, z:r2 다.
    const R = best.R, t = best.t;
    const M = new THREE.Matrix4().set(
      R[0], -R[2], R[1], t[0],
      R[3], -R[5], R[4], t[1],
      R[6], -R[8], R[7], t[2],
      0, 0, 0, 1,
    );
    return new THREE.Matrix4().multiplyMatrices(CV_FIX, M);
  },

  tick(time, dt) {
    const accP = new THREE.Vector3();
    let accQ = null;
    let used = 0;

    // 마커는 붙어 있는 물체별로 묶는다. 바닥 4장은 설치물에 고정된 강체이고,
    // 매단 큐브와 천장 마커는 각자 줄에 달려 따로 흔들린다. 섞으면 서로 다른
    // 위치를 주장해 월드가 떨린다. 보이는 것 중 가장 믿을 만한 묶음 하나만 쓴다.
    // ⚠️ 큐브 여럿은 같은 낚싯줄에 꿴 하나의 강체로 본다. 줄을 둘로 나눠
    //    매달면 여기서 줄마다 갈라야 한다.
    // 검출기에서 바로 읽어 우리가 푼다. 결과는 마커 번호 -> 카메라 좌표 행렬.
    this.poses = this.solvePoses();
    const visible = this.poses.size
      ? this.slots.filter((s) => this.poses.has(s.conf.value))
      : this.slots.filter((s) => s.el && s.seen && s.el.object3D.visible);
    const by = (k) => visible.filter((s) => (s.conf.kind || "floor") === k);
    const group = ANCHOR.preferFloor
      ? (by("floor").length ? by("floor") : by("cube").length ? by("cube") : visible)
      : visible;
    this.source = group.length ? (group[0].conf.kind || "floor") : null;
    // 지금 무엇이 보이는지. 바닥 네 장만 깔았는데 큐브 번호가 뜨면 오검출이다.
    this.seenValues = visible.map((s) => s.conf.value);
    this.usingCeiling = this.source === "ceiling";

    // 🔴 바닥을 통째로 푼 결과가 있으면 그것 하나만 쓴다. 장당 풀어 평균내는
    //    것보다 훨씬 안정적이다 (열여섯 점이 1m 에 걸쳐 있어 자세가 하나로
    //    결정된다). 이때는 어긋남을 잴 것도 없다.
    const direct = this.poses && this.poses.get("__world_floor");
    if (direct && this.source === "floor") {
      this.holding = false;
      this.heldSeconds = 0;
      const p = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
      direct.decompose(p, q, sc);
      this.spread = 0;
      this.rejected = false;
      this.visibleCount = group.length;
      this.applyPose(p, q);
      return;
    }

    // 마커마다 믿을 만한 정도를 매긴다. AR.js 는 비스듬히 보이는 평면에서
    // 포즈 오차가 크므로, 정면으로 크게 보이는 마커에 비중을 더 준다.
    const cands = [];
    for (const s of group) {
      let mw = this.poses && this.poses.get(s.conf.value);
      if (!mw) {
        if (!s.el) continue;
        s.el.object3D.updateMatrixWorld();
        mw = s.el.object3D.matrixWorld;
      }
      this.tmpM.multiplyMatrices(mw, s.inv);
      const p = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
      this.tmpM.decompose(p, q, sc);

      // 카메라가 원점이고 마커가 움직인다. 마커 위치가 곧 시선 벡터다.
      const mp = new THREE.Vector3().setFromMatrixPosition(mw);
      const dist = Math.max(0.05, mp.length());
      const nrm = new THREE.Vector3(0, 1, 0)
        .applyQuaternion(new THREE.Quaternion().setFromRotationMatrix(mw));
      const facing = Math.abs(nrm.dot(mp.clone().normalize()));
      const w = Math.pow(facing, ANCHOR.facingPower) / (dist * dist);
      cands.push({ p, q, w });
    }

    // 셋 이상이면 중앙값에서 크게 벗어난 것을 버린다. 조형물에 반쯤 가려
    // 잘못 잡힌 마커 하나가 월드를 끌고 가는 것을 막는다.
    //
    // 🔴 둘만 보일 때는 중앙값이 없어 누가 바깥값인지 가릴 수 없다. 그런데
    //    둘 중 하나가 오검출이면 두 마커가 아주 다른 자리를 주장하므로, 그
    //    어긋남 자체로 알아챌 수 있다. 어긋남이 rejectMeters 를 넘으면 평균을
    //    내지 않고 그 프레임을 버린다 (마커를 놓친 것과 같이 처리한다).
    //    좌대 위의 QR 처럼 "검은 사각 테두리 안에 패턴" 인 그림은 없는 마커
    //    번호로 읽힐 수 있고, 그게 쓰는 번호와 겹치면 월드가 그쪽으로 끌려간다.
    //    (markers/qr_test.html 로 실측: 검은 QR 은 44가지 거리 중 22가지에서
    //     유령 번호를 만들고, 그중 하나는 바닥 마커 63 이었다)
    let use = cands;
    if (cands.length >= 3) {
      const med = new THREE.Vector3();
      for (const a of ["x", "y", "z"]) {
        const v = cands.map((c) => c.p[a]).sort((x, y) => x - y);
        med[a] = v[Math.floor(v.length / 2)];
      }
      const kept = cands.filter((c) => c.p.distanceTo(med) <= ANCHOR.outlierMeters);
      if (kept.length) use = kept;
    }

    // 🔴 마커들이 서로 얼마나 다른 자리를 주장하는가. 이게 흔들림의 원인이다.
    //    실제 배치가 config 와 다르면 마커마다 월드 원점이 따로 나오고,
    //    폰을 움직여 보이는 마커가 바뀔 때마다 평균이 튄다.
    //    잘 맞으면 2~3cm, 배치가 틀리면 수십 cm 가 나온다.
    this.spread = 0;
    for (let i = 0; i < cands.length; i++)
      for (let j = i + 1; j < cands.length; j++)
        this.spread = Math.max(this.spread, cands[i].p.distanceTo(cands[j].p));

    // 둘만 보이고 서로 너무 다른 자리를 주장하면 믿지 않는다.
    if (use.length === 2 && this.spread > ANCHOR.rejectMeters) {
      this.rejected = true;
      use = [];
    } else {
      this.rejected = false;
    }

    use.sort((a, b) => b.w - a.w);
    let accW = 0;
    for (const c of use) {
      if (used >= ANCHOR.maxMarkers) break;
      accW += c.w;
      accP.addScaledVector(c.p, c.w);
      if (!accQ) {
        accQ = c.q.clone();
      } else {
        if (accQ.dot(c.q) < 0) c.q.set(-c.q.x, -c.q.y, -c.q.z, -c.q.w);
        accQ.slerp(c.q, c.w / accW);
      }
      used++;
    }

    this.visibleCount = used;
    const obj = this.el.object3D;

    if (!used) {
      obj.visible = this.started;
      if (!this.started) return;
      this.heldSeconds += (dt || 16) / 1000;

      // 마커를 놓쳤다. 처음 놓친 순간의 기기 방향과 월드 포즈를 적어 둔다.
      if (!this.holding) {
        this.holding = true;
        this.holdPos.copy(this.pos);
        this.holdQuat.copy(this.quat);
        if (this.gyro && this.gyro.active) this.holdDevice.copy(this.gyro.q);
        else this.holding = this.gyro ? false : true;   // 센서가 없으면 그냥 멈춰 둔다
      }

      if (this.holding && this.gyro && this.gyro.active) {
        // 땅에 고정된 점의 카메라 좌표는 qNow^-1 * qHold 만큼 돌아간다.
        // 그만큼 월드에 먹여야 샹들리에가 실제 공간에 머문다.
        this.gyroDelta.copy(this.gyro.q).invert().multiply(this.holdDevice);
        obj.position.copy(this.holdPos).applyQuaternion(this.gyroDelta);
        obj.quaternion.copy(this.gyroDelta).multiply(this.holdQuat);
      }
      return;
    }
    this.holding = false;
    this.heldSeconds = 0;

    accP.multiplyScalar(1 / accW);
    this.applyPose(accP, accQ);
  },

  // 새로 잰 포즈를 화면에 먹인다. 통짜 풀이와 장별 평균이 같은 길을 쓴다.
  applyPose(p, q) {
    const obj = this.el.object3D;
    obj.visible = true;
    if (!this.started) {
      this.pos.copy(p);
      this.quat.copy(q);
      this.started = true;
    } else if (this.pos.distanceTo(p) > ANCHOR.snapMeters) {
      // 사방에서 보는 작품이라 관객이 좌대를 돌며 마커를 놓쳤다 다시 잡는다.
      // 그 사이 걸어간 거리는 자이로가 모르므로 다시 잡은 포즈가 크게 다를 수
      // 있다. 이때 저역 필터로 따라가면 샹들리에가 공중을 가로질러 미끄러져
      // 온다. 한 번에 끊어서 맞추는 쪽이 덜 어색하다.
      this.pos.copy(p);
      this.quat.copy(q);
    } else {
      this.pos.lerp(p, ANCHOR.smooth);
      this.quat.slerp(q, ANCHOR.smooth);
    }
    obj.position.copy(this.pos);
    obj.quaternion.copy(this.quat);
  },
});
