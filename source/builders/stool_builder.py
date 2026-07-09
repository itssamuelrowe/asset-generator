"""
stool_builder.py — Procedural hand-hewn stool for "The Giant Raft"
Style: Amazon river settler carpentry — chunky, intentional, structurally sound.

Coordinate system
  Origin      : seat top centre
  +Z          : up
  Legs        : point down (−Z)
  Seat planks : run along Y (depth), stacked along X

Assembly order
  1. Compute dimensions & variant
  2. Build seat planks
  3. Build leg frame (with ground levelling)
  4. Build braces (H-frame | X-brace | box)
  5. Add rope lashings (probability-gated)
  6. Assign materials
  7. Parent everything to Empty
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix, Euler

from primitives.timber_beam import create_timber
from primitives.plank_beam import create_plank
from materials.timber_material import assign_timber_material


# ---------------------------------------------------------------------------
# Variant table  (chosen by seed % 4)
# ---------------------------------------------------------------------------
# A: plain four-leg          — no braces
# B: cross-braced            — X-brace on both side pairs
# C: heavy work stool        — box frame (4 side rails)
# D: fishing stool           — H-frame (2 side rails only, front+back)

_VARIANTS = ['A', 'B', 'C', 'D']


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

def _dims(seed):
    """
    Return a dict of all construction dimensions.
    Variation is intentionally narrow — a carpenter measures twice.
    """
    rng = random.Random(seed)
    variant = _VARIANTS[seed % 4]

    seat_w = rng.uniform(0.32, 0.44)          # seat width  (X)
    seat_d = rng.uniform(0.28, 0.38)          # seat depth  (Y)
    seat_h = rng.uniform(0.42, 0.54)          # floor to seat top (Z)

    # Chunky proportions per spec
    plank_thick = rng.uniform(0.045, 0.060)   # 45–60 mm
    leg_w       = rng.uniform(0.070, 0.090)   # 70–90 mm
    brace_w     = rng.uniform(0.055, 0.070)   # 55–70 mm

    n_planks = rng.randint(3, 5)
    # Equal base width ± 5 % variation
    base_pw  = seat_w / n_planks
    plank_widths = [base_pw * rng.uniform(0.95, 1.05) for _ in range(n_planks)]
    # Normalise so they sum exactly to seat_w
    total = sum(plank_widths)
    plank_widths = [pw * seat_w / total for pw in plank_widths]

    gap = rng.uniform(0.002, 0.005)           # uniform gap between planks

    # Splay: 4–8° outward, same for all legs (slight per-leg noise ±0.5°)
    base_splay = rng.uniform(math.radians(4), math.radians(8))
    leg_splay  = [base_splay + rng.uniform(-math.radians(0.5), math.radians(0.5))
                  for _ in range(4)]

    # Length variation: ±1 % only
    leg_vary = [rng.uniform(0.99, 1.01) for _ in range(4)]

    # Brace height: 25–40 % up from floor
    brace_h_frac = rng.uniform(0.25, 0.40)

    # Rope probability
    rope_prob = rng.uniform(0.4, 0.8)

    return dict(
        seed         = seed,
        variant      = variant,
        seat_w       = seat_w,
        seat_d       = seat_d,
        seat_h       = seat_h,
        plank_thick  = plank_thick,
        leg_w        = leg_w,
        brace_w      = brace_w,
        n_planks     = n_planks,
        plank_widths = plank_widths,
        gap          = gap,
        leg_splay    = leg_splay,
        leg_vary     = leg_vary,
        brace_h_frac = brace_h_frac,
        rope_prob    = rope_prob,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _link(obj, parent, loc=(0, 0, 0), rot=(0, 0, 0)):
    obj.location      = loc
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    obj.parent = parent


def _align_z_to(direction):
    """
    Return an Euler that rotates the local +Z axis to point along `direction`.
    Used to orient beams (which run along their local +Z) toward a target.
    """
    z   = direction.normalized()
    up  = Vector((0, 0, 1))
    axis = up.cross(z)
    if axis.length < 1e-6:
        # Already aligned or anti-aligned
        if z.dot(up) > 0:
            return Euler((0, 0, 0), 'XYZ')
        else:
            return Euler((math.pi, 0, 0), 'XYZ')
    axis.normalize()
    angle = math.acos(max(-1.0, min(1.0, up.dot(z))))
    return Matrix.Rotation(angle, 4, axis).to_euler('XYZ')


def _leg_top_positions(d):
    """
    Four leg attachment points at the underside of the seat.
    Inset from seat edge by half leg width so legs sit inside the seat boundary.
    Returns list of Vector (x, y, z=−plank_thick).
    """
    inset = d['leg_w'] * 0.5
    hw    = d['seat_w'] * 0.5 - inset
    hd    = d['seat_d'] * 0.5 - inset
    z     = -d['plank_thick']
    return [
        Vector(( hw,  hd, z)),   # 0: front-right
        Vector((-hw,  hd, z)),   # 1: front-left
        Vector((-hw, -hd, z)),   # 2: back-left
        Vector(( hw, -hd, z)),   # 3: back-right
    ]


def _foot_position(top, splay, leg_length):
    """
    Given a leg top position and outward splay angle, return the foot position.
    Splay is applied radially outward from the stool centre (XY origin).
    """
    outward = Vector((top.x, top.y, 0.0))
    if outward.length < 1e-6:
        outward = Vector((1, 0, 0))
    outward.normalize()
    # Foot shifts outward by sin(splay)*length, drops by cos(splay)*length
    foot = Vector((
        top.x + outward.x * math.sin(splay) * leg_length,
        top.y + outward.y * math.sin(splay) * leg_length,
        top.z - math.cos(splay) * leg_length,
    ))
    return foot


def _leg_rotation(top, foot):
    """
    Euler rotation to orient a beam (local +Z) from `top` toward `foot`.
    The beam origin will be placed at `top`; it extends toward `foot`.
    """
    return _align_z_to(foot - top)


# ---------------------------------------------------------------------------
# Rope lashing  (simple torus at joint)
# ---------------------------------------------------------------------------

def _add_rope(parent, pos, radius=0.012, tube_r=0.004, seed=0):
    """Add a torus rope lashing at `pos`, parented to `parent`."""
    rng   = random.Random(seed)
    turns = rng.randint(2, 4)
    for t in range(turns):
        offset_z = (t - turns * 0.5) * tube_r * 2.5
        bpy.ops.mesh.primitive_torus_add(
            major_radius   = radius,
            minor_radius   = tube_r,
            major_segments = 24,
            minor_segments = 8,
            location       = (pos.x, pos.y, pos.z + offset_z),
        )
        rope = bpy.context.active_object
        assign_timber_material(rope)   # reuse wood material; close enough
        rope.parent = parent


# ---------------------------------------------------------------------------
# Seat
# ---------------------------------------------------------------------------

def _build_seat(d, parent, rng):
    """
    Place n_planks side-by-side along X, running full depth along Y.
    Planks are generated along their local +Z; rotated −90° around X
    so they run along world +Y.  Top face sits at Z = 0.
    """
    plank_thick = d['plank_thick']
    total_gap   = d['gap'] * (d['n_planks'] - 1)
    # Start X so the whole seat is centred
    start_x = -(d['seat_w'] + total_gap) * 0.5

    x = start_x
    for i, pw in enumerate(d['plank_widths']):
        cx = x + pw * 0.5
        # Tiny height offset for handmade feel (±1 mm)
        dz = rng.uniform(-0.001, 0.001)

        plank = create_plank(
            length = d['seat_d'],
            width  = pw,
            height = plank_thick,
            seed   = d['seed'] * 100 + i,
        )
        assign_timber_material(plank)

        # Rotate −90° around X: plank local +Z → world +Y
        # Centre of plank sits at z = −plank_thick/2
        _link(plank, parent,
              loc = (cx, 0.0, -plank_thick * 0.5 + dz),
              rot = (-math.pi * 0.5, 0.0, 0.0))

        x += pw + d['gap']


# ---------------------------------------------------------------------------
# Leg frame
# ---------------------------------------------------------------------------

def _build_legs(d, parent, rng):
    """
    Place four legs, splay outward 4–8°.
    After computing all foot positions, find the highest foot Z (least negative)
    and extend every leg so all feet reach exactly Z = −seat_h.

    Returns (tops, feet, leg_lengths) — all as Vectors / floats.
    """
    tops    = _leg_top_positions(d)
    splay   = d['leg_splay']
    vary    = d['leg_vary']
    seat_h  = d['seat_h']
    leg_w   = d['leg_w']

    # Nominal leg length (top to foot along the beam axis)
    nominal_ll = seat_h - d['plank_thick']

    # First pass: compute foot positions with ±1% variation
    raw_lengths = [nominal_ll * vary[i] for i in range(4)]
    raw_feet    = [_foot_position(tops[i], splay[i], raw_lengths[i])
                   for i in range(4)]

    # Ground levelling: all feet must reach Z = −seat_h
    # The foot Z = top.z − cos(splay)*length  →  length = (top.z − target_z) / cos(splay)
    target_z = -seat_h
    final_lengths = []
    final_feet    = []
    for i in range(4):
        cos_s = math.cos(splay[i])
        ll    = (tops[i].z - target_z) / cos_s
        final_lengths.append(ll)
        final_feet.append(_foot_position(tops[i], splay[i], ll))

    # Build leg objects
    for i in range(4):
        ll  = final_lengths[i]
        top = tops[i]
        rot = _leg_rotation(top, final_feet[i])

        leg = create_timber(
            length = ll,
            width  = leg_w,
            height = leg_w,
            seed   = d['seed'] * 7 + i,
        )
        assign_timber_material(leg)
        _link(leg, parent, loc=tuple(top), rot=tuple(rot))

    return tops, final_feet, final_lengths


# ---------------------------------------------------------------------------
# Brace helpers
# ---------------------------------------------------------------------------

def _brace_attach(top, foot, frac):
    """Point on leg at `frac` from top toward foot."""
    return top.lerp(foot, frac)


def _place_brace(d, parent, pa, pb, seed_offset):
    """
    Place a single brace beam between world points pa and pb.
    The brace is inset by half its width at each end to simulate a lap joint
    (beam sits against the leg face rather than passing through it).
    """
    brace_w = d['brace_w']
    diff    = pb - pa
    length  = diff.length
    if length < 0.01:
        return

    # Inset both ends by half brace width (lap joint clearance)
    inset  = brace_w * 0.5
    shrink = max(0.0, length - inset * 2) / length
    centre = (pa + pb) * 0.5
    pa_in  = centre + (pa - centre) * shrink
    pb_in  = centre + (pb - centre) * shrink
    length_in = (pb_in - pa_in).length

    rot = _align_z_to(pb_in - pa_in)

    brace = create_timber(
        length = length_in,
        width  = brace_w,
        height = brace_w,
        seed   = d['seed'] * 50 + seed_offset,
    )
    assign_timber_material(brace)
    _link(brace, parent, loc=tuple(pa_in), rot=tuple(rot))


def _build_braces_H(d, parent, tops, feet, rng):
    """
    H-frame: one horizontal rail on each of the two long sides (front & back).
    Rails run between the two legs on each side at brace_h_frac height.
    """
    frac = d['brace_h_frac']
    # Front side: legs 0 (FR) and 1 (FL)
    # Back  side: legs 3 (BR) and 2 (BL)
    for side_idx, (ia, ib) in enumerate([(0, 1), (3, 2)]):
        pa = _brace_attach(tops[ia], feet[ia], frac)
        pb = _brace_attach(tops[ib], feet[ib], frac)
        _place_brace(d, parent, pa, pb, side_idx)
        if rng.random() < d['rope_prob']:
            _add_rope(parent, pa, radius=d['leg_w'] * 0.55,
                      tube_r=0.004, seed=d['seed'] + side_idx * 3)


def _build_braces_X(d, parent, tops, feet, rng):
    """
    X-brace: diagonal cross on both side pairs.
    Each pair gets two crossing diagonals.
    Diagonals are offset ±brace_w/2 in the perpendicular axis so they
    pass in front of / behind each other rather than intersecting.
    """
    frac = d['brace_h_frac']
    pairs = [(0, 2), (1, 3)]   # diagonal pairs across the stool
    for pi, (ia, ib) in enumerate(pairs):
        pa_lo = _brace_attach(tops[ia], feet[ia], frac + 0.10)
        pa_hi = _brace_attach(tops[ia], feet[ia], frac - 0.10)
        pb_lo = _brace_attach(tops[ib], feet[ib], frac + 0.10)
        pb_hi = _brace_attach(tops[ib], feet[ib], frac - 0.10)
        _place_brace(d, parent, pa_lo, pb_hi, pi * 2)
        _place_brace(d, parent, pa_hi, pb_lo, pi * 2 + 1)
        if rng.random() < d['rope_prob']:
            mid = (pa_lo + pb_hi) * 0.5
            _add_rope(parent, mid, radius=d['brace_w'] * 0.6,
                      tube_r=0.004, seed=d['seed'] + pi * 5)


def _build_braces_box(d, parent, tops, feet, rng):
    """
    Box frame: four horizontal rails connecting all adjacent leg pairs
    at brace_h_frac height — forms a complete rectangular frame.
    """
    frac = d['brace_h_frac']
    # Adjacent pairs: FR-FL, FL-BL, BL-BR, BR-FR
    adj = [(0, 1), (1, 2), (2, 3), (3, 0)]
    for si, (ia, ib) in enumerate(adj):
        pa = _brace_attach(tops[ia], feet[ia], frac)
        pb = _brace_attach(tops[ib], feet[ib], frac)
        _place_brace(d, parent, pa, pb, si)
        if rng.random() < d['rope_prob']:
            _add_rope(parent, pa, radius=d['leg_w'] * 0.55,
                      tube_r=0.004, seed=d['seed'] + si * 7)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_stool(seed=42, shape='square', braces=True):
    """
    Build a procedural hand-hewn stool.

    Args:
        seed   – integer; same seed → same stool
        shape  – ignored (kept for API compatibility; layout always square)
        braces – whether to add structural braces

    Returns:
        bpy.types.Object  (Empty, parent of all pieces, linked to scene)
    """
    d   = _dims(seed)
    rng = random.Random(seed + 99)

    # Parent empty
    empty = bpy.data.objects.new(f"Stool_{seed}", None)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = 0.04
    bpy.context.collection.objects.link(empty)

    # 1. Seat
    _build_seat(d, empty, rng)

    # 2. Leg frame
    tops, feet, lengths = _build_legs(d, empty, rng)

    # 3. Braces
    if braces:
        variant = d['variant']
        if variant == 'A':
            pass                                          # no braces
        elif variant == 'B':
            _build_braces_X(d, empty, tops, feet, rng)
        elif variant == 'C':
            _build_braces_box(d, empty, tops, feet, rng)
        else:                                             # D
            _build_braces_H(d, empty, tops, feet, rng)

    print(f"  Stool seed={seed} variant={d['variant']} "
          f"seat={d['seat_w']:.3f}×{d['seat_d']:.3f} "
          f"h={d['seat_h']:.3f} planks={d['n_planks']}")

    return empty
