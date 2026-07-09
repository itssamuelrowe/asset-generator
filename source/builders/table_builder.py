"""
table_builder.py — Procedural hand-hewn work table for "The Giant Raft"

Structure is described by a TableStructure (see table_structure.py).
The builder engine reads that description and generates geometry; it never
hard-codes counts or roles.

Coordinate system
    Origin      : tabletop surface centre
    +Z          : up
    +X          : along table length
    +Y          : along table width
    Legs        : point down (−Z)

Assembly order (matches spec)
    1. Solve dimensions
    2. Generate timbers  → pick 10
    3. Generate planks   → pick 5
    4. Build leg frame
    5. Lash upper rails
    6. Lash lower stretchers
    7. Place tabletop
    8. Attach tabletop (lashings or pegs)
    9. Final cleanup
"""

import bpy
import math
import random
from mathutils import Vector, Matrix, Euler

from primitives.timber_beam import create_timber
from primitives.plank_beam import create_plank
from materials.timber_material import assign_timber_material
from rope.rope import create_rope
from rope.rope_joinery import Joinery
from structure.table_structure import TableStructure, canonical_work_table


# ---------------------------------------------------------------------------
# Dimension solver
# ---------------------------------------------------------------------------

def _solve(width, depth, height, plank_count, seed):
    rng = random.Random(seed)

    leg_w      = max(0.070, min(0.090, depth * 0.10))
    rail_w     = max(0.050, min(0.070, leg_w * 0.75))
    stretch_w  = max(0.040, min(0.060, rail_w * 0.80))
    plank_t    = max(0.035, min(0.050, rail_w * 0.70))

    overhang   = 0.035 + (((seed * 2654435761) & 0xFFFF) / 0xFFFF - 0.5) * 0.010
    leg_inset  = max(0.060, min(0.120, depth * 0.12))

    # Leg centre offsets from table centre
    leg_cx = width * 0.5 - leg_inset - leg_w * 0.5
    leg_cy = depth * 0.5 - leg_inset - leg_w * 0.5
    leg_cx += rng.uniform(-0.005, 0.005)
    leg_cy += rng.uniform(-0.005, 0.005)

    # Rail spans (outer face to outer face of leg pair)
    long_rail_span  = leg_cx * 2   # along X, one per Y side
    short_rail_span = leg_cy * 2   # along Y, one per X end

    # Tabletop planks
    gap          = rng.uniform(0.002, 0.008)
    plank_length = min(long_rail_span * 1.02, width * 1.05)
    width_budget = depth - overhang * 2 - gap * (plank_count - 1)
    base_pw      = max(0.08, min(0.18, width_budget / plank_count))
    raw_w        = [base_pw * (1.0 + rng.uniform(-0.08, 0.08)) for _ in range(plank_count)]
    raw_w        = [max(0.08, min(0.18, w)) for w in raw_w]
    plank_widths = [w * width_budget / sum(raw_w) for w in raw_w]

    leg_height   = height - plank_t
    stretch_frac = 0.35   # lower stretchers at 35 % up from floor

    return dict(
        seed          = seed,
        width         = width,
        depth         = depth,
        height        = height,
        leg_w         = leg_w,
        rail_w        = rail_w,
        stretch_w     = stretch_w,
        plank_t       = plank_t,
        overhang      = overhang,
        leg_cx        = leg_cx,
        leg_cy        = leg_cy,
        long_rail_span  = long_rail_span,
        short_rail_span = short_rail_span,
        leg_height    = leg_height,
        plank_count   = plank_count,
        plank_widths  = plank_widths,
        plank_length  = plank_length,
        gap           = gap,
        stretch_frac  = stretch_frac,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _link(obj, parent, loc=(0, 0, 0), rot=(0, 0, 0)):
    obj.location       = loc
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    obj.parent = parent


def _align_z_to(direction):
    z    = direction.normalized()
    up   = Vector((0, 0, 1))
    axis = up.cross(z)
    if axis.length < 1e-6:
        return Euler((0, 0, 0), 'XYZ') if z.dot(up) > 0 else Euler((math.pi, 0, 0), 'XYZ')
    axis.normalize()
    angle = math.acos(max(-1.0, min(1.0, up.dot(z))))
    return Matrix.Rotation(angle, 4, axis).to_euler('XYZ')


def _place_timber(d, parent, pa, pb, width, seed_offset):
    diff   = pb - pa
    length = diff.length
    if length < 0.005:
        return None
    inset    = width * 0.5
    shrink   = max(0.0, length - inset * 2) / length
    centre   = (pa + pb) * 0.5
    pa_in    = centre + (pa - centre) * shrink
    length_in = diff.length * shrink
    rot = _align_z_to(diff)
    beam = create_timber(length=length_in, width=width, height=width,
                         seed=d['seed'] * 31 + seed_offset)
    assign_timber_material(beam)
    _link(beam, parent, loc=tuple(pa_in), rot=tuple(rot))
    return beam


def _add_lashing(parent, pos_a, pos_b, beam_radius, seed, style="cross"):
    if style == "cross":
        path = Joinery.bind_cross_members(pos_a, pos_b,
                                          beam_radius=beam_radius, strength="medium")
    else:
        path = Joinery.secure_to_post(pos_a, post_radius=beam_radius,
                                      rope_radius=0.004, load="medium")
    rope = create_rope(path, rope_type="lashing", age=0.4, seed=seed)
    rope.parent = parent
    bpy.context.collection.objects.link(rope)


# ---------------------------------------------------------------------------
# Stage builders  (each reads d + structure, returns joint positions)
# ---------------------------------------------------------------------------

def _build_legs(d, structure, parent):
    """
    Place 4 legs.  Returns dict: leg_name → (top: Vector, foot: Vector).
    """
    lx, ly = d['leg_cx'], d['leg_cy']
    top_z  = -d['plank_t']
    foot_z = top_z - d['leg_height']
    lw     = d['leg_w']

    positions = {
        "leg_front_left":  Vector((-lx, -ly, top_z)),
        "leg_front_right": Vector(( lx, -ly, top_z)),
        "leg_rear_left":   Vector((-lx,  ly, top_z)),
        "leg_rear_right":  Vector(( lx,  ly, top_z)),
    }

    joints = {}
    for i, timber in enumerate(t for t in structure.timbers if t.role == "leg"):
        top  = positions[timber.name]
        foot = Vector((top.x, top.y, foot_z))
        leg  = create_timber(length=d['leg_height'], width=lw, height=lw,
                             seed=d['seed'] * 13 + i)
        assign_timber_material(leg)
        _link(leg, parent, loc=tuple(top), rot=(math.pi, 0.0, 0.0))
        joints[timber.name] = (top, foot)

    return joints


def _build_upper_rails(d, structure, parent, leg_joints):
    """
    Place long rails and short rails at the top of the leg frame.

    long_rail  — runs along X (table length), one per Y side (front / rear).
                 Sits directly under the planks; planks lash to these.
    short_rail — runs along Y (table depth), one per X side (left / right).
                 Connects the two legs on each side, preventing spread.

    Returns dict: rail_name → (pa: Vector, pb: Vector).
    """
    top_z  = -d['plank_t']
    rail_z = top_z - d['rail_w'] * 0.5
    rw     = d['rail_w']
    joints = {}

    for i, timber in enumerate(t for t in structure.timbers
                                if t.role in ("long_rail", "short_rail")):
        if timber.role == "long_rail":
            # Runs along X between the two legs on the front or rear Y side
            if timber.side == "front":
                pa = Vector((leg_joints["leg_front_left"][0].x,
                             leg_joints["leg_front_left"][0].y, rail_z))
                pb = Vector((leg_joints["leg_front_right"][0].x,
                             leg_joints["leg_front_right"][0].y, rail_z))
            else:  # rear
                pa = Vector((leg_joints["leg_rear_left"][0].x,
                             leg_joints["leg_rear_left"][0].y, rail_z))
                pb = Vector((leg_joints["leg_rear_right"][0].x,
                             leg_joints["leg_rear_right"][0].y, rail_z))
        else:
            # short_rail: runs along Y between front and rear legs on one X side
            if timber.side == "left":
                pa = Vector((leg_joints["leg_front_left"][0].x,
                             leg_joints["leg_front_left"][0].y, rail_z))
                pb = Vector((leg_joints["leg_rear_left"][0].x,
                             leg_joints["leg_rear_left"][0].y, rail_z))
            else:  # right
                pa = Vector((leg_joints["leg_front_right"][0].x,
                             leg_joints["leg_front_right"][0].y, rail_z))
                pb = Vector((leg_joints["leg_rear_right"][0].x,
                             leg_joints["leg_rear_right"][0].y, rail_z))

        _place_timber(d, parent, pa, pb, rw, 50 + i)
        joints[timber.name] = (pa, pb)

    return joints


def _build_lower_stretchers(d, structure, parent, leg_joints):
    """
    Place lower stretchers at stretch_frac height.
    Mirror the long_rail orientation: front stretcher connects front-left
    and front-right legs; rear stretcher connects rear-left and rear-right.
    Returns dict: stretcher_name → (pa: Vector, pb: Vector).
    """
    frac   = d['stretch_frac']
    sw     = d['stretch_w']
    joints = {}

    for i, timber in enumerate(t for t in structure.timbers if t.role == "stretcher"):
        if timber.side == "front":
            top_a, foot_a = leg_joints["leg_front_left"]
            top_b, foot_b = leg_joints["leg_front_right"]
        else:  # rear
            top_a, foot_a = leg_joints["leg_rear_left"]
            top_b, foot_b = leg_joints["leg_rear_right"]

        pa = top_a.lerp(foot_a, frac)
        pb = top_b.lerp(foot_b, frac)
        _place_timber(d, parent, pa, pb, sw, 70 + i)
        joints[timber.name] = (pa, pb)

    return joints


def _build_tabletop(d, structure, parent, rng):
    """Place tabletop planks centred over the frame."""
    total_width = sum(d['plank_widths']) + d['gap'] * (d['plank_count'] - 1)
    y = -total_width * 0.5
    rot = (math.pi * 0.5, 0.0, math.pi * 0.5)

    plank_objects = {}
    for plank_role in structure.planks:
        pw = d['plank_widths'][plank_role.index]
        cy = y + pw * 0.5
        dz = rng.uniform(-0.0005, 0.0005)
        plank = create_plank(length=d['plank_length'], width=pw, height=d['plank_t'],
                             seed=d['seed'] * 200 + plank_role.index)
        assign_timber_material(plank)
        _link(plank, parent,
              loc=(-d['plank_length'] * 0.5, cy, -d['plank_t'] * 0.5 + dz),
              rot=rot)
        plank_objects[plank_role.name] = cy
        y += pw + d['gap']

    return plank_objects


def _rail_x_at_leg(leg_top, rail_pa, rail_pb):
    """
    Return the point on the rail (pa→pb) that is closest to the leg centre
    in the XY plane — i.e. the actual intersection point of leg and rail.
    """
    seg   = rail_pb - rail_pa
    seg_l = seg.length
    if seg_l < 1e-6:
        return rail_pa.copy()
    t = (leg_top - rail_pa).dot(seg) / (seg_l * seg_l)
    t = max(0.0, min(1.0, t))
    return rail_pa.lerp(rail_pb, t)


def _apply_lashings(d, structure, parent, leg_joints, rail_joints, stretch_joints,
                    plank_objects, attachment):
    """
    Walk the LashingSpec list and emit rope lashings for each joint.

    Frame lashings (leg × rail / stretcher)
        Square lashing at the exact intersection point.  Both points passed
        to bind_cross_members are the same world position — the crossing —
        approached from each member’s axis.  This is visible and decorative.

    Tabletop lashings (plank × long rail)
        Small lashing from underneath.  The rope wraps around the plank and
        the rail at the crossing point.  Skipped when attachment == "pegs".
    """
    all_joints = {**leg_joints, **rail_joints, **stretch_joints}

    for i, spec in enumerate(structure.lashings):
        seed = d['seed'] + i * 11

        # --- Tabletop lashings (plank × long rail, hidden underside) --------
        if spec.member_a in plank_objects or spec.member_b in plank_objects:
            if attachment != "lashing":
                continue
            plank_name = spec.member_a if spec.member_a in plank_objects else spec.member_b
            rail_name  = spec.member_b if spec.member_a in plank_objects else spec.member_a
            if rail_name not in all_joints:
                continue
            # Intersection: plank Y centre × rail Z, X from rail midpoint
            plank_cy     = plank_objects[plank_name]
            rail_pa, rail_pb = all_joints[rail_name]
            rail_mid     = (rail_pa + rail_pb) * 0.5
            cross        = Vector((rail_mid.x, plank_cy, rail_mid.z))
            # pos_a: on the plank (above the rail), pos_b: on the rail (below)
            pos_plank = cross + Vector((0, 0,  d['plank_t'] * 0.5))
            pos_rail  = cross + Vector((0, 0, -d['rail_w']  * 0.5))
            _add_lashing(parent, pos_plank, pos_rail, d['rail_w'] * 0.5, seed,
                         style="cross")
            continue

        # --- Frame lashings (leg × rail or leg × stretcher) -----------------
        if spec.member_a not in all_joints or spec.member_b not in all_joints:
            continue

        leg_name  = spec.member_a if spec.member_a in leg_joints else spec.member_b
        rail_name = spec.member_b if spec.member_a in leg_joints else spec.member_a

        leg_top, _       = all_joints[leg_name]
        rail_pa, rail_pb = all_joints[rail_name]

        # Exact crossing point: project leg XY onto the rail line
        cross = _rail_x_at_leg(leg_top, rail_pa, rail_pb)
        cross.z = rail_pa.z   # stay at rail height

        # Two points straddling the joint along each member’s axis
        pos_leg  = cross + Vector((0, 0,  d['rail_w']))
        pos_rail = cross + Vector((0, 0, -d['rail_w']))
        _add_lashing(parent, pos_leg, pos_rail, d['rail_w'], seed, style="cross")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TableBuilder:
    """
    Procedural hand-hewn work table builder.

    The same engine is used for any TableStructure; vary the structure to
    get different table layouts without touching the builder.

    Args:
        width               – overall length along X  (default 1.5 m)
        depth               – overall width  along Y  (default 0.8 m)
        height              – floor to tabletop top   (default 0.85 m)
        plank_count         – number of tabletop planks (default 5)
        tabletop_attachment – "lashing" or "pegs"
        age                 – 0–1 weathering
        damage              – 0–1 damage level (reserved for future use)
        wetness             – 0–1 wetness (reserved for future use)
        seed                – integer; same seed → same table
        structure           – TableStructure; defaults to canonical_work_table()
    """

    def __init__(
        self,
        width=1.5,
        depth=0.8,
        height=0.85,
        plank_count=5,
        leg_count=4,
        rail_style="double",
        tabletop_style="planks",
        lashing_style="square",
        tabletop_attachment="lashing",
        age=0.35,
        damage=0.2,
        wetness=0.1,
        seed=42,
        structure: TableStructure = None,
    ):
        self.d = _solve(width, depth, height, plank_count, seed)
        self.d['age']    = age
        self.d['damage'] = damage
        self.d['wetness'] = wetness
        self.tabletop_attachment = tabletop_attachment
        self.structure = structure or canonical_work_table(plank_count)
        self.rng = random.Random(seed + 77)

    def build(self) -> bpy.types.Object:
        """
        Execute the full assembly sequence and return the root Empty.

        Assembly order:
            legs → upper rails → lower stretchers →
            tabletop planks → lashings / pegs
        """
        d   = self.d
        s   = self.structure
        rng = self.rng

        empty = bpy.data.objects.new(f"Table_{d['seed']}", None)
        empty.empty_display_type = 'PLAIN_AXES'
        empty.empty_display_size = 0.05
        bpy.context.collection.objects.link(empty)

        leg_joints     = _build_legs(d, s, empty)
        rail_joints    = _build_upper_rails(d, s, empty, leg_joints)
        stretch_joints = _build_lower_stretchers(d, s, empty, leg_joints)
        plank_objects  = _build_tabletop(d, s, empty, rng)

        _apply_lashings(d, s, empty,
                        leg_joints, rail_joints, stretch_joints,
                        plank_objects, self.tabletop_attachment)

        leg_count    = sum(1 for t in s.timbers if t.role == "leg")
        rail_count   = sum(1 for t in s.timbers if t.role in ("long_rail", "short_rail"))
        stretch_count = sum(1 for t in s.timbers if t.role == "stretcher")
        print(
            f"  Table seed={d['seed']} "
            f"{d['width']:.2f}×{d['depth']:.2f}×{d['height']:.2f}m  "
            f"legs={leg_count} rails={rail_count} stretchers={stretch_count} "
            f"planks={d['plank_count']} attach={self.tabletop_attachment}"
        )
        return empty


# ---------------------------------------------------------------------------
# Convenience function (backwards-compatible with main.py)
# ---------------------------------------------------------------------------

def create_table(table_length=1.50, table_width=0.80, table_height=0.85, seed=42):
    return TableBuilder(
        width=table_length,
        depth=table_width,
        height=table_height,
        seed=seed,
    ).build()
