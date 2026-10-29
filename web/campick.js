// 카메라 고르기 화면.
//
// ⚠️ 관객 폰에서는 절대 뜨면 안 된다. 폰에서는 AR.js 가 facingMode 로 뒷면 카메라를
// 알아서 고르는 게 맞고, 선택 화면이 끼면 관객이 한 단계를 더 거쳐야 한다.
// 그래서 터치 기기가 아닐 때만 쓴다. 판단은 부르는 쪽에서 한다.

export const isDesktop = () =>
  !(navigator.maxTouchPoints > 0 || "ontouchstart" in window);

export async function listCameras() {
  // label 을 받으려면 권한이 한 번 있어야 한다. 받자마자 바로 끈다.
  const probe = await navigator.mediaDevices.getUserMedia({ video: true });
  probe.getTracks().forEach((t) => t.stop());
  const all = await navigator.mediaDevices.enumerateDevices();
  return all.filter((d) => d.kind === "videoinput");
}

/** 선택 화면을 띄우고 고른 deviceId 를 돌려준다. 건너뛰면 null. */
export function pickCamera() {
  return new Promise((resolve) => {
    const box = document.createElement("div");
    box.id = "campick";
    box.style.cssText =
      "position:fixed;inset:0;z-index:99997;background:#0e1116;color:#d8e0ea;" +
      "padding:28px;font:14px/1.6 system-ui,sans-serif;overflow:auto";
    const btn = (html, on) => {
      const b = document.createElement("button");
      b.innerHTML = html;
      b.style.cssText =
        "display:block;width:100%;max-width:460px;text-align:left;margin-bottom:8px;" +
        "padding:12px 14px;border-radius:6px;background:#1f2630;color:#d8e0ea;" +
        "border:1px solid #2a323d;font:13px/1.4 system-ui,sans-serif;cursor:pointer";
      b.onclick = on;
      box.appendChild(b);
      return b;
    };
    const done = (id) => { box.remove(); resolve(id); };

    box.innerHTML = "<h1 style='font-size:16px;margin:0 0 6px'>카메라 고르기</h1>" +
      "<p style='color:#8b97a6;font-size:12.5px;margin:0 0 16px'>권한을 허용하면 목록이 나옵니다...</p>";
    document.body.appendChild(box);

    listCameras().then((cams) => {
      box.innerHTML = "<h1 style='font-size:16px;margin:0 0 6px'>카메라 고르기</h1>" +
        "<p style='color:#8b97a6;font-size:12.5px;margin:0 0 16px'>" +
        "아이폰을 연속성 카메라로 연결했다면 목록에 같이 나옵니다. " +
        "이 화면은 데스크탑에서만 뜨고 관객 폰에서는 뜨지 않습니다.</p>";
      cams.forEach((c, i) =>
        btn((c.label || `카메라 ${i + 1}`) +
            `<br><small style="color:#7f8b99">${c.deviceId.slice(0, 24)}...</small>`,
            () => done(c.deviceId)));
      btn("<span style='color:#8b97a6'>건너뛰기 (기본 카메라로)</span>", () => done(null));
      if (!cams.length) box.innerHTML += "<p>카메라를 못 찾았습니다.</p>";
    }).catch((e) => {
      box.innerHTML = "<h1 style='font-size:16px'>카메라 권한 실패</h1>" +
        `<p style='color:#8b97a6'>${e.name}: ${e.message}</p>`;
      btn("기본 카메라로 계속", () => done(null));
    });
  });
}
