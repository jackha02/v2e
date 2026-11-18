"""Build the river scene, reproducibly.
Run:  blender -b --factory-startup -P make_scene.py -- [--render] [--mask] [--motion] [--frames N] [--fps F] [--samples S]
Blender 4.5 LTS. Units: metres, Z up, camera looks along +Y.
"""
import bpy, sys, os, json, math
import mathutils
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default

RES_X, RES_Y = 346, 260
FPS = opt("--fps", 120)
NFRAMES = opt("--frames", 200)
SAMPLES = opt("--samples", 128)
SUN_STRENGTH = opt("--sun", 8.0)
SUN_ELEV = math.radians(opt("--elev", 14.0))
SUN_AZ = math.radians(opt("--az", 25.0))      # from +Y axis towards +X (sun is in front of camera, slightly right)
SUN_ANGLE_DEG = opt("--sunangle", 8.0)
WORLD_STRENGTH = opt("--world", 0.02)
SEED = 0
CARD_ALBEDO = 0.18
RENDER_DIR = os.path.join(HERE, opt("--out", "renders"))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = "river"

# ---------- helpers
def mat_diffuse(name, color, rough=0.9, noise=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = 0.0
    if noise:  # procedural texture banks: colour variation + bump
        tc = nt.nodes.new("ShaderNodeTexCoord")
        vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.inputs["Scale"].default_value = noise
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'
        mix.inputs["A"].default_value = (*[c * 0.5 for c in color], 1)
        mix.inputs["B"].default_value = (*[c * 1.5 for c in color], 1)
        bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.4
        nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
        nt.links.new(vor.outputs["Distance"], mix.inputs["Factor"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        bsdf.inputs["Base Color"].default_value = (*color, 1)
    return m

def box(name, loc, size, mat):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object; o.name = name; o.scale = [s / 2 for s in size]
    o.data.materials.append(mat); return o

# ---------- world (dim constant sky so shadows are genuinely dark)
world = bpy.data.worlds.new("sky"); scene.world = world; world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.55, 0.65, 0.85, 1); bg.inputs["Strength"].default_value = WORLD_STRENGTH

# ---------- sun: low angle, in front of camera so wave facets glint towards it
s_dir = Vector((math.sin(SUN_AZ) * math.cos(SUN_ELEV), math.cos(SUN_AZ) * math.cos(SUN_ELEV), math.sin(SUN_ELEV)))  # towards sun
sun_d = bpy.data.lights.new("sun", 'SUN'); sun_d.energy = SUN_STRENGTH; sun_d.angle = math.radians(SUN_ANGLE_DEG)
sun = bpy.data.objects.new("sun", sun_d); scene.collection.objects.link(sun)
sun.rotation_euler = s_dir.to_track_quat('Z', 'Y').to_euler()   # light travels along local -Z = -s_dir

# ---------- water: Ocean modifier (deterministic function of time), waves travel towards camera (-Y)
bpy.ops.mesh.primitive_plane_add(size=1)
water = bpy.context.object; water.name = "water"
om = water.modifiers.new("Ocean", 'OCEAN')
om.geometry_mode = 'GENERATE'; om.resolution = opt("--res", 16); om.viewport_resolution = om.resolution; om.spatial_size = 60
om.repeat_x = 1; om.repeat_y = 1
om.wave_scale = opt("--wscale", 0.5); om.wave_scale_min = 0.2; om.choppiness = 0.8
om.wind_velocity = 4.0; om.wave_alignment = 0.8; om.wave_direction = 0.0; om.damping = 0.5
om.depth = 200.0; om.random_seed = 3; om.use_normals = True; om.use_foam = False
water.rotation_euler = (0, 0, math.radians(-90))     # +X travel -> -Y (towards camera)
for p in water.data.polygons: p.use_smooth = True
wm = bpy.data.materials.new("water"); wm.use_nodes = True
b = wm.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.01, 0.015, 0.015, 1); b.inputs["Roughness"].default_value = 0.03
b.inputs["IOR"].default_value = 1.33
water.data.materials.append(wm)
water.pass_index = 1

# ---------- static scenery
rock_m = mat_diffuse("rock", (0.10, 0.09, 0.08), noise=6.0)
bank_m = mat_diffuse("bank", (0.07, 0.055, 0.035), noise=3.0)
hill_m = mat_diffuse("hill", (0.03, 0.035, 0.025), noise=1.5)
concrete_m = mat_diffuse("concrete", (0.12, 0.12, 0.12), noise=8.0)
box("bank_L", (-15.0, 20, 0.3), (20, 120, 3.0), bank_m)   # inner face at x=-5
box("bank_R", (15.0, 20, 0.3), (20, 120, 3.0), bank_m)    # inner face at x=+5
box("hill", (0, 75, 2.0), (160, 4, 11), hill_m)
for i, (loc, sc) in enumerate([((-2.0, 12, 0.0), (0.9, 0.7, 0.6)), ((3.2, 22, 0.0), (1.2, 1.0, 0.8))]):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, location=loc)
    r = bpy.context.object; r.name = f"rock{i+1}"; r.scale = sc
    tex = bpy.data.textures.new(f"rocktex{i}", 'CLOUDS'); tex.noise_scale = 0.6
    d = r.modifiers.new("disp", 'DISPLACE'); d.texture = tex; d.strength = 0.35
    r.data.materials.append(rock_m)
