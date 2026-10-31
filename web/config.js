// =============================================================
//  가상 샹들리에 (Playground 파생작) 설정
//  여기 있는 값만 채우면 나머지 코드는 건드릴 필요가 없습니다.
//  TODO 가 붙은 항목은 실측값이나 계정 정보가 필요한 것입니다.
// =============================================================

// 현장 보정용 URL 덮어쓰기.
//   ?floorceiling=3.4  바닥에서 천장까지 (m). 현장에서 줄자로 재는 값
//   ?ped=0.8       좌대 지름 (m)
//   ?pedh=0.8      바닥에서 좌대 상단면까지 (m)
//   ?ceiling=2.6   좌대 상단면에서 천장까지 (m). floorceiling 대신 직접 넣을 때
//   ?mring=0.3     마커를 놓은 원의 반지름 (m). 비우면 좌대 지름에서 자동
//   ?period=1      링이 한 겹 내려오는 주기 (시간)
//   ?layers=32     겹의 최대 개수
//   ?days=2        시연 날수
//   ?open=11&close=19  전시장 운영 시간 (시)
//   ?rmax=0.6      링이 커질 수 있는 한계 반지름 (m)
// 전시장에서 폰으로 숫자를 바꿔가며 맞춰 보라고 둔 것이다.
// 값이 정해지면 아래 기본값에 적어 넣고 URL 은 떼고 쓴다.
const QS = new URLSearchParams(typeof location === "undefined" ? "" : location.search);

// 현장 보정값은 이 기기에만 남는다. 확정되면 아래 기본값에 적어 넣는다.
export const CAL_KEY = "raonsum.cal";
function stored(key) {
  try {
    const v = JSON.parse(localStorage.getItem(CAL_KEY) || "{}")[key];
    return Number.isFinite(v) ? v : null;
  } catch { return null; }
}

const num = (key, fallback) => {
  const q = parseFloat(QS.get(key));
  if (Number.isFinite(q)) return q;          // URL 이 가장 세다
  const s = stored(key);
  if (s !== null) return s;                  // 그다음이 이 기기에 저장된 보정값
  return fallback;                           // 없으면 코드의 기본값
};

// 바닥에서 천장까지. 현장에서 줄자로 재는 값이 이것이다.
// 코드가 쓰는 높이는 좌대 상단면 기준이라 좌대 높이를 뺀다.
const fc = num("floorceiling", null);
const floorCeiling = Number.isFinite(fc) ? fc : null;

// ?desk=1 : 책상 위 시험용. 샹들리에를 마커 바로 위 30~70cm 에 두어 통째로
// 화면에 들어오게 한다. 실제 전시는 마커에서 1.7~3.1m 위라, 책상에 마커를 놓고
// 폰을 비추면 샹들리에가 화면 한참 위에 있어 아무것도 안 보인다.
// 🔴 비례를 보는 자리가 아니다. 돌아가는지 보는 자리다.
export const DESK = QS.get("desk") === "1";

// 책상 모드 값은 이 기기에 남은 보정값보다 세다. 시험하려고 켠 플래그인데
// 예전에 저장된 천장 높이 때문에 안 먹으면 더 헷갈린다.
// URL 로 직접 준 값만 이보다 세다.
const deskNum = (key, deskValue, fallback) => {
  const q = parseFloat(QS.get(key));
  if (Number.isFinite(q)) return q;
  if (DESK) return deskValue;
  return num(key, fallback);
};

// 마커 반지름을 손으로 못박았는지. 못박으면 좌대 지름을 바꿔도 따라가지 않는다.
const mr = num("mring", null);
const MRING_FIXED = Number.isFinite(mr) ? mr : null;

// =============================================================
//  인식 해상도. 마커를 놓치는 거리를 정한다.
//
//  AR.js 는 카메라 요청 해상도(sourceWidth)와 실제 인식 처리 해상도(canvasWidth)가
//  따로다. canvasWidth 기본값이 640x480 이라 소스만 올리면 다시 줄여서 처리한다.
//  둘 다 올려야 인식 거리가 늘어난다.
//
//  10cm 마커가 3x3 을 읽히려면 화면에서 50px 쯤 돼야 한다. 화각 60도 기준으로
//    640 폭  -> 약 1.1m 까지
//   1280 폭  -> 약 2.2m 까지
//  대신 픽셀이 4배라 처리가 무거워진다. maxDetectionRate 로 초당 인식 횟수를
//  낮춰 상쇄한다. 매 프레임 인식할 필요는 없고 30회면 충분하다.
//  오래된 폰에서 버거우면 960x720 으로 낮춘다.
// =============================================================

// 🔴 카메라에 요청하는 크기(width/height)와 실제로 인식을 돌리는 캔버스
//    크기(canvasW/canvasH)는 반드시 따로 둬야 한다.
//
//    iOS 는 요청한 비율을 "반대 방향으로" 만족시킨다. 1280x960 을 요청하면
//    960x1280 을 주고, 960x1280 을 요청하면 1280x960 을 준다. 그래서 요청
//    크기를 바꿔서 맞추려 하면 폰이 같이 뒤집혀 영원히 안 맞는다.
//
//    안 맞은 채로 두면 AR.js 가 세로 영상을 가로 캔버스에 욱여넣어 정사각형
//    마커가 가로세로비 0.56 의 직사각형이 된다. ARToolKit 이 정사각형을 거기
//    끼워 맞추려다 해가 발산해서 현장에서 월드 원점이 200m 로 나왔다.
//
//    그래서 요청은 그대로 두고, 캔버스만 폰이 실제로 내준 영상 크기에 맞춘다.
//    app.js 가 영상이 뜬 뒤 재서 ?cw= ?ch= 를 붙여 한 번 다시 연다.
export const AR_SOURCE = {
  width:  num("arw", 1280),
  height: num("arh", 960),
  canvasW: num("cw", 0) || null,     // 0 이면 영상 크기를 재서 맞춘다
  canvasH: num("ch", 0) || null,

  // 🔴 렌즈 화각 (긴 변 기준, 도). 이 값이 틀리면 거리가 통째로 틀어진다.
  //    vendor/camera_para.dat 의 55.4 도는 일반 웹캠 값이다. 아이폰 메인은
  //    보통 63~65 도이고, 사파리가 초광각을 고르면 100 도를 넘는다. 그러면
  //    초점거리가 몇 배씩 어긋나 포즈가 발산한다.
  //    현장에서 줄자로 맞춘다. 좌대 중심에서 정확히 1m 떨어져 패널의
  //    "원점까지" 가 1.00 이 되는 값이 그 폰의 화각이다.
  fov: num("fov", 55.4),
  maxDetectionRate: num("arrate", 30),
};

