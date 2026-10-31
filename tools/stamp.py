#!/usr/bin/env python3
"""모든 모듈 import 에 빌드 번호를 붙인다.

🔴 ES 모듈은 import 주소가 그대로 캐시 열쇠다. ar.html 의 app.js 에만 ?v= 를
   붙여 봐야, app.js 가 불러오는 config.js / marker_anchor.js / pose.js 는
   옛것이 그대로 쓰인다. GitHub Pages 가 10분 캐시하므로 그 사이에 고친 것이
   절반만 반영되고, 현장에서 "고쳤는데 왜 그대로지" 가 된다. 실제로 그랬다.

   그래서 고칠 때마다 이걸 돌려 전부 한 번에 올린다.
       python3 tools/stamp.py 1101l
"""
import io, os, re, sys

VER = sys.argv[1] if len(sys.argv) > 1 else None
if not VER:
    sys.exit("쓰는 법: python3 tools/stamp.py 1101l")

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
# from "./x.js" 뿐 아니라 import "./x.js" (부수효과 전용) 와 import("./x.js") 도 잡는다.
# marker_anchor.js 가 바로 그 형태라 한 번 놓쳤다. 가장 중요한 파일이었다.
pat = re.compile(r'((?:from|import)\s*\(?\s*"\./)([A-Za-z0-9_\-/]+\.js)(\?v=[^"]*)?(")')
n = 0
for name in sorted(os.listdir(WEB)):
    if not name.endswith(".js"):
        continue
    p = os.path.join(WEB, name)
    s = io.open(p, encoding="utf-8").read()
    out = pat.sub(lambda m: m.group(1) + m.group(2) + "?v=" + VER + m.group(4), s)
    if out != s:
        io.open(p, "w", encoding="utf-8").write(out)
        n += len(pat.findall(s))
        print("  " + name)

for name in ("ar.html", "index.html"):
    p = os.path.join(WEB, name)
    if not os.path.exists(p):
        continue
    s = io.open(p, encoding="utf-8").read()
    out = re.sub(r'(src="\./)([A-Za-z0-9_\-/]+\.js)(\?v=[^"]*)?(")',
                 lambda m: m.group(1) + m.group(2) + "?v=" + VER + m.group(4), s)
    if out != s:
        io.open(p, "w", encoding="utf-8").write(out)
        print("  " + name)

p = os.path.join(WEB, "app.js")
s = io.open(p, encoding="utf-8").read()
s2 = re.sub(r'const VERSION = "build [^"]*";', 'const VERSION = "build ' + VER + '";', s)
if s2 != s:
    io.open(p, "w", encoding="utf-8").write(s2)
    print("  VERSION -> build " + VER)
print("\nimport " + str(n) + "군데에 ?v=" + VER + " 를 붙였습니다")
