"""
rope_material.py — Procedural cordage shader for "The Giant Raft"
Style: 50% Journey · 30% Sea of Thieves · 20% Firewatch

Fully procedural — no image textures.
Supports age (0=fresh, 1=old jungle rope) and wetness (0=dry, 1=soaked).
Material name: MAT_Rope
"""

import bpy

MATERIAL_NAME = "MAT_Rope"

# Hemp/jute palette (linear sRGB)
_COL_LIGHT  = (0.62, 0.52, 0.36, 1)   # warm hemp
_COL_MID    = (0.44, 0.36, 0.24, 1)   # jute brown
_COL_DARK   = (0.28, 0.22, 0.14, 1)   # shadow / old fiber
_COL_GREEN  = (0.30, 0.34, 0.20, 1)   # damp / mossy tint


def _node(nodes, bl_idname, location, **kwargs):
    n = nodes.new(bl_idname)
    n.location = location
    for k, v in kwargs.items():
        setattr(n, k, v)
    return n


def get_rope_material(age=0.3, wetness=0.0):
    """
    Return shared MAT_Rope, creating it if absent.
    age     – 0.0 fresh … 1.0 old jungle rope
    wetness – 0.0 dry  … 1.0 soaked
    """
    if MATERIAL_NAME in bpy.data.materials:
        return bpy.data.materials[MATERIAL_NAME]

    mat = bpy.data.materials.new(MATERIAL_NAME)
    mat.use_nodes = True
    nt    = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    def link(a, b):
        links.new(a, b)

    output = _node(nodes, "ShaderNodeOutputMaterial", (1400, 0))
    bsdf   = _node(nodes, "ShaderNodeBsdfPrincipled",  (1100, 0))
    link(bsdf.outputs["BSDF"], output.inputs["Surface"])

    # -----------------------------------------------------------------------
    # Coordinates — Object space + Mapping
    # Z axis = rope length; scale Z low so fibers stretch along the rope.
    # -----------------------------------------------------------------------
    texcoord = _node(nodes, "ShaderNodeTexCoord", (-1400, 0))
    mapping  = _node(nodes, "ShaderNodeMapping",  (-1200, 0))
    mapping.inputs["Scale"].default_value = (1.0, 1.0, 0.08)
    link(texcoord.outputs["Object"], mapping.inputs["Vector"])

    def vec(n):
        link(mapping.outputs["Vector"], n.inputs["Vector"])

    # -----------------------------------------------------------------------
    # Per-object variation (Object Info Random)
    # -----------------------------------------------------------------------
    obj_info = _node(nodes, "ShaderNodeObjectInfo", (-1400, -300))

    hue_var = _node(nodes, "ShaderNodeMath", (-1100, -300))
    hue_var.operation = "MULTIPLY_ADD"
    hue_var.inputs[1].default_value =  0.04    # ±2° hue range
    hue_var.inputs[2].default_value = -0.02
    link(obj_info.outputs["Random"], hue_var.inputs[0])

    sat_var = _node(nodes, "ShaderNodeMath", (-1100, -420))
    sat_var.operation = "MULTIPLY_ADD"
    sat_var.inputs[1].default_value =  0.10    # ±5% saturation
    sat_var.inputs[2].default_value =  0.95
    link(obj_info.outputs["Random"], sat_var.inputs[0])

    val_var = _node(nodes, "ShaderNodeMath", (-1100, -540))
    val_var.operation = "MULTIPLY_ADD"
    val_var.inputs[1].default_value =  0.16    # ±8% value
    val_var.inputs[2].default_value =  0.92
    link(obj_info.outputs["Random"], val_var.inputs[0])

    # -----------------------------------------------------------------------
    # Base color — Wave (fiber twist bands) + Noise (fiber variation)
    # -----------------------------------------------------------------------
    wave = _node(nodes, "ShaderNodeTexWave", (-800, 200))
    wave.wave_type    = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value      = 18.0
    wave.inputs["Distortion"].default_value =  3.5
    wave.inputs["Detail"].default_value     =  2.0
    wave.inputs["Detail Scale"].default_value = 2.0
    wave.inputs["Detail Roughness"].default_value = 0.6
    vec(wave)

    noise_fiber = _node(nodes, "ShaderNodeTexNoise", (-800, -50))
    noise_fiber.inputs["Scale"].default_value      =  6.0
    noise_fiber.inputs["Detail"].default_value     =  2.0
    noise_fiber.inputs["Roughness"].default_value  =  0.6
    noise_fiber.inputs["Distortion"].default_value =  0.4
    vec(noise_fiber)

    # Blend wave + noise for fiber texture
    fiber_mix = _node(nodes, "ShaderNodeMixRGB", (-500, 100))
    fiber_mix.blend_type = "OVERLAY"
    fiber_mix.inputs["Fac"].default_value = 0.45
    link(wave.outputs["Color"],        fiber_mix.inputs["Color1"])
    link(noise_fiber.outputs["Color"], fiber_mix.inputs["Color2"])

    # Color ramp: dark → mid → light hemp
    col_ramp = _node(nodes, "ShaderNodeValToRGB", (-250, 100))
    col_ramp.color_ramp.interpolation = "EASE"
    col_ramp.color_ramp.elements[0].position = 0.0
    col_ramp.color_ramp.elements[0].color    = _COL_DARK
    col_ramp.color_ramp.elements[1].position = 1.0
    col_ramp.color_ramp.elements[1].color    = _COL_LIGHT
    mid_el = col_ramp.color_ramp.elements.new(0.45)
    mid_el.color = _COL_MID
    link(fiber_mix.outputs["Color"], col_ramp.inputs["Fac"])

    # Age darkens and desaturates toward old jungle rope
    age_mix = _node(nodes, "ShaderNodeMixRGB", (50, 100))
    age_mix.blend_type = "MULTIPLY"
    age_mix.inputs["Fac"].default_value = age * 0.55
    age_mix.inputs["Color2"].default_value = (0.55, 0.48, 0.36, 1)
    link(col_ramp.outputs["Color"], age_mix.inputs["Color1"])

    # Wetness adds green tint
    wet_mix = _node(nodes, "ShaderNodeMixRGB", (250, 100))
    wet_mix.blend_type = "MIX"
    wet_mix.inputs["Fac"].default_value = wetness * 0.4
    wet_mix.inputs["Color2"].default_value = _COL_GREEN
    link(age_mix.outputs["Color"], wet_mix.inputs["Color1"])

    # Per-object HSV shift
    hsv = _node(nodes, "ShaderNodeHueSaturation", (450, 100))
    hsv.inputs["Fac"].default_value = 1.0
    link(wet_mix.outputs["Color"], hsv.inputs["Color"])
    link(hue_var.outputs["Value"], hsv.inputs["Hue"])
    link(sat_var.outputs["Value"], hsv.inputs["Saturation"])
    link(val_var.outputs["Value"], hsv.inputs["Value"])
    link(hsv.outputs["Color"],     bsdf.inputs["Base Color"])

    # -----------------------------------------------------------------------
    # Roughness — very matte, avg 0.82, range 0.72–0.92
    # -----------------------------------------------------------------------
    noise_rough = _node(nodes, "ShaderNodeTexNoise", (-800, -400))
    noise_rough.inputs["Scale"].default_value     =  4.0
    noise_rough.inputs["Detail"].default_value    =  1.0
    noise_rough.inputs["Roughness"].default_value =  0.5
    vec(noise_rough)

    rough_ramp = _node(nodes, "ShaderNodeValToRGB", (-500, -400))
    rough_ramp.color_ramp.interpolation = "LINEAR"
    rough_ramp.color_ramp.elements[0].position = 0.0
    rough_ramp.color_ramp.elements[0].color    = (0.72, 0.72, 0.72, 1)
    rough_ramp.color_ramp.elements[1].position = 1.0
    rough_ramp.color_ramp.elements[1].color    = (0.92, 0.92, 0.92, 1)
    link(noise_rough.outputs["Fac"], rough_ramp.inputs["Fac"])

    # Wetness smooths roughness (wet rope is slightly shinier)
    rough_wet = _node(nodes, "ShaderNodeMath", (-250, -400))
    rough_wet.operation = "MULTIPLY_ADD"
    rough_wet.inputs[1].default_value = 1.0 - wetness * 0.18
    rough_wet.inputs[2].default_value = 0.0
    link(rough_ramp.outputs["Color"], rough_wet.inputs[0])
    link(rough_wet.outputs["Value"],  bsdf.inputs["Roughness"])

    # -----------------------------------------------------------------------
    # Bump — broad fiber ridges, very subtle (0.01–0.03)
    # -----------------------------------------------------------------------
    voronoi = _node(nodes, "ShaderNodeTexVoronoi", (-800, -700))
    voronoi.voronoi_dimensions = "3D"
    voronoi.feature = "DISTANCE_TO_EDGE"
    voronoi.inputs["Scale"].default_value = 22.0
    vec(voronoi)

    bump = _node(nodes, "ShaderNodeBump", (-400, -700))
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.02
    link(voronoi.outputs["Distance"], bump.inputs["Height"])
    link(bump.outputs["Normal"],      bsdf.inputs["Normal"])

    bsdf.inputs["Metallic"].default_value  = 0.0
    bsdf.inputs["Specular IOR Level"].default_value = 0.04 if "Specular IOR Level" in bsdf.inputs else None

    return mat


def assign_rope_material(obj, age=0.3, wetness=0.0):
    """Assign (or replace slot 0 of) MAT_Rope on obj."""
    mat = get_rope_material(age=age, wetness=wetness)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
