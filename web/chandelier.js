// 크리스탈의 수명 주기. 천 중앙에서 태어나 나선으로 올라가 뼈대에 매달린다.
// 생김새는 crystal.js 가 담당하고 여기서는 움직임과 성능 단계만 다룬다.

import { GEOMETRY, MOTION, MAX_CRYSTALS, QUALITY, SCHEDULE } from "./config.js?v=1101p";
import { makeCrystal, setQuality, disposeCrystal } from "./crystal.js?v=1101p";
import { glassTime } from "./glass_material.js?v=1101p";

const smoothstep = (p) => p * p * (3 - 2 * p);
const lerp = (a, b, t) => a + (b - a) * t;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));   // 슬롯이 겹치지 않게 퍼지는 각
const HOUR_MS = 3600000;

// 한 겹이 머무는 시간. SCHEDULE.periodHours 로 정한다.
// 하루 한 겹이던 것을 시간 단위로 바꿨다. 센서부를 가져가 시연하는 기간이
// 이틀이라, 하루 단위면 겹이 둘밖에 안 생긴다.
export const periodMs = () => Math.max(0.0167, SCHEDULE.periodHours) * HOUR_MS;

// startISO 는 "2026-11-01" 처럼 날짜만 올 수도, 시간대까지 붙어 올 수도 있다.
// 시간대가 없으면 자정을 붙이고 관객 폰의 시간대를 따른다.
const START_MS = new Date(
  /[T ]/.test(SCHEDULE.startISO) ? SCHEDULE.startISO : `${SCHEDULE.startISO}T00:00:00`
).getTime();

// 시작 시각에서 몇 번째 주기인지. 겹 번호가 아니다.
// 겹은 주기가 아니라 그려진 것으로 넘어가므로 Chandelier.nextLayer 가 따로 센다.
function periodIndexOf(t) {
  if (!Number.isFinite(START_MS)) return 0;
  return Math.floor(((t ?? Date.now()) - START_MS) / periodMs());
}

// 그 겹에 몇 개가 걸렸는지로 링 반지름이 나온다.
// n 개가 서로 겹치지 않고 한 바퀴에 놓이려면 둘레가 n * 폭 이상이어야 한다.
//   2*pi*r >= n * crystalSpan
// 그래서 많이 그려진 시간대의 겹이 넓어진다. 임의로 키운 값이 아니라
// 크리스탈이 서로 파고들지 않는 최소 반지름이다.
export function ringRadius(n) {
  const r = n * GEOMETRY.crystalSpan / (2 * Math.PI);
  return Math.max(GEOMETRY.ringRadiusMin, Math.min(GEOMETRY.ringRadiusMax, r));
}

// 링 간격. 지정이 없으면 천장에서 바닥 한계까지를 전시 일수로 나눈다.
// 이렇게 해야 천장 높이를 실측값으로 바꿔도 마지막 날 링이 바닥에 겹치지 않는다.
export let RING_GAP = computeGap();

function computeGap() {
  return GEOMETRY.ringGap ||
    (GEOMETRY.ceilingHeight - GEOMETRY.ringMinY) / Math.max(1, SCHEDULE.maxRings - 1);
}

// 현장에서 천장 높이를 고치면 이걸 부른다. 링과 크리스탈 목표 높이를 다시 잡는다.
export function recomputeHeights(chandelier) {
  RING_GAP = computeGap();
  if (!chandelier) return;
  for (const [layer, r] of chandelier.rings) {
    if (r.mesh) r.mesh.position.y = ringY(layer);
  }
  for (const it of chandelier.items) it.targetY = ringY(it.layer);
}

// 몇 번째 겹이 어느 높이에 있는지. 첫 겹이 천장이고 주기마다 한 겹씩 내려온다.
export function ringY(layer) {
  return Math.max(GEOMETRY.ringMinY, GEOMETRY.ceilingHeight - layer * RING_GAP);
}

// 기록이 그려진 지 몇 초 됐는지. 시각이 없거나 미래면 0 (지금 태어난 것).
// ⚠️ 폰 시계가 틀어져 있으면 음수가 나온다. 그래서 0 으로 자른다.
function riseAgeOf(data) {
  const t = data && data.t;
  if (!Number.isFinite(t)) return 0;
  return Math.max(0, (Date.now() - t) / 1000);
}