export const FIREBASE = {
  // 🔴 주소 하나만 쓴다. Firebase SDK 를 안 쓰고 Realtime Database 의 REST
  //    스트리밍을 EventSource 로 직접 읽기 때문에 apiKey 도 projectId 도
  //    필요 없다 (feed.js 가 이 값만 읽는다). 웹 앱을 추가할 필요도 없다.
  //
  //    콘솔 > Realtime Database 맨 위에 적힌 주소를 그대로 붙여넣는다.
  //      asia-southeast1 : https://<이름>-default-rtdb.asia-southeast1.firebasedatabase.app
  //      us-central1     : https://<이름>-default-rtdb.firebaseio.com
  //    이 주소는 관객 폰이 직접 읽으므로 공개된다. 그래서 쓰기는 반드시
  //    규칙으로 막아야 한다 (hub/firebase_rules.json).
  databaseURL: "https://facets-between-us-default-rtdb.asia-southeast1.firebasedatabase.app",
};

// 읽을 경로. 허브가 쓰는 경로와 같아야 합니다 (hub/hub_v1.py 의 RTDB_PATH).
export const DB_PATH = "crystals";

// 화면에 유지할 최대 크리스탈 수.
// ⚠️ 한 시간에 한 겹이 되면서 겹이 48개까지 늘었다. 120 으로 두면 겹당 2~3개만
//    남아 넓은 링이 빈 테처럼 보인다. 쌓인다는 전제가 깨지므로 올렸다.
//    무거우면 QUALITY 가 fps 를 보고 알아서 단계를 내린다.
export const MAX_CRYSTALS = num("max", 300);

// =============================================================
//  원형 좌대
//  작품은 둥근 좌대 위에 올라가고 관객은 사방에서 본다.
//  그래서 이 두 값이 나머지 기하를 거의 다 정한다.
//    지름 -> 마커를 놓을 수 있는 반지름
//    높이 -> 천장 높이의 기준면, 그리고 샹들리에가 머리 위로 떠야 하는 높이
// =============================================================

export const PEDESTAL = {
  // 🔴 좌대 지름 (m). 현장 실측값으로.
  // 낮고 넓은 원형 좌대다. 사진으로 어림한 값이라 반드시 재서 고칠 것.
  diameter: num("ped", 1.05),

  // 🔴 바닥에서 좌대 상단면까지 (m).
  // ⚠️ 좌대가 낮으면 천이 낮아진다. 천 높이 = 이 값 + 장치 높이 0.20m 이고,
  //    0.75m 아래로 내려가면 관객이 쪼그려야 손가락으로 그릴 수 있다.
  // 천장 높이를 줄자로 재면 바닥 기준으로 나오는데 코드가 쓰는 높이는 모두
  // 상단면 기준이다. 보정 패널이 이 값만큼 빼서 넘긴다.
  height: num("pedh", 0.32),

  // 마커를 좌대 테두리에서 이만큼 떼어 놓는다. 모서리가 걸쳐 잘리는 것을 막는다.
  rimMargin: 0.02,
};

// =============================================================
//  기하 (단위: 미터). 설치물 실측값으로 바꾸세요.
//  월드 원점 = 천의 중앙, 좌대 상단면.
// =============================================================

export const GEOMETRY = {
  // 바코드 마커 한 변 길이 (검은 테두리 포함, 흰 여백은 뺀다).
  // 🔴 이 값이 틀리면 월드 전체의 크기가 그만큼 틀어진다. AR.js 는 "이만한
  //    마커가 화면에 이만큼 보인다" 로 거리를 푼다. 실제 마커가 적어 놓은 것보다
  //    작으면 더 멀리 있다고 계산해서 샹들리에가 작고 멀게, 그리고 화면 위로
  //    한참 벗어난 자리에 선다.
  //    인쇄 전에 노트북 화면에 띄워 놓고 시험할 때는 자로 검은 사각형을 재서
  //    ?msize=0.062 처럼 넣을 것. 화면의 CSS mm 는 실제 mm 가 아니다.
  markerSize: num("msize", 0.10),

  // 센싱 장치 (알루미늄 프레임 + ESP32 + ToF). 좌대 한가운데에 놓인다.
  // 마커가 이 위로 올라오면 안 되므로 마커 반지름의 안쪽 한계를 정한다.
  deviceSize: 0.40,
  // 실측 22cm. 천은 이 위에 덮인다. 크리스탈이 태어나는 높이가 여기서 나온다.
  deviceHeight: num("devh", 0.22),

  // 장치 위에 씌운 천 한 변 길이. 관객이 누르는 면이다.
  clothSize: 0.33,

  // 마커 네 개를 놓을 원의 반지름 (m). ?mring= 으로 못박지 않으면 좌대 지름에서
  // 자동으로 잡는다 (refreshPedestal).
  // ⚠️ 정사각형 배열을 45도 돌려 천의 네 변 쪽에 하나씩 놓는다. 전과 같은
  //    마커 4장이고 붙이는 방향도 그대로지만, 모서리 쪽에 놓는 전 배치는
  //    대각선이 길어서 둥근 좌대를 많이 잡아먹는다. 장치가 40cm 각이므로
  //    변 쪽으로 돌려도 좌대는 66cm 이상이어야 한다.
  markerRing: 0,

  // 천장 마커 검은 사각형 한 변. 이제 선택이라 A4 한 장에 들어가는 크기로 둔다.
  // 바닥 3.40m 에 달면 관객이 1.6m 뒤까지 읽힌다. 그 바깥은 큐브가 맡는다.
  ceilingMarkerSize: 0.133,

  // 🔴 좌대 상단면에서 매단 천장 뼈대까지의 높이. 현장에서 재야 한다.
  // 줄자로 재면 바닥 기준이 나오므로 ?floorceiling= 으로 넣는 쪽이 편하다.
  // 보정 패널도 바닥 기준으로 받아서 좌대 높이를 빼고 이 값에 넣는다.
  // 링 간격이 이 값에서 자동으로 나오므로 확정되면 여기에 적어 넣을 것.
  // 기본값 3.08 은 바닥에서 천장 3.40m 에 좌대 0.32m 를 뺀 것이다.
  // 좌대 높이를 고치면 이 값도 같이 고쳐야 바닥 기준 높이가 유지된다.
  ceilingHeight: deskNum("ceiling", 0.70, floorCeiling !== null
    ? floorCeiling - PEDESTAL.height
    : 3.08),

  // 크리스탈이 생겨나는 높이 (천 바로 위).
  // 🔴 좌대 상단면이 0 이고 장치가 그 위에 놓이므로, 장치 높이를 더해야
  //    천에서 솟아오른다. 0.02 로 두면 장치 안에서 솟아나 보인다.
  //    refreshPedestal 이 deviceHeight 에서 다시 잡는다.
  spawnY: 0.24,

  // 링 반지름은 고정이 아니라 그 겹에 걸린 개수에서 나온다.
  // 겹치지 않고 한 바퀴에 놓이려면 둘레가 개수 x 폭 이상이어야 한다는 데서 온다.
  //   2*pi*r >= n * crystalSpan
  // 그래서 사람이 많이 그린 시간대의 겹이 넓어지고, 샹들리에 옆모습이 그 기록이 된다.
  // 임의로 키우는 게 아니라 크리스탈이 서로 겹치지 않는 최소 반지름이다.
  crystalSpan:   num("cspan", 0.085),   // 크리스탈 하나가 링 위에서 차지하는 폭 (m)
  ringRadiusMin: num("rmin", 0.10),    // 한두 개만 걸렸을 때
  ringRadiusMax: num("rmax", 0.60),    // 아무리 많아도 여기서 멈춘다

  // 일별 링. 하루에 하나씩 아래로 생긴다.
  // 첫날 링은 천장(ceilingHeight)에 있는 실제 뼈대이고, 그 아래는 전부 가상이다.
  // 링 사이 수직 간격 (m). null 이면 천장 높이와 전시 일수에서 자동으로 구한다.
  // 손으로 넣으면 전시 후반 링이 바닥 한계에 겹쳐 쌓이기 쉬우니 null 을 권한다.
  // 겹 사이 간격 (m). 0 이면 천장과 맨 아래 링 사이를 maxRings 로 나눠 쓴다.
  // ?gap= 나 setcal --gap 으로 직접 준다. 크게 주면 샹들리에가 아래로 길어진다.
  ringGap: num("gap", 0) || null,

  // 바닥에서 샹들리에 맨 아래까지 띄울 높이 (m).
  // 사방에서 보는 작품이라 관객이 좌대를 돌며 팔 길이 안으로 들어온다.
  // 마지막 날 링이 눈높이에 걸리면 크리스탈이 얼굴을 통과해 깨져 보인다.
  // 좌대가 높아지면 상단면 기준 ringMinY 는 그만큼 낮아진다.
  headroom: deskNum("headroom", 0.32, 2.05),
  ringMinY: 0,        // headroom 과 좌대 높이에서 아래에서 채운다

  ringTube: 0.004,    // 가상 링의 두께 (m)
};

