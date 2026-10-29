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
