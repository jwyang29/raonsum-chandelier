// 랜딩 화면 맨 위에서 크리스탈 하나를 돌린다.
//
// 전시에 실제로 쓰이는 형태와 셰이더를 그대로 쓴다. 홍보용으로 따로 만든
// 그림이 아니라 관객이 AR 에서 볼 바로 그것이어야 한다.
//
// ⚠️ THREE 는 vendor/aframe.min.js 가 들고 있는 것을 쓴다. three 를 따로
//    받으면 600KB 가 더 붙는데, 어차피 AR 로 넘어가면 A-Frame 을 받는다.
//    같은 파일을 쓰면 AR 화면이 캐시에서 바로 뜬다.
// ⚠️ 2MB 를 기다리는 동안 글과 목차는 이미 떠 있어야 한다. 그래서 이 모듈은
//    페이지가 다 그려진 뒤에 불린다.

import { loadBlobs, makeCrystal, setQuality, disposeCrystal } from "./crystal.js";
import { glassTime } from "./glass_material.js";
import { mockData } from "./feed.js";

const loadScript = (src) => new Promise((ok, no) => {
  const s = document.createElement("script");
  s.src = src;
  s.onload = ok;
  s.onerror = () => no(new Error(src));
  document.head.appendChild(s);
});

export async function startHero(holder) {
  await loadScript("./vendor/aframe.min.js");
  await loadBlobs().catch(() => {});

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.outputEncoding = THREE.sRGBEncoding;
  holder.appendChild(renderer.domElement);
  renderer.domElement.style.cssText = "display:block;width:100%;height:100%";

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 50);
  camera.position.set(0, 0, 3.0);

  // 크리스탈 셰이더는 환경광을 스스로 흉내내므로 조명이 필요 없다.
  const pivot = new THREE.Object3D();
  scene.add(pivot);

  let mesh = null;
  function reroll() {
    if (mesh) {
      pivot.remove(mesh);
      disposeCrystal(mesh);
    }
    const d = mockData();
    mesh = makeCrystal(d, "high");
    setQuality(mesh, "high");

    // 구운 형태는 가장 긴 변이 1 로 정규화되어 있고 makeCrystal 이 실제 크기
    // (4.5~14cm)로 줄여 놓는다. 화면에서는 크기 차이가 아니라 생김새를 보는
    // 자리이므로 가장 큰 축을 1 로 되돌려 늘 같은 크기로 띄운다.
    const s = mesh.scale;
    const k = 1 / Math.max(s.x, s.y, s.z);
    mesh.scale.multiplyScalar(k);

    // 🔴 유리 셰이더는 카메라 영상 위에서 맞춘 값이다. 뒤가 어두운 전시장
    //    벽이든 여기 검정 바탕이든, 그대로 두면 거의 안 보인다. 유리는 뒤에
    //    있는 것 때문에 보이는 것이라 받칠 게 없으면 사라진다.
    //    히어로에서만 더 진하고 더 반짝이게 올린다. AR 쪽 값은 그대로 둔다.
    mesh.traverse((o) => {
      const u = o.material && o.material.uniforms;
      if (!u) return;
      if (u.uAlphaCore) u.uAlphaCore.value = 0.40;
      if (u.uAbsorb)    u.uAbsorb.value    = 0.30;
      if (u.uEnvLow)    u.uEnvLow.value    = 0.34;
      if (u.uEnvHigh)   u.uEnvHigh.value   = 1.55;
      if (u.uSparkle)   u.uSparkle.value   = 2.3;
      if (u.uIridWhite) u.uIridWhite.value = 0.22;   // 무지개빛이 더 살게
    });

    mesh.position.set(0, 0, 0);
    pivot.add(mesh);
  }
  reroll();
  holder.addEventListener("click", reroll);   // 눌러 보면 다른 조각이 나온다

  function resize() {
    const w = holder.clientWidth || 1;
    const h = holder.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // 세로로 긴 칸에서는 가로 화각이 좁아져 조각이 잘린다. 뒤로 물린다.
    camera.position.z = 3.0 / Math.min(1, Math.max(0.45, camera.aspect));
    camera.updateProjectionMatrix();
  }
  resize();
  new ResizeObserver(resize).observe(holder);

  const t0 = performance.now();
  let running = true;
  // 화면 밖으로 나가면 멈춘다. 폰 배터리를 설명 읽는 동안 태울 이유가 없다.
  new IntersectionObserver(([e]) => { running = e.isIntersecting; })
    .observe(holder);

  renderer.setAnimationLoop(() => {
    if (!running) return;
    const t = (performance.now() - t0) / 1000;
    glassTime.value = t;                      // 셰이더의 무지개빛이 이걸로 흐른다
    pivot.rotation.y = t * 0.42;
    pivot.rotation.x = Math.sin(t * 0.33) * 0.22;
    renderer.render(scene, camera);
  });

  holder.classList.add("ready");
}