// =============================================================
//  좌대에서 따라 나오는 값들
//  좌대 지름과 높이를 고치면 이걸 다시 부른다 (보정 패널이 부른다).
// =============================================================

export function refreshPedestal(report = false) {
  // 🔴 검은 사각형이 아니라 인쇄물 한 변으로 잰다. 흰 여백까지가 종이다.
  //    검은 사각형(10cm)으로 재면 반지름 0.45 가 나오는데, 그러면 15cm 종이의
  //    바깥 모서리가 좌대 테두리를 5.3mm 넘어간다. 둥근 좌대라 모서리가 뜨고
  //    종이가 들린다. 여백까지 넣어 재면 0.42 다.
  const s = GEOMETRY.markerSize * 1.5;
  const half = s / 2;

  // 마커를 천의 네 변 쪽에 축과 나란히 하나씩 둔다.
  //   바깥 한계: 중심에서 가장 먼 모서리 sqrt((R+s/2)^2 + (s/2)^2) 가 테두리 안
  //   안쪽 한계: 안쪽 변 R-s/2 가 천을 밟지 않아야 한다
  const pedR = PEDESTAL.diameter / 2 - PEDESTAL.rimMargin;
  const outer = Math.sqrt(Math.max(0, pedR * pedR - half * half)) - half;
  const inner = GEOMETRY.deviceSize / 2 + half + 0.005;

  // 테두리에 가까울수록 좋다. 마커 사이가 멀어져 각도가 잘 잡히고, 좌대 밖에
  // 선 관객에게 가까운 쪽 마커가 바로 눈앞에 들어온다. 5mm 단위로 떨어뜨려
  // 현장에서 줄자로 재기 쉽게 한다.
  const fits = outer >= inner;
  GEOMETRY.markerRing = MRING_FIXED !== null ? MRING_FIXED
    : (fits ? Math.floor(outer * 200) / 200 : inner);

  // 간격을 크게 주면 맨 아래 링이 더 내려와야 한다. 0.3 으로 막아 두면
  // 아래쪽 겹들이 한 자리에 포개진다. 바닥에 닿지만 않게 0.1 로 낮춘다.
  GEOMETRY.ringMinY = Math.max(0.1, GEOMETRY.headroom - PEDESTAL.height);
  // 크리스탈은 천에서 솟는다. 천은 장치 위에 덮여 있다.
  GEOMETRY.spawnY = GEOMETRY.deviceHeight + 0.02;

  // 이 배치가 들어가는 가장 작은 좌대. 안 들어가면 콘솔에 적어 준다.
  const needD = 2 * (Math.hypot(inner + half, half) + PEDESTAL.rimMargin);
  if (report) {
    const R = GEOMETRY.markerRing;
    console.log(
      `[좌대] 지름 ${PEDESTAL.diameter.toFixed(2)}m / 높이 ${PEDESTAL.height.toFixed(2)}m\n` +
      `[마커] 반지름 ${R.toFixed(3)}m (마주 보는 마커 사이 ${(R * 2).toFixed(2)}m), ` +
      `테두리까지 ${(PEDESTAL.diameter / 2 - Math.hypot(R + half, half)).toFixed(3)}m\n` +
      `[링]  맨 아래 링 상단면 기준 ${GEOMETRY.ringMinY.toFixed(2)}m = 바닥 기준 ${GEOMETRY.headroom.toFixed(2)}m`);
    if (!fits) {
      console.warn(`[좌대] 지름 ${PEDESTAL.diameter.toFixed(2)}m 는 좁습니다. ` +
        `이 배치는 ${needD.toFixed(2)}m 이상이 필요하고, 지금은 마커가 테두리를 넘습니다.`);
    }
  }
  return { fits, needD, outer, inner };
}
refreshPedestal();

