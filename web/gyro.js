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

export class Gyro {
  constructor() {
    this.q = new THREE.Quaternion();
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
      this.q.setFromEuler(this._euler);
      this.q.multiply(this._q1);
      this.q.multiply(this._q0.setFromAxisAngle(this._zee, -orient));
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
