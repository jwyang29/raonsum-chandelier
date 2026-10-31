// 크리스탈의 생김새.
//
// 형태는 Blender 에서 미리 구운 blobs.json 에서 고른다. 관객 폰에서
// 마칭큐브를 돌리지 않으려는 것이다. 크리스탈이 120개까지 쌓이는데
// 매번 생성하면 오래된 폰이 버티지 못한다.
//
// 같은 변형끼리는 BufferGeometry 를 공유한다. 재질만 크리스탈마다 따로 둔다.
// ⚠️ 그래서 크리스탈을 버릴 때 geometry 를 dispose 하면 안 된다.

import { MAPPING, FORM, TINTS, GLASS } from "./config.js?v=1101p";
import { makeGlass } from "./glass_material.js?v=1101p";

const lerp = (a, b, t) => a + (b - a) * t;
const clamp01 = (v) => Math.max(0, Math.min(1, v));

let LIB = null;          // { arc: [geo...], loop: [...], ribbon: [...] }

export async function loadBlobs(url = "./blobs.json") {
  if (LIB) return LIB;
  const data = await (await fetch(url)).json();
  LIB = {};
  for (const v of data.variants) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(v.verts, 3));
    g.setIndex(v.index);
    g.computeVertexNormals();
    (LIB[v.kind] = LIB[v.kind] || []).push(g);
  }
  console.log(`[crystal] 형태 ${data.variants.length}개 불러옴`,
              Object.entries(LIB).map(([k, a]) => `${k} ${a.length}`).join(", "));
  return LIB;
}

// 획의 기하가 크리스탈의 종류를 고른다. 임의로 고르지 않는다.
function pickKind(d) {
  if ((d.wind ?? 0) > FORM.windToLoop) return "loop";
  return (d.elong ?? 0.5) > FORM.elongToArc ? "arc" : "ribbon";
}

function makeMaterial(d, level) {
  const [oMin, oMax] = MAPPING.opacityFromSpeed;
  const opacity = lerp(oMin, oMax, clamp01(d.speed ?? 0.5));
  const idx = Math.floor(Math.abs(d.dir ?? 0) / Math.PI * TINTS.length) % TINTS.length;

  if (level === "low") {
    // 셰이더까지 버거운 폰. 가장 싼 길로 간다.
    return new THREE.MeshBasicMaterial({
      color: TINTS[idx], transparent: true, opacity: Math.min(1, opacity + 0.25),
    });
  }
  return makeGlass({
    tint: TINTS[idx],
    opacity,
    irid: GLASS.irid * (level === "mid" ? 0.6 : 1.0),
    phase: ((d.curl ?? 0) + 1) * 0.5 + (d.n ?? 0) * 0.017,
    quality: level === "mid" ? 0 : 1,
  });
}

export function makeCrystal(data, level = "high") {
  const kind = pickKind(data);
  const pool = (LIB && LIB[kind]) || null;

  let geo;
  if (pool && pool.length) {
    // 같은 획이면 같은 변형이 나오도록 데이터에서 고른다
    const h = Math.abs(Math.round((data.t ?? 0) / 7 + (data.n ?? 0) * 13));
    geo = pool[h % pool.length];
  } else {
    // 라이브러리가 아직 안 왔을 때만 쓰는 임시 도형
    geo = new THREE.OctahedronGeometry(0.5, 1);
    geo.userData.temporary = true;
  }

  const mesh = new THREE.Mesh(geo, makeMaterial(data, level));

  const [sMin, sMax] = MAPPING.sizeFromPress;
  const [tMin, tMax] = MAPPING.stretchFromElong;
  const [wMin, wMax] = MAPPING.twistFromCurl;

  const size = lerp(sMin, sMax, clamp01(data.press ?? 0.5));
  const stretch = lerp(tMin, tMax, clamp01(data.elong ?? 0.5));
  const twist = lerp(wMin, wMax, clamp01(Math.abs(data.curl ?? 0))) * Math.sign(data.curl || 1);

  // 구운 형태는 가장 긴 변이 1 로 정규화되어 있다
  mesh.scale.set(size, size * stretch, size);
  mesh.rotation.set(0, data.dir ?? 0, twist);

  mesh.userData.data = data;
  return mesh;
}

export function setQuality(mesh, level) {
  const old = mesh.material;
  mesh.material = makeMaterial(mesh.userData.data || {}, level);
  old.dispose();
}

// 공유 지오메트리는 버리지 않는다. 임시 도형만 버린다.
export function disposeCrystal(mesh) {
  mesh.material.dispose();
  if (mesh.geometry.userData.temporary) mesh.geometry.dispose();
}