// =============================================================
//  일정. 며칠째인지로 어느 링에 걸릴지가 정해진다.
// =============================================================

// 시연 일정. 셋이 서로 맞아야 샹들리에가 천장에서 바닥 한계까지 꽉 찬다.
//   첫 겹이 첫 운영 시간이고, 마지막 겹이 마지막 날 마지막 운영 시간이다.
const DEMO_DAYS = num("days", 2);      // 센서부를 가져가 시연하는 날수
const OPEN = [num("open", 11), num("close", 19)];   // 전시장 운영 시간 (시)
const PERIOD = num("period", 1);       // 한 겹이 머무는 시간

export const SCHEDULE = {
  // 시연 첫날 첫 운영 시간. 이 시각이 첫 겹이다.
  // ⚠️ +09:00 을 붙여 한국시간으로 못박는다. 안 붙이면 관객 폰의 시간대를 따라가서
  //    시차가 다른 폰에서 겹이 밀린다.
  startISO: "2026-11-01T11:00:00+09:00",

  // 링이 한 겹 내려오는 주기 (시간). 1 이면 한 시간에 한 겹이다.
  // 센서부를 가져가 시연하는 기간이 이틀이라, 하루 단위로는 겹이 둘뿐이다.
  // ?period=24 로 하루 한 겹으로 돌릴 수 있다.
  periodHours: PERIOD,

  // 전시장 운영 시간 (시). 닫힌 시간에는 아무도 그리지 않는다.
  // 그 주기에는 겹이 아예 열리지 않고 다음에 그려진 것이 앞 겹을 이어받으므로
  // 샹들리에 중간이 끊기지 않는다. 겹 수를 잡는 데만 쓴다.
  openHours: OPEN,

  // 겹의 최대 개수. 이보다 길어지면 마지막 겹에 모인다.
  // 겹은 그려진 주기에만 열리니, 운영 시간을 꽉 채워도 이 수를 넘지 않는다.
  // 이틀에 11시부터 19시, 한 시간에 한 겹이면 2 * 8 = 16 겹이다.
  // 책상 시험은 높이가 40cm 뿐이라 16겹을 넣으면 겹 간격이 2.7cm 가 되어
  // 크리스탈(4.5~14cm)끼리 뭉개진다. 겹 수를 줄여 간격을 8cm 로 둔다.
  maxRings: deskNum("layers", 6, Math.max(2,
    Math.ceil(DEMO_DAYS * (OPEN[1] - OPEN[0]) / PERIOD))),

  showRings: true,    // 가상 링을 그릴지
};

// =============================================================
//  마커 배치
//  AR.js 바코드 마커. value 는 바코드 번호.
//  pos = 마커 중심의 월드 좌표 (미터). 월드 원점은 천 중앙, 설치물 상단면.
//  yaw = 마커를 붙인 방향 (도). 바코드가 월드 축과 어긋나게 붙었을 때만 넣는다.
//  ⚠️ 네 마커를 같은 방향으로 붙여야 yaw 를 0 으로 둘 수 있다.
//     현장에서 ?debug=1 로 계산된 포즈를 보면서 맞추세요.
// =============================================================

// 천장 마커는 이제 없어도 된다. 큐브 밑면이 그 자리를 맡는다 (2026-10-29).
// 달 수 있으면 덤으로 하나 더 잡히므로 ?ceilingmarker=1 로 켠다.
// 번호 26 은 다른 데 쓰지 않고 이 자리로 비워 두었다.
export const HAS_CEILING_MARKER = QS.get("ceilingmarker") === "1";

const R = GEOMETRY.markerRing;

// 천장에서 낚싯줄로 매단 마커 큐브. 옆면 넷에 서로 다른 바코드를 붙인다.
// 큐브라 어느 방향에서 올려다봐도 한 면은 보인다. 좌대를 안 비춰도 샹들리에가 선다.
//
// 🔴 반드시 두 줄 이상으로 맬 것. 한 줄이면 줄이 꼬여 큐브가 천천히 돈다.
//    마커가 돌면 샹들리에가 그만큼 통째로 같이 돈다. 흔들리는 건 (수 cm) 괜찮지만
//    도는 건 안 된다. 줄 둘을 큐브 윗면 양 끝에 10cm 쯤 떨어뜨려 매면 안 돈다.
//
// 🔴 면 크기(face)는 흰 여백까지 포함한 한 변이다. 검은 사각형은 그 2/3 다.
//    영상에서 이 면이 화면 가로의 1/20 보다 작아지면 안 읽힌다 (cubeFaceFor).
//    1280 폭 기준으로 2m 거리에서 약 16cm, 1.5m 에서 약 12cm 가 필요하다.
//
// 면 순서는 바닥 마커와 같은 방향이다. 바닥 0 / 7 / 44 / 63 이 붙은 쪽을
// 각각 바라보는 면 넷이다 (+Z, +X, -Z, -X). 네 장 모두 인쇄물 위쪽이 천장을 향하게.
//
// 축에 매달면 샹들리에 부피 안이라 가상 크리스탈에 가려 보인다. 검출은 영상에서
// 하므로 읽히는 데는 지장이 없고, 가려도 된다고 정해졌다 (2026-10-29).
// 축에 두면 올려다보는 거리가 짧아져 큐브가 작아진다. 그게 축에 매다는 이유다.
// ⚠️ 대신 축에서는 면을 잘못 읽어도 위치가 거의 안 틀려서 outlierMeters 가
//    못 걸러낸다. 샹들리에가 90도 돌아버린다. 그래서 같은 큐브 안 네 면의
//    코드 거리를 먼저 키워 놨다 (아래 CUBE_CODES). r 을 주면 이 위험도 준다.
//
//   { y: 높이(m), face: 한 변(m), r: 축에서 떨어진 거리(m), az: 방위(도),
//     codes: [+Z, +X, -Z, -X] }
// y 는 좌대 상단면 기준이다. 줄자는 바닥에서 재므로 좌대 높이를 빼고 적을 것.
// r 과 az 는 없으면 0 이다 (중심축).
// ?cube=2.4,0.16 으로 한 개를 임시로 켜 볼 수 있다 (현장에서 크기 가늠용).
// ?cube=2.4,0.16,0.8,45 처럼 r 과 az 까지 주고, 여러 개는 세미콜론으로 잇는다.
// 🔴 번호를 함부로 바꾸지 말 것. 3x3 격자 64개 중에서 고른 것이다.
//    회전까지 넣은 최소 거리가 3 인 묶음은 이 알파벳 전체에서 7개가 최대이고
//    (3, 13, 16, 30, 38, 40, 59), 바닥 4 + 천장 1 이 이미 거리 3 으로 꽉 찼다.
//    그래서 큐브는 거리 2 로 간다. 칸 하나가 잘못 읽혀도 다른 마커가 되지는 않고
//    버려지기만 한다. 두 칸이 같이 틀려야 뒤바뀐다.
//    같은 큐브 안에서 뒤바뀌면 샹들리에가 90도 돌아버리므로 큐브 안쪽 거리를
//    먼저 키워 잡았다 (대부분 4, 큐브마다 한 쌍만 2).
//    다섯 면을 쓴다. 옆면 넷 + 밑면 하나. 윗면은 아무도 못 보므로 비운다.
// 🔴 다섯째(밑면)는 네 옆면 모두와 거리 4 가 되게 골랐다. 옆면끼리 뒤바뀌면
//    월드가 90도 돌지만, 옆면과 밑면이 뒤바뀌면 90도 기울어진다. 그게 훨씬
//    나쁘다. 옆면끼리는 거리 2 를 허용하고 밑면만 멀리 떼어 놓았다.
export const CUBE_CODES = [[21, 52, 50, 38, 11], [14, 13, 28, 41, 19],
                           [42, 49, 56, 25, 22]];
