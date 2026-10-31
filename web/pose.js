// =============================================================
//  마커 네 모서리에서 포즈를 직접 푼다
//
//  🔴 왜 직접 푸는가
//
//  ARToolKit 의 검출은 믿을 만하다. 번호도 모서리도 정확하다. 현장에서
//  모서리를 80px 로 제대로 집는 것을 확인했다. 그런데 같은 함수가 내놓는
//  포즈는 그 모서리와 모순된다. 80px 이면 1.5m 인데 43m 라고 한다. 카메라
//  파라미터, 캔버스 크기, 마커 폭, 그림 복사 경로를 전부 맞춰 놓아도 그렇고,
//  시험대에서는 거리를 바꿔도 값이 한 자리에 얼어붙는다.
//
//  모서리와 마커 크기와 초점거리를 알면 포즈는 우리가 풀 수 있다. 남의
//  라이브러리 속을 더듬는 대신 아는 수학을 쓴다. 정답을 아는 합성 그림으로
//  검증할 수 있다는 것도 크다 (markers/solve_test.html).
//
//  🔴 덤으로 얻는 것
//
//  바닥 마커 네 장은 한 평면 위에 있다. 그래서 장당 따로 풀지 않고 네 장의
//  모서리 열여섯 점을 한 번에 풀 수 있다. 점이 많을수록 해가 안정적이라
//  장당 풀어 평균내는 지금 방식보다 흔들림이 적다.
//
//  규약: 영상 좌표는 왼쪽 위가 (0,0) 이고 v 는 아래로 간다 (OpenCV 와 같다).
//        포즈도 OpenCV 규약으로 낸다. +X 오른쪽, +Y 아래, +Z 앞.
//        three.js 로 넘길 때 Y 와 Z 를 뒤집는다 (아래 CV_TO_THREE).
// =============================================================

// ── 작은 선형대수 ─────────────────────────────────────────────

// n x n 선형계를 부분 피벗 가우스 소거로 푼다. 못 풀면 null.
function solveLinear(A, b, n) {
  const M = [];
  for (let i = 0; i < n; i++) M.push(A[i].slice().concat(b[i]));
  for (let col = 0; col < n; col++) {
    let piv = col;
    for (let r = col + 1; r < n; r++)
      if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r;
    if (Math.abs(M[piv][col]) < 1e-12) return null;       // 특이행렬
    if (piv !== col) { const t = M[piv]; M[piv] = M[col]; M[col] = t; }
    const d = M[col][col];
    for (let c = col; c <= n; c++) M[col][c] /= d;
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const f = M[r][col];
      if (!f) continue;
      for (let c = col; c <= n; c++) M[r][c] -= f * M[col][c];
    }
  }
  return M.map((row) => row[n]);
}

// 점들을 중심이 원점, 평균 거리가 sqrt(2) 가 되게 옮긴다.
// 안 하면 좌표가 수백 단위라 8x8 계수행렬의 조건수가 나빠져 해가 흔들린다.
function normalize(pts, kx, ky) {
  let mx = 0, my = 0;
  for (const p of pts) { mx += p[kx]; my += p[ky]; }
  mx /= pts.length; my /= pts.length;
  let d = 0;
  for (const p of pts) d += Math.hypot(p[kx] - mx, p[ky] - my);
  d /= pts.length;
  const s = d > 1e-9 ? Math.SQRT2 / d : 1;
  return { s, mx, my, apply: (x, y) => [(x - mx) * s, (y - my) * s] };
}

// ── 평면에서 영상으로 가는 호모그래피 ────────────────────────
//
// pts: [{X, Y, u, v}] 네 점 이상. (X, Y) 는 평면 위 좌표, (u, v) 는 영상 픽셀.
// h33 = 1 로 두고 8개 미지수를 최소제곱으로 푼다. 평면이 카메라 중심을
// 지나지 않는 한 h33 은 0 이 아니므로 이렇게 둬도 된다.
export function homography(pts) {
  if (!pts || pts.length < 4) return null;
  const np = normalize(pts, "X", "Y");
  const ni = normalize(pts, "u", "v");

  // 정규방정식 (A^T A) h = A^T b 를 쌓는다. 점이 넷이면 정확해, 더 많으면 최소제곱.
  const ATA = Array.from({ length: 8 }, () => new Array(8).fill(0));
  const ATb = new Array(8).fill(0);
  const add = (row, rhs) => {
    for (let i = 0; i < 8; i++) {
      ATb[i] += row[i] * rhs;
      for (let j = 0; j < 8; j++) ATA[i][j] += row[i] * row[j];
    }
  };
  for (const p of pts) {
    const [X, Y] = np.apply(p.X, p.Y);
    const [u, v] = ni.apply(p.u, p.v);
    add([X, Y, 1, 0, 0, 0, -u * X, -u * Y], u);
    add([0, 0, 0, X, Y, 1, -v * X, -v * Y], v);
  }
  const h = solveLinear(ATA, ATb, 8);
  if (!h) return null;
  const Hn = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];

  // 정규화를 되돌린다.  H = Ti^-1 * Hn * Tp
  const Tp = [[np.s, 0, -np.s * np.mx], [0, np.s, -np.s * np.my], [0, 0, 1]];
  const TiInv = [[1 / ni.s, 0, ni.mx], [0, 1 / ni.s, ni.my], [0, 0, 1]];
  const mul = (A, B) => {
    const C = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
      let s = 0;
      for (let k = 0; k < 3; k++) s += A[i][k] * B[k][j];
      C[i][j] = s;
    }
    return C;
  };
  return mul(TiInv, mul(Hn, Tp));
}

