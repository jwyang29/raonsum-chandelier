// 크리스탈을 누르면 기계가 그 선을 어떻게 읽었는지 보여준다.
//
// 보여주는 방식은 물체 검출(YOLO) 출력의 생김새를 빌린다. 화면에 뜬 크리스탈에
// 바운딩 박스를 씌우고 클래스 이름과 확신도, 그리고 판독한 수치를 붙인다.
// 기계가 사람의 선을 읽은 결과를, 기계가 세상을 보는 방식으로 되돌려주는 셈이다.
//
// 느낌 판독(feeling)과 확신도(conf)는 허브의 playground_v24.stroke_feeling 에서 온다.
// ESP32 는 거리값만 보낸다.


// stroke_feeling 이 내는 이름. 그대로 쓰고 옆에 짧은 풀이를 붙인다.
const FEELING_NOTE = {
  fast_hard: "빠르고 세게",
  fast_soft: "빠르고 여리게",
  slow_hard: "느리고 세게",
  slow_soft: "느리고 여리게",
  varied:    "세기가 오르내림",
  neutral:   "판단하기엔 짧음",
  mock:      "가짜 데이터",
};

// 손가락 탭 관용 범위 (CSS px). 애플과 구글이 권하는 최소 터치 영역이 44px 쯤 된다.
const TAP_RADIUS_PX = 44;

const ROWS = [
  ["press", "누른 깊이"],
  ["speed", "빠르기"],
  ["elong", "길쭉함"],
  ["wind",  "맴돈 정도"],
  ["curl",  "비틀림"],
];

export class Detector {
  constructor({ sceneEl, boxEl, labelEl, getMeshes }) {
    this.scene = sceneEl;
    this.box = boxEl;
    this.label = labelEl;
    this.getMeshes = getMeshes;
    this.picked = null;

    this.ray = new THREE.Raycaster();
    this.ndc = new THREE.Vector2();
    this.b3 = new THREE.Box3();
    this.v = new THREE.Vector3();

    const canvas = sceneEl.canvas || sceneEl.querySelector("canvas");
    const onTap = (e) => {
      const t = e.changedTouches ? e.changedTouches[0] : e;
      this.pick(t.clientX, t.clientY);
    };
    if (canvas) {
      canvas.addEventListener("click", onTap);
      canvas.addEventListener("touchend", onTap, { passive: true });
    }
  }

  pick(clientX, clientY) {
    const cam = this.scene.camera;
    if (!cam) return;
    const r = this.scene.canvas.getBoundingClientRect();
    const px = clientX - r.left, py = clientY - r.top;

    this.ndc.set((px / r.width) * 2 - 1, -(py / r.height) * 2 + 1);
    this.ray.setFromCamera(this.ndc, cam);

    const meshes = this.getMeshes();
    const hits = this.ray.intersectObjects(meshes, false);
    if (hits.length) { this.select(hits[0].object); return; }

    // 빗나갔으면 가까운 것을 집어 준다.
    // 크리스탈은 화면에서 수십 px 밖에 안 되고 손가락은 그보다 굵다.
    // 정확히 맞힐 때까지 반복하게 두면 전시에서 아무도 안 누른다.
    this.select(this.nearest(px, py, r, cam));
  }

  nearest(px, py, r, cam) {
    let best = null, bestD = TAP_RADIUS_PX * TAP_RADIUS_PX;
    for (const m of this.getMeshes()) {
      if (!m.parent) continue;
      this.v.setFromMatrixPosition(m.matrixWorld).project(cam);
      if (this.v.z >= 1) continue;                       // 카메라 뒤
      const dx = (this.v.x * 0.5 + 0.5) * r.width - px;
      const dy = (-this.v.y * 0.5 + 0.5) * r.height - py;
      const d = dx * dx + dy * dy;
      if (d < bestD) { bestD = d; best = m; }
    }
    return best;
  }

  select(mesh) {
    this.picked = mesh;
    if (!mesh) { this.hide(); return; }
    this.label.innerHTML = this.describe(mesh.userData.data || {}, mesh.userData.layer);
    this.box.style.display = "block";
    this.label.style.display = "block";
    this.update();
  }

  hide() {
    this.box.style.display = "none";
    this.label.style.display = "none";
  }

  describe(d, layerIndex) {
    const name = d.feeling || "unknown";
    const conf = typeof d.conf === "number" ? d.conf.toFixed(2) : "-";
    const when = d.t ? new Date(d.t) : null;
    // 겹은 시각에서 계산되지 않는다. 빈 주기는 겹을 열지 않으므로
    // 매달 때 정해진 번호를 그대로 읽는다.
    const layer = Number.isFinite(layerIndex) ? layerIndex + 1 : null;
    const hhmm = when
      ? `${String(when.getHours()).padStart(2, "0")}:${String(when.getMinutes()).padStart(2, "0")}`
      : "-";

    const bars = ROWS.map(([k, ko]) => {
      const v = Number(d[k]);
      if (!Number.isFinite(v)) return "";
      const pct = Math.round(Math.abs(v) * 100);
      return `<div class="r"><span>${ko}</span>` +
             `<i><b style="width:${Math.min(100, pct)}%"></b></i>` +
             `<em>${v.toFixed(2)}</em></div>`;
    }).join("");

    return `<div class="cls">${name} <span>${conf}</span></div>` +
           `<div class="note">${FEELING_NOTE[name] || ""}</div>` +
           bars +
           `<div class="meta">${layer ? `${layer}번째 겹` : ""} ${hhmm}` +
           `${Number.isFinite(d.dur) ? `, ${d.dur.toFixed(1)}초` : ""}` +
           `${Number.isFinite(d.n) ? `, 점 ${d.n}개` : ""}</div>`;
  }

  // 크리스탈이 올라가는 동안에도 박스가 따라붙어야 한다. 매 프레임 부른다.
  update() {
    const mesh = this.picked;
    if (!mesh) return;
    if (!mesh.parent) { this.select(null); return; }   // 버려진 크리스탈

    const cam = this.scene.camera;
    const r = this.scene.canvas.getBoundingClientRect();
    this.b3.setFromObject(mesh);

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, front = false;
    for (let i = 0; i < 8; i++) {
      this.v.set(i & 1 ? this.b3.max.x : this.b3.min.x,
                 i & 2 ? this.b3.max.y : this.b3.min.y,
                 i & 4 ? this.b3.max.z : this.b3.min.z);
      this.v.project(cam);
      if (this.v.z < 1) front = true;
      const x = (this.v.x * 0.5 + 0.5) * r.width;
      const y = (-this.v.y * 0.5 + 0.5) * r.height;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
    if (!front) { this.hide(); return; }               // 카메라 뒤로 갔다

    const pad = 6;
    const bx = minX - pad, by = minY - pad;
    const bw = (maxX - minX) + pad * 2, bh = (maxY - minY) + pad * 2;

    this.box.style.display = "block";
    this.box.style.left = `${bx}px`;
    this.box.style.top = `${by}px`;
    this.box.style.width = `${bw}px`;
    this.box.style.height = `${bh}px`;

    // 라벨은 박스 위에 붙이되 화면 밖으로 나가면 아래로 넘긴다
    this.label.style.display = "block";
    const lh = this.label.offsetHeight || 140;
    this.label.style.left = `${Math.max(6, Math.min(bx, r.width - 200))}px`;
    this.label.style.top = by - lh - 4 > 6 ? `${by - lh - 4}px` : `${by + bh + 4}px`;
  }
}