// 🔴 매단 큐브 셋. [바닥 기준 높이(m), 흰 여백 포함 한 변(m)]
//
// 왜 셋인가, 왜 이 높이인가:
//   바닥 마커는 관객이 1.2m 쯤 위를 겨누는 순간 화면에서 빠진다. 좌대에 깔려
//   있는데 관객은 위를 보기 때문이다 (세로 화각 65도, 폰 높이 1.5m 기준).
//   크리스탈은 60초에 걸쳐 천(0.52m)에서 샹들리에(2.05m)까지 올라간다.
//   그 장면이 작품의 핵심인데 그 구간에 기준이 없었다. 그래서 1.25m 부터
//   천장까지 0.9m 간격으로 셋을 건다. 모든 높이에서 최소 하나가 화면에 남는다.
//
// 왜 이 크기인가:
//   관객이 2.0m 뒤에서도 읽히는 최소값이다 (cubeFaceFor). 높이 매달수록
//   멀어지므로 커진다. ?arw=1920&arh=1440 으로 올리면 2/3 로 줄어든다.
//
// 높이는 바닥 기준으로 적는다. 줄자가 그렇고, 천장에서 내려 매다는 것이라
// 좌대 높이와 상관이 없다. 코드가 쓰는 y 는 좌대 상단면 기준이라 여기서 뺀다.
// [바닥 기준 높이(m), 한 변(m), Y축으로 돌아간 각(도)]
// 🔴 돌아간 각은 현장에서 실제로 매단 대로 적는다. 큐브1 은 90도 돌려 달렸다.
//    markers/photo_test.html 로 현장 사진을 검출기에 넣어 확인했다.
//    +Z 를 보아야 할 21 이 +X 를 보고, 52 가 -Z, 50 이 -X, 38 이 +Z 를 본다.
//    네 면이 한 칸씩 밀렸으니 Y축 +90도다.
// 현장에서 실제로 매단 높이다 (좌대 윗면 기준 92 / 137 / 184cm 에 좌대 20cm).
// 보정은 setcal 의 --cubey 로 들어가고, 여기 값은 그게 안 실릴 때의 대비다.
const CUBE_PLAN = [
  [1.12, 0.130, 90],
  [1.57, 0.135,  0],
  [2.04, 0.160,  0],
];

// ?cubes=0 이면 매단 큐브를 통째로 끈다. 바닥 네 장만 두고 시험할 때 쓴다.
// 큐브 마커는 자리가 1.25~3.05m 위라, 하나라도 잘못 읽히면 월드가 그리로 끌려간다.
const CUBES_ON = QS.get("cubes") !== "0";
const cubeParam = (QS.get("cube") || "").trim();
export const CUBES = !CUBES_ON ? [] : cubeParam
  ? cubeParam.split(";").map((t, i) => {
      const [y, face, r, az, rot] = t.split(",").map(Number);
      return { y, face, r: r || 0, az: az || 0, rot: rot || 0,
               codes: CUBE_CODES[i % CUBE_CODES.length] };
    }).filter((c) => Number.isFinite(c.y) && Number.isFinite(c.face))
  : CUBE_PLAN.map(([floorY, face, rot], i) => ({
      y: floorY - PEDESTAL.height,   // 좌대 상단면 기준으로 바꾼다
      floorY, face, r: 0, az: 0, rot: rot || 0,
      codes: CUBE_CODES[i % CUBE_CODES.length],
    }));

// 큐브가 Y축으로 돌아가 달렸을 때 면의 법선과 yaw 를 같이 돌린다.
// three.js 의 Ry(t) 는 (x, z) 를 (x cos t + z sin t, -x sin t + z cos t) 로 보낸다.
export function cubeFaceDir(face, rot) {
  const [dx, dz, yaw] = CUBE_DIRS[face];
  if (!rot) return [dx, dz, yaw];
  const t = rot * Math.PI / 180, c = Math.cos(t), s = Math.sin(t);
  return [dx * c + dz * s, -dx * s + dz * c, yaw + rot];
}

// 매단 자리. 비켜 매달아도 큐브는 돌리지 않는다. 면은 바닥 마커와 같은 네 방향을 본다.
export const cubeCenter = (c) => [
  Math.sin((c.az || 0) * Math.PI / 180) * (c.r || 0),
  c.y,
  Math.cos((c.az || 0) * Math.PI / 180) * (c.r || 0),
];

