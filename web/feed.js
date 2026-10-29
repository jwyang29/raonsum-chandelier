// 크리스탈 데이터를 받아온다.
//
// Firebase SDK 를 쓰지 않고 Realtime Database 의 REST 스트리밍을 EventSource 로
// 읽는다. 읽기 공개 규칙이면 그대로 동작하고, SDK 수백 KB 를 받지 않아도 되므로
// 오래된 폰에 유리하다 (문서 리스크 2번).
//
// ?mock=1 을 붙이면 Firebase 없이 가짜 크리스탈을 만들어 보낸다.

import { FIREBASE, DB_PATH } from "./config.js";

const seen = new Set();

// 허브가 올리는 모양을 그대로 흉내낸다. 누르면 뜨는 판독 화면도 확인할 수 있어야 한다.
const FEELINGS = ["fast_hard", "fast_soft", "slow_hard", "slow_soft", "varied", "neutral"];

export function mockData() {
  const r = Math.random;
  return {
    t: Date.now(),
    press: r(), speed: r(), elong: r(), wind: r() * 0.6,
    curl: r() * 2 - 1, dir: r() * Math.PI * 2,
    dur: 0.6 + r() * 4, n: 7 + Math.floor(r() * 180),
    feeling: FEELINGS[Math.floor(r() * FEELINGS.length)],
    conf: Math.round((0.55 + r() * 0.44) * 100) / 100,
  };
}

export function startFeed(onCrystal, onStatus) {
  const params = new URLSearchParams(location.search);


  if (params.get("mock") === "1" || params.get("preview") === "1") {
    const rate = Number(params.get("rate")) || (params.get("preview") === "1" ? 1500 : 4000);
    onStatus(`mock 피드, ${rate}ms 간격`);
    onCrystal(mockData());
    setInterval(() => onCrystal(mockData()), rate);
    return;
  }

  if (!FIREBASE.databaseURL || FIREBASE.databaseURL.includes("PASTE_")) {
    onStatus("config.js 의 databaseURL 이 아직 비어 있습니다. ?mock=1 로 확인하세요");
    return;
  }

  const url = `${FIREBASE.databaseURL.replace(/\/$/, "")}/${DB_PATH}.json`;
  const es = new EventSource(url);

  const take = (key, value) => {
    if (!value || seen.has(key)) return;
    seen.add(key);
    onCrystal(value);
  };

  es.addEventListener("put", (e) => {
    const { path, data } = JSON.parse(e.data);
    if (data === null) return;
    if (path === "/") {
      // 접속할 때 지금까지 쌓인 전체가 한 번에 온다.
      Object.entries(data).forEach(([k, v]) => take(k, v));
      onStatus(`${Object.keys(data).length}개 불러왔습니다`);
    } else {
      take(path.replace(/^\//, ""), data);
    }
  });

  es.addEventListener("patch", (e) => {
    const { path, data } = JSON.parse(e.data);
    if (path === "/") Object.entries(data || {}).forEach(([k, v]) => take(k, v));
  });

  es.onopen = () => onStatus("연결됐습니다");
  es.onerror = () => onStatus("연결이 끊겼습니다. 자동으로 다시 붙습니다");
}
