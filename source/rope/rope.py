"""
rope.py — Procedural Cordage System for "The Giant Raft"
Style: 50% Journey · 30% Sea of Thieves · 20% Firewatch

Architecture
------------
create_rope(path, ...)          ← single public entry point
        │
   RopeGenerator
        │
        ├── _sample_path()          sample + resample input path
        ├── _parallel_transport()   stable tangent frame (no twist artifacts)
        ├── _strand_params()        per-strand personality
        ├── _build_strand()         fat tube along frame-relative orbit
        ├── _apply_end()            end treatments
        └── _make_object()          cleanup + material

The generator NEVER computes rope paths.
Paths come from RopePath or Joinery.

Rope types
----------
twine       r=0.004   2 strands
utility     r=0.012   3 strands   ← default
structural  r=0.022   3 strands
mooring     r=0.040   3 strands
palm_fiber  r=0.015   4 strands   flat/irregular
decorative  r=0.008   3 strands   tight twist

Public API
----------
create_rope(path, rope_type, radius, twist_density, age, wetness,
            fray, end_style, lod, seed)
create_rope_lods(path, ...)  → (lod0, lod1, lod2)
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix

from materials.rope_material import assign_rope_material
from rope.rope_path import RopePath


# ---------------------------------------------------------------------------
# Rope type presets
# (radius_m, strand_count, twist_cycles_per_m, strand_sides_lod0)
# ---------------------------------------------------------------------------
_ROPE_TYPES = {
    "twine":      (0.004, 2, 8.0, 6),
    "utility":    (0.012, 3, 5.0, 8),
    "structural": (0.022, 3, 4.0, 8),
    "mooring":    (0.040, 3, 3.0, 9),
    "palm_fiber": (0.015, 4, 3.5, 7),
    "decorative": (0.008, 3, 7.0, 7),
    # Legacy aliases
    "rope":       (0.012, 3, 5.0, 8),
    "lashing":    (0.006, 2, 8.0, 6),
    "vine":       (0.018, 3, 2.5, 8),
}

# Samples per metre at each LOD
_SAMPLES_PER_M = (60, 30, 12)
# Strand tube sides at each LOD
_SIDES_LOD     = (8, 6, 5)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _rng(seed):
    return random.Random(int(seed))


def _sin_sum(t, waves):
    return sum(math.sin(t * f + p) * a for f, p, a in waves)


def _rand_waves(rng, n=3, base=1.5):
    return [(base * (k + 1), rng.uniform(0, 6.283), 1.0 / (k + 1))
            for k in range(n)]


def _path_length(pts):
    return sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))


# ---------------------------------------------------------------------------
# Parallel transport frame
# ---------------------------------------------------------------------------

def _parallel_transport(pts):
    """
    Build a stable, twist-free Frenet-like frame along pts.

    Returns list of (tangent, normal, binormal) as Vector triples,
    one per point.  Uses parallel transport to avoid the gimbal-lock
    and sudden flips that plague naive Frenet frames on curved paths.
    """
    n = len(pts)
    tangents = []

    # Tangents via central differences
    for i in range(n):
        if i == 0:
            t = (pts[1] - pts[0])
        elif i == n - 1:
            t = (pts[-1] - pts[-2])
        else:
            t = (pts[i + 1] - pts[i - 1])
        l = t.length
        tangents.append(t / l if l > 1e-9 else Vector((0, 0, 1)))

    # Seed the first normal — pick any vector not parallel to tangent[0]
    t0  = tangents[0]
    ref = Vector((0, 0, 1)) if abs(t0.dot(Vector((0, 0, 1)))) < 0.9 \
          else Vector((1, 0, 0))
    n0  = t0.cross(ref).normalized()
    b0  = t0.cross(n0).normalized()

    frames = [(tangents[0], n0, b0)]

    # Propagate frame by rotating the previous normal into the new tangent plane
    for i in range(1, n):
        t_prev, n_prev, b_prev = frames[-1]
        t_curr = tangents[i]

        # Rotation axis and angle from t_prev to t_curr
        axis  = t_prev.cross(t_curr)
        al    = axis.length
        if al > 1e-9:
            axis  /= al
            angle  = math.acos(max(-1.0, min(1.0, t_prev.dot(t_curr))))
            rot    = Matrix.Rotation(angle, 3, axis)
            n_curr = (rot @ n_prev).normalized()
            b_curr = t_curr.cross(n_curr).normalized()
        else:
            n_curr = n_prev
            b_curr = b_prev

        frames.append((t_curr, n_curr, b_curr))

    return frames


# ---------------------------------------------------------------------------
# Strand parameters — each strand has its own personality
# ---------------------------------------------------------------------------

def _strand_params(strand_idx, base_r, base_twist, seed, age):
    rng = _rng(seed + strand_idx * 1031)

    r_offsets     = [0.06, -0.04, 0.02, 0.05]
    twist_offsets = [0.00,  0.08, -0.05, 0.03]

    r_scale     = 1.0 + r_offsets[strand_idx % 4]     + rng.uniform(-0.02, 0.02)
    twist_scale = 1.0 + twist_offsets[strand_idx % 4] + rng.uniform(-0.02, 0.02)

    return dict(
        strand_r    = base_r * r_scale,
        twist_scale = twist_scale,
        rad_waves   = _rand_waves(rng, 2, 1.6),    # diameter variation ±5%
        twist_waves = _rand_waves(rng, 3, 0.9),    # spacing variation ±7%
        sub_twist   = rng.uniform(3.0, 6.0) * math.pi,
        age_loose   = rng.uniform(0.0, age * 0.12),
    )


# ---------------------------------------------------------------------------
# RopeGenerator
# ---------------------------------------------------------------------------

class RopeGenerator:
    """
    Builds rope mesh along an arbitrary path.

    Do not instantiate directly — use create_rope().
    """

    def __init__(self, pts, rope_type, radius, twist_density,
                 age, wetness, fray, end_style, lod, seed):

        preset = _ROPE_TYPES.get(rope_type, _ROPE_TYPES["utility"])
        base_r, strand_count, base_twist_pm, _ = preset

        self.rope_r       = (radius if radius is not None else base_r)
        self.strand_count = strand_count
        self.twist_pm     = base_twist_pm * twist_density
        self.age          = age
        self.wetness      = wetness
        self.fray         = fray
        self.end_style    = end_style
        self.lod          = lod
        self.seed         = seed

        # Strand proportions — fat strands that bulge at the silhouette
        self.strand_r = self.rope_r * 0.55
        self.orbit_r  = self.rope_r * 0.44

        self.pts    = self._sample_path(pts, lod)
        self.length = _path_length(self.pts)
        self.frames = _parallel_transport(self.pts)

    # ------------------------------------------------------------------
    # Path sampling
    # ------------------------------------------------------------------

    def _sample_path(self, raw_pts, lod):
        """Accept RopePath, Curve object, or list[Vector]. Resample to target density."""
        if isinstance(raw_pts, RopePath):
            raw_pts = raw_pts.to_points()
        elif isinstance(raw_pts, bpy.types.Object) and raw_pts.type == 'CURVE':
            raw_pts = RopePath.from_curve(raw_pts).to_points()
        else:
            raw_pts = [Vector(p) for p in raw_pts]

        if len(raw_pts) < 2:
            raise ValueError("Rope path must have at least 2 points.")

        length  = _path_length(raw_pts)
        spm     = _SAMPLES_PER_M[lod]
        target  = max(8, int(length * spm))
        return RopePath(raw_pts).resample(target).to_points()

    # ------------------------------------------------------------------
    # Strand centre path in world space
    # ------------------------------------------------------------------

    def _strand_centre_path(self, strand_idx, sp):
        """
        Orbit the strand around the rope spine using the parallel-transport
        frame so the orbit stays perpendicular to the path at every point.
        """
        n        = len(self.pts)
        phase    = 2.0 * math.pi * strand_idx / self.strand_count
        t_scale  = sp["twist_scale"]
        t_waves  = sp["twist_waves"]
        age_l    = sp["age_loose"]

        # Accumulate arc length for twist angle
        arc = 0.0
        path = []
        for i in range(n):
            if i > 0:
                arc += (self.pts[i] - self.pts[i - 1]).length
            t = arc / max(self.length, 1e-9)

            _, normal, binormal = self.frames[i]

            # Twist spacing variation ±7%
            spacing_var = 1.0 + 0.07 * _sin_sum(t, t_waves)
            angle = phase + arc * self.twist_pm * 2.0 * math.pi \
                          * t_scale * spacing_var

            # Orbit radius: slight compression/expansion + age looseness
            r = self.orbit_r * (1.0 + 0.05 * math.sin(angle * 2.0 + phase)
                                + age_l)

            centre = self.pts[i] \
                   + normal   * math.cos(angle) * r \
                   + binormal * math.sin(angle) * r
            path.append(centre)
        return path

    # ------------------------------------------------------------------
    # Strand tube
    # ------------------------------------------------------------------

    def _build_strand(self, bm, strand_idx, sp, sides,
                      cap_start=True, cap_end=True):
        path      = self._strand_centre_path(strand_idx, sp)
        n         = len(path)
        strand_r  = sp["strand_r"]
        rad_waves = sp["rad_waves"]
        sub_twist = sp["sub_twist"]

        tube_rings = []
        for i in range(n):
            t  = i / max(n - 1, 1)
            cp = path[i]
            _, normal, binormal = self.frames[i]

            r     = strand_r * (1.0 + 0.05 * _sin_sum(t, rad_waves))
            twist = t * sub_twist

            ring = []
            for si in range(sides):
                a  = 2.0 * math.pi * si / sides + twist
                co = cp + (normal * math.cos(a) + binormal * math.sin(a)) * r
                ring.append(co)
            tube_rings.append(ring)

        verts = [[bm.verts.new(v) for v in ring] for ring in tube_rings]
        for i in range(n - 1):
            for si in range(sides):
                sn = (si + 1) % sides
                bm.faces.new([verts[i][si],   verts[i][sn],
                              verts[i+1][sn], verts[i+1][si]])

        if cap_start:
            _cap(bm, verts[0],  inward=True)
        if cap_end:
            _cap(bm, verts[-1], inward=False)

        return verts[0], verts[-1], path

    # ------------------------------------------------------------------
    # End treatments
    # ------------------------------------------------------------------

    def _apply_end(self, bm, end_ring, tip_pos, sp, strand_idx, is_start):
        style = self.end_style
        do_fray = self.fray > 0.0 or style == "frayed"

        if do_fray:
            _end_frayed(bm, tip_pos, sp["strand_r"],
                        self.seed + strand_idx * 7, self.age, self.fray)
        elif style == "wrapped":
            _end_wrapped(bm, tip_pos, sp["strand_r"],
                         self.seed + strand_idx * 13)
            _cap(bm, end_ring, inward=is_start)
        elif style == "burned":
            _end_burned(bm, end_ring, self.seed + strand_idx * 19)
            _cap(bm, end_ring, inward=is_start)
        elif style == "compressed":
            _end_compressed(bm, end_ring, axis_x=(strand_idx % 2 == 0))
            _cap(bm, end_ring, inward=is_start)
        elif style == "hidden":
            pass   # no cap — caller will merge into another mesh
        # "cut" — cap already added in _build_strand

    # ------------------------------------------------------------------
    # Build full mesh
    # ------------------------------------------------------------------

    def build(self):
        sides = _SIDES_LOD[self.lod]
        bm    = bmesh.new()

        do_fray = self.fray > 0.0 or self.end_style == "frayed"

        for si in range(self.strand_count):
            sp = _strand_params(si, self.strand_r, self.twist_pm,
                                self.seed + si * 1031, self.age)
            first, last, path = self._build_strand(
                bm, si, sp, sides,
                cap_start=True,
                cap_end=not do_fray,
            )
            self._apply_end(bm, last, path[-1], sp, si, is_start=False)

        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00005)
        bm.normal_update()

        mesh = bpy.data.meshes.new("SM_Rope_01")
        bm.to_mesh(mesh)
        bm.free()
        mesh.validate()
        mesh.update()
        return mesh


# ---------------------------------------------------------------------------
# Shared end-treatment functions (used by RopeGenerator._apply_end)
# ---------------------------------------------------------------------------

def _cap(bm, ring_verts, inward):
    sides = len(ring_verts)
    co    = sum((v.co for v in ring_verts), Vector()) / sides
    ctr   = bm.verts.new(co)
    for si in range(sides):
        sn = (si + 1) % sides
        if inward:
            bm.faces.new([ctr, ring_verts[sn], ring_verts[si]])
        else:
            bm.faces.new([ctr, ring_verts[si], ring_verts[sn]])


def _end_frayed(bm, tip_pos, strand_r, seed, age, fray_amount=1.0):
    rng     = _rng(seed)
    n       = rng.randint(4, 6)
    fiber_r = strand_r * 0.16
    sides   = 4
    for _ in range(n):
        angle  = rng.uniform(0, 2 * math.pi)
        spread = strand_r * rng.uniform(0.4, 1.0)
        flen   = strand_r * rng.uniform(3.0, 5.5) * (1.0 + age * 0.5) * fray_amount
        droop  = rng.uniform(0.15, 0.45)
        curl   = rng.uniform(-0.6, 0.6)
        steps  = 7
        rings  = []
        for si in range(steps + 1):
            ft = si / steps
            fx = tip_pos.x + math.cos(angle) * spread * (1.0 + ft * 0.5)
            fy = tip_pos.y + math.sin(angle) * spread * (1.0 + ft * 0.5) \
                           - droop * ft * ft * flen
            fz = tip_pos.z + ft * flen
            ta = ft * curl * math.pi * 2.0
            r  = fiber_r * (1.0 - ft * 0.65)
            row = []
            for vi in range(sides):
                a = 2.0 * math.pi * vi / sides + ta
                row.append(Vector((fx + math.cos(a) * r,
                                   fy + math.sin(a) * r, fz)))
            rings.append(row)
        fv = [[bm.verts.new(v) for v in ring] for ring in rings]
        for ri in range(steps):
            for si in range(sides):
                sn = (si + 1) % sides
                bm.faces.new([fv[ri][si], fv[ri][sn],
                              fv[ri+1][sn], fv[ri+1][si]])
        _cap(bm, fv[-1], inward=False)


def _end_wrapped(bm, tip_pos, strand_r, seed):
    rng    = _rng(seed)
    turns  = rng.randint(2, 3)
    wr     = strand_r * 1.02
    tube_r = strand_r * 0.08
    sides  = 5
    steps  = turns * 16
    rings  = []
    for si in range(steps + 1):
        t  = si / steps
        a  = t * turns * 2.0 * math.pi
        z  = tip_pos.z - strand_r * 2.5 * (1.0 - t)
        cx = tip_pos.x + math.cos(a) * wr
        cy = tip_pos.y + math.sin(a) * wr
        row = []
        for vi in range(sides):
            va = 2.0 * math.pi * vi / sides + a
            row.append(Vector((cx + math.cos(va) * tube_r,
                               cy + math.sin(va) * tube_r, z)))
        rings.append(row)
    fv = [[bm.verts.new(v) for v in ring] for ring in rings]
    for ri in range(steps):
        for si in range(sides):
            sn = (si + 1) % sides
            bm.faces.new([fv[ri][si], fv[ri][sn],
                          fv[ri+1][sn], fv[ri+1][si]])


def _end_burned(bm, ring_verts, seed):
    rng = _rng(seed)
    co  = sum((v.co for v in ring_verts), Vector()) / len(ring_verts)
    for v in ring_verts:
        dx, dy = v.co.x - co.x, v.co.y - co.y
        shrink = rng.uniform(0.05, 0.18)
        v.co.x -= dx * shrink
        v.co.y -= dy * shrink
        v.co.z += rng.uniform(-0.003, 0.003)


def _end_compressed(bm, ring_verts, axis_x=True):
    co = sum((v.co for v in ring_verts), Vector()) / len(ring_verts)
    for v in ring_verts:
        if axis_x:
            v.co.x = co.x + (v.co.x - co.x) * 0.45
        else:
            v.co.y = co.y + (v.co.y - co.y) * 0.45


# ---------------------------------------------------------------------------
# Label helper  (shared by all generate_examples functions)
# ---------------------------------------------------------------------------

def _make_label(text, x, y, z, size=0.030, collection=None):
    """
    Create a Blender Text object at (x, y, z) and link it into collection.
    Text faces +Y so it reads correctly when viewed from above (top-down).
    """
    font_data = bpy.data.curves.new(name=text, type='FONT')
    font_data.body      = text
    font_data.size      = size
    font_data.align_x   = 'CENTER'
    obj = bpy.data.objects.new(name=text, object_data=font_data)
    obj.location        = (x, y, z)
    obj.rotation_euler  = (math.radians(90), 0, 0)   # face +Y → readable top-down
    col = collection or bpy.context.scene.collection
    col.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------

# Grid layout constants shared by all generate_examples functions
_SX        = 0.32   # column spacing
_SY        = 0.55   # row spacing
_PER_ROW   = 6      # items per row
_LABEL_DY  = -0.12  # label offset below item origin
_LABEL_Z   = 0.0
_HDR_SIZE  = 0.036
_LBL_SIZE  = 0.028
_HDR_X     = -0.28  # header sits left of column 0


def _grid_place(col, obj, row, col_idx, base_y):
    x = col_idx * _SX
    y = base_y - row * _SY
    obj.location = (x, y, 0)
    col.objects.link(obj)
    return x, y


def _grid_label(text, col, row, col_idx, base_y):
    x = col_idx * _SX
    y = base_y - row * _SY
    _make_label(text, x, y + _LABEL_DY, _LABEL_Z, size=_LBL_SIZE, collection=col)


def _grid_header(text, col, row, base_y):
    y = base_y - row * _SY
    _make_label(text, _HDR_X, y, _LABEL_Z, size=_HDR_SIZE, collection=col)


def generate_examples(collection=None):
    """
    Generate one object per showcase case and link them into `collection`.

    Layout: groups of rows along -Y, items along X, max _PER_ROW per row.
      Group 0 — rope types
      Group 1 — end styles
      Group 2 — path shapes
      Group 3 — age progression
      Group 4 — wetness progression
      Group 5 — twist density
    """
    import bpy
    from mathutils import Vector
    from rope_path import RopePath

    col    = collection or bpy.context.scene.collection
    base_y = 0.0
    row    = 0

    def emit(items, header, make_fn, label_fn):
        """Lay out items in rows of _PER_ROW, advancing `row` as needed."""
        nonlocal row
        _grid_header(header, col, row, base_y)
        for i, item in enumerate(items):
            if i > 0 and i % _PER_ROW == 0:
                row += 1
                _grid_header("", col, row, base_y)  # blank header for continuation
            col_idx = i % _PER_ROW
            obj = make_fn(item, i)
            _grid_place(col, obj, row, col_idx, base_y)
            _grid_label(label_fn(item), col, row, col_idx, base_y)
        row += 1

    # --- rope types ---
    types = ["twine", "utility", "structural", "mooring", "palm_fiber", "decorative"]
    def _make_type(rtype, i):
        path = RopePath.line(Vector((0,0,0)), Vector((0,0,0.4)))
        return create_rope(path, rope_type=rtype, age=0.3, seed=i)
    emit(types, "ROPE TYPE", _make_type, lambda x: x)

    # --- end styles ---
    end_styles = ["cut", "frayed", "wrapped", "burned", "compressed"]
    def _make_end(style, i):
        path = RopePath.line(Vector((0,0,0)), Vector((0,0,0.35)))
        return create_rope(path, rope_type="utility", end_style=style,
                           fray=0.8 if style == "frayed" else 0.0,
                           age=0.4, seed=i + 10)
    emit(end_styles, "END STYLE", _make_end, lambda x: x)

    # --- path shapes ---
    path_shapes = [
        ("line",     RopePath.line(Vector((0,0,0)), Vector((0,0,0.4)))),
        ("arc",      RopePath.arc(Vector((0,0,0.2)), 0.15, 0, math.pi)),
        ("bezier",   RopePath.bezier(Vector((0,0,0)), Vector((0.1,0,0.15)),
                                     Vector((-0.1,0,0.25)), Vector((0,0,0.4)))),
        ("catenary", RopePath.catenary(Vector((0,0,0.35)), Vector((0,0,0.05)),
                                       sag=0.06)),
        ("spiral",   RopePath.spiral(Vector((0,0,0)), 0.06, 0.06, 0.3, 2)),
    ]
    def _make_shape(item, i):
        return create_rope(item[1], rope_type="utility", age=0.3, seed=i + 20)
    emit(path_shapes, "PATH SHAPE", _make_shape, lambda x: x[0])

    # --- age ---
    ages = [0.0, 0.25, 0.5, 0.75, 1.0]
    def _make_age(age, i):
        path = RopePath.line(Vector((0,0,0)), Vector((0,0,0.35)))
        return create_rope(path, rope_type="utility", age=age, seed=30)
    emit(ages, "AGE", _make_age, lambda x: f"{x:.2f}")

    # --- wetness ---
    wets = [0.0, 0.25, 0.5, 0.75, 1.0]
    def _make_wet(wet, i):
        path = RopePath.line(Vector((0,0,0)), Vector((0,0,0.35)))
        return create_rope(path, rope_type="utility", wetness=wet, age=0.3, seed=40)
    emit(wets, "WETNESS", _make_wet, lambda x: f"{x:.2f}")

    # --- twist density ---
    twists = [0.5, 1.0, 1.5, 2.0, 3.0]
    def _make_twist(td, i):
        path = RopePath.line(Vector((0,0,0)), Vector((0,0,0.4)))
        return create_rope(path, rope_type="utility", twist_density=td,
                           age=0.3, seed=50)
    emit(twists, "TWIST", _make_twist, lambda x: f"x{x:.1f}")


# ---------------------------------------------------------------------------
# Object assembly
# ---------------------------------------------------------------------------

def _make_object(mesh, age, wetness):
    obj = bpy.data.objects.new("SM_Rope_01", mesh)
    for poly in mesh.polygons:
        poly.use_smooth = True
    mod = obj.modifiers.new("EdgeSplit", "EDGE_SPLIT")
    mod.split_angle    = math.radians(55)
    mod.use_edge_angle = True
    mod.use_edge_sharp = False
    assign_rope_material(obj, age=age, wetness=wetness)
    return obj


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_rope(
    path,
    rope_type     = "utility",
    radius        = None,
    twist_density = 1.0,
    age           = 0.3,
    wetness       = 0.0,
    fray          = 0.0,
    end_style     = "cut",
    lod           = 0,
    seed          = 42,
):
    """
    Generate rope along an arbitrary path.

    path          – list[Vector] or Blender Curve object
    rope_type     – twine | utility | structural | mooring | palm_fiber | decorative
    radius        – override nominal radius (metres); None = use type default
    twist_density – multiplier on the type's default twist cycles per metre
    age           – 0.0 fresh … 1.0 old jungle rope
    wetness       – 0.0 dry  … 1.0 soaked
    fray          – 0.0 none … 1.0 heavily frayed ends
    end_style     – cut | frayed | wrapped | burned | compressed | hidden
    lod           – 0 high | 1 mid | 2 low
    seed          – integer; same seed = same rope

    Returns a bpy.types.Object (not linked to any collection).
    """
    gen  = RopeGenerator(path, rope_type, radius, twist_density,
                         age, wetness, fray, end_style, lod, seed)
    mesh = gen.build()
    return _make_object(mesh, age, wetness)


def create_rope_lods(path, rope_type="utility", radius=None,
                     twist_density=1.0, age=0.3, wetness=0.0,
                     fray=0.0, end_style="cut", seed=42):
    """Returns (lod0, lod1, lod2) for the same rope path."""
    return tuple(
        create_rope(path, rope_type, radius, twist_density,
                    age, wetness, fray, end_style, lod, seed)
        for lod in range(3)
    )