// 흰 여백 포함 한 변이 영상에서 몇 픽셀이면 읽히는가. 실측값이다
// (markers/cube_test.html, 마커 넷 x 흐림 둘 = 8판씩).
//
//   1280x960 으로 읽으면  블록 45px 에서 0/30/45/60도 전부 통과
//   1920x1440 으로 읽으면 블록 54px
//
// 🔴 이 수치는 "검출 처리 해상도" 기준이다. AR.js 는 영상 크기(sourceWidth)와
//    검출 처리 크기(canvasWidth)가 따로이고, canvasWidth 를 안 주면 기본이
//    640x480 이라 1280 영상을 반으로 줄여서 읽는다. 그 설정으로 재면 80px 이
//    나오는데, app.js 는 canvasWidth 를 영상 크기와 같게 주므로 45px 이 맞다.
//    전에 80px 로 잡아서 마커를 1.8배 크게 만들 뻔했다 (2026-10-30 에 바로잡음).
//
// 설계에는 63px 을 쓴다. 실측의 1.4배다. 합성 영상에는 없는 것들
// (움직임 번짐, 노출 흔들림, 종이 휨)에 쓸 여유다.
// 폰 뒷 카메라 화각을 65도로 보면 필요한 한 변이 거리에 비례한다.
export const CUBE_FOV = 65;
export const CUBE_PX = 63;
export const cubeFaceFor = (d, frameW = 1280) =>
  d * Math.tan(CUBE_FOV * Math.PI / 360) * CUBE_PX / (frameW / 2);

// 큐브 하나를 다섯 장의 마커로 편다. 면은 중심에서 face/2 만큼 바깥이다.
// [면 법선 x, 면 법선 z, yaw]. yaw 0 이 +Z 를 본다.
const CUBE_DIRS = [[0, 1, 0], [1, 0, 90], [0, -1, 180], [-1, 0, 270]];
const cubeMarkers = () => CUBES.flatMap((c) => {
  const [cx, , cz] = cubeCenter(c);
  const faces = CUBE_DIRS.map((_, i) => {
    const [dx, dz, yaw] = cubeFaceDir(i, c.rot);
    return {
      value: c.codes[i],
      size: c.face / 1.5,               // 검은 사각형. 흰 여백이 25% 씩이다
      pos: [cx + dx * c.face / 2, c.y, cz + dz * c.face / 2],
      yaw, tilt: 90, kind: "cube", cube: CUBES.indexOf(c), face: i,
    };
  });

  // 🔴 밑면. 이게 없으면 좌대 바로 앞에 선 관객이 올려다볼 때 기준이 없다.
  //    옆면은 세워져 있어서 가파르게 올려다보면 모서리로 보여 안 읽힌다.
  //    (모서리 쪽에서 보면 두 면이 각각 방위 45도 틀어지므로, 고도가 45도만
  //     넘어가도 법선과의 각이 60도를 넘는다. 60도가 실측 한계다.)
  //    밑면은 법선이 아래라 그 자세에서 가장 정면으로 보인다. 큐브가 가장
  //    약한 자세를 큐브 자신이 메운다. 윗면은 아무도 못 보므로 비운다.
  faces.push({
    value: c.codes[4],
    size: c.face / 1.5,
    pos: [cx, c.y - c.face / 2, cz],
    yaw: c.rot || 0, tilt: 180, kind: "cube", cube: CUBES.indexOf(c), face: 4,
  });
  return faces;
});

export const MARKERS = [
  // 바코드 번호는 0~4 가 아니라 0, 7, 44, 63, 26 을 쓴다.
  // 0~4 는 3x3 격자가 서로 한 칸밖에 안 달라서(회전 포함 최소 거리 1)
  // 멀리서 한 칸만 잘못 읽혀도 다른 마커가 된다. 이 조합은 최소 거리가 3 이다.

  // 좌대 테두리 가까이, 천의 네 변 쪽에 하나씩. 위를 향해 평평하게.
  // ⚠️ 네 장을 모두 같은 방향으로 붙인다 (인쇄물의 위쪽이 전부 같은 쪽).
  //    그래야 yaw 를 0 으로 둘 수 있다. 둥근 좌대에는 맞출 모서리가 없으니
  //    테이프로 기준선 하나를 긋고 네 장을 그 선과 나란히 붙이는 쪽이 쉽다.
  { value:  0, size: GEOMETRY.markerSize, pos: [ 0, 0,  R], yaw: 0, kind: "floor" },
  { value:  7, size: GEOMETRY.markerSize, pos: [-R, 0,  0], yaw: 0, kind: "floor" },
  { value: 44, size: GEOMETRY.markerSize, pos: [ 0, 0, -R], yaw: 0, kind: "floor" },
  { value: 63, size: GEOMETRY.markerSize, pos: [ R, 0,  0], yaw: 0, kind: "floor" },

  // 천장 뼈대 아랫면 1개. 아래를 향하므로 flip 을 켠다.
  // 전시장 사정으로 못 달면 HAS_CEILING_MARKER 를 false 로 두면 빠진다.
  ...(HAS_CEILING_MARKER ? [{
    value: 26, size: GEOMETRY.ceilingMarkerSize,
    pos: [0, GEOMETRY.ceilingHeight, 0], yaw: 0, flip: true, kind: "ceiling",
  }] : []),

  ...cubeMarkers(),
];

// 좌대 지름을 현장에서 고치면 마커 반지름이 달라진다. 위치를 다시 잡는다.
// 네 방향 순서는 위 배열과 같다: +Z, -X, -Z, +X
const RING_DIRS = [[0, 1], [-1, 0], [0, -1], [1, 0]];

// 🔴 바닥 마커 네 장의 자리를 하나씩 못박는다.
//
//    설치를 마치면 마커를 옮기거나 다시 찍을 수 없다. 그런데 기본 계산은
//    네 장이 완벽한 정사각형 위에 있다고 가정한다. 실제로는 몇 cm 씩 어긋나고,
//    사람이 손으로 붙이면 방향도 조금씩 돌아간다. 그 차이를 못 적으면
//    마커마다 다른 월드 원점을 내놓고 화면이 튄다.
//
//    순서는 MARKERS 의 바닥 네 장 순서, 곧 0 / 7 / 44 / 63 이다.
//    각 항목은 [x, z, yaw도] 이고 원점은 장치(천)의 한가운데다.
//      ?fm=0,0.42,0;-0.41,0,2;0,-0.43,0;0.42,0,-1
//    비워 두면 지금처럼 반지름 하나로 정사각형을 만든다.
let FLOOR_FIX = null;

export function setFloorFix(list) {
  FLOOR_FIX = (Array.isArray(list) && list.length === 4) ? list : null;
}

(function parseFm() {
  const raw = (QS.get("fm") || "").trim();
  if (!raw) return;
  const got = raw.split(";").map((t) => t.split(",").map(Number))
                 .filter((a) => a.length >= 2 && a.every(Number.isFinite));
  if (got.length === 4) FLOOR_FIX = got;
  else console.warn("[config] ?fm= 은 네 장을 전부 적어야 합니다. 무시합니다.");
})();

