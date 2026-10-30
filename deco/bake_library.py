"""
크리스탈 형태 라이브러리를 굽는다.

관객 폰에서 마칭큐브를 돌리지 않기 위해, 블롭 몇 개를 미리 만들어
web/blobs.json 으로 내보낸다. 폰은 이걸 불러다 크기와 비틀림만 입힌다.

실행:
  /Applications/Blender.app/Contents/MacOS/Blender -b --python bake_library.py -- \
      --out ../web/blobs.json --per-kind 6 --tris 700
"""

import bpy, json, math, os, random, sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d, c=str):
    return c(argv[argv.index(n)+1]) if n in argv else d

OUT      = arg("--out", "../web/blobs.json")
PER_KIND = arg("--per-kind", 6, int)
TRIS     = arg("--tris", 700, int)
SEED     = arg("--seed", 1000, int)
SMOOTH      = arg("--smooth", 0.5, float)    # 데시메이트가 남긴 각을 편다
SMOOTH_ITER = arg("--smooth-iter", 3, int)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for blk in (bpy.data.meshes, bpy.data.metaballs, bpy.data.objects):
        for b in list(blk):
            if b.users == 0:
                blk.remove(b)


def wobble(rng, n=3):
    T = [(rng.uniform(0.4, 1.3), rng.uniform(0, math.tau), rng.uniform(1, 3)) for _ in range(n)]
    return lambda t: sum(a * math.sin(t * w * math.tau + p) for a, p, w in T)


def path_arc(rng):
    fx, fy, fz, bend = wobble(rng), wobble(rng), wobble(rng), rng.uniform(0.9, 1.8)
    def p(t):
        a = (t - 0.5) * math.pi * bend
        return (math.sin(a)*1.6 + 0.25*fx(t), 0.35*fy(t), -math.cos(a)*1.1 + 0.25*fz(t))
    return p


def path_loop(rng):
    fr, fz, sq = wobble(rng), wobble(rng), rng.uniform(0.55, 0.95)
    def p(t):
        a, r = t*math.tau, 1.25 + 0.3*fr(t)
        return (math.cos(a)*r, math.sin(a)*r*sq, 0.38*fz(t))
    return p


def path_ribbon(rng):
    fx, fy = wobble(rng), wobble(rng)
    return lambda t: ((t-0.5)*3.0 + 0.5*fx(t), 0.9*fy(t), 0.0)


FAMILIES = {"arc": path_arc, "loop": path_loop, "ribbon": path_ribbon}


def keep_largest(obj):
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
    for o in parts[1:]:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.objects.active = parts[0]
    parts[0].select_set(True)
    return parts[0]


def build(kind, seed, steps=70):
    rng = random.Random(seed)
    path = FAMILIES[kind](rng)
    bpy.ops.object.metaball_add(type="BALL", location=(0, 0, 0))
    obj = bpy.context.object
    mb = obj.data
    mb.resolution = mb.render_resolution = 0.05

    base = rng.uniform(0.30, 0.42)
    bulge = wobble(rng, 2)
    for i in range(steps):
        t = i / (steps - 1)
        taper = math.sin(math.pi * t) ** 0.4
        r = max(base * (0.40 + 0.60*taper) * (0.80 + 0.40*bulge(t)), base*0.30)
        el = mb.elements.new(type="BALL")
        el.co = path(t)
        el.radius = r * 2.0
        el.stiffness = 2.0
    mb.elements[0].co = path(0.0)
    mb.elements[0].radius = base

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = keep_largest(bpy.context.object)
    if kind == "ribbon":
        obj.scale.z = 0.28
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # 폰에서 쓸 수 있게 면 수를 줄인다
    n = len(obj.data.polygons)
    if n > TRIS:
        m = obj.modifiers.new("dec", "DECIMATE")
        m.ratio = TRIS / n
        bpy.ops.object.modifier_apply(modifier=m.name)

    # 🔴 데시메이트는 면을 접어 없애는 방식이라 실루엣에 각이 남는다. 법선은
    #    폰에서 computeVertexNormals 로 부드럽게 깔리지만, 윤곽선은 면 수가
    #    그대로 드러난다. 보석처럼 보여야 하는 형태라 각이 남으면 안 된다.
    #    접은 자리를 펴 준다. 부피가 조금 줄지만 어차피 정규화한다.
    if SMOOTH > 0:
        m = obj.modifiers.new("sm", "SMOOTH")
        m.factor = SMOOTH
        m.iterations = SMOOTH_ITER
        bpy.ops.object.modifier_apply(modifier=m.name)

    # 원점 중심, 가장 긴 변이 1 이 되게 정규화. 크기는 폰에서 입힌다.
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    longest = max(obj.dimensions)
    obj.scale = (1.0/longest,) * 3
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
    return obj


def triangles(obj):
    """인덱스 메시로 뽑는다. 정점을 중복 저장하면 파일이 서너 배로 커진다.
    소수점 3자리면 가장 긴 변 1 기준 0.001 이라 10cm 크리스탈에서 0.1mm 다. 충분하다."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    verts, index, lookup = [], [], {}
    for tri in mesh.loop_triangles:
        for vi in tri.vertices:
            co = mesh.vertices[vi].co
            key = (round(co.x, 3), round(co.y, 3), round(co.z, 3))
            j = lookup.get(key)
            if j is None:
                j = len(lookup)
                lookup[key] = j
                verts += list(key)
            index.append(j)
    return verts, index


def main():
    variants = []
    for kind in FAMILIES:
        for i in range(PER_KIND):
            clear()
            seed = SEED + hash(kind) % 1000 + i * 37
            obj = build(kind, seed)
            verts, index = triangles(obj)
            variants.append({"kind": kind, "seed": seed, "tris": len(index)//3,
                             "verts": verts, "index": index})
            print(f"  {kind}_{seed}  삼각형 {len(index)//3}, 정점 {len(verts)//3}")

    path = os.path.abspath(OUT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"note": "정점은 원점 중심, 가장 긴 변이 1. 크기와 비틀림은 crystal.js 가 입힌다.",
                   "variants": variants}, f, separators=(",", ":"))
    total = sum(v["tris"] for v in variants)
    print(f"\n{len(variants)}개, 삼각형 합계 {total}, {os.path.getsize(path)//1024} KB")
    print(f"저장: {path}")


main()
