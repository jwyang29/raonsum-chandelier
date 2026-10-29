// AR.js 가 넣는 비디오의 상태를 화면에 계속 찍는다. 카메라가 안 보일 때 원인을 가린다.
// camtest.html 은 항상, index.html 은 ?diag=1 일 때만 쓴다.
(function () {
  const d = document.createElement("pre");
  d.id = "videodiag";
  d.style.cssText = "position:fixed;top:0;left:0;z-index:99999;max-width:100%;" +
    "padding:8px 10px;background:rgba(0,0,0,.82);color:#9fe;" +
    "font:11px/1.5 ui-monospace,Menlo,monospace;white-space:pre;pointer-events:none;margin:0";
  d.textContent = "카메라 준비 중...";
  const put = () => document.body ? document.body.appendChild(d) : setTimeout(put, 50);
  put();

  let lastSeen = null, lostAt = null, events = [], hooked = null;

  // 스트림이 끊기는 순간을 잡는다. 카메라가 사라지는 원인이 트랙 종료인지 가린다.
  function hook(track) {
    if (!track || hooked === track) return;
    hooked = track;
    for (const ev of ["ended", "mute", "unmute"]) {
      track.addEventListener(ev, () => {
        events.push(`${ev} @${(performance.now() / 1000).toFixed(1)}s`);
      });
    }
  }
  setInterval(() => {
    const v = document.querySelector("#arjs-video") || document.querySelector("video");
    const sc = document.querySelector("a-scene");
    const cv = sc && sc.canvas;
    const s = v ? getComputedStyle(v) : null;
    const vr = v ? v.getBoundingClientRect() : null;
    const cr = cv ? cv.getBoundingClientRect() : null;
    const tr = v && v.srcObject ? v.srcObject.getVideoTracks()[0] : null;
    hook(tr);

    // 보이다가 사라지는 순간을 잡아 둔다
    const visible = !!(vr && vr.width > 1 && vr.height > 1 &&
                       s.display !== "none" && s.visibility !== "hidden" && +s.opacity > 0);
    if (visible) lastSeen = performance.now();
    else if (lastSeen && !lostAt) lostAt = performance.now();

    d.textContent = [
      `viewport   ${innerWidth} x ${innerHeight}`,
      `video      ${v ? "있음" : "없음"}  id=${v ? v.id || "(없음)" : "-"}  parent=${v ? v.parentElement.tagName : "-"}`,
      v ? `  원본     ${v.videoWidth}x${v.videoHeight}  readyState=${v.readyState}  paused=${v.paused}` : "",
      v ? `  style    w=${s.width} h=${s.height} ml=${s.marginLeft} mt=${s.marginTop}` : "",
      v ? `  배치     ${s.position} top=${s.top} left=${s.left} z=${s.zIndex}` : "",
      v ? `  표시     display=${s.display} vis=${s.visibility} opacity=${s.opacity}` : "",
      v ? `  화면상   x=${Math.round(vr.x)} y=${Math.round(vr.y)} ${Math.round(vr.width)}x${Math.round(vr.height)}` : "",
      tr ? `  track    enabled=${tr.enabled} state=${tr.readyState} muted=${tr.muted}` : "  track    없음",
      tr && tr.label ? `  카메라   ${tr.label.slice(0, 34)}` : "",
      events.length ? `  이벤트   ${events.slice(-4).join(", ")}` : "",
      `canvas     ${cr ? `${Math.round(cr.width)}x${Math.round(cr.height)} @${Math.round(cr.x)},${Math.round(cr.y)}` : "없음"}`,
      (window.__camlog && window.__camlog.length)
        ? "요청기록\n  " + window.__camlog.slice(-6).join("\n  ") : "",
      `판정       ${visible ? "보이는 상태" : lastSeen ? `사라짐 (보였다가 ${((lostAt-lastSeen)/1000).toFixed(1)}초 뒤)` : "아직 안 나옴"}`,
    ].filter(Boolean).join("\n");
  }, 400);

  addEventListener("error", (e) => { d.textContent = "ERROR: " + e.message; });
})();
