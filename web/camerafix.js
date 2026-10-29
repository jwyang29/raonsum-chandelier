// 카메라 요청을 가로채서 계측하고 손본다. AR.js 스크립트보다 먼저 로드해야 한다.
//
// 두 가지를 한다.
//  1) AR.js 가 넣는 facingMode:"environment" 를 걷어낸다.
//     맥 내장 카메라는 전면이라 이 조건에 안 맞고, 연속성 카메라가 섞이면
//     스트림이 갈아끼워지며 끊길 수 있다.
//  2) 호출 횟수와 조건, 스트림이 끝나는 순간을 기록한다.
//     카메라가 켜졌다 바로 꺼지면 보통 요청이 두 번 일어나 뒤의 것이 앞의 것을 죽인다.
(function () {
  const log = (window.__camlog = []);
  const t = () => (performance.now() / 1000).toFixed(1) + "s";
  const CAM = new URLSearchParams(location.search).get("cam");

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    log.push("getUserMedia 없음");
    return;
  }

  // ⚠️ facingMode 를 언제 걷어낼지가 중요하다.
  //   데스크탑: 뒷면 카메라가 없어서 이 조건 때문에 스트림이 떨어진다. 걷어내야 한다.
  //   폰: "environment" 가 바로 뒷면 카메라를 고르라는 올바른 요청이다.
  //       걷어내면 전면 카메라가 잡혀서 관객이 마커 대신 자기 얼굴을 본다.
  // 그래서 터치 기기가 아니거나 카메라를 직접 지정했을 때만 제거한다.
  const isTouch = navigator.maxTouchPoints > 0 || "ontouchstart" in window;
  const stripFacing = !isTouch || !!CAM;
  log.push(`기기 ${isTouch ? "터치(폰)" : "데스크탑"} · facingMode ${stripFacing ? "제거" : "유지"}`);

  const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  let calls = 0;

  navigator.mediaDevices.getUserMedia = function (c) {
    calls++;
    const n = calls;
    const v = c && c.video;
    if (v && typeof v === "object") {
      if (v.facingMode && stripFacing) {
        log.push(`#${n} facingMode=${JSON.stringify(v.facingMode)} 제거 @${t()}`);
        delete v.facingMode;
      }
      if (CAM) v.deviceId = { exact: CAM };
    }
    log.push(`#${n} 요청 @${t()}`);

    return orig(c).then((stream) => {
      const tr = stream.getVideoTracks()[0];
      log.push(`#${n} 받음 ${tr ? tr.label.slice(0, 22) : "?"} @${t()}`);
      if (tr) {
        tr.addEventListener("ended", () => log.push(`#${n} 끊김(ended) @${t()}`));
        tr.addEventListener("mute", () => log.push(`#${n} 끊김(mute) @${t()}`));
        const stop = tr.stop.bind(tr);
        tr.stop = function () {
          log.push(`#${n} 누군가 stop() 호출 @${t()}`);
          return stop();
        };
      }
      return stream;
    }).catch((e) => {
      log.push(`#${n} 실패 ${e.name} @${t()}`);
      throw e;
    });
  };
})();
