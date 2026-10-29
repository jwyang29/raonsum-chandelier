"""생성한 STL 들을 격자로 늘어놓고 한 장으로 렌더한다."""
import bpy, os, sys, math, glob
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d, c=str):
    return c(argv[argv.index(n)+1]) if n in argv else d

SRC = arg("--src", "stl")
OUT = arg("--out", "preview.png")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

files = sorted(glob.glob(os.path.join(SRC, "*.stl")))
cols = 3
gap = 110.0
objs = []
for i, f in enumerate(files):
    try:
        bpy.ops.wm.stl_import(filepath=f)
    except AttributeError:
        bpy.ops.import_mesh.stl(filepath=f)
    o = bpy.context.selected_objects[0]
    o.location = ((i % cols - 1) * gap, -(i // cols) * gap + gap/2, 0)
    for p in o.data.polygons:
        p.use_smooth = True
    objs.append(o)

# 바닥 판
bpy.ops.mesh.primitive_plane_add(size=600, location=(0, 0, -0.1))

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.studio_light = "Default"
sc.display.shading.color_type = "SINGLE"
sc.display.shading.single_color = (0.78, 0.82, 0.88)
sc.display.shading.show_cavity = True
sc.display.shading.cavity_type = "BOTH"
sc.display.render_aa = "16"
sc.render.resolution_x, sc.render.resolution_y = 1400, 1000
sc.render.film_transparent = False
sc.world.color = (0.09, 0.10, 0.12) if sc.world else None

bpy.ops.object.camera_add(location=(0, -300, 250), rotation=(math.radians(55), 0, 0))
cam = bpy.context.object
cam.data.type = "ORTHO"
cam.data.ortho_scale = 420
sc.camera = cam

sc.render.filepath = os.path.abspath(OUT)
bpy.ops.render.render(write_still=True)
print(f"렌더 저장: {sc.render.filepath}  ({len(files)}개)")
