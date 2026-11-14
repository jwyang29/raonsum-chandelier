// AR 페이지의 문지기. 안내를 먼저 보여 주고, 시작을 누른 뒤에 app.js 를 부른다.
//
// 🔴 app.js 는 뜨는 즉시 <a-scene arjs=...> 를 만들고, AR.js 가 그 자리에서
//    카메라를 요청한다. 그래서 QR 을 찍고 들어온 관객은 아무 설명도 못 본 채
//    권한 창부터 받는다. 무인 전시에서 한 번 거절하면 옆에서 다시 눌러 줄
//    사람이 없다. 설명을 읽고 누르게 한 다음에 묻는다.
//
// 🔴 이 버튼 한 번이 아이폰 자이로 권한의 사용자 제스처이기도 하다.
//    DeviceOrientationEvent.requestPermission 은 제스처 안에서만 물을 수 있다.
//    여기서 받아 두면 app.js 는 "화면을 한 번 누르세요" 를 안 띄워도 된다.
//
// 🔴 app.js 자체는 건드리지 않았다. AR 이 돌아가기까지 들인 것이 많아서
//    장면을 만드는 차례를 손대고 싶지 않았다. 부르는 때만 늦춘다.

import { countVisit } from "./visit.js?v=1114g";

const QS = new URLSearchParams(location.search);
const intro = document.getElementById("intro");
const go = document.getElementById("intro-go");

// 미리보기는 카메라를 안 쓴다. ?intro=0 은 현장에서 건너뛸 때.
const SKIP = QS.get("preview") === "1" || QS.get("intro") === "0";

// 한 번 본 사람은 다시 안 본다. 보다가 새로고침하는 일이 잦다.
// 🔴 sessionStorage 라 탭을 닫으면 지워진다. 다음 관객은 처음부터 본다.
//    localStorage 로 두면 작가가 시험하는 폰에서만 편하고 관객은 못 본다.
let seen = false;
try { seen = sessionStorage.getItem("introseen") === "1"; } catch (e) {}

async function start() {
  if (go) go.disabled = true;

  // 자이로를 먼저 받는다. 반드시 이 클릭 안이어야 한다.
  // 거절해도 그냥 간다. 마커가 보이는 동안은 자이로 없이도 멀쩡하다.
  try {
    if (typeof DeviceOrientationEvent !== "undefined" &&
        typeof DeviceOrientationEvent.requestPermission === "function") {
      const res = await DeviceOrientationEvent.requestPermission();
      if (res === "granted") window.__gyroGranted = true;
    }
  } catch (e) {
    console.warn("[boot] 자이로 권한을 못 받았습니다", e);
  }

  countVisit("start");   // 여기는 SKIP 이면 아예 안 지나간다
  try { sessionStorage.setItem("introseen", "1"); } catch (e) {}
  if (intro) intro.classList.add("gone");

  // 이제 카메라를 묻는다.
  await import("./app.js?v=1114g");
}

// 🔴 미리보기와 안내 건너뛰기는 작가가 확인할 때 쓰는 길이다. 세면 안 된다.
//    관객 수에 제 시험이 섞이면 그 숫자를 믿을 수 없게 된다.
if (!SKIP) countVisit("ar");

if (SKIP || seen || !intro || !go) {
  if (intro) intro.classList.add("gone");
  import("./app.js?v=1114g");
} else {
  intro.hidden = false;
  go.addEventListener("click", start, { once: true });
}
