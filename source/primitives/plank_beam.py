"""
plank_beam.py — Procedural hand-hewn plank for "The Giant Raft"

A plank is wide and thin (width 3–6× height). The full deformation
pipeline is identical to timber_beam; only _params differs:

    - height multiplier kept small (planks are thin)
    - taper primarily in Y (thickness), X stays stable
    - bow strong in X (wide face), minimal in Y
    - twist reduced to 0.5–2°
    - hew_depth: top/bottom faces cut deeper, narrow edges lighter
    - hew_facet_depth: shallower on wide faces, more visible on edges
    - cs_drift: Y-axis faces drift more (thickness variation)
    - wave_amp: wide faces get more waviness, edges less
    - edge_wear_base: long top/bottom edges wear heavily, short edges lightly
    - end chip spread wider (plank end spans more width)
"""

import bpy
import bmesh
import random
from mathutils import Vector

from primitives.timber_beam import (
    _waves, _bbox, _face_of, _sn,
    make_log, apply_taper, apply_bow, apply_twist,
    flatten_sides, hew_faces, distort_cross_section,
    apply_surface_waviness, wear_edges, shape_ends,
    apply_knots, _build_mesh,
)


# ---------------------------------------------------------------------------
# Plank parameters  (overrides timber _params entirely)
# ---------------------------------------------------------------------------

def _params(seed, length, width, height):
    rng = random.Random(seed)

    # Planks have more sides to give the wide face enough vertices
    sides = rng.randint(12, 16)

    def facet_angles(n):
        return [rng.uniform(-0.06, 0.06) for _ in range(n)]

    end0_seed = rng.randint(0, 9999)
    end1_seed = rng.randint(0, 9999)

    # Wide faces: 1=+y (top), 3=-y (bottom)
    # Narrow edges: 0=+x (right), 2=-x (left)
    return dict(
        seed            = seed,
        sides           = sides,
        rings           = 32,

        # Width stays close to nominal; height (thickness) kept thin
        width           = width  * rng.uniform(1.02, 1.08),
        height          = height * rng.uniform(1.02, 1.08),

        # Taper mostly in Y (thickness), X barely changes
        taper_start     = rng.uniform(0.97, 1.00),
        taper_end       = rng.uniform(0.88, 0.96),
        taper_exp       = rng.uniform(0.9, 1.2),

        # Low noise — planks are already flat, not round logs
        log_noise_waves = _waves(rng, 3, 2.0),
        log_noise_amp   = rng.uniform(0.03, 0.07),

        # Bow strong along width (X), minimal through thickness (Y)
        bow_x           = rng.uniform(-0.03, 0.03) * length,
        bow_y           = rng.uniform(-0.005, 0.005) * length,

        # Planks twist less than round logs
        twist_deg       = rng.uniform(0.5, 2.0) * rng.choice([-1, 1]),

        # Wide faces (top/bottom) cut deeper; narrow edges lighter
        # face order: 0=+x, 1=+y, 2=-x, 3=-y
        hew_depth       = [
            rng.uniform(0.95, 1.02),   # +x narrow edge
            rng.uniform(1.05, 1.20),   # +y wide top face
            rng.uniform(0.95, 1.02),   # -x narrow edge
            rng.uniform(1.05, 1.20),   # -y wide bottom face
        ],

        # More facet segments on wide faces; fewer on narrow edges
        hew_facet_n     = [
            rng.randint(2, 4),         # narrow edge
            rng.randint(5, 9),         # wide top
            rng.randint(2, 4),         # narrow edge
            rng.randint(5, 9),         # wide bottom
        ],
        hew_facet_ang   = [facet_angles(rng.randint(2, 9)) for _ in range(4)],

        # Shallower on wide faces (large area), more visible on narrow edges
        hew_facet_depth = [
            rng.uniform(0.010, 0.020) * height,   # narrow edge
            rng.uniform(0.004, 0.008) * width,    # wide top
            rng.uniform(0.010, 0.020) * height,   # narrow edge
            rng.uniform(0.004, 0.008) * width,    # wide bottom
        ],

        # Thickness (Y) drifts more; width (X) stays stable
        cs_drift        = [
            rng.uniform(0.02, 0.06) * (width  * 0.5) * rng.choice([-1, 1]),  # +x
            rng.uniform(0.10, 0.20) * (height * 0.5) * rng.choice([-1, 1]),  # +y
            rng.uniform(0.02, 0.06) * (width  * 0.5) * rng.choice([-1, 1]),  # -x
            rng.uniform(0.10, 0.20) * (height * 0.5) * rng.choice([-1, 1]),  # -y
        ],
        cs_drift_peak   = [rng.uniform(0.25, 0.75) for _ in range(4)],

        # Wide faces get more waviness; narrow edges get less
        wave_amp        = [
            rng.uniform(0.002, 0.005),   # narrow edge
            rng.uniform(0.006, 0.014),   # wide top
            rng.uniform(0.002, 0.005),   # narrow edge
            rng.uniform(0.006, 0.014),   # wide bottom
        ],
        wave_freq       = [rng.uniform(1.0, 2.0) for _ in range(4)],
        wave_phase      = [rng.uniform(0, 6.283) for _ in range(4)],

        # Long top/bottom edges wear heavily; short side edges lightly
        edge_wear_base  = [
            rng.uniform(0.4, 0.8),    # +x/+y corner (short edge)
            rng.uniform(1.5, 2.5),    # +y/-x corner (long top edge)
            rng.uniform(0.4, 0.8),    # -x/-y corner (short edge)
            rng.uniform(1.5, 2.5),    # -y/+x corner (long bottom edge)
        ],
        edge_wear_waves = [_waves(rng, 2, 1.0) for _ in range(4)],

        # Ends: wider chip spread to match the plank's wide face
        end0_ax         = rng.uniform(-0.20, 0.20),
        end0_ay         = rng.uniform(-0.08, 0.08),   # less tilt through thin axis
        end0_seed       = end0_seed,
        end1_ax         = rng.uniform(-0.20, 0.20),
        end1_ay         = rng.uniform(-0.08, 0.08),
        end1_seed       = end1_seed,
        end_chip        = rng.uniform(0.012, 0.028) * width,
        end_compress    = rng.uniform(0.008, 0.018) * height,

        knots           = [
            dict(t=rng.uniform(0.15, 0.85),
                 face=rng.choice([1, 3]),          # knots on wide faces only
                 depth=rng.uniform(0.008, 0.018) * height,
                 radius=rng.uniform(0.04, 0.10) * width)
            for _ in range(rng.randint(0, 2))
        ],
    )


