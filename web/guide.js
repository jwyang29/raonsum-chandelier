// AR 화면 아래에 뜨는 관람 안내 문구를 고른다.
//
// 🔴 무인 기간에는 설명해 줄 사람이 없다. 관객이 폰을 들고 좌대 앞에 서면
//    마커는 발밑에 있고 샹들리에는 머리 위에 있다. 둘을 한 화면에 담을 수
//    없으므로, 아무 말이 없으면 관객은 마커만 보다가 돌아간다. 실제로
//    "비추세요" 한 줄만 떠 있었다.
//
// 🔴 문구는 깜빡이면 안 된다. 매 프레임 상태가 조금씩 흔들리는데 그대로
//    글자에 먹이면 두 문장이 번갈아 뜬다. 그래서 고른 문구를 바로 쓰지 않고
//    Guide 가 붙잡는다. 아래 세 가지를 지킨다.
//      1. 새 문구가 CONFIRM 초 동안 계속 이겨야 바뀐다
//      2. 한 번 띄우면 최소 HOLD 초는 그대로 둔다
//      3. 권유성 문구(tip)는 몇 번만 보여 주고 그만둔다. 계속 뜨면 잔소리다
//
// 문구만 고치고 싶으면 TEXT 만 보면 된다. 숫자는 그 아래 NUM 에 모았다.

const QS = new URLSearchParams(location.search);
const num = (k, d) => {
  const v = parseFloat(QS.get(k));
  return Number.isFinite(v) ? v : d;
};

// ── 문구 ────────────────────────────────────────────────────
// 여기 글자만 바꾸면 됩니다. 빈 문자열 "" 로 두면 그 안내는 안 뜹니다.
export const TEXT = {
  preview:  "미리보기입니다. 드래그로 둘러보고 WASD 로 움직이세요",

  // 아직 한 번도 못 잡았을 때
  hunting:  "좌대 위의 마커를 화면에 담아 주세요",

  // 잡은 직후, 샹들리에가 화면 위쪽 밖에 있을 때.
  // 관객이 마커만 보고 있는 상태다. 이 한 줄이 이 전시의 핵심 안내다.
  lift:     "그대로 폰을 천천히 들어 올려 보세요",

  // 샹들리에가 화면 뒤에 있을 때 (몸을 돌린 상태)
  turn:     "몸을 돌려 좌대 쪽을 향해 주세요",

  // 너무 멀리 섰을 때
  far:      "좌대 가까이 다가가 보세요",

  // 마커를 오래 놓쳐 자이로로만 버티고 있을 때
  relocate: "좌대를 한 번 비추면 위치가 다시 맞습니다",

  // 다 잘 보고 있을 때 가끔 한 번씩. 눌러 보라는 것을 모르면 평생 모른다.
  tipTap:   "크리스탈을 누르면 그 손짓을 어떻게 읽었는지 보입니다",

  // 올려다본 직후 한 번. 걸어 다니며 보라는 뜻
  tipWalk:  "좌대 앞을 걸으며 각도를 바꿔 보세요",
};

// ── 숫자 ────────────────────────────────────────────────────
// 현장에서 ?far=2.4 처럼 붙여 바로 바꿀 수 있다.
export const NUM = {
  // 폰에서 좌대 한가운데까지 이보다 멀면 "가까이" 를 띄운다 (m).
  // 좌대 20cm, 관객이 2m 뒤에서 폰을 1.4m 높이로 들면 약 2.4m 다.
  // 그보다 멀면 10cm 마커가 화면에서 너무 작아 검출도 흔들린다.
  far:     num("far", 2.6),
  // 한 번 띄운 뒤 이 안쪽으로 들어오면 내린다. 경계에서 깜빡이지 않게 벌린다.
  farBack: num("farback", 2.2),

  // 샹들리에 한가운데가 화면 위 끝에서 이만큼 밖에 있으면 "들어 올리세요".
  // 1.0 이 화면 끝이다. 조금 넘겨야 끝에 걸친 상태에서 안 뜬다.
  above:   num("above", 1.05),

  // 바뀌기 전에 새 문구가 이겨야 하는 시간 (초)
  confirm: num("gconfirm", 0.7),
  // 한 번 띄우면 지키는 최소 시간 (초)
  hold:    num("ghold", 2.0),

  // 권유성 문구를 띄워 두는 시간과 다시 띄우기까지 쉬는 시간 (초)
  tipFor:  num("gtipfor", 6),
  tipRest: num("gtiprest", 40),
  // 권유성 문구를 한 관람에 보여 줄 최대 횟수
  tipMax:  num("gtipmax", 2),
};


/** 지금 상태에서 띄울 문구 하나를 고른다. 순수 함수라 따로 시험할 수 있다.
 *
 *  s.preview  미리보기 모드인가
 *  s.started  마커를 한 번이라도 잡았는가
 *  s.held     마커 없이 자이로로 버틴 시간 (초)
 *  s.hint     held 가 이만큼을 넘으면 다시 비춰 달라고 한다 (초)
 *  s.dist     폰에서 좌대 한가운데까지 (m). 못 잡았으면 null
 *  s.behind   샹들리에가 카메라 뒤에 있는가
 *  s.ny       샹들리에 한가운데의 화면 세로 위치. 1 이 위 끝, -1 이 아래 끝
 *  s.settled  잡은 뒤 흔들림 없이 보고 있는 시간 (초)
 *
 *  돌려주는 값은 { id, text, tip } 이다. id 는 같은 안내인지 보는 데만 쓴다.
 */