for p in bpy.data.objects["rock1"].data.polygons: p.use_smooth = True
for p in bpy.data.objects["rock2"].data.polygons: p.use_smooth = True
# bridge: deck across the river at y=18 plus a round pier
box("bridge_deck", (0, 18, 3.5), (18, 3.0, 0.7), concrete_m)
bpy.ops.mesh.primitive_cylinder_add(radius=0.6, depth=5.0, location=(3.0, 18, 1.0), vertices=24)
pier = bpy.context.object; pier.name = "pier"; pier.data.materials.append(concrete_m)
for p in pier.data.polygons: p.use_smooth = True

# ---------- camera
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 35; cam_d.sensor_width = 36; cam_d.sensor_fit = 'HORIZONTAL'
cam = bpy.data.objects.new("cam", cam_d); scene.collection.objects.link(cam)
cam.location = (0.0, -3.0, opt("--camz", 1.5)); cam.rotation_euler = (math.radians(86), 0, 0)
scene.camera = cam

# ---------- gray card (albedo 0.18) on a post, horizontal, floating at z=0.4 on a post
card_pos = Vector((-1.4, 1.8, 0.4))
bpy.ops.mesh.primitive_plane_add(size=1.5, location=card_pos)
card = bpy.context.object; card.name = "gray_card"; card.pass_index = 2
n_card = Vector((0, 0, 1))   # horizontal card: the sun is in front of the camera, so any sun-facing vertical card would face away from it
to_cam = (cam.location - card_pos).normalized()
card.data.materials.append(mat_diffuse("graycard", (CARD_ALBEDO,) * 3, rough=1.0))
bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=2.0, location=(-1.4, 1.8, -0.6))
bpy.context.object.name = "card_post"
bpy.context.object.data.materials.append(rock_m)
cos_card = max(n_card.dot(s_dir), 0)

# ---------- render settings
scene.render.engine = 'CYCLES'
c = scene.cycles
c.samples = SAMPLES; c.use_adaptive_sampling = True; c.adaptive_threshold = 0.01; c.adaptive_min_samples = 16
c.use_denoising = False                      # denoiser OFF (would smear glints / is temporally unstable)
c.seed = SEED; c.use_animated_seed = False   # fixed noise pattern across frames
c.device = 'CPU'
c.sample_clamp_direct = 0.0; c.sample_clamp_indirect = 0.0   # no clamping: keep HDR peaks
scene.render.threads_mode = 'FIXED'; scene.render.threads = 8
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = RES_X, RES_Y, 100
scene.render.fps = FPS; scene.render.fps_base = 1.0
scene.frame_start, scene.frame_end = 1, NFRAMES
scene.render.film_transparent = False
vs = scene.view_settings
vs.view_transform = 'Standard'; vs.look = 'None'; vs.exposure = 0.0; vs.gamma = 1.0
scene.display_settings.display_device = 'sRGB'
scene.sequencer_colorspace_settings.name = 'Linear Rec.709'
im = scene.render.image_settings
im.file_format = 'OPEN_EXR'; im.color_depth = '16'; im.exr_codec = 'ZIP'; im.color_mode = 'RGB'
scene.render.use_file_extension = True
scene.render.filepath = os.path.join(RENDER_DIR, "frame_")

# ocean time = frame / fps (real seconds), linear keyframes at first/last frame
om.time = 0.0; om.keyframe_insert("time", frame=1)
om.time = (NFRAMES - 1) / FPS; om.keyframe_insert("time", frame=NFRAMES)
for fc in water.animation_data.action.layers[0].strips[0].channelbags[0].fcurves if hasattr(water.animation_data.action, "layers") else water.animation_data.action.fcurves:
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
scene.frame_set(1)

# centre the ocean patch on x=0,y=20 using its evaluated bounding box
dg = bpy.context.evaluated_depsgraph_get()
ev = water.evaluated_get(dg)
xs = [(water.matrix_world @ v.co) for v in ev.data.vertices]
cx = (min(p.x for p in xs) + max(p.x for p in xs)) / 2; cy = (min(p.y for p in xs) + max(p.y for p in xs)) / 2
water.location = (-cx, 20 - cy, 0)
scene.frame_set(1)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "scene.blend"))

