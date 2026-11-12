#!/usr/bin/env python3
"""몇 명이 열어 봤는지 날짜별로 센다.

    python3 hub/visits.py            전체
    python3 hub/visits.py --days 7   최근 7일
    python3 hub/visits.py --clear    다 지운다 (시험 자국 치울 때만)

읽는 자리는 web/visit.js 가 쓰는 곳과 같다.

    visits/2026-11-12/home/<자동키> = 1762934...

세 칸의 뜻:
    열람   설명 페이지를 연 수. QR 을 찍은 사람이다
    AR     AR 보기 버튼까지 누른 수
    시작   안내를 읽고 시작하기를 누른 수. 카메라를 묻는 데까지 간 수다

🔴 관객을 구분하지 않는다. 같은 사람이 두 번 오면 두 번 센다. 반대로 한 번
   열고 새로고침을 열 번 해도 한 번만 센다 (탭 단위). 그래서 이 숫자는
   "사람 수" 가 아니라 "열어 본 횟수" 다. 그 이상은 알 수 없고, 알려고
   남기지도 않았다.
"""
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_v1

hub_v1.load_env_file()

PAGES = [("home", "열람"), ("ar", "AR"), ("start", "시작")]


# 🔴 파이썬의 자릿수는 글자 수를 센다. 한글은 터미널에서 두 칸을 먹으므로
#    f"{'날짜':<12}" 은 눈으로 보면 네 칸이 밀린다. 실제 폭으로 맞춘다.
def width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def left(s, n):
    return s + " " * max(0, n - width(s))


def right(s, n):
    return " " * max(0, n - width(s)) + s


def offline(e):
    """🔴 망이 끊겼을 때 파이썬 역추적을 쏟지 않는다. setcal.py 와 같은 이유다."""
    sys.exit("\n[visits] 인터넷에 못 닿습니다. 숫자는 그대로 있습니다.\n"
             "  와이파이를 확인하고 다시 돌리세요.\n"
             f"  ({e.reason if hasattr(e, 'reason') else e})")


def get(up, path, shallow=False):
    url = f"{up.url}/{path}.json" + ("?shallow=true" if shallow else "")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            sys.exit("읽기가 막혀 있습니다. 콘솔 규칙 탭에 hub/firebase_rules.json 을\n"
                     "다시 붙여넣고 게시하세요. visits 칸이 아직 없는 것 같습니다.")
        raise
    except urllib.error.URLError as e:
        offline(e)


def take(name, cast=int):
    a = sys.argv[1:]
    if name not in a:
        return None
    i = a.index(name) + 1
    return cast(a[i]) if i < len(a) else None


def main():
    up = hub_v1.Uploader()
    print(f"[visits] {up.url}/visits.json\n")

    if "--clear" in sys.argv:
        ok = input("visits 를 통째로 지웁니다. 되돌릴 수 없습니다. 지울까요? (yes) ")
        if ok.strip() != "yes":
            sys.exit("그만둡니다.")
        req = urllib.request.Request(up._endpoint("visits"), method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=20).read()
        except urllib.error.URLError as e:
            offline(e)
        print("지웠습니다.")
        return

    # 🔴 통째로 받지 않는다. 날짜 목록만 먼저 얕게 받고, 날짜마다 다시 얕게
    #    받아 열쇠 수만 센다. 값은 필요 없다. 수천 건이 쌓여도 가볍다.
    days = get(up, "visits", shallow=True)
    if not days:
        print("아직 아무도 안 열었습니다.")
        print("(규칙을 게시하고 웹을 올린 뒤부터 쌓입니다. 그 전 기록은 없습니다)")
        return

    keep = take("--days")
    names = sorted(days.keys())
    if keep:
        names = names[-keep:]

    bar = "-" * 33
    print(left("날짜", 12) + "".join(right(t, 7) for _, t in PAGES))
    print(bar)
    total = {k: 0 for k, _ in PAGES}
    for day in names:
        row = []
        for key, _ in PAGES:
            got = get(up, f"visits/{day}/{key}", shallow=True)
            n = len(got) if isinstance(got, dict) else 0
            total[key] += n
            row.append(n)
        print(left(day, 12) + "".join(right(str(v), 7) for v in row))

    print(bar)
    print(left("합계", 12) + "".join(right(str(total[k]), 7) for k, _ in PAGES))

    if total["home"]:
        to_ar = total["ar"] / total["home"] * 100
        print(f"\n설명을 연 사람 중 {to_ar:.0f}% 가 AR 까지 갔습니다.")
    if total["ar"]:
        to_go = total["start"] / total["ar"] * 100
        print(f"AR 을 연 사람 중 {to_go:.0f}% 가 시작하기를 눌렀습니다.")
    print("\n사람 수가 아니라 열어 본 횟수입니다. 관객을 구분하지 않습니다.")


if __name__ == "__main__":
    main()