const BLANK = { id: "", text: "", tip: false };

export function choose(s) {
  const t = (id, tip) => ({ id, text: TEXT[id] || "", tip: !!tip });

  if (s.preview) return t("preview");
  if (!s.started) return t("hunting");

  // 🔴 놓친 상태가 가장 급하다. 이때 다른 안내를 띄우면 관객은 화면이
  //    맞은 줄 알고 그대로 서 있는다.
  if (s.held > s.hint) return t("relocate");

  if (s.behind) return t("turn");

  // 들어 올리라는 안내가 거리보다 앞선다. 마커를 비추는 동안은 거의 항상
  // 가까이 있고, 그때 "가까이 오세요" 는 틀린 말이 된다.
  if (s.ny !== null && s.ny > NUM.above) return t("lift");

  if (s.dist !== null && s.dist > NUM.far) return t("far");

  // 샹들리에가 화면에 들어왔다. 이제부터는 권유만 한다.
  if (s.settled > 2) return t("tipWalk", true);
  return BLANK;
}


/** 고른 문구를 붙잡아 깜빡임을 없앤다. 화면에 실제로 쓸 글자를 돌려준다. */

// 권유성 문구. 몇 번만 하고 그만둔다.
const TIPS = ["tipWalk", "tipTap"];

export class Guide {
  constructor() {
    this.id = "";          // 지금 띄워 둔 안내
    this.text = "";
    this.since = 0;        // 띄운 시각
    this.cand = "";        // 이기고 있는 후보
    this.candSince = 0;
    this.shown = {};       // 권유를 몇 번 띄웠나
    this.rested = {};      // 마지막으로 내린 시각
    this.turn = 0;         // 권유를 돌아가며 하나씩
  }

  /** now 는 초 단위. tick 마다 부른다. */
  update(s, now) {
    let pick = choose(s);

    // 권유는 쉬는 중이거나 할 만큼 했으면 아예 후보에서 뺀다.
    // 🔴 여기서 횟수를 올리면 안 된다. 이 함수는 매 tick 돌아간다.
    //    실제로 화면에 올라간 순간에만 센다.
    if (pick.tip) pick = this.eligibleTip(now) || BLANK;

    if (pick.id !== this.cand) {
      this.cand = pick.id;
      this.candSince = now;
    }

    const confirmed = now - this.candSince >= NUM.confirm;
    const held = now - this.since >= NUM.hold;

    // 🔴 급한 안내는 기다리지 않고 바로 바꾼다. 마커를 놓쳤는데 2초 동안
    //    "걸으며 보세요" 가 남아 있으면 관객은 그대로 서 있는다.
    const instant = pick.id === "relocate" || pick.id === "hunting";

    // 🔴 "비춰 주세요" 를 띄워 둔 상태는 아직 아무것도 안 되는 상태다.
    //    그러다 마커를 잡은 순간이 이 전시에서 가장 중요한 0.5초다. 여기서
    //    hold 를 지키면 관객은 화면이 맞았는데도 2초 동안 계속 바닥만 본다.
    //    그래서 띄워 둔 것이 없거나 "비춰 주세요" 일 때는 hold 를 건너뛴다.
    //    대신 confirm 은 그대로 둔다. 한 프레임 깜빡임에 넘어가면 안 된다.
    const waiting = this.id === "" || this.id === "hunting";

    if (pick.id !== this.id && (instant || (confirmed && (held || waiting)))) {
      this.retire(now);
      this.id = pick.id;
      this.text = pick.text;
      this.since = now;
      if (TIPS.includes(pick.id)) {
        this.shown[pick.id] = (this.shown[pick.id] || 0) + 1;
        this.turn = TIPS.indexOf(pick.id) + 1;
      }
    }

    // 권유는 혼자 사라진다. 계속 떠 있으면 안내가 아니라 자막이다.
    if (TIPS.includes(this.id) && now - this.since > NUM.tipFor) {
      this.retire(now);
      this.id = "";
      this.text = "";
      this.since = now;
    }

    return this.text;
  }

  /** 내리는 문구가 권유였으면 쉬기 시작한 시각을 적어 둔다. */
  retire(now) {
    if (TIPS.includes(this.id)) this.rested[this.id] = now;
  }

  /** 아직 할 말이 남은 권유를 하나 고른다. 세지는 않는다. 없으면 null. */
  eligibleTip(now) {
    for (let i = 0; i < TIPS.length; i++) {
      const id = TIPS[(this.turn + i) % TIPS.length];
      if ((this.shown[id] || 0) >= NUM.tipMax) continue;
      const rest = this.rested[id];
      if (rest !== undefined && now - rest < NUM.tipRest) continue;
      return { id, text: TEXT[id] || "", tip: true };
    }
    return null;
  }
}