manifest = dict(fps=FPS, frame_count=NFRAMES, resolution=[RES_X, RES_Y], sun_strength=SUN_STRENGTH,
                sun_elevation_deg=math.degrees(SUN_ELEV), sun_azimuth_deg_from_plusY=math.degrees(SUN_AZ),
                sun_angle_deg=SUN_ANGLE_DEG, world_strength=WORLD_STRENGTH,
                gray_card_albedo=CARD_ALBEDO, gray_card_cos_sun=cos_card,
                gray_card_expected_luminance_sun_only=CARD_ALBEDO * SUN_STRENGTH * cos_card / math.pi,   # Blender sun strength = irradiance W/m2; L = albedo*E*cos/pi
                gray_card_expected_luminance_sky=CARD_ALBEDO * WORLD_STRENGTH * (0.2126 * 0.55 + 0.7152 * 0.65 + 0.0722 * 0.85),
                seed=SEED, animated_seed=False, samples=SAMPLES, adaptive_sampling=True, denoiser="off",
                device="CPU", blender_version=bpy.app.version_string, view_transform=vs.view_transform,
                exr="OPEN_EXR 16-bit half, ZIP, RGB, single layer", camera_lens_mm=35, sensor_width_mm=36)
mpath = os.path.join(HERE, "manifest.json")
if os.path.exists(mpath):
    old = json.load(open(mpath)); old.update(manifest); manifest = old
json.dump(manifest, open(mpath, "w"), indent=1)

# ---------- optional: vertex-motion estimate in pixels per frame
if "--motion" in argv:
    from bpy_extras.object_utils import world_to_camera_view
    def proj(frame):
        scene.frame_set(frame)
        dg = bpy.context.evaluated_depsgraph_get(); e = water.evaluated_get(dg)
        out = []
        for v in e.data.vertices:
            p = world_to_camera_view(scene, cam, water.matrix_world @ v.co)
            out.append((p.x * RES_X, (1 - p.y) * RES_Y, p.z))
        return out
    import numpy as np
    res = []
    for f in range(1, NFRAMES, max(1, (NFRAMES - 1) // 10)):
        a, b2 = np.array(proj(f)), np.array(proj(f + 1))
        ok = (a[:, 2] > 0) & (a[:, 0] > 0) & (a[:, 0] < RES_X) & (a[:, 1] > 0) & (a[:, 1] < RES_Y)
        d = np.hypot(*(b2[ok, :2] - a[ok, :2]).T)
        res.append(dict(frame=f, n_verts_in_view=int(ok.sum()), mean_px=float(d.mean()), p99_px=float(np.percentile(d, 99)), max_px=float(d.max())))
    summ = dict(fps=FPS, per_frame=res, max_px=max(r["max_px"] for r in res), max_p99_px=max(r["p99_px"] for r in res),
                n_water_verts=len(water.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices))
    json.dump(summ, open(os.path.join(HERE, "motion_estimate.json"), "w"), indent=1)
    print("MOTION", json.dumps({k: v for k, v in summ.items() if k != "per_frame"}))

# ---------- optional: sun-lit / object-index mask (debug, frame 1)
if "--mask" in argv:
    ov = bpy.data.materials.new("white"); ov.use_nodes = True
    ov.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 1, 1, 1)
    ov.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
    ov.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.0
    bpy.context.view_layer.material_override = ov
    bg.inputs["Strength"].default_value = 0.0
    bpy.context.view_layer.use_pass_object_index = True
    scene.cycles.samples = 64
    scene.cycles.max_bounces = 0   # direct sunlight only: a pixel is "sunlit" iff the sun reaches it
    os.makedirs(os.path.join(HERE, "debug"), exist_ok=True)
    scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
    scene.render.filepath = os.path.join(HERE, "debug", "mask", "mask_")
    bpy.ops.render.render(animation=True)   # one mask per frame (waves move, shadow edges move)

if "--render" in argv:
    os.makedirs(RENDER_DIR, exist_ok=True)
    bpy.ops.render.render(animation=True)

if "--still" in argv:
    os.makedirs(RENDER_DIR, exist_ok=True)
    scene.frame_start = scene.frame_end = opt("--stillframe", 1)
    bpy.ops.render.render(animation=True)

if "--sweep" in argv:   # quick look-development: every 20th frame, glint-pixel counting done by sweep_count.py
    os.makedirs(RENDER_DIR, exist_ok=True)
    scene.frame_step = 20
    bpy.ops.render.render(animation=True)

if "--calib" in argv:   # calibration render: ONLY the gray card (no occluders, no water), same sun/world/view settings, frame 1
    for o in bpy.data.objects:
        if o.name not in ("gray_card",) and o.type == 'MESH':
            o.hide_render = True
    scene.frame_start = scene.frame_end = 1
    scene.render.filepath = os.path.join(HERE, "debug", "calib", "frame_")
    bpy.ops.render.render(animation=True)
