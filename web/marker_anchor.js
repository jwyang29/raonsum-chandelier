// 여러 마커에서 하나의 월드 좌표계를 만든다.
//
// AR.js 의 <a-marker> 는 자기 자식만 마커 위에 올려준다. 그런데 이 작품은
// 어느 마커가 보이든 같은 공간에 같은 샹들리에가 있어야 하므로, 마커를 포즈
// 측정에만 쓰고 장면은 마커 밖의 #world 에 두고 그 포즈를 매 프레임 갱신한다.
// 보이는 마커가 둘 이상이면 평균을 낸다 (문서의 "2개 이상 보이면 평균").

import { MARKERS, ANCHOR } from "./config.js";
import { Gyro } from "./gyro.js";

const DEG = Math.PI / 180;

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

    this.tmpM = new THREE.Matrix4();
    this.tmpQ = new THREE.Quaternion();
    this.tmpS = new THREE.Vector3();
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
    const visible = this.slots.filter((s) => s.el && s.seen && s.el.object3D.visible);
    const by = (k) => visible.filter((s) => (s.conf.kind || "floor") === k);
    const group = ANCHOR.preferFloor
      ? (by("floor").length ? by("floor") : by("cube").length ? by("cube") : visible)
      : visible;
    this.source = group.length ? (group[0].conf.kind || "floor") : null;
    // 지금 무엇이 보이는지. 바닥 네 장만 깔았는데 큐브 번호가 뜨면 오검출이다.
    this.seenValues = visible.map((s) => s.conf.value);
    this.usingCeiling = this.source === "ceiling";

    // 마커마다 믿을 만한 정도를 매긴다. AR.js 는 비스듬히 보이는 평면에서
    // 포즈 오차가 크므로, 정면으로 크게 보이는 마커에 비중을 더 준다.
    const cands = [];
    for (const s of group) {
      s.el.object3D.updateMatrixWorld();
      this.tmpM.multiplyMatrices(s.el.object3D.matrixWorld, s.inv);
      const p = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
      this.tmpM.decompose(p, q, sc);

      // AR.js 는 카메라를 원점에 두고 마커를 움직인다. 마커 위치가 곧 시선 벡터다.
      const mp = new THREE.Vector3().setFromMatrixPosition(s.el.object3D.matrixWorld);
      const dist = Math.max(0.05, mp.length());
      const nrm = new THREE.Vector3(0, 1, 0)
        .applyQuaternion(new THREE.Quaternion().setFromRotationMatrix(s.el.object3D.matrixWorld));
      const facing = Math.abs(nrm.dot(mp.clone().normalize()));
      const w = Math.pow(facing, ANCHOR.facingPower) / (dist * dist);
      cands.push({ p, q, w });
    }

    // 셋 이상이면 중앙값에서 크게 벗어난 것을 버린다. 조형물에 반쯤 가려
    // 잘못 잡힌 마커 하나가 월드를 끌고 가는 것을 막는다.
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
    obj.visible = true;

    if (!this.started) {
      this.pos.copy(accP);
      this.quat.copy(accQ);
      this.started = true;
    } else if (this.pos.distanceTo(accP) > ANCHOR.snapMeters) {
      // 사방에서 보는 작품이라 관객이 좌대를 돌며 마커를 놓쳤다 다시 잡는다.
      // 그 사이 걸어간 거리는 자이로가 모르므로 다시 잡은 포즈가 크게 다를 수
      // 있다. 이때 저역 필터로 따라가면 샹들리에가 공중을 가로질러 미끄러져
      // 온다. 한 번에 끊어서 맞추는 쪽이 덜 어색하다.
      this.pos.copy(accP);
      this.quat.copy(accQ);
    } else {
      this.pos.lerp(accP, ANCHOR.smooth);
      this.quat.slerp(accQ, ANCHOR.smooth);
    }
    obj.position.copy(this.pos);
    obj.quaternion.copy(this.quat);
  },
});