// 호모그래피로 점을 옮겨 보고 영상 좌표와 얼마나 어긋나는지 잰다 (픽셀).
export function reprojectionError(H, pts) {
  let sum = 0;
  for (const p of pts) {
    const w = H[2][0] * p.X + H[2][1] * p.Y + H[2][2];
    if (Math.abs(w) < 1e-12) return Infinity;
    const u = (H[0][0] * p.X + H[0][1] * p.Y + H[0][2]) / w;
    const v = (H[1][0] * p.X + H[1][1] * p.Y + H[1][2]) / w;
    sum += Math.hypot(u - p.u, v - p.v);
  }
  return sum / pts.length;
}

// ── 호모그래피에서 평면의 포즈를 되돌린다 ────────────────────
//
// K^-1 H 의 두 열이 회전의 1열, 2열이고 세 열이 평행이동이다. 다만 호모그래피는
// 배율이 자유로우므로 두 열의 길이가 1 이 되게 맞춘다. 두 열이 정확히 직교하지는
// 않으므로 그람슈미트로 바로잡는다.
export function poseFromHomography(H, fx, fy, cx, cy) {
  if (!H) return null;
  // M = K^-1 H
  const M = [
    [(H[0][0] - cx * H[2][0]) / fx, (H[0][1] - cx * H[2][1]) / fx, (H[0][2] - cx * H[2][2]) / fx],
    [(H[1][0] - cy * H[2][0]) / fy, (H[1][1] - cy * H[2][1]) / fy, (H[1][2] - cy * H[2][2]) / fy],
    [H[2][0], H[2][1], H[2][2]],
  ];
  const col = (j) => [M[0][j], M[1][j], M[2][j]];
  const n1 = Math.hypot(...col(0)), n2 = Math.hypot(...col(1));
  if (!(n1 > 1e-12) || !(n2 > 1e-12)) return null;
  let lam = 2 / (n1 + n2);

  let r1 = col(0).map((v) => v * lam);
  let r2 = col(1).map((v) => v * lam);
  let t  = col(2).map((v) => v * lam);

  // 마커는 카메라 앞에 있다. tz 가 음수면 배율의 부호를 뒤집는다.
  if (t[2] < 0) { r1 = r1.map((v) => -v); r2 = r2.map((v) => -v); t = t.map((v) => -v); }

  // 그람슈미트로 직교화
  const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
  const sub = (a, b, k) => [a[0]-k*b[0], a[1]-k*b[1], a[2]-k*b[2]];
  const unit = (a) => { const n = Math.hypot(...a); return n > 1e-12 ? a.map(v=>v/n) : null; };
  const e1 = unit(r1);
  if (!e1) return null;
  const e2 = unit(sub(r2, e1, dot(r2, e1)));
  if (!e2) return null;
  const e3 = [e1[1]*e2[2] - e1[2]*e2[1], e1[2]*e2[0] - e1[0]*e2[2], e1[0]*e2[1] - e1[1]*e2[0]];

  // 열이 e1, e2, e3 인 회전행렬 (행 우선 3x3)
  return {
    R: [e1[0], e2[0], e3[0],
        e1[1], e2[1], e3[1],
        e1[2], e2[2], e3[2]],
    t,
  };
}

// ── 평면 위 점들에서 바로 포즈를 푼다 ────────────────────────
export function solvePlane(pts, K) {
  const H = homography(pts);
  if (!H) return null;
  const pose = poseFromHomography(H, K.fx, K.fy, K.cx, K.cy);
  if (!pose) return null;
  pose.err = reprojectionError(H, pts);
  return pose;
}

// ── 마커 한 장의 모서리 네 점 ────────────────────────────────
//
// ⚠️ ARToolKit 이 네 모서리를 어느 차례로 주는지, 그리고 영상에서 시계인지
//    반시계인지는 문서로 확정하기 어렵다. 그래서 짐작하지 않는다. 네 가지
//    돌림과 두 가지 방향, 모두 여덟 가지를 넣어 보고 어긋남이 가장 작은 것을
//    고른다. 한 번 고르면 같은 차례가 계속 쓰이므로 비용은 사실상 없다.
const ORDERS = [];
for (let flip = 0; flip < 2; flip++)
  for (let rot = 0; rot < 4; rot++)
    ORDERS.push({ flip, rot });

// 마커 로컬 평면에서의 네 모서리. 반시계.
function localCorners(size) {
  const h = size / 2;
  return [[-h, -h], [h, -h], [h, h], [-h, h]];
}

// vertex: [[u,v] x4], size: 검은 사각형 한 변 (m)
// 반환: { R, t, err, order }  마커 로컬 -> 카메라 (OpenCV 규약)
export function solveMarker(vertex, size, K, hint) {
  if (!vertex || vertex.length !== 4) return null;
  const L = localCorners(size);
  let best = null;
  const list = hint ? [hint, ...ORDERS] : ORDERS;
  for (const o of list) {
    const pts = [];
    for (let i = 0; i < 4; i++) {
      const j = o.flip ? (o.rot + 3 - i) % 4 : (o.rot + i) % 4;
      pts.push({ X: L[i][0], Y: L[i][1], u: vertex[j][0], v: vertex[j][1] });
    }
    const p = solvePlane(pts, K);
    if (!p) continue;
    if (!best || p.err < best.err) { best = p; best.order = o; }
    if (best.err < 0.5) break;        // 충분히 좋으면 더 볼 것 없다
  }
  return best;
}

// OpenCV 카메라 좌표를 three.js 카메라 좌표로. Y 와 Z 를 뒤집는다.
export const CV_TO_THREE = [1, -1, -1];