// 올라가다 멈추는 지점. 0~1, 없으면 1 (끝까지 올라간다).
function holdOf(data) {
  const h = data && data.hold;
  if (!Number.isFinite(h)) return 1;
  return Math.max(0.05, Math.min(1, h));
}

export class Chandelier {
  constructor() {
    this.root = new THREE.Object3D();
    this.items = [];
    this.rings = new Map();     // layer -> { mesh, used, radius }
    this.layer = 0;             // 지금 받고 있는 겹
    this.period = -Infinity;    // 그 겹을 열었던 주기 번호
    this.ringMat = null;
    this.level = "high";
    this.cap = QUALITY.highEndCrystals;
    this._now = 0;          // update() 가 넘겨주는 장면 시각. add() 도 이걸 쓴다.
    this._frames = 0;
    this._since = performance.now();
    this._start = performance.now();
    this._bad = 0;
    this._good = 0;

    // 탭이 가려지면 브라우저가 rAF 를 조여서 fps 가 바닥으로 측정된다.
    // 그대로 두면 관객이 전화를 받았다 돌아온 뒤 품질이 low 로 내려앉은 채 남는다.
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", () => this.resetFpsWindow());
    }
  }

  // 겹은 시계가 아니라 쌓인 것으로 넘어간다.
  // 주기가 바뀌어도 지금 겹이 비어 있으면 새 겹을 열지 않고 그대로 이어 쓴다.
  // 닫힌 시간처럼 아무도 그리지 않은 주기가 빈 테로 남으면 샹들리에 중간이
  // 끊어져 보이고, 내려올 높이만 축낸다. 그래서 겹 번호는 "몇 시간째"가 아니라
  // "그려진 것이 있는 몇 번째 주기"다. 다섯 시간을 건너뛰어도 한 겹만 내려온다.
  nextLayer(t) {
    const p = periodIndexOf(t);
    if (!Number.isFinite(p)) return this.layer;
    if (p > this.period) {
      const cur = this.rings.get(this.layer);
      if (cur && cur.used > 0) {
        this.layer = Math.min(SCHEDULE.maxRings - 1, this.layer + 1);
      }
      this.period = p;
    }
    return this.layer;
  }

  // 처음부터 다시 쌓을 때 부른다. 링을 비웠으면 커서도 같이 되돌려야 한다.
  resetLayers() {
    this.layer = 0;
    this.period = -Infinity;
  }

  // 그 겹의 링을 준비한다. 없으면 만든다.
  // ⚠️ 겹마다 반지름이 다르므로 지오메트리를 나눠 쓸 수 없다. 겹당 하나씩 갖는다.
  ensureRing(layer) {
    let r = this.rings.get(layer);
    if (r) return r;

    if (!this.ringMat) {
      this.ringMat = new THREE.MeshStandardMaterial({
        color: 0xbcd0dd, roughness: 0.35, metalness: 0.2,
        transparent: true, opacity: 0.5,
      });
    }
    r = { mesh: null, used: 0, radius: ringRadius(0) };
    this.rings.set(layer, r);
    this.reshapeRing(layer, r);
    return r;
  }

  // 개수가 늘면 링이 넓어진다. 토러스를 다시 만들고 옛것은 버린다.
  // 크리스탈 하나가 더 걸릴 때마다 반지름이 span/2pi 만큼(약 1.4cm) 커진다.
  reshapeRing(layer, r) {
    if (!SCHEDULE.showRings) return;
    const geo = new THREE.TorusGeometry(r.radius, GEOMETRY.ringTube, 6, 48);
    geo.rotateX(Math.PI / 2);
    if (r.mesh) {
      r.mesh.geometry.dispose();
      r.mesh.geometry = geo;
    } else {
      r.mesh = new THREE.Mesh(geo, this.ringMat);
      this.root.add(r.mesh);
    }
    r.mesh.position.y = ringY(layer);
  }

  // 상한을 넘으면 **가장 많이 찬 링**에서 가장 오래된 것을 버린다.
  // 전체에서 가장 오래된 것을 버리면 1일차 링부터 통째로 비어서
  // 3주 누적이라는 작품의 전제가 깨진다. 이렇게 하면 모든 날이 남는다.
  evictOne() {
    if (!this.items.length) return;

    const perLayer = new Map();
    for (const it of this.items) perLayer.set(it.layer, (perLayer.get(it.layer) || 0) + 1);

    let fullest = null, most = -1;
    for (const [layer, n] of perLayer) {
      if (n > most) { most = n; fullest = layer; }
    }

    const i = this.items.findIndex((it) => it.layer === fullest);
    if (i < 0) return;
    const [old] = this.items.splice(i, 1);   // 그 링에서 가장 오래된 것
    this.root.remove(old.mesh);
    disposeCrystal(old.mesh);
    // ring.used 는 줄이지 않는다. 황금각이 계속 사이를 메우므로 각이 겹치지 않는다.
  }

  add(data) {
    if (this.items.length >= Math.min(this.cap, MAX_CRYSTALS)) this.evictOne();

    const mesh = makeCrystal(data, this.level);
    setQuality(mesh, this.level);
    mesh.position.set(0, GEOMETRY.spawnY, 0);
    this.root.add(mesh);

    const layer = this.nextLayer(data.t);
    const ring = this.ensureRing(layer);
    mesh.userData.layer = layer;   // 검출 오버레이가 몇 번째 겹인지 읽는다

    // 하나 더 걸렸으니 링이 그만큼 넓어진다.
    // ⚠️ used 는 줄이지 않는다. evictOne 은 그리기 예산 때문에 버리는 것이지
    //    그 시간에 그려진 개수가 줄어든 게 아니다. 링 굵기는 기록을 따른다.
    // ⚠️ 올라가다 멈추는 것(hold)은 세지 않는다. 그 링에 영영 안 걸린다.
    //    세면 아무도 안 걸린 자리만큼 링이 넓어져서, 겹별 개수로 읽히는
    //    옆모습이 틀어진다.
    if (holdOf(data) >= 1) {
      ring.used++;
      const nr = ringRadius(ring.used);
      if (nr !== ring.radius) {
        ring.radius = nr;
        this.reshapeRing(layer, ring);
      }
    }

    this.items.push({
      mesh,
      data,
      layer,
      ring,
      targetY: ringY(layer),
      slotAngle: (ring.used - 1) * GOLDEN,
      phase: Math.random() * Math.PI * 2,

      // 🔴 지금 태어난 것으로 두면 안 된다. Firebase 에 쌓인 것을 받아 올 때
      //    관객이 열 때마다 전부가 처음부터 다시 60초를 올라간다. 매번.
      //    기록에 적힌 시각을 보고 그만큼 태어난 때를 되돌린다. 그러면 오래된
      //    것은 이미 매달린 채로 뜨고, 방금 그린 것만 올라간다.
      //    라이브 시연 중에 들어온 관객이 보는 그림도 이게 맞다.
      born: this._now - riseAgeOf(data),

      attached: false,
    });
    return mesh;
  }

  // 미리보기에서 바로 샹들리에가 차 보이도록 과거에 태어난 것처럼 만든다.
  // 겹마다 개수를 다르게 준다. 한산한 시간과 붐비는 시간이 번갈아 오는 모습이고,
  // 그래야 개수에 따라 링이 넓어지는 게 눈에 보인다.
  seed(count, data, layers = 1) {
    // 겹은 그려진 주기에만 생기므로 빈 겹이 없다. 닫힌 시간을 따로 뺄 필요가 없고,
    // 겹마다 개수만 다르다. 한산한 시간과 붐비는 시간이 번갈아 오는 모습이다.
    // ⚠️ 커서는 여기서 되돌리지 않는다. seed 는 더하는 함수이고,
    //    링을 비운 쪽이 resetLayers 도 같이 불러야 둘이 어긋나지 않는다.
    const w = [];
    let sum = 0;
    for (let L = 0; L < layers; L++) {
      const v = 0.22 + 0.78 * (1 + Math.sin(L * 0.9 + 0.6)) / 2;
      w.push(v);
      sum += v;
    }
    if (sum <= 0) return;

    let i = 0;
    for (let L = 0; L < layers && i < count; L++) {
      const n = Math.max(1, Math.round(count * w[L] / sum));
      for (let k = 0; k < n && i < count; k++, i++) {
        const d = data();
        d.t = START_MS + L * periodMs() + periodMs() * 0.4;
        this.add(d);
        const it = this.items[this.items.length - 1];
        // 이미 다 올라가 매달린 상태로 둔다. riseSeconds 안쪽으로 흩으면 먼저 넣은
        // 것부터 아직 올라가는 중이라 첫 겹이 비어 보인다. 쌓인 모습을 보려는
        // 자리이므로 전부 도착시키고, 올라가는 장면은 실제 피드가 만든다.
        it.born = this._now - MOTION.riseSeconds * (1.05 + i * 0.03);
      }
    }
  }

  update(now) {
    this._now = now;
    glassTime.value = now;
    for (const it of this.items) {
      const age = now - it.born;
      // hold 가 있으면 그 지점에서 선다. 올라가다 멈춘 조각이다.
      // 무인 기간에 "지금도 올라가는 중" 으로 보이게 하려고 몇 개를 세워 둔다.
      const cap = holdOf(it.data);
      const p = Math.min(cap, age / MOTION.riseSeconds);

      if (p < 1) {
        const e = smoothstep(p);
        // 올라가면서 감긴 나선을 풀어 슬롯 각으로 도착한다.
        const angle = it.slotAngle + (1 - p) * MOTION.spiralTurns * Math.PI * 2;
        const radius = lerp(0, it.ring.radius, e)
                     + MOTION.spiralRadius * Math.sin(p * Math.PI) * 0.6;
        it.mesh.position.set(
          Math.cos(angle) * radius,
          lerp(GEOMETRY.spawnY, it.targetY, e),
          Math.sin(angle) * radius,
        );
      } else {
        if (!it.attached) it.attached = true;   // hold 가 있으면 여기 안 온다
        // 매달린 뒤 살짝 흔들린다.
        const s = Math.sin((now * Math.PI * 2) / MOTION.swaySeconds + it.phase);
        // 링이 넓어지면 이미 매달린 것들도 따라 나간다. 그래야 한 겹으로 보인다.
        const R = it.ring.radius;
        it.mesh.position.set(
          Math.cos(it.slotAngle) * R + s * MOTION.swayAmplitude,
          it.targetY,
          Math.sin(it.slotAngle) * R + s * MOTION.swayAmplitude * 0.6,
        );
        it.mesh.rotation.y += 0.0015;
      }
    }
    this._measure();
  }

  // 평균 fps 로 단계를 조절한다.
  // 카메라 초기화와 마커 탐색 워밍업 때 fps 가 바닥을 치므로 warmupSeconds 동안은
  // 재지 않고, 한 구간만 나쁜 것으로는 내리지 않는다. 회복하면 되올린다.
  // 측정 구간을 처음부터 다시 잰다. 돌아온 직후의 들쭉날쭉한 프레임을 버린다.
  resetFpsWindow() {
    this._frames = 0;
    this._since = performance.now();
    this._start = performance.now();   // 워밍업도 다시 준다
    this._bad = 0;
    this._good = 0;
  }

  _measure() {
    // 가려진 동안의 프레임은 세지 않는다
    if (typeof document !== "undefined" && document.hidden) {
      this._frames = 0;
      this._since = performance.now();
      return;
    }
    this._frames++;
    const now = performance.now();
    if (now - this._start < QUALITY.warmupSeconds * 1000) {
      this._frames = 0;
      this._since = now;
      return;
    }

    const elapsed = (now - this._since) / 1000;
    if (elapsed < QUALITY.fpsSampleSeconds) return;

    const fps = this._frames / elapsed;
    this._frames = 0;
    this._since = now;
    this.fps = fps;

    if (fps < QUALITY.fpsDownshiftBelow) {
      this._bad++; this._good = 0;
    } else if (fps > QUALITY.fpsUpshiftAbove) {
      this._good++; this._bad = 0;
    } else {
      this._bad = 0; this._good = 0;
    }

    if (this._bad >= 2) { this._bad = 0; this._shift(-1); }
    else if (this._good >= 2) { this._good = 0; this._shift(+1); }
  }

  _shift(dir) {
    const order = ["low", "mid", "high"];
    const i = order.indexOf(this.level);
    const next = order[i + dir];
    if (!next) return;

    this.level = next;
    this.cap = next === "high" ? QUALITY.highEndCrystals
             : next === "mid"  ? QUALITY.midEndCrystals
             :                   QUALITY.lowEndCrystals;
    this.items.forEach((it) => setQuality(it.mesh, next));
    while (this.items.length > Math.min(this.cap, MAX_CRYSTALS)) this.evictOne();
    console.log(`[chandelier] fps ${this.fps.toFixed(1)} 이라 ${next} 단계로 ${dir < 0 ? "내렸" : "올렸"}습니다`);
  }
}
