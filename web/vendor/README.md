# 왜 여기에 복사해 두는가

전시는 이틀 동안 사람 없이 돌아간다. CDN 한 곳이 끊기면 그 시간 동안 관객 폰에
아무것도 안 뜬다. 그래서 받아 와서 저장소에 넣는다.

| 파일 | 받은 곳 | 버전 |
|---|---|---|
| aframe.min.js | https://aframe.io/releases/1.3.0/aframe.min.js | 1.3.0 |
| aframe-ar.js | https://cdn.jsdelivr.net/gh/AR-js-org/AR.js@3.4.5/aframe/build/aframe-ar.js | 3.4.5 |
| camera_para.dat | https://ar-js-org.github.io/AR.js/data/data/camera_para.dat | AR.js 기본값 |

받은 날 2026-10-29.

🔴 camera_para.dat 를 빼먹기 쉽다. AR.js 는 이 파일을 지정하지 않으면
ar-js-org.github.io 에서 직접 받아 온다. 못 받으면 ARToolKit 이 아예 초기화되지
않아서 마커가 하나도 안 잡힌다. app.js 의 arjs 에 cameraParametersUrl 로
이 파일을 못박아 두었다.

🔴 버전을 올리지 말 것. A-Frame 1.3.0 은 three.js r137 이고, 코드가 그 전제로
쓰여 있다 (CapsuleGeometry 없음, iridescence 없음). AR.js 3.4.5 와 짝이다.

## 🔴 aframe-ar.js 를 한 군데 고쳐 두었다

AR.js 3.4.5 는 **바코드 마커의 size 를 버린다.** arjs-anchor 가 ArMarkerControls
로 넘길 파라미터를 만들 때, 바코드일 때만 기본값을 복사하지 않고 객체를 통째로
새로 만드는데 거기에 size 가 빠져 있다.

    "barcode"===A.data.type ? C={type:...,changeMatrixMode:...,barcodeValue:...,markersAreaEnabled:!1}

hiro, kanji, area, pattern 은 전부 defaultMarkerParameters 를 복사해 쓰므로
멀쩡하다. 바코드만 그렇다.

그래서 `<a-marker size="0.1">` 을 줘도 검출기는 기본값 1 을 쓴다. 월드가
"마커 한 변 = 1 단위" 로 만들어지고, 실제 마커가 10cm 면 모든 것이 10배 작아진다.
샹들리에를 마커 위 1.73m 에 두면 17cm 로 내려앉아 바닥에 깔린다.

고친 내용은 `size:A.data.size,` 한 토막을 그 객체에 넣은 것뿐이다.

🔴 **이 파일을 다시 받으면 이 수정이 사라진다.** 다시 받았으면 위 문자열을
찾아서 size 를 도로 넣어야 한다.

## 🔴 고친 뒤에는 ?v= 번호를 올릴 것

이 파일들은 2MB 라 폰이 오래 들고 있는다. 고쳐서 배포해도 안 받아 간다.
현장에서 "고쳤는데 그대로인데요" 가 되는 자리다.

부르는 곳이 여섯 군데다. 전부 같이 올려야 한다.

    web/ar.html      web/venue.html   web/camtest.html
    web/app.js       web/hero.js      web/index.html
