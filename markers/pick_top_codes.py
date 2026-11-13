#!/usr/bin/env python3
"""큐브 윗면에 쓸 바코드 번호를 고른다.

🔴 번호를 눈으로 고르면 안 된다. 3x3 격자 64개는 서로 한 칸만 다른 것이
   수두룩하고, 마커는 네 방향 중 어느 쪽으로 붙어도 읽히므로 회전까지 넣어
   재야 한다. 한 칸이 잘못 읽혀 다른 마커가 되면 월드가 통째로 그리로 끌려간다.

무엇을 피하려고 거리를 재는가:
   옆면끼리 뒤바뀌면   샹들리에가 90도 돈다
   옆면과 밑면/윗면이  샹들리에가 90도 기울어진다. 이쪽이 훨씬 나쁘다
   바닥/천장과 뒤바뀌면 월드 원점이 큐브 자리로 날아간다. 제일 나쁘다

그래서 요구 조건을 이렇게 둔다.
   바닥 네 장 + 천장 한 장과  거리 3 이상
   다른 큐브의 모든 면과      거리 2 이상
   같은 큐브의 다섯 면과      거리 4 이상 (기울어짐을 막는다)

    python3 markers/pick_top_codes.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GRIDS = {int(k): v for k, v in
         json.load(open(os.path.join(HERE, "grids.json"))).items()}

FLOOR = [0, 7, 44, 63]
CEILING = [26]
CUBE_CODES = [[21, 52, 50, 38, 11], [14, 13, 28, 41, 19], [42, 49, 56, 25, 22]]


def inner(code):
    """5x5 에서 바깥 테두리를 뺀 가운데 3x3. 이게 실제 코드다."""
    g = GRIDS[code]
    return [row[1:4] for row in g[1:4]]


def rot90(m):
    return [list(r) for r in zip(*m[::-1])]


def dist(a, b):
    """회전까지 넣은 최소 해밍 거리. b 를 네 방향으로 돌려 가장 가까운 것을 센다."""
    best = 99
    gb = inner(b)
    for _ in range(4):
        d = sum(1 for y in range(3) for x in range(3)
                if inner(a)[y][x] != gb[y][x])
        best = min(best, d)
        gb = rot90(gb)
    return best


def main():
    used = set(FLOOR + CEILING + [c for cube in CUBE_CODES for c in cube])
    anchors = FLOOR + CEILING

    print("지금 쓰는 번호")
    print(f"  바닥   {FLOOR}")
    print(f"  천장   {CEILING}")
    for i, cube in enumerate(CUBE_CODES):
        print(f"  큐브{i+1}  옆면 {cube[:4]}  밑면 {cube[4]}")

    # 먼저 지금 묶음이 정말 그 거리를 지키는지 확인한다. 주석만 믿지 않는다.
    print("\n지금 묶음이 지키고 있는 거리")
    mn = min(dist(a, b) for i, a in enumerate(anchors) for b in anchors[i+1:])
    print(f"  바닥+천장 서로       최소 {mn}")
    for i, cube in enumerate(CUBE_CODES):
        side = min(dist(a, b) for j, a in enumerate(cube[:4]) for b in cube[j+1:4])
        bot = min(dist(cube[4], s) for s in cube[:4])
        print(f"  큐브{i+1} 옆면끼리 최소 {side}   밑면과 옆면 최소 {bot}")

    picked = []
    print("\n윗면 후보 (조건: 바닥천장>=3, 다른큐브>=2, 같은큐브>=4)")
    for ci, cube in enumerate(CUBE_CODES):
        others = [c for cj, cu in enumerate(CUBE_CODES) if cj != ci for c in cu]
        best = None
        for cand in range(64):
            if cand in used:
                continue
            d_anchor = min(dist(cand, a) for a in anchors)
            d_other = min(dist(cand, o) for o in others) if others else 9
            d_self = min(dist(cand, s) for s in cube)
            if d_anchor < 3 or d_other < 2 or d_self < 4:
                continue
            # 같은 큐브와 제일 멀고, 그다음 바닥천장과 먼 것을 고른다
            score = (d_self, d_anchor, d_other, -cand)
            if best is None or score > best[0]:
                best = (score, cand, d_anchor, d_other, d_self)
        if best is None:
            print(f"  큐브{ci+1}  없음. 조건을 못 맞춥니다")
            picked.append(None)
            continue
        _, cand, da, do, ds = best
        used.add(cand)
        picked.append(cand)
        print(f"  큐브{ci+1}  {cand:>2}   바닥천장 {da}   다른큐브 {do}   같은큐브 {ds}")

    if any(p is None for p in picked):
        sys.exit("\n조건을 못 맞춘 큐브가 있습니다. 윗면을 넣지 마세요.")

    print("\nCUBE_CODES 에 넣을 모양 (여섯째가 윗면)")
    rows = [f"[{', '.join(str(c) for c in cube)}, {picked[i]}]"
            for i, cube in enumerate(CUBE_CODES)]
    print("  " + ",\n  ".join(rows))

    # 마지막으로 전체를 다시 한 번 확인한다. 고른 뒤의 전수 검사다.
    allc = FLOOR + CEILING + [c for i, cube in enumerate(CUBE_CODES)
                              for c in cube + [picked[i]]]
    assert len(allc) == len(set(allc)), "번호가 겹칩니다"
    worst = min((dist(a, b), a, b) for i, a in enumerate(allc) for b in allc[i+1:])
    print(f"\n전체 {len(allc)}개 중 가장 가까운 두 개: "
          f"{worst[1]} 과 {worst[2]}, 거리 {worst[0]}")
    for i, cube in enumerate(CUBE_CODES):
        six = cube + [picked[i]]
        w = min((dist(a, b), a, b) for j, a in enumerate(six) for b in six[j+1:])
        flat = [cube[4], picked[i]]
        wf = min(dist(f, s) for f in flat for s in cube[:4])
        print(f"  큐브{i+1} 여섯 면 중 최소 {w[0]} ({w[1]}/{w[2]})   "
              f"눕힌면과 선면 최소 {wf}")


if __name__ == "__main__":
    main()
