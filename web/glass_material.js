// 크리스탈 유리 질감 셰이더.
//
// three 의 MeshPhysicalMaterial 로는 원하는 느낌이 안 나온다.
//   iridescence 는 r141 부터인데 A-Frame 1.3.0 은 r137 이다
//   transmission 은 화면을 한 번 더 그려서 AR 에서 너무 비싸다
// 그래서 프레넬, 얇은 막 간섭, 가짜 환경 반사, 반짝임을 직접 쓴다.
// 렌더 타깃이 없어서 오래된 폰에서도 가볍다.

import { GLASS } from "./config.js?v=1114b";

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
uniform float uRolloff;   // 1 이면 하이라이트를 부드럽게 눕힌다. 0 이면 예전처럼 잘린다
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

  // ⚠️ uSpecPower, uDispersion, uFlash 도 선언만 되어 있고 식에 안 들어가 있었다.
  //    disperse() 는 함수까지 써 놓고 한 번도 부르지 않았고, 날카로움은
  //    GLASS.specPower(170) 대신 96.0 이 박혀 있었다. alphaCore/alphaRim 때와
  //    같은 종류다. 셋 다 살린다.
  vec3 L1 = normalize((viewMatrix * vec4(0.45, 1.0, 0.35, 0.0)).xyz);

  // 분산. 파장마다 꺾이는 각이 조금씩 달라 반짝임의 가장자리에서 색이 갈라진다.
  // 유리가 유리로 읽히는 건 이것 때문이다. 흰 점 하나로는 플라스틱이 된다.
  // 🔴 분산은 pow 를 셋 쓴다. 한 프레임에 크리스탈 120개가 앞뒤로 겹쳐
  //    그려지는 화면이라 약한 폰에서는 이게 그냥 비용이다. uQuality 로
  //    나눈다. 이 값은 한 번 그리는 동안 모든 픽셀에서 같아서 분기가
  //    갈라지지 않는다. 낮은 단계는 예전과 같은 비용으로 돌아간다.
  vec3 spec;
  vec3 fill = vec3(0.0);
  if (uQuality > 0.5) {
    spec = disperse(R, L1, uSpecPower, uDispersion);
    // 반대쪽에서 넓게 받치는 빛. 날카로움은 주 광원의 1/5 로 둔다.
    // ⚠️ 이건 spec 과 따로 센다. 섞어서 알파에 넣었더니 넓은 쪽까지
    //    불투명해져 몸통이 통째로 허옇게 떴다.
    vec3 L2 = normalize((viewMatrix * vec4(-0.6, 0.3, -0.55, 0.0)).xyz);
    fill = vec3(pow(max(dot(R, L2), 0.0), uSpecPower * 0.2)) * 0.45;
  } else {
    spec = vec3(pow(max(dot(R, L1), 0.0), uSpecPower));
  }

  // 🔴 1 을 넘는 하이라이트는 그냥 흰 덩어리로 잘린다. 제일 밝은 데가
  //    통째로 평평해져서 모양이 사라지고, 분산으로 갈라 놓은 색도 같이
  //    날아간다. 부드럽게 눕혀야 가장 밝은 데에도 결이 남는다.
  //    uRolloff 를 0 으로 두면 예전처럼 잘린다 (되돌리는 길).
  vec3 lit  = spec * uSparkle;
  vec3 litF = fill * uSparkle;
  spec = mix(min(lit,  vec3(1.0)), vec3(1.0) - exp(-lit),  uRolloff);
  vec3 sfill = mix(min(litF, vec3(1.0)), vec3(1.0) - exp(-litF), uRolloff);
  col += spec + sfill;

  // 비스듬히 볼 때 가장자리에서 터지는 섬광. 크리스탈이 돌면서 실루엣이
  // 시선과 스칠 때 한 번씩 번쩍한다.
  // 🔴 fres 로 재면 안 된다. fres 는 uRimPower 로 이미 휘어 있어서 문턱을
  //    높게 잡아도 넓게 번진다. 재 보니 화면 평균 밝기가 11.6 에서 18.1 로
  //    뛰었다. 가장자리가 아니라 몸통이 밝아진 것이다. 실루엣은 ndv 로
  //    직접 재야 한다. 1-ndv 가 1 에 가까운 데가 시선과 스치는 면이다.
  float graze = smoothstep(0.94, 1.0, 1.0 - ndv);
  col += graze * uFlash * mix(vec3(1.0), irid, 0.6);

  // ⚠️ uAlphaCore 와 uAlphaRim 은 선언만 되어 있고 식에 안 들어가 있었다.
  //    config.js 의 GLASS.alphaCore 를 아무리 바꿔도 화면이 안 변하던 이유다.
  float peak = max(max(spec.r, spec.g), spec.b);
  float a = clamp(uOpacity * (uAlphaCore + uAlphaRim * fres)
                  + peak + graze * uFlash * 0.3, 0.0, 1.0);
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
      uRolloff:   { value: GLASS.rolloff },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,        // 겹쳐 보여야 유리 같다
    side: THREE.DoubleSide,   // 뒷면이 비쳐야 두께가 읽힌다
  });
}