# ---------------------------------------------------------------------------
# hew_faces override — per-face depth list instead of single scalar
# ---------------------------------------------------------------------------

import math as _math

def _hew_faces_plank(pts, p, length):
    """
    Same logic as timber hew_faces but reads hew_facet_depth as a
    per-face list so wide and narrow faces get different cut depths.
    """
    rings      = len(pts)
    depth_list = p['hew_facet_depth']

    for ri, row in enumerate(pts):
        t = ri / (rings - 1)
        max_x, min_x, max_y, min_y = _bbox(row)

        new_row = []
        for x, y, z in row:
            face   = _face_of(x, y, max_x, min_x, max_y, min_y)
            depth  = depth_list[face]
            n_segs = p['hew_facet_n'][face]
            angles = p['hew_facet_ang'][face]
            n_a    = len(angles)
            seg    = min(int(t * n_segs), n_segs - 1)
            tilt   = angles[seg % n_a]
            seg_t  = t * n_segs - seg
            push   = depth * (_math.tan(tilt) * seg_t + seg * 0.15 / n_segs)

            normals = [(1, 0), (0, 1), (-1, 0), (0, -1)]
            nx, ny  = normals[face]
            new_row.append((x - nx * push, y - ny * push, z))
        pts[ri] = new_row


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_plank(length=2.0, width=0.25, height=0.04, seed=42):
    """
    Procedurally generate a stylized hand-hewn plank.

    Args:
        length  – plank length along Z
        width   – nominal X width  (wide face)
        height  – nominal Y height (thickness)
        seed    – integer; same seed always produces the same plank

    Returns:
        bpy.types.Object  (not linked to any collection)
    """
    p = _params(seed, length, width, height)

    pts = make_log(p, length)
    apply_taper(pts, p, length)
    apply_bow(pts, p, length)
    apply_twist(pts, p, length)
    flatten_sides(pts, p)
    _hew_faces_plank(pts, p, length)
    distort_cross_section(pts, p, length)
    apply_surface_waviness(pts, p, length)
    wear_edges(pts, p)
    shape_ends(pts, p, length)
    apply_knots(pts, p, length)

    bm   = _build_mesh(pts)
    mesh = bpy.data.meshes.new("Plank")
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate()
    mesh.update()

    return bpy.data.objects.new("Plank", mesh)
