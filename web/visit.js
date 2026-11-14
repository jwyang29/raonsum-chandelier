// 몇 명이 열어 봤는지만 센다.
//
// 🔴 남기는 것은 "언제" 하나뿐이다. 숫자 한 개를 날짜와 페이지 아래에 붙인다.
//        visits/2026-11-12/home/<자동키> = 1762934... (밀리초)
//    아이피도 기기 정보도 식별자도 없다. 관객을 구분할 수 있는 것을 하나도
//    안 남기므로, 같은 사람이 다음 날 또 와도 다른 사람과 구별되지 않는다.
//    그건 못 세는 게 아니라 안 세는 것이다. 전시에 필요한 건 "왔다" 뿐이다.
//
// 🔴 실패해도 조용히 넘어간다. 집계는 작품이 아니다. 와이파이가 흔들려도
//    관객 화면은 멀쩡해야 한다. 그래서 await 하지 않고 에러도 삼킨다.
//
// 세어 보는 법:  python3 hub/visits.py

import { FIREBASE } from "./config.js?v=1114a";

/** 한국 날짜 YYYY-MM-DD.
 *
 *  🔴 폰의 시간대를 쓰면 안 된다. 시간대가 어긋난 폰 하나가 전날 칸에
 *     들어가면 날짜별 숫자를 믿을 수 없게 된다. UTC 에 9시간을 더해
 *     어느 폰에서 열든 같은 칸에 들어가게 한다.
 */
function kstDay(ms) {
  return new Date(ms + 9 * 3600 * 1000).toISOString().slice(0, 10);
}

/** page 는 셋 중 하나다. Firebase 규칙이 이 셋만 받는다.
 *
 *    home    설명 페이지를 열었다 (QR 을 찍은 사람)
 *    ar      AR 페이지까지 왔다 (버튼을 눌렀다)
 *    start   안내를 읽고 시작하기를 눌렀다 (카메라를 허락할 기회까지 갔다)
 *
 *  home 과 ar 의 차이가 "설명만 보고 돌아간 사람" 이고,
 *  ar 과 start 의 차이가 "첫 화면에서 그만둔 사람" 이다. 무인 전시라
 *  이 두 숫자 말고는 어디서 놓치는지 알 길이 없다.
 */
export function countVisit(page) {
  const url = FIREBASE && FIREBASE.databaseURL;
  if (!url) return;

  // 한 번 열 때 한 번만. 새로고침해도 안 는다.
  // 탭을 닫으면 지워지므로 다음 관객은 다시 한 번 센다.
  try {
    const key = "counted_" + page;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");
  } catch (e) {
    // 사생활 보호 모드에서는 저장이 막힌다. 그래도 세는 쪽을 택한다.
  }

  const now = Date.now();
  try {
    fetch(`${url}/visits/${kstDay(now)}/${page}.json`, {
      method: "POST",
      body: String(now),
      // 관객이 바로 AR 로 넘어가도 요청이 살아 있게 한다
      keepalive: true,
    }).catch(() => {});
  } catch (e) {}
}