export function refreshMarkers() {
  const R = GEOMETRY.markerRing;
  let i = 0;
  for (const m of MARKERS) {
    if (m.kind === "ceiling") { m.pos[1] = GEOMETRY.ceilingHeight; continue; }
    // ⚠️ 매단 큐브는 좌대 지름과 상관없다. 여기서 건드리면 자리가 통째로 틀어진다.
    if (m.kind === "cube") {
      // 매단 높이는 현장에서 재서 고칠 수 있다. 줄을 올리고 내리면 되니까.
      const c = CUBES[m.cube];
      if (!c) continue;
      const [cx, , cz] = cubeCenter(c);
      if (m.face === 4) {
        m.pos[0] = cx; m.pos[1] = c.y - c.face / 2; m.pos[2] = cz;
        m.yaw = c.rot || 0;
      } else {
        const [dx, dz, yaw] = cubeFaceDir(m.face, c.rot);
        m.pos[0] = cx + dx * c.face / 2;
        m.pos[1] = c.y;
        m.pos[2] = cz + dz * c.face / 2;
        m.yaw = yaw;
      }
      continue;
    }
    if (m.kind !== "floor") continue;
    const k = i++;
    if (FLOOR_FIX) {
      const [x, z, yaw] = FLOOR_FIX[k];
      m.pos[0] = x;
      m.pos[2] = z;
      m.yaw = Number.isFinite(yaw) ? yaw : 0;
    } else {
      const [dx, dz] = RING_DIRS[k % 4];
      m.pos[0] = dx * R;
      m.pos[2] = dz * R;
      m.yaw = 0;
    }
  }
}

// =============================================================
//  설치를 마친 뒤 현장 실측값을 Firebase 에서 받아 적용한다.
//
//  🔴 설치가 끝나면 마커를 옮기거나 다시 찍을 수 없다. 숫자로 맞추는 길이
//     유일하다. 그런데 QR 은 이미 인쇄되어 있고 현장에서 다시 배포하는 것도
//     불안하다. 그래서 DB 에 적어 두고 앱이 읽어 간다. 모든 폰이 따라온다.
//  ⚠️ URL 로 직접 준 값이 이것보다 세다. 현장에서 한 대만 다르게 보며
//     맞춰 볼 때 필요하다.
// =============================================================

export function applyRemoteCal(cal) {
  if (!cal || typeof cal !== "object") return [];
  const hit = [];
  const urlHas = (k) => QS.get(k) !== null;
  const num_ = (k) => Number(cal[k]);
  const take = (k, fn, lo, hi) => {
    const v = num_(k);
    if (urlHas(k) || !Number.isFinite(v) || v < lo || v > hi) return;
    fn(v);
    hit.push(`${k}=${v}`);
  };

  take("ped",  (v) => { PEDESTAL.diameter = v; }, 0.2, 3);
  take("pedh", (v) => { PEDESTAL.height = v; },   0,   2);
  take("msize", (v) => {
    GEOMETRY.markerSize = v;
    for (const m of MARKERS) if (m.kind === "floor") m.size = v;
  }, 0.02, 0.6);
  take("headroom", (v) => { GEOMETRY.headroom = v; }, 0.3, 6);
  take("devh", (v) => { GEOMETRY.deviceHeight = v; }, 0, 1);
  take("fov",  (v) => { AR_SOURCE.fov = v; }, 20, 140);
  take("gap",  (v) => { GEOMETRY.ringGap = v; }, 0.02, 1);
  take("smooth", (v) => { ANCHOR.smooth = v; }, 0.02, 1);

  refreshPedestal();                 // 자동으로 나오는 값들을 먼저 다시 잡는다

  take("mring", (v) => { GEOMETRY.markerRing = v; }, 0.05, 1.5);
  take("floorceiling",
       (v) => { GEOMETRY.ceilingHeight = Math.max(0.5, v - PEDESTAL.height); }, 1.2, 9);
  take("ceiling", (v) => { GEOMETRY.ceilingHeight = v; }, 0.5, 9);

  // 바닥 마커 네 장의 실측 자리. [x, z, yaw도] 넷.
  if (!urlHas("fm") && Array.isArray(cal.fm) && cal.fm.length === 4) {
    setFloorFix(cal.fm);
    hit.push("fm");
  }
  // 매단 큐브 높이. 한 변은 인쇄물이라 못 바꾼다.
  if (!urlHas("cube") && Array.isArray(cal.cubeY)) {
    cal.cubeY.forEach((y, i) => {
      if (CUBES[i] && Number.isFinite(y)) {
        CUBES[i].floorY = y;
        CUBES[i].y = y - PEDESTAL.height;
      }
    });
    hit.push("cubeY");
  }
  // 돌아간 각. 매달고 보니 틀어졌을 때 배포 없이 고친다.
  if (!urlHas("cube") && Array.isArray(cal.cubeRot)) {
    cal.cubeRot.forEach((r, i) => {
      if (CUBES[i] && Number.isFinite(r)) CUBES[i].rot = r;
    });
    hit.push("cubeRot");
  }

  refreshMarkers();
  return hit;
}

