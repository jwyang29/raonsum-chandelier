"""
전시 꾸밈용 비정형 오브제 생성기 (Blender 메타볼 기반)

레퍼런스의 형태 언어를 셋으로 나눠 만든다.
  arc     휘어진 관 모양. 끝이 가늘어지고 갈고리처럼 감긴다
  loop    구멍이 뚫린 고리. 도넛이나 매듭에 가깝다
  ribbon  납작하게 퍼진 판. 바닥에 눕혀 찍기 좋다

실행:
  /Applications/Blender.app/Contents/MacOS/Blender -b --python make_blobs.py -- \
      --out stl --count 6 --size 80

옵션:
  --size   가장 긴 변의 길이 (mm)
  --shell  0 이 아니면 Solidify 로 두께를 준 껍데기로 만든다 (기본 0, 아래 주석 참고)
  --seed   난수 씨앗

⚠️ --shell 은 기본으로 끈다. FDM 에서 필라멘트를 아끼는 더 좋은 방법은
   속이 찬 STL 을 그대로 두고 슬라이서에서 인필 0% 로 뽑는 것이다.
   모델 자체를 껍데기로 만들면 안쪽 면까지 벽으로 찍혀서 오히려 더 쓰고,
   내부 면 때문에 투명도도 탁해진다.
"""

import bpy, bmesh, math, random, sys, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

def arg(name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default

OUT     = arg("--out", "stl")
COUNT   = arg("--count", 6, int)
SIZE_MM = arg("--size", 80.0, float)
SHELL   = arg("--shell", 0.0, float)
SEED    = arg("--seed", 7, int)

os.makedirs(OUT, exist_ok=True)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.metaballs, bpy.data.objects):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def wobble(rng, n=3):
    """부드러운 난수 곡선 하나. 사인 몇 개를 겹쳐 흐르는 느낌을 만든다."""
    terms = [(rng.uniform(0.4, 1.3), rng.uniform(0, math.tau), rng.uniform(1, 3)) for _ in range(n)]
    def f(t):
        return sum(a * math.sin(t * w * math.tau + p) for a, p, w in terms)
    return f


def path_arc(rng):
    fx, fy, fz = wobble(rng), wobble(rng), wobble(rng)
    bend = rng.uniform(0.9, 1.8)
    def p(t):
        a = (t - 0.5) * math.pi * bend
        return Vector((math.sin(a) * 1.6 + 0.25 * fx(t),
                       0.35 * fy(t),
                       -math.cos(a) * 1.1 + 0.25 * fz(t)))
    return p


def path_loop(rng):
    fr, fz = wobble(rng), wobble(rng)
    squash = rng.uniform(0.55, 0.95)
    def p(t):
        a = t * math.tau
        r = 1.25 + 0.3 * fr(t)
        return Vector((math.cos(a) * r, math.sin(a) * r * squash, 0.38 * fz(t)))
    return p


def path_ribbon(rng):
    fx, fy = wobble(rng), wobble(rng)
    def p(t):
        return Vector(((t - 0.5) * 3.0 + 0.5 * fx(t), 0.9 * fy(t), 0.0))
    return p


FAMILIES = {"arc": path_arc, "loop": path_loop, "ribbon": path_ribbon}


def keep_largest(obj):
    """메타볼이 끊어져 생긴 부스러기를 버리고 가장 큰 덩어리만 남긴다.
    떠다니는 조각이 있으면 슬라이서에서 그대로 작은 점으로 찍힌다."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")

    parts = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if len(parts) <= 1:
        return obj
    parts.sort(key=lambda o: len(o.data.polygons), reverse=True)
    biggest = parts[0]
    for o in parts[1:]:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.objects.active = biggest
    biggest.select_set(True)
    return biggest


def build(kind, seed, steps=70):
    rng = random.Random(seed)
    path = FAMILIES[kind](rng)

    bpy.ops.object.metaball_add(type="BALL", location=(0, 0, 0))
    obj = bpy.context.object
    mb = obj.data
    mb.resolution = 0.045          # 작을수록 매끈하고 무겁다
    mb.render_resolution = 0.045

    flat = kind == "ribbon"
    base = rng.uniform(0.30, 0.42)
    bulge = wobble(rng, 2)   # 굵기도 흐르게. 레퍼런스처럼 불룩했다 가늘어진다

    for i in range(steps):
        t = i / (steps - 1)
        pos = path(t)
        taper = math.sin(math.pi * t) ** 0.4
        r = base * (0.40 + 0.60 * taper) * (0.80 + 0.40 * bulge(t))
        r = max(r, base * 0.30)        # 너무 가늘면 끊어진다

        el = mb.elements.new(type="BALL")
        el.co = pos
        el.radius = r * 2.0
        el.stiffness = 2.0

    # metaball_add 가 원점에 만든 첫 요소를 경로 위로 옮긴다
    mb.elements[0].co = path(0.0)
    mb.elements[0].radius = base * 1.0

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.name = f"{kind}_{seed}"
    obj = keep_largest(obj)
    if flat:
        obj.scale.z = 0.28       # 눌러서 판으로. 바닥에 눕혀 찍기 좋다
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # 크기를 mm 로 맞춘다 (Blender 1 unit = 1 mm 로 내보낸다)
    dims = obj.dimensions
    longest = max(dims)
    if longest > 0:
        obj.scale = (SIZE_MM / longest,) * 3
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # 바닥을 Z=0 에 올린다
    zmin = min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
    obj.location.z -= zmin
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    if SHELL > 0:
        m = obj.modifiers.new("shell", "SOLIDIFY")
        m.thickness = SHELL
        m.offset = 1.0
        bpy.ops.object.modifier_apply(modifier=m.name)

    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def export(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True,
                              global_scale=1.0, apply_modifiers=True)
    except AttributeError:
        bpy.ops.export_mesh.stl(filepath=path, use_selection=True, global_scale=1.0)


def main():
    kinds = ["arc", "loop", "ribbon"]
    made = []
    for i in range(COUNT):
        clear()
        kind = kinds[i % len(kinds)]
        seed = SEED + i * 101
        obj = build(kind, seed)
        name = f"{kind}_{seed}.stl"
        export(obj, os.path.join(OUT, name))
        tris = len(obj.data.polygons)
        made.append((name, tuple(round(d, 1) for d in obj.dimensions), tris))
        print(f"  {name}  {made[-1][1]} mm  면 {tris}")
    print(f"\n{len(made)}개를 {OUT}/ 에 저장했습니다")


main()
