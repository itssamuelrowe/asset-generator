"""
timber_beam.py — Procedural hand-hewn timber for "The Giant Raft"
Style: 50% Journey · 30% Sea of Thieves · 20% Firewatch

Pipeline (one function per stage):
  1. make_log              — tapered N-sided cylinder, organic radius noise
  2. apply_taper           — non-linear taper along length
  3. apply_bow             — smooth quadratic arc
  4. apply_twist           — 1–3° gradual rotation
  5. flatten_sides         — carve 4 flat faces from the log
  6. hew_faces             — 4–8 explicit planar axe-cut segments per face
  7. distort_cross_section — slow per-face profile drift (5–8%)
  8. apply_surface_waviness— 1–2 low-freq waves per face, 2–4 mm amplitude
  9. wear_edges            — variable-width bevel with flat/round sections
 10. shape_ends            — unique angled cut + chips + splinters per end
 11. apply_knots           — shallow dimples
 12. Assemble into bpy Object

No materials. No UVs. No subdivision. Target 200–350 tris.
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sn(t, waves):
    """Summed sinusoids at t. waves = [(freq, phase, amp), ...]"""
    return sum(math.sin(t * f + p) * a for f, p, a in waves)


def _waves(rng, n=3, base=2.0):
    return [(base * (k + 1), rng.uniform(0, 6.283), 1.0 / (k + 1))
            for k in range(n)]


def _bbox(row):
    xs = [v[0] for v in row]
    ys = [v[1] for v in row]
    return max(xs), min(xs), max(ys), min(ys)


def _face_of(x, y, max_x, min_x, max_y, min_y):
    """Return index of nearest face: 0=+x, 1=+y, 2=-x, 3=-y"""
    return min(range(4), key=lambda f: [
        max_x - x, max_y - y, x - min_x, y - min_y][f])


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

def _params(seed, length, width, height):
    rng = random.Random(seed)

    sides = rng.randint(10, 14)

    # Per-face axe facets: list of N tilt angles (radians) per face.
    # Each angle is the inward tilt of one planar cut segment.
    def facet_angles(n):
        return [rng.uniform(-0.018, 0.018) for _ in range(n)]

    # Per-end unique seeds drive chip pattern and splinter offsets
    end0_seed = rng.randint(0, 9999)
    end1_seed = rng.randint(0, 9999)

    return dict(
        seed            = seed,
        sides           = sides,
        rings           = 32,

        width           = width  * rng.uniform(1.25, 1.35),
        height          = height * rng.uniform(1.20, 1.30),

        taper_start     = rng.uniform(0.95, 1.00),
        taper_end       = rng.uniform(0.75, 0.88),
        taper_exp       = rng.uniform(0.8, 1.3),

        log_noise_waves = _waves(rng, 3, 2.0),
        log_noise_amp   = rng.uniform(0.10, 0.18),

        bow_x           = rng.uniform(-0.04, 0.04) * length,
        bow_y           = rng.uniform(-0.03, 0.03) * length,

        # Twist: 4–9 degrees total
        twist_deg       = rng.uniform(4.0, 9.0) * rng.choice([-1, 1]),

        hew_depth       = [rng.uniform(0.88, 1.14) for _ in range(4)],

        # Axe facets: 4–8 segments per face, each with its own tilt
        hew_facet_n     = [rng.randint(4, 8) for _ in range(4)],
        hew_facet_ang   = [facet_angles(rng.randint(4, 8)) for _ in range(4)],
        # Depth of each facet cut (inward push at segment boundary)
        hew_facet_depth = rng.uniform(0.03, 0.06) * width,

        # Cross-section drift: per-face slow evolution (15–25% of half-width)
        cs_drift        = [rng.uniform(0.15, 0.25) * (width * 0.5)
                           * rng.choice([-1, 1]) for _ in range(4)],
        cs_drift_peak   = [rng.uniform(0.25, 0.75) for _ in range(4)],

        # Surface waviness: 1–2 waves, 8–16 mm amplitude, per face
        wave_amp        = [rng.uniform(0.008, 0.016) for _ in range(4)],
        wave_freq       = [rng.uniform(1.0, 2.0) for _ in range(4)],
        wave_phase      = [rng.uniform(0, 6.283) for _ in range(4)],

        # Edge wear: per-corner base width + along-length variation
        edge_wear_base  = [rng.uniform(1.0, 2.5) for _ in range(4)],
        edge_wear_waves = [_waves(rng, 2, 1.0) for _ in range(4)],

        # Ends: unique per end
        end0_ax         = rng.uniform(-0.20, 0.20),
        end0_ay         = rng.uniform(-0.16, 0.16),
        end0_seed       = end0_seed,
        end1_ax         = rng.uniform(-0.20, 0.20),
        end1_ay         = rng.uniform(-0.16, 0.16),
        end1_seed       = end1_seed,
        end_chip        = rng.uniform(0.018, 0.040) * width,
        end_compress    = rng.uniform(0.018, 0.040) * height,

        knots           = [
            dict(t=rng.uniform(0.15, 0.85),
                 face=rng.randint(0, 3),
                 depth=rng.uniform(0.015, 0.030) * width,
                 radius=rng.uniform(0.06, 0.14) * width)
            for _ in range(rng.randint(1, 3))
        ],
    )


# ---------------------------------------------------------------------------
# Stage 1 — Log
# ---------------------------------------------------------------------------

def make_log(p, length):
    sides = p['sides']
    rings = p['rings']
    w     = p['width']
    h     = p['height']
    pts   = []

    for ri in range(rings):
        t = ri / (rings - 1)
        z = t * length
        log_noise = _sn(t, p['log_noise_waves']) * p['log_noise_amp']
        row = []
        for si in range(sides):
            angle = 2 * math.pi * si / sides
            rx = w * 0.5 * (1.0 + log_noise * math.cos(angle * 2 + 0.5))
            ry = h * 0.5 * (1.0 + log_noise * math.sin(angle * 2 + 1.1))
            row.append((math.cos(angle) * rx, math.sin(angle) * ry, z))
        pts.append(row)

    return pts


# ---------------------------------------------------------------------------
# Stage 2 — Taper
# ---------------------------------------------------------------------------

def apply_taper(pts, p, length):
    rings = len(pts)
    for ri, row in enumerate(pts):
        t  = ri / (rings - 1)
        tp = ((1 - t) * p['taper_start'] + t * p['taper_end']) ** p['taper_exp']
        pts[ri] = [(x * tp, y * tp, z) for x, y, z in row]


# ---------------------------------------------------------------------------
# Stage 3 — Bow
# ---------------------------------------------------------------------------

def apply_bow(pts, p, length):
    bx, by = p['bow_x'], p['bow_y']
    rings  = len(pts)
    for ri, row in enumerate(pts):
        t  = ri / (rings - 1)
        cx = bx * 4 * t * (1 - t)
        cy = by * 4 * t * (1 - t)
        pts[ri] = [(x + cx, y + cy, z) for x, y, z in row]


# ---------------------------------------------------------------------------
# Stage 4 — Twist  (1–3°)
# ---------------------------------------------------------------------------

def apply_twist(pts, p, length):
    rings     = len(pts)
    total_rad = math.radians(p['twist_deg'])
    for ri, row in enumerate(pts):
        t     = ri / (rings - 1)
        angle = total_rad * t
        c, s  = math.cos(angle), math.sin(angle)
        pts[ri] = [(x * c - y * s, x * s + y * c, z) for x, y, z in row]


# ---------------------------------------------------------------------------
# Stage 5 — Flatten sides
# ---------------------------------------------------------------------------

def flatten_sides(pts, p):
    hd = p['hew_depth']
    for ri, row in enumerate(pts):
        max_x, min_x, max_y, min_y = _bbox(row)
        lim_px =  max_x / hd[0]
        lim_py =  max_y / hd[1]
        lim_nx =  min_x / hd[2]
        lim_ny =  min_y / hd[3]
        pts[ri] = [
            (min(max(x, lim_nx), lim_px),
             min(max(y, lim_ny), lim_py), z)
            for x, y, z in row
        ]


# ---------------------------------------------------------------------------
# Stage 6 — Hew faces  (explicit planar axe-cut segments)
# ---------------------------------------------------------------------------

def hew_faces(pts, p, length):
    """
    Each face is divided into N segments along Z. Within each segment
    the face plane tilts by a fixed angle — a true planar axe cut.
    Vertices on that face are pushed inward by the segment's plane offset.

    This produces the characteristic staircase of broad flat facets:
        ----------
         \________
          \_______
    """
    rings = len(pts)
    depth = p['hew_facet_depth']

    for ri, row in enumerate(pts):
        t = ri / (rings - 1)
        max_x, min_x, max_y, min_y = _bbox(row)

        new_row = []
        for x, y, z in row:
            face = _face_of(x, y, max_x, min_x, max_y, min_y)

            n_segs  = p['hew_facet_n'][face]
            angles  = p['hew_facet_ang'][face]
            n_a     = len(angles)
            seg     = int(t * n_segs)
            seg     = min(seg, n_segs - 1)
            tilt    = angles[seg % n_a]

            # Inward push: base depth * tilt contribution
            # tilt gives the slope of the cut plane; at segment boundaries
            # the accumulated offset creates a visible step/facet edge.
            seg_t   = t * n_segs - seg          # 0..1 within segment
            push    = depth * (math.tan(tilt) * seg_t + seg * 0.15 / n_segs)

            normals = [(1, 0), (0, 1), (-1, 0), (0, -1)]
            nx, ny  = normals[face]
            new_row.append((x - nx * push, y - ny * push, z))
        pts[ri] = new_row


# ---------------------------------------------------------------------------
# Stage 7 — Distort cross-section  (slow per-face profile drift 5–8%)
# ---------------------------------------------------------------------------

def distort_cross_section(pts, p, length):
    """
    Each face's plane distance drifts slowly along Z with a bell-curve
    peak at cs_drift_peak[f]. One face bulges, another flattens, etc.
    """
    rings = len(pts)
    for ri, row in enumerate(pts):
        t = ri / (rings - 1)
        max_x, min_x, max_y, min_y = _bbox(row)

        new_row = []
        for x, y, z in row:
            face = _face_of(x, y, max_x, min_x, max_y, min_y)
            pk   = p['cs_drift_peak'][face]
            bell = math.exp(-((t - pk) ** 2) / 0.12)
            push = p['cs_drift'][face] * bell

            normals = [(1, 0), (0, 1), (-1, 0), (0, -1)]
            nx, ny  = normals[face]
            new_row.append((x + nx * push, y + ny * push, z))
        pts[ri] = new_row


# ---------------------------------------------------------------------------
# Stage 8 — Surface waviness  (1–2 low-freq waves, 2–4 mm amplitude)
# ---------------------------------------------------------------------------

def apply_surface_waviness(pts, p, length):
    """
    Very low-frequency sinusoidal push per face. One or two full cycles
    over the beam length. No high-frequency noise.
    """
    rings = len(pts)
    for ri, row in enumerate(pts):
        t = ri / (rings - 1)
        max_x, min_x, max_y, min_y = _bbox(row)

        new_row = []
        for x, y, z in row:
            face = _face_of(x, y, max_x, min_x, max_y, min_y)
            push = p['wave_amp'][face] * math.sin(
                t * p['wave_freq'][face] * 2 * math.pi + p['wave_phase'][face])

            normals = [(1, 0), (0, 1), (-1, 0), (0, -1)]
            nx, ny  = normals[face]
            new_row.append((x + nx * push, y + ny * push, z))
        pts[ri] = new_row


# ---------------------------------------------------------------------------
# Stage 9 — Wear edges  (variable bevel width, flat/round sections)
# ---------------------------------------------------------------------------

def wear_edges(pts, p):
    """
    Each of the 4 long corners gets a bevel whose width varies along Z:
    some sections are nearly flat (wide bevel), others are sharper.
    """
    rings = len(pts)
    for ri, row in enumerate(pts):
        t  = ri / (rings - 1)
        xs = [v[0] for v in row]
        ys = [v[1] for v in row]
        cx = (max(xs) + min(xs)) * 0.5
        cy = (max(ys) + min(ys)) * 0.5
        half_w = max(xs) - cx
        half_h = max(ys) - cy

        new_row = []
        for x, y, z in row:
            dx, dy = x - cx, y - cy
            ci = (0 if dx >= 0 else 2) + (0 if dy >= 0 else 1)

            # Bevel width varies along length via low-freq wave
            wear = p['edge_wear_base'][ci] * (
                1.0 + 0.4 * _sn(t, p['edge_wear_waves'][ci]))

            rx = abs(dx) / (half_w + 1e-6)
            ry = abs(dy) / (half_h + 1e-6)
            corner_weight = rx * ry
            inset = 0.055 * min(half_w, half_h) * wear * corner_weight

            nr = math.sqrt(dx * dx + dy * dy) or 1.0
            new_row.append((x - (dx / nr) * inset,
                            y - (dy / nr) * inset, z))
        pts[ri] = new_row


# ---------------------------------------------------------------------------
# Stage 10 — Shape ends  (unique per end: angle + chips + splinters)
# ---------------------------------------------------------------------------

def shape_ends(pts, p, length):
    """
    Each end has its own cut angle, chip pattern (driven by its own seed),
    and splinter offsets. No two ends share parameters.
    """
    ends = [
        (0,            p['end0_ax'], p['end0_ay'], p['end0_seed'], -1),
        (len(pts) - 1, p['end1_ax'], p['end1_ay'], p['end1_seed'],  1),
    ]
    for ri, ax, ay, eseed, sign in ends:
        erng    = random.Random(eseed)
        row     = pts[ri]
        sides   = len(row)
        chip    = p['end_chip']
        compress = p['end_compress']

        # Per-vertex splinter offsets (unique to this end)
        splinters = [erng.uniform(-chip * 0.6, chip * 0.6) for _ in range(sides)]

        cx_e = sum(v[0] for v in row) / sides
        cy_e = sum(v[1] for v in row) / sides

        new_row = []
        for si, (x, y, z) in enumerate(row):
            dz      = x * math.tan(ax) + y * math.tan(ay)
            chip_v  = math.sin(si * 2.71 + eseed * 0.001) * chip
            splint  = splinters[si]
            x      += (cx_e - x) * compress * 2
            y      += (cy_e - y) * compress * 2
            new_row.append((x, y, z + dz + chip_v + splint))
        pts[ri] = new_row


# ---------------------------------------------------------------------------
# Stage 11 — Knots
# ---------------------------------------------------------------------------

def apply_knots(pts, p, length):
    rings = len(pts)
    for ri, row in enumerate(pts):
        t  = ri / (rings - 1)
        max_x, min_x, max_y, min_y = _bbox(row)
        cx = (max_x + min_x) * 0.5
        cy = (max_y + min_y) * 0.5

        new_row = []
        for x, y, z in row:
            dx, dy = x - cx, y - cy
            nr   = math.sqrt(dx * dx + dy * dy) or 1.0
            face = _face_of(x, y, max_x, min_x, max_y, min_y)
            for k in p['knots']:
                if face == k['face']:
                    dt = abs(t - k['t']) * length
                    if dt < k['radius'] * 4:
                        falloff = max(0.0, 1.0 - (dt / (k['radius'] * 4)) ** 2)
                        x -= (dx / nr) * k['depth'] * falloff
                        y -= (dy / nr) * k['depth'] * falloff
            new_row.append((x, y, z))
        pts[ri] = new_row


# ---------------------------------------------------------------------------
# Mesh assembly
# ---------------------------------------------------------------------------

def _build_mesh(pts):
    rings = len(pts)
    sides = len(pts[0])
    bm    = bmesh.new()

    verts = [[bm.verts.new(Vector(v)) for v in row] for row in pts]

    for ri in range(rings - 1):
        for si in range(sides):
            sn = (si + 1) % sides
            bm.faces.new([verts[ri][si], verts[ri][sn],
                          verts[ri+1][sn], verts[ri+1][si]])

    for ri, sign in ((0, -1), (rings - 1, 1)):
        row = verts[ri]
        xs  = [v.co.x for v in row]
        ys  = [v.co.y for v in row]
        zs  = [v.co.z for v in row]
        ctr = bm.verts.new(Vector((
            sum(xs) / sides, sum(ys) / sides, sum(zs) / sides)))
        for si in range(sides):
            sn = (si + 1) % sides
            if sign == -1:
                bm.faces.new([ctr, row[sn], row[si]])
            else:
                bm.faces.new([ctr, row[si], row[sn]])

    bm.normal_update()
    return bm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_timber(length=2.0, width=0.2, height=0.18, seed=42):
    """
    Procedurally generate a stylized hand-hewn timber beam.

    Args:
        length  – beam length along Z
        width   – nominal X width
        height  – nominal Y height
        seed    – integer; same seed always produces the same beam

    Returns:
        bpy.types.Object  (not linked to any collection)
    """
    p = _params(seed, length, width, height)

    pts = make_log(p, length)
    apply_taper(pts, p, length)
    apply_bow(pts, p, length)
    apply_twist(pts, p, length)
    flatten_sides(pts, p)
    hew_faces(pts, p, length)
    distort_cross_section(pts, p, length)
    apply_surface_waviness(pts, p, length)
    wear_edges(pts, p)
    shape_ends(pts, p, length)
    apply_knots(pts, p, length)

    bm   = _build_mesh(pts)
    mesh = bpy.data.meshes.new("TimberBeam")
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate()
    mesh.update()

    return bpy.data.objects.new("TimberBeam", mesh)