// 마커 포즈가 떨릴 때 쓰는 저역 통과 필터. 0 에 가까우면 둔하고 안정적.
export const ANCHOR = {
  // 0~1, 프레임당 따라가는 비율. 낮을수록 안정적이고 반응이 느리다.
  // 포즈를 매 프레임 새로 푸니 잡음이 섞인다. 0.18 은 그 잡음을 꽤 따라간다.
  // ?smooth= 나 setcal --smooth 로 현장에서 맞춘다.
  smooth: num("smooth", 0.10),
  maxMarkers: 4,       // 동시에 평균낼 바닥 마커 수

  // 마커들 사이에 조형물이 있어 4개가 한꺼번에 안 보일 수 있다.
  // 비스듬히 보이거나 먼 마커는 포즈 오차가 크므로 비중을 낮춘다.
  facingPower: 2.0,    // 정면으로 보일수록 비중이 커지는 급함
  outlierMeters: 0.22, // 3개 이상 보일 때 중앙값에서 이만큼 벗어나면 버린다

  // 2개만 보일 때는 누가 바깥값인지 가릴 수 없다. 대신 둘이 주장하는 월드
  // 원점이 이만큼 넘게 어긋나면 둘 다 안 믿고 그 프레임을 버린다. 잘 맞으면
  // 2~3cm 가 나오므로 0.35m 는 넉넉하다. 오검출 한 장이 월드를 끌고 가는 것과,
  // 좌대 위의 QR 이 없는 마커 번호로 읽히는 것을 둘 다 막는다.
  rejectMeters: num("reject", 0.35),

  // ⚠️ 바닥 마커와 천장 마커를 섞어서 평균내지 않는다.
  // 바닥 4개는 설치물에 고정되어 서로 강체지만, 천장 마커는 우레탄 줄에 매달려
  // 따로 흔들린다. 섞으면 둘이 다른 위치를 주장하며 월드가 떨린다.
  // 그래서 바닥이 하나라도 보이면 바닥만 쓰고, 안 보일 때만 천장으로 넘어간다.
  preferFloor: true,

  // 마커가 하나도 안 보일 때 기기 방향 센서로 샹들리에를 제자리에 붙잡는다.
  // 끄면 마지막 포즈를 그대로 둬서 샹들리에가 화면에 붙어 따라다닌다.
  //
  // ⚠️ 이 작품에서는 예외가 아니라 기본 상태다. 샹들리에는 머리 위에 있고
  //    마커는 발밑 좌대에 있어서, 샹들리에를 보는 자세에서는 마커가 화면에
  //    들어오지 않는다. 그래서 자이로 유지를 끄거나 시간제한을 두면 안 된다.
  gyroHold: true,

  // 다시 마커를 잡았을 때 포즈가 이만큼 넘게 다르면 부드럽게 따라가지 않고
  // 바로 맞춘다. 사방에서 보는 작품이라 관객이 좌대를 돌면서 마커를 놓쳤다
  // 다시 잡는데, 그 사이 많이 움직였으면 샹들리에가 공중을 가로질러
  // 미끄러져 오는 게 보인다. 끊어서 맞추는 쪽이 덜 어색하다.
  snapMeters: 0.25,

  // 이만큼 마커 없이 자이로만으로 버텼으면 다시 비춰 달라고 안내한다.
  // 자이로는 돌아간 각도만 알고 걸어간 거리는 모르므로 서서히 어긋난다.
  hintSeconds: 12,
};

// =============================================================
//  움직임
// =============================================================

export const MOTION = {
  // 천에서 그날 링까지 올라가는 시간.
  // 올라가는 동안이 크리스탈을 누르기 가장 좋은 구간이다. 링에 매달리고 나면
  // 좁은 반경에 몰려서 개별 선택이 어렵다. 그래서 넉넉하게 둔다.
  riseSeconds: 60,
  spiralTurns: 1.5,     // 올라가면서 도는 횟수
  spiralRadius: 0.18,   // 나선 반지름
  swayAmplitude: 0.012, // 매달린 뒤 흔들림 크기
  swaySeconds: 3.4,     // 흔들림 주기
};

// =============================================================
//  데이터에서 크리스탈로 가는 매핑
//  형태는 Blender 에서 구운 blobs.json 에서 고르고,
//  크기와 늘임, 비틀림, 투명도는 획 데이터로 입힌다.
// =============================================================

export const MAPPING = {
  sizeFromPress:    [0.045, 0.14],  // press 0~1 을 크리스탈 최대 길이 m 로
  opacityFromSpeed: [0.85, 0.28],   // speed 0~1 을 불투명도로 (느리면 진하게)
  stretchFromElong: [1.0, 1.9],     // elong 0~1 을 한 축 늘임 배율로
  twistFromCurl:    [0, 1.1],       // curl 절대값을 비틀림 라디안으로
};

// 획의 모양이 크리스탈의 종류를 고른다.
//   맴돌았으면 loop, 길쭉했으면 arc, 퍼졌으면 ribbon
// 임의로 고르지 않고 획 자체의 기하에서 끌어온다.
export const FORM = {
  windToLoop: 0.42,   // wind 가 이보다 크면 loop
  elongToArc: 0.50,   // 아니면 elong 이 이보다 크면 arc, 작으면 ribbon
};

// 유리 질감 조절값. 눈으로 보고 맞추는 값이라 여기 빼둔다.
export const GLASS = {
  irid:      0.55,  // 무지개가 도는 정도. 0 이면 단색 유리
  iridWhite: 0.55,  // 무지개를 흰색에 섞는 비율. 높을수록 엷다
  rimPower:  2.4,   // 가장자리가 밝아지는 급함. 낮을수록 테두리가 넓다
  envLow:    0.38,  // 아래쪽 환경 밝기
  envHigh:   1.15,  // 위쪽 환경 밝기

  // 투명도. 가운데는 비치고 가장자리에서 드러나야 유리로 읽힌다.
  // ⚠️ 전시장이 흰 화이트큐브라 값을 올렸다. 어두운 배경에서 맞춘 0.10 으로 두면
  //    흰 벽 앞에서 크리스탈이 통째로 사라진다. venue.html 에서 확인할 수 있다.
  alphaCore: 0.22,  // 정면으로 볼 때 남는 비율. 낮을수록 투명
  alphaRim:  0.95,  // 가장자리에서 더해지는 양

  // 두께를 지나며 먹히는 빛. 정면일수록 유리를 길게 지나 어두워진다.
  // 흰 배경에서 형태를 읽히게 하는 건 투명도가 아니라 이쪽이다.
  // 투명도만 올리면 흰 유리가 더 희어질 뿐 대비가 안 생긴다.
  absorb: 0.42,

  // 반짝임
  sparkle:    1.6,  // 하이라이트 세기
  specPower:  170,  // 하이라이트 날카로움. 높을수록 점처럼 맺힌다
  dispersion: 0.02, // 분산. 반짝일 때 색이 갈라지는 정도
  flash:      1.2,  // 비스듬히 볼 때 가장자리에서 터지는 섬광
};

// 레퍼런스의 무지개빛을 흉내낸 엷은 색. dir 로 고른다.
export const TINTS = [0xdff0e6, 0xe4e2f5, 0xdcecf5, 0xf0e6f2, 0xe8f2ea];

// =============================================================
//  성능 단계. 오래된 폰에서 자동으로 낮춥니다.
// =============================================================

export const QUALITY = {
  highEndCrystals: 300,  // 이 수까지는 좋은 질감
  midEndCrystals:  140,
  lowEndCrystals:  55,
  fpsSampleSeconds: 4,    // 이 시간 동안 평균 fps 를 봅니다
  fpsDownshiftBelow: 24,  // 이보다 낮은 구간이 연속 2번이면 단계를 내립니다
  fpsUpshiftAbove: 48,    // 이보다 높은 구간이 연속 2번이면 되올립니다
  warmupSeconds: 8,       // 카메라 초기화와 마커 탐색 워밍업 동안은 재지 않습니다
};
