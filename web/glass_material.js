// 크리스탈 유리 질감 셰이더.
//
// three 의 MeshPhysicalMaterial 로는 원하는 느낌이 안 나온다.
//   iridescence 는 r141 부터인데 A-Frame 1.3.0 은 r137 이다
//   transmission 은 화면을 한 번 더 그려서 AR 에서 너무 비싸다
// 그래서 프레넬, 얇은 막 간섭, 가짜 환경 반사, 반짝임을 직접 쓴다.
// 렌더 타깃이 없어서 오래된 폰에서도 가볍다.

import { GLASS } from "./config.js?v=1101p";

export const glassTime = { value: 0 };   // chandelier 가 매 프레임 올린다

// ⚠️ logarithmicDepthBuffer 를 켠 렌더러에서는 ShaderMaterial 도 로그 깊이를 써야 한다.
//    three 의 기본 재질은 gl_FragDepthEXT 에 로그 깊이를 쓰는데, 이 청크를 안 넣으면
//    여기만 선형 깊이를 쓴다. 두 값은 척도가 달라서 뒤에 있는 벽이 깊이 검사를 이기고
//    크리스탈이 통째로 사라진다. AR 에서는 뒤에 3D 물체가 없어서(카메라 영상은 DOM 비디오다)
//    드러나지 않다가, 전시장을 세운 venue.html 에서 드러났다.
const VERT = `
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec3 vN;
varying vec3 vP;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  // 크리스탈은 한 축으로 늘어나 있다. normalMatrix 를 써야 법선이 안 틀어진다.
  vN = normalize(normalMatrix * normal);
  vP = mv.xyz;
  gl_Position = projectionMatrix * mv;
  #include <logdepthbuf_vertex>
}`;

const FRAG = `
#include <common>
#include <logdepthbuf_pars_fragment>
uniform vec3  uTint;
uniform float uOpacity;
uniform float uIrid;      // 무지개빛 정도
uniform float uPhase;     // 크리스탈마다 다른 색으로
uniform float uTime;
uniform float uQuality;   // 1 이면 반짝임 하나 더
uniform float uIridWhite; // 무지개를 흰색에 섞는 비율
uniform float uRimPower;
uniform float uEnvLow;
uniform float uEnvHigh;
uniform float uSparkle;
uniform float uAlphaCore;
uniform float uAlphaRim;
uniform float uSpecPower;
uniform float uDispersion;
uniform float uFlash;
uniform float uAbsorb;    // 두께를 지나며 먹히는 빛. 흰 배경에서 형태가 읽히게 한다
varying vec3 vN;
varying vec3 vP;

// 코사인 팔레트. 얇은 막 간섭의 색 변화를 흉내낸다.
vec3 pal(float t) {
  return 0.5 + 0.5 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67)));
}

// 분산. 파장마다 꺾이는 각이 조금씩 달라서 반짝일 때 색이 갈라진다.
// R 을 아주 조금씩 틀어 세 번 재는 것으로 흉내낸다.
vec3 disperse(vec3 R, vec3 L, float p, float d) {
  vec3 off = normalize(cross(R, L)) * d;
  return vec3(
    pow(max(dot(normalize(R + off), L), 0.0), p),
    pow(max(dot(R, L), 0.0), p),
    pow(max(dot(normalize(R - off), L), 0.0), p)
  );
}

void main() {
  #include <logdepthbuf_fragment>
  vec3 N = normalize(vN);
  if (!gl_FrontFacing) N = -N;        // 뒷면도 보이므로 뒤집어 준다
  vec3 V = normalize(-vP);

  float ndv  = clamp(dot(N, V), 0.0, 1.0);
  float fres = pow(1.0 - ndv, uRimPower);   // 가장자리가 밝고 가운데가 비친다

  vec3 R    = reflect(-V, N);
  vec3 upV  = normalize((viewMatrix * vec4(0.0, 1.0, 0.0, 0.0)).xyz);
  float envY = dot(R, upV) * 0.5 + 0.5;
  // 위는 밝고 아래는 어두운 가짜 환경. 유리가 무언가를 비치는 느낌을 준다.
  vec3 env = mix(vec3(uEnvLow, uEnvLow * 1.07, uEnvLow * 1.24),
                 vec3(uEnvHigh, uEnvHigh, uEnvHigh * 1.02),
                 smoothstep(0.22, 0.95, envY));

  // 레퍼런스는 흰 유리에 무지개가 엷게 도는 쪽이다. 팔레트를 흰색에 섞어 채도를 낮춘다.
  vec3 irid = mix(vec3(1.0, 0.995, 1.0), pal(ndv * 0.9 + uPhase + uTime * 0.012), 1.0 - uIridWhite);
  vec3 base = mix(uTint, irid, uIrid * (0.32 + 0.68 * fres));
  vec3 col  = base * env;

  // 정면으로 볼수록 유리를 더 길게 지나므로 더 먹힌다. 가장자리는 밝게 남는다.
  // 물리적으로도 맞고, 흰 전시장 벽 앞에서 형태가 사라지는 것을 막는 유일한 수단이다.
  // 투명도만 올리면 흰 유리가 더 희어질 뿐이라 대비가 생기지 않는다.
  col *= mix(1.0 - uAbsorb, 1.0, fres);

  vec3 L1 = normalize((viewMatrix * vec4(0.45, 1.0, 0.35, 0.0)).xyz);
  float s1 = pow(max(dot(R, L1), 0.0), 96.0);
  col += vec3(s1) * uSparkle;

  if (uQuality > 0.5) {
    vec3 L2 = normalize((viewMatrix * vec4(-0.6, 0.3, -0.55, 0.0)).xyz);
    col += vec3(pow(max(dot(R, L2), 0.0), 34.0)) * 0.45 * uSparkle;
  }

  // ⚠️ uAlphaCore 와 uAlphaRim 은 선언만 되어 있고 식에 안 들어가 있었다.
  //    config.js 의 GLASS.alphaCore 를 아무리 바꿔도 화면이 안 변하던 이유다.
  float a = clamp(uOpacity * (uAlphaCore + uAlphaRim * fres) + s1 * uSparkle, 0.0, 1.0);
  gl_FragColor = vec4(col, a);
}`;

export function makeGlass({ tint, opacity, irid = 0.85, phase = 0, quality = 1 }) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTint:    { value: new THREE.Color(tint) },
      uOpacity: { value: opacity },
      uIrid:    { value: irid },
      uPhase:   { value: phase },
      uTime:    glassTime,
      uQuality: { value: quality },
      uIridWhite: { value: GLASS.iridWhite },
      uRimPower:  { value: GLASS.rimPower },
      uEnvLow:    { value: GLASS.envLow },
      uEnvHigh:   { value: GLASS.envHigh },
      uSparkle:   { value: GLASS.sparkle },
      uAlphaCore: { value: GLASS.alphaCore },
      uAlphaRim:  { value: GLASS.alphaRim },
      uSpecPower: { value: GLASS.specPower },
      uDispersion:{ value: GLASS.dispersion },
      uFlash:     { value: GLASS.flash },
      uAbsorb:    { value: GLASS.absorb },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,        // 겹쳐 보여야 유리 같다
    side: THREE.DoubleSide,   // 뒷면이 비쳐야 두께가 읽힌다
  });
}
