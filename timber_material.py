"""
timber_material.py — PBR shader pipeline for hand-hewn timber.

Texture discovery (case-insensitive keyword match in TEXTURE_DIR):
    diffuse / albedo / basecolor / diff  → Base Color  (sRGB)
    ao                                   → multiplied onto Base Color
    aorm / orm / ao_rough_metal          → packed ORM  (R=AO, G=Rough, B=Metal)
    rough                                → Roughness   (Non-Color)
    metal                                → Metallic    (Non-Color)
    spec                                 → Specular    (Non-Color)
    nor_gl / normal_gl / normalgl        → Normal map  OpenGL
    nor_dx / normal_dx / normaldx        → Normal map  DirectX
    bump                                 → Bump height (Non-Color)
    disp                                 → Displacement(Non-Color)

Procedural layers (no extra textures needed):
    - Object-space coords  → no UV seam
    - Mapping scale (1, 1, 0.25) → grain stretches 4× along beam length
    - Noise → ColorRamp    → per-surface color variation (warm/cool patches)
    - Noise → roughness    → breaks up uniform reflectance
    - Object Info Random   → per-object hue/roughness shift
    - ShaderNodeBevel      → curvature-based edge wear (Cycles only)
"""

import os
import bpy

TEXTURE_DIR       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures/weathered_planks")
USE_OPENGL_NORMAL = True
MATERIAL_NAME     = "TimberMaterial"

# Grain scale: lower Z = fewer repeats along beam length.
# 0.12 → one repeat spans ~8× the beam radius (broad painted-grain look).
TEXTURE_SCALE = (1.0, 1.0, 0.12)

_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find(keyword):
    kw = keyword.lower()
    for f in os.listdir(TEXTURE_DIR):
        lo = f.lower()
        if kw in lo and lo.endswith(_EXTS):
            return os.path.join(TEXTURE_DIR, f)
    return None


def _img(path, colorspace="sRGB"):
    if path is None:
        return None
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = colorspace
    return img


def _tex(nodes, path, colorspace, location):
    node = nodes.new("ShaderNodeTexImage")
    node.location = location
    node.image = _img(path, colorspace)
    return node


def _node(nodes, bl_idname, location, **kwargs):
    n = nodes.new(bl_idname)
    n.location = location
    for k, v in kwargs.items():
        setattr(n, k, v)
    return n


# ---------------------------------------------------------------------------
# Build / retrieve material
# ---------------------------------------------------------------------------

