// 기기 방향 센서. 마커가 하나도 안 보일 때 샹들리에를 제자리에 붙잡아 두는 데 쓴다.
//
// AR.js 는 카메라를 원점에 두고 마커를 움직인다. 그래서 씬 공간이 곧 카메라 공간이고,
// 마커가 사라졌을 때 포즈를 그대로 두면 샹들리에가 화면에 붙어 같이 따라온다.
// 고개를 들면 샹들리에도 같이 올라가 버려서 천장에 있는 것처럼 보이지 않는다.
// 기기가 얼마나 돌았는지 알면 그만큼 되돌려서 실제 공간에 머물게 할 수 있다.
//
// 좌표 변환은 three.js 의 DeviceOrientationControls 가 쓰던 식을 그대로 따른다.
// alpha/beta/gamma 를 YXZ 오일러로 보고, 기기 축을 카메라 축에 맞추는 회전을 곱한다.

const DEG = Math.PI / 180;

// 🔴 기기 방향 센서는 가만히 들고 있어도 값이 떤다. 날것을 그대로 쓰면
//    마커를 놓친 동안 월드가 그 떨림을 그대로 받는다. 그런데 샹들리에는
//    머리 위에 있고 마커는 발밑 좌대에 있어서, 보는 자세에서는 마커가
//    화면 밖인 시간이 대부분이다. 곧 떨림의 대부분이 이 길에서 나온다.
//    marker_anchor 의 smooth 와 데드밴드는 마커 길에만 걸려 있어서
//    여기는 지금까지 아무것도 안 걸러지고 있었다.
//
//    ?gyrosmooth=0.1  낮을수록 둔하고 안정적 (0 이면 아예 안 따라간다)
//    ?gyrodead=0.5    이 각도(도) 안쪽으로 떨면 아예 무시한다
const GQ = new URLSearchParams(location.search);
const gnum = (k, d) => {
  const v = parseFloat(GQ.get(k));
  return Number.isFinite(v) ? v : d;
};
export const GYRO_TUNE = {
  smooth: gnum("gyrosmooth", 0.12),
  dead: gnum("gyrodead", 0.6),
};

export class Gyro {
  constructor() {
    this.q = new THREE.Quaternion();
    this._target = new THREE.Quaternion();
    this._first = true;
    this.active = false;
    this.needsPermission =
      typeof DeviceOrientationEvent !== "undefined" &&
      typeof DeviceOrientationEvent.requestPermission === "function";

    this._zee = new THREE.Vector3(0, 0, 1);
    this._euler = new THREE.Euler();
    this._q0 = new THREE.Quaternion();
    // 기기 좌표계를 카메라 좌표계로 돌리는 고정 회전 (x 축 기준 -90도)
    this._q1 = new THREE.Quaternion(-Math.sqrt(0.5), 0, 0, Math.sqrt(0.5));

    this._onOrient = (e) => {
      if (e.alpha === null || e.alpha === undefined) return;
      const orient = (screen.orientation && screen.orientation.angle
        ? screen.orientation.angle
        : window.orientation || 0) * DEG;

      this._euler.set(e.beta * DEG, e.alpha * DEG, -e.gamma * DEG, "YXZ");
      const t = this._target;
      t.setFromEuler(this._euler);
      t.multiply(this._q1);
      t.multiply(this._q0.setFromAxisAngle(this._zee, -orient));

      // 🔴 첫 값은 그대로 받는다. 안 그러면 0 에서부터 천천히 기어온다.
      if (this._first) {
        this.q.copy(t);
        this._first = false;
      } else {
        // 떨림만큼 움직였으면 아예 무시한다. 가만히 들고 있을 때 그래픽이
        // 계속 바뀌는 것이 이것 때문이다.
        const ang = 2 * Math.acos(Math.min(1, Math.abs(this.q.dot(t)))) / DEG;
        if (ang > GYRO_TUNE.dead) this.q.slerp(t, GYRO_TUNE.smooth);
      }
      this.active = true;
    };
  }

  // 아이폰(iOS 13 이상)은 사용자 제스처 안에서 권한을 받아야 한다.
  // 안드로이드와 그 이전 iOS 는 바로 붙는다.
  async start() {
    if (this.needsPermission) {
      try {
        const res = await DeviceOrientationEvent.requestPermission();
        if (res !== "granted") return false;
      } catch {
        return false;
      }
    }
    window.addEventListener("deviceorientation", this._onOrient, true);
    return true;
  }

  stop() {
    window.removeEventListener("deviceorientation", this._onOrient, true);
    this.active = false;
  }
}
