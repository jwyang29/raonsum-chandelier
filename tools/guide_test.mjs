globalThis.location = { search: "" };
const { Guide, choose, TEXT, NUM } = await import(
  new URL("../web/guide.js", import.meta.url).href);

let fail = 0;
const eq = (got, want, what) => {
  const ok = got === want;
  if (!ok) fail++;
  console.log(`${ok ? "  ok  " : "  FAIL"} ${what}  ->  ${JSON.stringify(got)}${ok ? "" : "  (기대: " + JSON.stringify(want) + ")"}`);
};

const base = { preview:false, started:true, held:0, hint:12, dist:1.7,
               behind:false, ny:0, settled:0 };

console.log("choose() 단독");
eq(choose({...base, preview:true}).id, "preview", "미리보기");
eq(choose({...base, started:false}).id, "hunting", "아직 못 잡음");
eq(choose({...base, held:20}).id, "relocate", "오래 놓침");
eq(choose({...base, behind:true}).id, "turn", "뒤를 봄");
eq(choose({...base, ny:1.6}).id, "lift", "샹들리에가 화면 위 밖");
eq(choose({...base, ny:0.5}).id, "", "화면 안에 들어옴");
eq(choose({...base, dist:3.1}).id, "far", "멀리 섬");
eq(choose({...base, dist:3.1, ny:1.6}).id, "lift", "멀어도 들어올리기가 먼저");
eq(choose({...base, held:20, ny:1.6}).id, "relocate", "놓침이 가장 급함");
eq(choose({...base, settled:5}).tip, true, "안정되면 권유");

console.log("\nGuide 붙잡기");
const g = new Guide();
let t = 0;
const step = (s, dt) => { t += dt; return g.update({...base, ...s}, t); };

eq(step({started:false}, 0.1), TEXT.hunting, "못 잡았을 때는 바로 뜬다");
// 0.1초만 들어 올렸다 내리면 바뀌면 안 된다
step({ny:1.6}, 0.2);
eq(g.text, TEXT.hunting, "0.2초짜리 흔들림에는 안 바뀐다");
step({ny:1.6}, 0.8);
eq(g.text, TEXT.lift, "잡은 직후 0.8초면 바뀐다");
// 바뀐 직후 다른 후보가 와도 HOLD 동안은 지킨다
step({ny:0.2, dist:3.1}, 0.8);
eq(g.text, TEXT.lift, "띄운 지 2초 안에는 안 뺏긴다");
step({ny:0.2, dist:3.1}, 1.5);
eq(g.text, TEXT.far, "2초 넘으면 넘어간다");
// 놓치면 즉시
eq(step({held:20}, 0.05), TEXT.relocate, "놓치면 기다리지 않는다");

console.log("\n권유는 몇 번만 한다");
const h = new Guide();
let u = 0, seen = [];
for (let i = 0; i < 4000; i++) {
  u += 0.1;
  const txt = h.update({...base, settled:9}, u);
  if (txt && seen[seen.length-1] !== txt) seen.push(txt);
}
console.log("  400초 동안 띄운 권유:", seen.length, "번");
eq(seen.length <= NUM.tipMax * 2, true, `최대 ${NUM.tipMax*2}번을 안 넘는다`);
eq(new Set(seen).size, 2, "두 문구가 번갈아 나온다");

console.log(fail ? `\n${fail}개 실패` : "\n전부 통과");
process.exit(fail ? 1 : 0);