def get_timber_material():
    """
    Returns the shared TimberMaterial, creating it if it doesn't exist yet.
    Safe to call multiple times — nodes are only built once.
    """
    if MATERIAL_NAME in bpy.data.materials:
        return bpy.data.materials[MATERIAL_NAME]

    # --- locate textures ---
    diffuse = _find("diffuse") or _find("albedo") or _find("basecolor") or _find("diff")
    ao      = _find("ao")
    orm     = _find("aorm") or _find("orm") or _find("ao_rough_metal")
    rough   = _find("rough")
    metal   = _find("metal")
    spec    = _find("spec")
    normal  = (_find("nor_gl") or _find("normal_gl") or _find("normalgl")) if USE_OPENGL_NORMAL \
              else (_find("nor_dx") or _find("normal_dx") or _find("normaldx"))
    bump    = _find("bump")
    disp    = _find("disp")

    # --- material ---
    mat = bpy.data.materials.new(MATERIAL_NAME)
    mat.use_nodes = True
    nt    = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    def link(a, b):
        links.new(a, b)

    output = _node(nodes, "ShaderNodeOutputMaterial", (1600, 0))
    bsdf   = _node(nodes, "ShaderNodeBsdfPrincipled",  (1100, 0))
    link(bsdf.outputs["BSDF"], output.inputs["Surface"])

    # -----------------------------------------------------------------------
    # Coordinates — Object space avoids the UV seam entirely.
    # Mapping scale stretches grain along the beam's long axis (Z).
    # -----------------------------------------------------------------------
    texcoord = _node(nodes, "ShaderNodeTexCoord", (-1400, 0))
    mapping  = _node(nodes, "ShaderNodeMapping",  (-1200, 0))
    mapping.inputs["Scale"].default_value = TEXTURE_SCALE
    link(texcoord.outputs["Object"], mapping.inputs["Vector"])

    def vec(node):
        link(mapping.outputs["Vector"], node.inputs["Vector"])

    # -----------------------------------------------------------------------
    # Per-object HSV variation driven by Object Info → Random (0–1).
    # Hue ±3° (±0.008 normalized), Saturation ±5%, Value ±8%.
    # Also drives grain scale and rotation so no two beams tile identically.
    # -----------------------------------------------------------------------
    obj_info = _node(nodes, "ShaderNodeObjectInfo", (-1400, -300))

    # Map Random 0–1 → hue offset –0.008..+0.008
    hue_map = _node(nodes, "ShaderNodeMath", (-1100, -300))
    hue_map.operation = "MULTIPLY_ADD"
    hue_map.inputs[1].default_value =  0.016
    hue_map.inputs[2].default_value = -0.008
    link(obj_info.outputs["Random"], hue_map.inputs[0])

    # Map Random 0–1 → saturation 0.95..1.05
    sat_map = _node(nodes, "ShaderNodeMath", (-1100, -450))
    sat_map.operation = "MULTIPLY_ADD"
    sat_map.inputs[1].default_value =  0.10
    sat_map.inputs[2].default_value =  0.95
    link(obj_info.outputs["Random"], sat_map.inputs[0])

    # Map Random 0–1 → value 0.92..1.08
    val_map = _node(nodes, "ShaderNodeMath", (-1100, -600))
    val_map.operation = "MULTIPLY_ADD"
    val_map.inputs[1].default_value =  0.16
    val_map.inputs[2].default_value =  0.92
    link(obj_info.outputs["Random"], val_map.inputs[0])

    # Per-object grain scale variation: ±15% around base Z scale
    grain_scale = _node(nodes, "ShaderNodeMath", (-1100, -750))
    grain_scale.operation = "MULTIPLY_ADD"
    grain_scale.inputs[1].default_value =  0.30 * TEXTURE_SCALE[2]   # ±15% range
    grain_scale.inputs[2].default_value =  0.85 * TEXTURE_SCALE[2]   # lower bound
    link(obj_info.outputs["Random"], grain_scale.inputs[0])

    # Per-object grain rotation: ±5° around Z
    grain_rot = _node(nodes, "ShaderNodeMath", (-1100, -900))
    grain_rot.operation = "MULTIPLY_ADD"
    grain_rot.inputs[1].default_value =  0.175   # 10° range in radians
    grain_rot.inputs[2].default_value = -0.087   # −5° offset
    link(obj_info.outputs["Random"], grain_rot.inputs[0])

    # Per-object roughness shift: ±0.05
    rough_shift = _node(nodes, "ShaderNodeMath", (-1100, -1050))
    rough_shift.operation = "MULTIPLY_ADD"
    rough_shift.inputs[1].default_value =  0.10
    rough_shift.inputs[2].default_value = -0.05
    link(obj_info.outputs["Random"], rough_shift.inputs[0])

    # Apply grain scale + rotation to a per-instance mapping node.
    # Rotation Z varies ±5°; Scale Z varies ±15% around base.
    mapping_inst = _node(nodes, "ShaderNodeMapping", (-950, 0))
    mapping_inst.inputs["Scale"].default_value    = TEXTURE_SCALE
    mapping_inst.inputs["Rotation"].default_value = (0.0, 0.0, 0.0)
    link(texcoord.outputs["Object"], mapping_inst.inputs["Vector"])

    # Build a scale vector (X=1, Y=1, Z=grain_scale) via CombineXYZ
    scale_xyz = _node(nodes, "ShaderNodeCombineXYZ", (-950, -200))
    scale_xyz.inputs["X"].default_value = TEXTURE_SCALE[0]
    scale_xyz.inputs["Y"].default_value = TEXTURE_SCALE[1]
    link(grain_scale.outputs["Value"], scale_xyz.inputs["Z"])
    link(scale_xyz.outputs["Vector"],  mapping_inst.inputs["Scale"])

    # Build a rotation vector (0, 0, grain_rot) via CombineXYZ
    rot_xyz = _node(nodes, "ShaderNodeCombineXYZ", (-950, -350))
    rot_xyz.inputs["X"].default_value = 0.0
    rot_xyz.inputs["Y"].default_value = 0.0
    link(grain_rot.outputs["Value"],  rot_xyz.inputs["Z"])
    link(rot_xyz.outputs["Vector"],   mapping_inst.inputs["Rotation"])

    # Reroute vec() to use the instance mapping for all texture lookups
    def vec(node):  # noqa: F811  (intentional shadow)
        link(mapping_inst.outputs["Vector"], node.inputs["Vector"])

    # -----------------------------------------------------------------------
    # Base Color
    # -----------------------------------------------------------------------
    color_out = None   # will hold the final color socket going into BSDF

    if diffuse:
        dtex = _tex(nodes, diffuse, "sRGB", (-800, 400))
        vec(dtex)

        if ao:
            ao_tex = _tex(nodes, ao, "Non-Color", (-800, 150))
            vec(ao_tex)
            ao_mix = _node(nodes, "ShaderNodeMixRGB", (-400, 300))
            ao_mix.blend_type = "MULTIPLY"
            ao_mix.inputs["Fac"].default_value = 1.0
            link(dtex.outputs["Color"],   ao_mix.inputs["Color1"])
            link(ao_tex.outputs["Color"], ao_mix.inputs["Color2"])
            color_out = ao_mix.outputs["Color"]
        else:
            color_out = dtex.outputs["Color"]

    # Low-frequency noise: broad brush-stroke color patches, no fine detail.
    noise_col = _node(nodes, "ShaderNodeTexNoise", (-800, -50))
    noise_col.inputs["Scale"].default_value      = 0.6
    noise_col.inputs["Detail"].default_value     = 0.0   # no high-freq speckle
    noise_col.inputs["Roughness"].default_value  = 0.5
    noise_col.inputs["Distortion"].default_value = 0.2
    vec(noise_col)

    col_ramp = _node(nodes, "ShaderNodeValToRGB", (-500, -50))
    col_ramp.color_ramp.interpolation = "EASE"
    # Narrow dark band (0.0–0.2), soft transition, no pure black
    col_ramp.color_ramp.elements[0].position = 0.0
    col_ramp.color_ramp.elements[0].color    = (0.28, 0.20, 0.14, 1)  # soft dark brown
    col_ramp.color_ramp.elements[1].position = 1.0
    col_ramp.color_ramp.elements[1].color    = (0.72, 0.68, 0.60, 1)  # bleached gray
    mid = col_ramp.color_ramp.elements.new(0.22)
    mid.color = (0.55, 0.50, 0.42, 1)                                  # neutral mid
    link(noise_col.outputs["Fac"], col_ramp.inputs["Fac"])

    # Per-object hue shift via Object Random → mix factor
    hue_mix = _node(nodes, "ShaderNodeMixRGB", (-150, 150))
    hue_mix.blend_type = "MIX"
    link(col_ramp.outputs["Color"], hue_mix.inputs["Color1"])

    if color_out:
        # Blend diffuse at 60% over procedural — broad tint, not photographic
        hue_mix.inputs["Fac"].default_value = 0.6
        link(color_out, hue_mix.inputs["Color2"])
    else:
        hue_mix.inputs["Fac"].default_value = 0.0  # procedural only
        hue_mix.inputs["Color2"].default_value = (0, 0, 0, 1)

    link(hue_mix.outputs["Color"], bsdf.inputs["Base Color"])

    # Apply per-object HSV shift
    hsv = _node(nodes, "ShaderNodeHueSaturation", (100, 150))
    link(hue_mix.outputs["Color"],  hsv.inputs["Color"])
    link(hue_map.outputs["Value"],  hsv.inputs["Hue"])
    link(sat_map.outputs["Value"],  hsv.inputs["Saturation"])
    link(val_map.outputs["Value"],  hsv.inputs["Value"])
    hsv.inputs["Fac"].default_value = 1.0

    # -----------------------------------------------------------------------
    # Roughness
    # -----------------------------------------------------------------------
    rough_out = None

    if orm:
        otex = _tex(nodes, orm, "Non-Color", (-800, -350))
        vec(otex)
        sep = _node(nodes, "ShaderNodeSeparateColor", (-450, -350))
        link(otex.outputs["Color"], sep.inputs["Color"])
        link(sep.outputs["Blue"],   bsdf.inputs["Metallic"])
        rough_out = sep.outputs["Green"]
    elif rough:
        rtex = _tex(nodes, rough, "Non-Color", (-800, -350))
        vec(rtex)
        rough_out = rtex.outputs["Color"]

    # Noise breaks up uniform roughness (polished vs dry patches)
    noise_rough = _node(nodes, "ShaderNodeTexNoise", (-800, -600))
    noise_rough.inputs["Scale"].default_value     = 3.5
    noise_rough.inputs["Detail"].default_value    = 1.0
    noise_rough.inputs["Roughness"].default_value = 0.6
    vec(noise_rough)

    rough_add = _node(nodes, "ShaderNodeMath", (-450, -600))
    rough_add.operation = "ADD"
    rough_add.inputs[1].default_value = -0.1   # slight darkening bias
    link(noise_rough.outputs["Fac"], rough_add.inputs[0])

    rough_mix = _node(nodes, "ShaderNodeMixRGB", (-150, -450))
    rough_mix.blend_type = "OVERLAY"
    rough_mix.inputs["Fac"].default_value = 0.35
    link(rough_add.outputs["Value"], rough_mix.inputs["Color2"])

    if rough_out:
        link(rough_out, rough_mix.inputs["Color1"])
    else:
        rough_mix.inputs["Color1"].default_value = (0.82, 0.82, 0.82, 1)

    link(rough_mix.outputs["Color"], bsdf.inputs["Roughness"])  # superseded by edge/groove chain below

    # -----------------------------------------------------------------------
    # Metallic (standalone, skipped if ORM already handled it)
    # -----------------------------------------------------------------------
    if metal and not orm:
        mtex = _tex(nodes, metal, "Non-Color", (-800, -800))
        vec(mtex)
        link(mtex.outputs["Color"], bsdf.inputs["Metallic"])

    # -----------------------------------------------------------------------
    # Specular
    # -----------------------------------------------------------------------
    if spec:
        stex = _tex(nodes, spec, "Non-Color", (-800, -1000))
        vec(stex)
        if "Specular IOR Level" in bsdf.inputs:
            link(stex.outputs["Color"], bsdf.inputs["Specular IOR Level"])

    # -----------------------------------------------------------------------
    # Two-scale normals:
    #   Large scale — gentle hand-hewn undulations (Noise, low freq)
    #   Small scale — wood grain detail (texture normal map / bump)
    # Both feed into a chained Bump setup.
    # -----------------------------------------------------------------------

    # Large-scale undulation bump
    noise_large = _node(nodes, "ShaderNodeTexNoise", (-800, -2400))
    noise_large.inputs["Scale"].default_value      = 0.8
    noise_large.inputs["Detail"].default_value     = 0.0
    noise_large.inputs["Roughness"].default_value  = 0.5
    noise_large.inputs["Distortion"].default_value = 0.1
    vec(noise_large)

    bump_large = _node(nodes, "ShaderNodeBump", (-400, -2400))
    bump_large.inputs["Strength"].default_value = 0.4
    bump_large.inputs["Distance"].default_value = 0.05
    link(noise_large.outputs["Fac"], bump_large.inputs["Height"])

    # Small-scale: normal map if available, else bump texture, else nothing
    normal_out = None
    if normal:
        ntex = _tex(nodes, normal, "Non-Color", (-800, -2650))
        vec(ntex)
        nmap = _node(nodes, "ShaderNodeNormalMap", (-400, -2650))
        nmap.inputs["Strength"].default_value = 0.3
        link(ntex.outputs["Color"], nmap.inputs["Color"])
        # Combine large + small via a Bump node that takes both
        bump_small = _node(nodes, "ShaderNodeBump", (-100, -2650))
        bump_small.inputs["Strength"].default_value = 0.3
        bump_small.inputs["Distance"].default_value = 0.01
        bump_small.inputs["Height"].default_value   = 0.5   # neutral height
        link(bump_large.outputs["Normal"], bump_small.inputs["Normal"])
        link(nmap.outputs["Normal"],       bump_small.inputs["Normal"])
        normal_out = bump_small.outputs["Normal"]
    else:
        normal_out = bump_large.outputs["Normal"]

    if bump:
        btex  = _tex(nodes, bump, "Non-Color", (-800, -2900))
        vec(btex)
        bnode = _node(nodes, "ShaderNodeBump", (-400, -2900))
        bnode.inputs["Strength"].default_value = 0.3
        bnode.inputs["Distance"].default_value = 0.02
        link(btex.outputs["Color"], bnode.inputs["Height"])
        link(normal_out,            bnode.inputs["Normal"])
        normal_out = bnode.outputs["Normal"]

    link(normal_out, bsdf.inputs["Normal"])

    # -----------------------------------------------------------------------
    # End grain — concentric rings + radial noise, masked to end faces.
    # Mask: |dot(face_normal, Z)| → 1 on ends, 0 on sides.
    # -----------------------------------------------------------------------
    geom_eg   = _node(nodes, "ShaderNodeNewGeometry", (-400, -1700))
    z_axis    = _node(nodes, "ShaderNodeCombineXYZ",  (-400, -1850))
    z_axis.inputs["X"].default_value = 0.0
    z_axis.inputs["Y"].default_value = 0.0
    z_axis.inputs["Z"].default_value = 1.0

    eg_dot  = _node(nodes, "ShaderNodeVectorMath", (-200, -1750))
    eg_dot.operation = "DOT_PRODUCT"
    link(geom_eg.outputs["Normal"], eg_dot.inputs[0])
    link(z_axis.outputs["Vector"],  eg_dot.inputs[1])

    eg_abs  = _node(nodes, "ShaderNodeMath", (-50, -1750))
    eg_abs.operation = "ABSOLUTE"
    link(eg_dot.outputs["Value"], eg_abs.inputs[0])

    # Sharpen the mask so only near-flat end faces get the treatment
    eg_mask_ramp = _node(nodes, "ShaderNodeValToRGB", (100, -1750))
    eg_mask_ramp.color_ramp.interpolation = "EASE"
    eg_mask_ramp.color_ramp.elements[0].position = 0.7
    eg_mask_ramp.color_ramp.elements[0].color    = (0, 0, 0, 1)
    eg_mask_ramp.color_ramp.elements[1].position = 0.95
    eg_mask_ramp.color_ramp.elements[1].color    = (1, 1, 1, 1)
    link(eg_abs.outputs["Value"], eg_mask_ramp.inputs["Fac"])

    # Convenience: use the ramp's red channel as the scalar mask
    eg_mask_sep = _node(nodes, "ShaderNodeSeparateColor", (300, -1750))
    link(eg_mask_ramp.outputs["Color"], eg_mask_sep.inputs["Color"])

    # XY coords for ring distance — use Object coords, ignore Z
    eg_coord  = _node(nodes, "ShaderNodeTexCoord", (-600, -1900))
    eg_sep    = _node(nodes, "ShaderNodeSeparateXYZ", (-400, -1950))
    link(eg_coord.outputs["Object"], eg_sep.inputs["Vector"])

    eg_dist = _node(nodes, "ShaderNodeVectorMath", (-200, -1950))
    eg_dist.operation = "LENGTH"
    eg_xy   = _node(nodes, "ShaderNodeCombineXYZ", (-350, -2050))
    link(eg_sep.outputs["X"], eg_xy.inputs["X"])
    link(eg_sep.outputs["Y"], eg_xy.inputs["Y"])
    eg_xy.inputs["Z"].default_value = 0.0
    link(eg_xy.outputs["Vector"], eg_dist.inputs[0])

    # Scale distance → ring frequency (~8 rings across the face)
    eg_scale = _node(nodes, "ShaderNodeMath", (-50, -1950))
    eg_scale.operation = "MULTIPLY"
    eg_scale.inputs[1].default_value = 18.0
    link(eg_dist.outputs["Value"], eg_scale.inputs[0])

    eg_fract = _node(nodes, "ShaderNodeMath", (100, -1950))
    eg_fract.operation = "FRACT"
    link(eg_scale.outputs["Value"], eg_fract.inputs[0])

    # Smooth the rings into soft bands
    eg_ring_ramp = _node(nodes, "ShaderNodeValToRGB", (260, -1950))
    eg_ring_ramp.color_ramp.interpolation = "EASE"
    eg_ring_ramp.color_ramp.elements[0].position = 0.0
    eg_ring_ramp.color_ramp.elements[0].color    = (0.55, 0.42, 0.30, 1)  # dark ring
    eg_ring_ramp.color_ramp.elements[1].position = 1.0
    eg_ring_ramp.color_ramp.elements[1].color    = (0.80, 0.72, 0.60, 1)  # light ring
    link(eg_fract.outputs["Value"], eg_ring_ramp.inputs["Fac"])

    # Radial crack noise — very subtle, low frequency
    eg_noise = _node(nodes, "ShaderNodeTexNoise", (-200, -2150))
    eg_noise.inputs["Scale"].default_value      = 4.0
    eg_noise.inputs["Detail"].default_value     = 0.0
    eg_noise.inputs["Roughness"].default_value  = 0.5
    link(eg_coord.outputs["Object"], eg_noise.inputs["Vector"])

    eg_crack_mix = _node(nodes, "ShaderNodeMixRGB", (480, -1950))
    eg_crack_mix.blend_type = "MULTIPLY"
    eg_crack_mix.inputs["Fac"].default_value = 0.18   # very subtle cracks
    link(eg_ring_ramp.outputs["Color"], eg_crack_mix.inputs["Color1"])
    link(eg_noise.outputs["Color"],     eg_crack_mix.inputs["Color2"])

    # Blend end-grain color over side color using the end-face mask
    eg_col_mix = _node(nodes, "ShaderNodeMixRGB", (680, -1800))
    link(eg_mask_sep.outputs["Red"],     eg_col_mix.inputs["Fac"])
    link(hsv.outputs["Color"],           eg_col_mix.inputs["Color1"])
    link(eg_crack_mix.outputs["Color"],  eg_col_mix.inputs["Color2"])

    # End grain roughness: slightly higher (0.88) than sides.
    # MULTIPLY_ADD: mask * (0.88 - 0.80) + 0.80
    eg_rough_mix = _node(nodes, "ShaderNodeMath", (680, -1950))
    eg_rough_mix.operation = "MULTIPLY_ADD"
    eg_rough_mix.inputs[1].default_value = 0.08   # 0.88 - 0.80
    eg_rough_mix.inputs[2].default_value = 0.80   # base side roughness
    link(eg_mask_sep.outputs["Red"], eg_rough_mix.inputs[0])

    # Blend end-grain roughness over side roughness using the same face mask
    final_rough = _node(nodes, "ShaderNodeMixRGB", (680, -2100))
    link(eg_mask_sep.outputs["Red"],    final_rough.inputs["Fac"])
    link(rough_mix.outputs["Color"],    final_rough.inputs["Color1"])
    link(eg_rough_mix.outputs["Value"], final_rough.inputs["Color2"])
    link(final_rough.outputs["Color"],  bsdf.inputs["Roughness"])

    # -----------------------------------------------------------------------
    # Edge wear — ShaderNodeBevel approximates curvature (Cycles only).
    # Brightens color and raises roughness at exposed edges.
    # -----------------------------------------------------------------------
    bevel = _node(nodes, "ShaderNodeBevel", (200, -200))
    bevel.inputs["Radius"].default_value = 0.012

    dot = _node(nodes, "ShaderNodeVectorMath", (400, -200))
    dot.operation = "DOT_PRODUCT"
    geom = _node(nodes, "ShaderNodeNewGeometry", (200, -350))
    link(bevel.outputs["Normal"], dot.inputs[0])
    link(geom.outputs["Normal"],  dot.inputs[1])

    inv = _node(nodes, "ShaderNodeMath", (580, -200))
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    link(dot.outputs["Value"], inv.inputs[1])

    # Tighter ramp: only the sharpest edges catch light
    edge_ramp = _node(nodes, "ShaderNodeValToRGB", (720, -200))
    edge_ramp.color_ramp.interpolation = "EASE"
    edge_ramp.color_ramp.elements[0].position = 0.70
    edge_ramp.color_ramp.elements[1].position = 1.00
    link(inv.outputs["Value"], edge_ramp.inputs["Fac"])

    # Soft 7% lighten on edges
    edge_col_mix = _node(nodes, "ShaderNodeMixRGB", (920, 100))
    edge_col_mix.blend_type = "LIGHTEN"
    edge_col_mix.inputs["Fac"].default_value  = 0.07
    edge_col_mix.inputs["Color2"].default_value = (0.88, 0.83, 0.73, 1)
    link(edge_ramp.outputs["Color"],       edge_col_mix.inputs["Fac"])
    link(eg_col_mix.outputs["Color"],      edge_col_mix.inputs["Color1"])
    link(edge_col_mix.outputs["Color"],    bsdf.inputs["Base Color"])

    # Roughness targets: base 0.80, worn edges 0.65, deep grooves 0.90
    # edge_ramp already gives us the edge mask (0 = flat, 1 = sharp edge)
    edge_rough = _node(nodes, "ShaderNodeMath", (720, -380))
    edge_rough.operation = "MULTIPLY_ADD"
    edge_rough.inputs[1].default_value = -0.15   # 0.80 - 0.65
    edge_rough.inputs[2].default_value =  0.80   # base
    link(edge_ramp.outputs["Color"], edge_rough.inputs[0])

    # Groove mask from roughness noise: values above 0.7 are grooves
    groove_mask = _node(nodes, "ShaderNodeValToRGB", (720, -520))
    groove_mask.color_ramp.interpolation = "EASE"
    groove_mask.color_ramp.elements[0].position = 0.65
    groove_mask.color_ramp.elements[1].position = 1.00
    link(noise_rough.outputs["Fac"], groove_mask.inputs["Fac"])

    groove_rough = _node(nodes, "ShaderNodeMath", (920, -450))
    groove_rough.operation = "MULTIPLY_ADD"
    groove_rough.inputs[1].default_value =  0.10   # 0.90 - 0.80
    groove_rough.inputs[2].default_value =  0.0
    link(groove_mask.outputs["Color"], groove_rough.inputs[0])

    # Combine: start from final_rough, subtract edge wear, add groove depth
    rough_edge_sub = _node(nodes, "ShaderNodeMath", (920, -580))
    rough_edge_sub.operation = "SUBTRACT"
    link(final_rough.outputs["Color"],  rough_edge_sub.inputs[0])
    link(edge_rough.outputs["Value"],   rough_edge_sub.inputs[1])

    rough_groove_add = _node(nodes, "ShaderNodeMath", (1060, -580))
    rough_groove_add.operation = "ADD"
    link(rough_edge_sub.outputs["Value"],  rough_groove_add.inputs[0])
    link(groove_rough.outputs["Value"],    rough_groove_add.inputs[1])

    # Add per-object roughness shift
    rough_inst = _node(nodes, "ShaderNodeMath", (1060, -460))
    rough_inst.operation = "ADD"
    link(rough_groove_add.outputs["Value"], rough_inst.inputs[0])
    link(rough_shift.outputs["Value"],      rough_inst.inputs[1])

    rough_clamp = _node(nodes, "ShaderNodeMath", (1060, -700))
    rough_clamp.operation = "MINIMUM"
    rough_clamp.use_clamp = True
    rough_clamp.inputs[1].default_value = 1.0
    link(rough_inst.outputs["Value"],  rough_clamp.inputs[0])
    link(rough_clamp.outputs["Value"], bsdf.inputs["Roughness"])

    # -----------------------------------------------------------------------
    # Displacement
    # -----------------------------------------------------------------------
    if disp:
        dtex2 = _tex(nodes, disp, "Non-Color", (-800, -1700))
        vec(dtex2)
        dnode = _node(nodes, "ShaderNodeDisplacement", (-400, -1700))
        dnode.inputs["Scale"].default_value = 0.015
        link(dtex2.outputs["Color"],        dnode.inputs["Height"])
        link(dnode.outputs["Displacement"], output.inputs["Displacement"])
        mat.displacement_method = "BOTH"

    return mat


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

def assign_timber_material(obj):
    """Assign (or replace slot 0 of) the shared timber material on obj."""
    mat = get_timber_material()
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
