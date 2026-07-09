"""
rope_path.py — RopePath: the universal spline abstraction for The Giant Raft.

A RopePath wraps a list of Vector points and exposes a fluent API for
construction, transformation, and composition.  It carries metadata so
builders can make placement and collision decisions without inspecting geometry.

Every joinery function and every builder works with RopePath.
RopeGenerator accepts RopePath directly.

Usage
-----
from rope.rope_path import RopePath

path = (
    RopePath.line(Vector((0,0,0)), Vector((0,0,2)))
        .smooth(iterations=2)
        .offset(Vector((0.01, 0, 0)))
)

rope = create_rope(path, rope_type="utility")

Composition
-----------
full = RopePath.catenary(start, end, sag=0.05).append(
           RopePath.circle(center, radius=0.1)
       )
"""

import math
import bpy
from mathutils import Vector, Matrix


# ---------------------------------------------------------------------------
# RopePath
# ---------------------------------------------------------------------------

class RopePath:
    """
    Fluent spline abstraction.  All transform/operation methods return a new
    RopePath so calls can be chained.

    Metadata attributes
    -------------------
    closed      – True if first and last points are the same
    tension     – 0.0 loose/saggy … 1.0 taut/straight
    path_type   – string tag set by factory methods ("line", "arc", etc.)
    radius      – characteristic radius (set by circle/arc/spiral factories)
    turns       – number of full rotations (set by spiral/coil factories)
    """

    def __init__(self, points, *, closed=False, tension=0.5,
                 path_type="custom", radius=0.0, turns=0):
        self._pts     = [Vector(p) for p in points]
        self.closed   = closed
        self.tension  = tension
        self.path_type = path_type
        self.radius   = radius
        self.turns    = turns

    # ------------------------------------------------------------------
    # Metadata properties
    # ------------------------------------------------------------------

    @property
    def length(self):
        pts = self._pts
        return sum((pts[i+1] - pts[i]).length for i in range(len(pts) - 1))

    @property
    def bounding_box(self):
        """Returns (min_corner, max_corner) as Vectors."""
        xs = [p.x for p in self._pts]
        ys = [p.y for p in self._pts]
        zs = [p.z for p in self._pts]
        return Vector((min(xs), min(ys), min(zs))), \
               Vector((max(xs), max(ys), max(zs)))

    def __len__(self):
        return len(self._pts)

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def to_points(self):
        """Return a plain list[Vector] copy."""
        return [Vector(p) for p in self._pts]

    def to_curve(self, name="RopePath", collection=None):
        """
        Create a Blender POLY Curve object from this path and link it into
        collection (or the active scene collection).
        Returns the bpy.types.Object.
        """
        curve_data = bpy.data.curves.new(name, type='CURVE')
        curve_data.dimensions = '3D'
        spline = curve_data.splines.new('POLY')
        spline.points.add(len(self._pts) - 1)
        for i, p in enumerate(self._pts):
            spline.points[i].co = (p.x, p.y, p.z, 1.0)
        spline.use_cyclic_u = self.closed
        obj = bpy.data.objects.new(name, curve_data)
        col = collection or bpy.context.scene.collection
        col.objects.link(obj)
        return obj

    # ------------------------------------------------------------------
    # Fluent transforms — each returns a new RopePath
    # ------------------------------------------------------------------

    def translate(self, x=0, y=0, z=0):
        off = Vector((x, y, z))
        return self._copy([p + off for p in self._pts])

    def offset(self, vector):
        off = Vector(vector)
        return self._copy([p + off for p in self._pts])

    def scale(self, x=1, y=1, z=1):
        s = Vector((x, y, z))
        return self._copy([Vector((p.x*s.x, p.y*s.y, p.z*s.z))
                           for p in self._pts])

    def rotate(self, x=0, y=0, z=0):
        """Rotate by Euler angles in degrees around origin."""
        mat = (Matrix.Rotation(math.radians(x), 4, 'X') @
               Matrix.Rotation(math.radians(y), 4, 'Y') @
               Matrix.Rotation(math.radians(z), 4, 'Z'))
        return self._copy([mat @ p for p in self._pts])

    def reverse(self):
        return self._copy(list(reversed(self._pts)))

    def subdivide(self, divisions=2):
        """Insert divisions-1 interpolated points between each pair."""
        out = []
        pts = self._pts
        for i in range(len(pts) - 1):
            for d in range(divisions):
                out.append(pts[i].lerp(pts[i+1], d / divisions))
        out.append(pts[-1])
        return self._copy(out)

    def smooth(self, iterations=2):
        """Laplacian smooth — pulls interior points toward neighbours."""
        result = [Vector(p) for p in self._pts]
        for _ in range(iterations):
            s = [Vector(result[0])]
            for i in range(1, len(result) - 1):
                s.append(result[i-1] * 0.25 + result[i] * 0.5 + result[i+1] * 0.25)
            s.append(Vector(result[-1]))
            result = s
        return self._copy(result)

    def resample(self, target_points):
        """Resample to exactly target_points evenly spaced along arc length."""
        pts = self._pts
        if len(pts) < 2:
            return self._copy(pts)
        lengths = [0.0]
        for i in range(1, len(pts)):
            lengths.append(lengths[-1] + (pts[i] - pts[i-1]).length)
        total = lengths[-1]
        if total < 1e-9:
            return self._copy([Vector(pts[0])] * target_points)
        out = []
        for k in range(target_points):
            tl = total * k / max(target_points - 1, 1)
            lo, hi = 0, len(lengths) - 2
            while lo < hi:
                mid = (lo + hi) // 2
                if lengths[mid+1] < tl:
                    lo = mid + 1
                else:
                    hi = mid
            seg = lengths[lo+1] - lengths[lo]
            t   = (tl - lengths[lo]) / seg if seg > 1e-9 else 0.0
            out.append(pts[lo].lerp(pts[lo+1], t))
        return self._copy(out)

    def sample(self, distance):
        """Resample so points are spaced approximately `distance` metres apart."""
        n = max(2, int(round(self.length / distance)) + 1)
        return self.resample(n)

    def append(self, other):
        """Concatenate another RopePath onto the end of this one."""
        return self._copy(self._pts + other.to_points())

    def set_tension(self, tension):
        c = self._copy(self._pts)
        c.tension = tension
        return c

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _copy(self, pts):
        return RopePath(pts, closed=self.closed, tension=self.tension,
                        path_type=self.path_type, radius=self.radius,
                        turns=self.turns)

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @staticmethod
    def line(start, end, points=2):
        start, end = Vector(start), Vector(end)
        pts = [start.lerp(end, i / max(points-1, 1)) for i in range(points)]
        return RopePath(pts, path_type="line")

    @staticmethod
    def arc(center, radius, start_angle, end_angle, normal=None, points=32):
        """Circular arc. Angles in radians."""
        center = Vector(center)
        normal = Vector(normal).normalized() if normal else Vector((0, 0, 1))
        ref    = Vector((1,0,0)) if abs(normal.dot(Vector((1,0,0)))) < 0.9 \
                 else Vector((0,1,0))
        x_ax   = normal.cross(ref).normalized()
        y_ax   = normal.cross(x_ax).normalized()
        pts = []
        for i in range(points):
            t = i / max(points-1, 1)
            a = start_angle + t * (end_angle - start_angle)
            pts.append(center + x_ax * math.cos(a) * radius
                               + y_ax * math.sin(a) * radius)
        return RopePath(pts, path_type="arc", radius=radius)

    @staticmethod
    def circle(center, radius, normal=None, points=64):
        path = RopePath.arc(center, radius, 0.0, 2.0*math.pi, normal, points+1)
        pts  = path.to_points()[:-1]
        return RopePath(pts, closed=True, path_type="circle", radius=radius)

    @staticmethod
    def spiral(center, radius_start, radius_end, height, turns, points=128):
        """Helix rising along Z. radius_start/end allow cone shapes."""
        center = Vector(center)
        pts = []
        for i in range(points):
            t = i / max(points-1, 1)
            a = t * turns * 2.0 * math.pi
            r = radius_start + (radius_end - radius_start) * t
            pts.append(center + Vector((math.cos(a)*r, math.sin(a)*r, t*height)))
        return RopePath(pts, path_type="spiral",
                        radius=(radius_start+radius_end)*0.5, turns=turns)

    @staticmethod
    def bezier(p0, p1, p2, p3, points=32):
        """Cubic Bézier through four control points."""
        p0, p1, p2, p3 = Vector(p0), Vector(p1), Vector(p2), Vector(p3)
        pts = []
        for i in range(points):
            t  = i / max(points-1, 1)
            u  = 1.0 - t
            pts.append(u**3*p0 + 3*u**2*t*p1 + 3*u*t**2*p2 + t**3*p3)
        return RopePath(pts, path_type="bezier")

    @staticmethod
    def catenary(start, end, sag, points=32):
        """Rope hanging under gravity. sag = downward displacement at midpoint."""
        start, end = Vector(start), Vector(end)
        pts = []
        for i in range(points):
            t  = i / max(points-1, 1)
            co = start.lerp(end, t)
            co.y -= sag * 4.0 * t * (1.0 - t)
            pts.append(co)
        return RopePath(pts, path_type="catenary")

    @staticmethod
    def from_curve(curve_obj, resolution=64):
        """Sample a Blender Curve object into a RopePath."""
        curve = curve_obj.data
        mat   = curve_obj.matrix_world
        pts   = []
        for spline in curve.splines:
            if spline.type == 'BEZIER':
                bpts = spline.bezier_points
                n    = len(bpts)
                segs = n - 1 if not spline.use_cyclic_u else n
                for seg in range(segs):
                    a  = bpts[seg]
                    b  = bpts[(seg+1) % n]
                    p0 = mat @ a.co
                    p1 = mat @ a.handle_right
                    p2 = mat @ b.handle_left
                    p3 = mat @ b.co
                    steps = max(4, resolution // max(segs, 1))
                    for i in range(steps if seg < segs-1 else steps+1):
                        t  = i / steps
                        u  = 1.0 - t
                        pts.append(u**3*p0 + 3*u**2*t*p1 + 3*u*t**2*p2 + t**3*p3)
            else:
                for p in spline.points:
                    pts.append(mat @ p.co.xyz)
        closed = any(s.use_cyclic_u for s in curve.splines)
        return RopePath(pts, closed=closed, path_type="curve")

    @staticmethod
    def from_points(points):
        """Wrap a plain list of Vector/tuple points into a RopePath."""
        return RopePath(points)


# ---------------------------------------------------------------------------
# RopeSequence — primitive-operation builder
# ---------------------------------------------------------------------------

class RopeSequence:
    """
    Builds a RopePath by composing named rope operations in the order a
    rigger would actually perform them.  Every method appends points and
    returns self so calls can be chained.

    Primitives
    ----------
    begin(anchor)                     — set start anchor, emit first point
    end(anchor)                       — emit final point at anchor
    wrap(center, turns, direction)    — orbit around a member
    wrap_many(centers, turns)         — orbit around multiple members in sequence
    cross_to(point)                   — straight run to a new member
    cross_back(point)                 — return run across the joint
    pass_over(member)                 — shallow arc over a member surface
    pass_under(member)                — shallow arc under a member surface
    pass_between(member_a, member_b)  — straight run through the gap
    loop(center, radius)              — full closed circle around a point
    circle(center, radius, normal)    — full orbit in a plane
    spiral(center, radius, rise, turns) — helix along the member axis
    arc(center, radius, angle)        — partial arc
    line_to(point)                    — straight segment
    offset(distance)                  — nudge last point outward
    reverse()                         — reverse accumulated points so far
    twist_self(turns)                 — rope twists around its own axis
    frap(member_a, member_b, turns)   — cinching turns between two members
    frap_all(*members, turns)         — frap between every adjacent pair
    lock()                            — half-turn tuck to lock the end
    tighten()                         — pull last segment inward
    exit(member)                      — run away from a member to clear it
    finish(knot)                      — terminal knot (clove_hitch / half_hitch)
    build(path_type)                  — return the completed RopePath
    """

    _ORBIT_PTS = 16   # points per full orbit
    _ARC_PTS   = 8    # points per pass_over / pass_under arc

    def __init__(self, beam_radius=0.04, rope_radius=0.006,
                 tension=0.85, clearance=0.002):
        self._pts        = []
        self.beam_radius = beam_radius
        self.rope_radius = rope_radius
        self.tension     = tension
        self._r          = beam_radius + clearance + rope_radius
        self._pitch      = rope_radius * 2.2   # axial spread per wrap

    # ------------------------------------------------------------------
    # Internal geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _axes(normal):
        """Return (x_ax, y_ax) perpendicular to normal."""
        n   = Vector(normal).normalized()
        ref = Vector((1, 0, 0)) if abs(n.dot(Vector((1, 0, 0)))) < 0.9 \
              else Vector((0, 1, 0))
        x   = n.cross(ref).normalized()
        y   = n.cross(x).normalized()
        return x, y

    def _orbit(self, center, radius, normal, turns, phase=0.0, direction="cw"):
        """Points for `turns` orbits around center in the plane of normal.
        Each call is self-contained — successive turns advance along the
        normal axis locally, starting from center with no global offset.
        """
        center = Vector(center)
        n_vec  = Vector(normal).normalized()
        x_ax, y_ax = self._axes(normal)
        sign   = -1.0 if direction == "ccw" else 1.0
        count  = max(1, int(abs(turns) * self._ORBIT_PTS))
        pts    = []
        for i in range(count + 1):
            t     = i / count
            angle = phase + sign * t * turns * 2.0 * math.pi
            dz    = (t * turns - turns * 0.5) * self._pitch
            pts.append(center
                       + x_ax * math.cos(angle) * radius
                       + y_ax * math.sin(angle) * radius
                       + n_vec * dz)
        return pts

    def _current(self):
        """Last accumulated point, or origin if empty."""
        return Vector(self._pts[-1]) if self._pts else Vector((0, 0, 0))

    # ------------------------------------------------------------------
    # Anchor / endpoint
    # ------------------------------------------------------------------

    def begin(self, anchor):
        """Set the rope start.  Must be called first."""
        self._pts.append(Vector(anchor))
        return self

    def end(self, anchor):
        """Emit a final point at anchor (before finish knot)."""
        self._pts.append(Vector(anchor))
        return self

    # ------------------------------------------------------------------
    # Wrapping
    # ------------------------------------------------------------------

    def wrap(self, center, turns=1, direction="cw", normal=(0, 0, 1), phase=0.0):
        """Orbit `turns` times around a member."""
        self._pts += self._orbit(center, self._r, normal, turns, phase, direction)
        return self

    def wrap_many(self, centers, turns=1, normal=(0, 0, 1)):
        """Orbit around each member in `centers` in sequence."""
        for c in centers:
            self.wrap(c, turns=turns, normal=normal)
        return self

    def wrap_parallel(self, center_a, center_b, turns=1, normal=(0, 0, 1)):
        """
        Wrap both members together as a pair — each turn visits A then B.
        Used in shear lashing where the two spars are treated as one bundle.
        """
        for _ in range(turns):
            self.wrap(center_a, turns=1, normal=normal)
            self.cross_to(center_b)
            self.wrap(center_b, turns=1, normal=normal)
            self.cross_back(center_a)
        return self

    def wrap_diagonal(self, center_a, center_b, turns=1, normal=(0, 0, 1)):
        """
        Diagonal wraps — orbit A, cross to midpoint, orbit B at 45° offset.
        Used in diagonal and Japanese lashings.
        """
        mid = Vector(center_a).lerp(Vector(center_b), 0.5)
        for _ in range(turns):
            self.wrap(center_a, turns=1, normal=normal, phase=math.pi * 0.25)
            self.cross_to(mid)
            self.wrap(center_b, turns=1, normal=normal, phase=math.pi * 0.25)
        return self

    def wrap_opposite_diagonal(self, center_a, center_b, turns=1, normal=(0, 0, 1)):
        """Same as wrap_diagonal but with the opposite 45° phase."""
        mid = Vector(center_a).lerp(Vector(center_b), 0.5)
        for _ in range(turns):
            self.wrap(center_b, turns=1, normal=normal, phase=-math.pi * 0.25)
            self.cross_to(mid)
            self.wrap(center_a, turns=1, normal=normal, phase=-math.pi * 0.25)
        return self

    # ------------------------------------------------------------------
    # Crossing moves
    # ------------------------------------------------------------------

    def cross_to(self, target):
        """Straight run from current position to target."""
        self._pts.append(Vector(target))
        return self

    def cross_back(self, target):
        """Return run across the joint — semantic alias for cross_to."""
        return self.cross_to(target)

    def cross_to_next(self, current, next_member):
        """Cross from current member to the next one in a sequence."""
        return self.cross_to(next_member)

    def pass_over(self, member, normal=(0, 0, 1)):
        """
        Shallow arc over the top of a member surface.
        Rope stays on the near side, rises over, comes back down.
        """
        center = Vector(member)
        x_ax, _ = self._axes(normal)
        for i in range(self._ARC_PTS + 1):
            t     = i / self._ARC_PTS
            angle = math.pi * t                          # 0 → π  (top half)
            self._pts.append(center
                             + x_ax * math.cos(angle) * self._r
                             + Vector(normal).normalized() * math.sin(angle) * self._r)
        return self

    def pass_under(self, member, normal=(0, 0, 1)):
        """
        Shallow arc under the bottom of a member surface.
        """
        center = Vector(member)
        x_ax, _ = self._axes(normal)
        for i in range(self._ARC_PTS + 1):
            t     = i / self._ARC_PTS
            angle = math.pi + math.pi * t                # π → 2π (bottom half)
            self._pts.append(center
                             + x_ax * math.cos(angle) * self._r
                             + Vector(normal).normalized() * math.sin(angle) * self._r)
        return self

    def pass_between(self, member_a, member_b):
        """Straight run through the gap between two members."""
        mid = Vector(member_a).lerp(Vector(member_b), 0.5)
        self._pts.append(mid)
        return self

    # ------------------------------------------------------------------
    # Curves and geometry
    # ------------------------------------------------------------------

    def loop(self, center, radius, normal=(0, 0, 1)):
        """Full closed circle — used for fixed loops and eye splices."""
        self._pts += self._orbit(center, radius, normal, turns=1)
        return self

    def circle(self, center, radius, normal=(0, 0, 1)):
        """Alias for loop — full orbit in a plane."""
        return self.loop(center, radius, normal)

    def spiral(self, center, radius, rise, turns, normal=(0, 0, 1)):
        """
        Helix along the member axis — used for wrapped handles and
        decorative seizings.
        """
        center = Vector(center)
        n_vec  = Vector(normal).normalized()
        x_ax, y_ax = self._axes(normal)
        count  = max(1, int(turns * self._ORBIT_PTS))
        for i in range(count + 1):
            t     = i / count
            angle = t * turns * 2.0 * math.pi
            z     = t * turns * rise
            self._pts.append(center
                             + x_ax * math.cos(angle) * radius
                             + y_ax * math.sin(angle) * radius
                             + n_vec * z)
        return self

    def arc(self, center, radius, angle, normal=(0, 0, 1), phase=0.0):
        """Partial arc spanning `angle` radians."""
        turns = angle / (2.0 * math.pi)
        self._pts += self._orbit(center, radius, normal, turns, phase)
        return self

    def line_to(self, point):
        """Straight segment to an explicit point."""
        self._pts.append(Vector(point))
        return self

    # ------------------------------------------------------------------
    # Modifiers
    # ------------------------------------------------------------------

    def offset(self, distance):
        """
        Nudge the last point outward along the direction from the
        second-to-last point — simulates rope standing off a surface.
        """
        if len(self._pts) >= 2:
            d = (self._pts[-1] - self._pts[-2])
            if d.length > 1e-9:
                self._pts[-1] += d.normalized() * distance
        return self

    def reverse(self):
        """Reverse the accumulated points so far."""
        self._pts.reverse()
        return self

    def twist_self(self, turns=1):
        """
        Rope twists around its own axis — represented as a tight local
        helix around the last point.  Used in timber hitch tails.
        """
        if not self._pts:
            return self
        center = self._current()
        r_self = self.rope_radius * 1.5
        self._pts += self._orbit(center, r_self, (0, 0, 1), turns)
        return self

    # ------------------------------------------------------------------
    # Frapping
    # ------------------------------------------------------------------

    def frap(self, member_a, member_b, turns=2, normal=(0, 0, 1)):
        """
        Frapping turns — tight cinching orbits in the gap between two
        members, perpendicular to the main wraps.  Locks the lashing.

        Frapping is visually TIGHTER than wrapping:
        - Smaller radius (bites into the wraps already laid)
        - More points per orbit (smoother, more compressed look)
        - Slight pitch so turns don't overlap
        """
        mid    = Vector(member_a).lerp(Vector(member_b), 0.5)
        # Frap radius is 50% of wrap radius — visibly tighter
        r_frap = self._r * 0.50
        # Use tighter pitch for frapping (turns sit close together)
        saved_pitch = self._pitch
        self._pitch = self.rope_radius * 2.5  # slightly wider than rope diameter
        self._pts += self._orbit(mid, r_frap, normal, turns)
        self._pitch = saved_pitch
        return self

    def frap_all(self, *members, turns=2, normal=(0, 0, 1)):
        """
        Frap between every adjacent pair in `members`.
        Used in tripod lashing to spread all three poles.
        """
        for i in range(len(members) - 1):
            self.frap(members[i], members[i + 1], turns=turns, normal=normal)
        return self

    # ------------------------------------------------------------------
    # Locking / finishing
    # ------------------------------------------------------------------

    def lock(self):
        """
        Half-turn tuck — rope passes back under the last wrap to lock it.
        Represented as a short reverse arc at the current position.
        """
        if len(self._pts) >= 2:
            prev = Vector(self._pts[-2])
            curr = self._current()
            mid  = curr.lerp(prev, 0.3)
            self._pts.append(mid)
            self._pts.append(curr)
        return self

    def tighten(self):
        """
        Pull the last segment inward by 15 % — simulates tension
        drawing the rope tight against the member.
        """
        if len(self._pts) >= 2:
            a, b = self._pts[-2], self._pts[-1]
            self._pts[-1] = a.lerp(b, 0.85)
        return self

    def exit(self, member, normal=(0, 0, 1)):
        """
        Run the rope away from a member to clear it before the finish knot.
        Emits a point one rope-radius beyond the member surface.
        """
        center = Vector(member)
        away   = (self._current() - center)
        if away.length > 1e-9:
            self._pts.append(center + away.normalized() * (self._r + self.rope_radius))
        return self

    def half_turn(self, member, normal=(0, 0, 1)):
        """Half orbit around a member — used inside knot sequences."""
        return self.wrap(member, turns=0.5, normal=normal)

    def small_loop(self, center, normal=(0, 0, 1)):
        """Small loop in the standing part — used in bowline."""
        return self.loop(center, self._r * 0.8, normal)

    def finish(self, knot="clove_hitch", member=None, normal=(0, 0, 1)):
        """
        Terminal knot to lock the rope end.

        knot — "clove_hitch"  two offset loops  (default)
               "half_hitch"   one loop + tuck
               "none"         no terminal knot
        """
        if knot == "none" or member is None:
            return self
        center = Vector(member)
        if knot == "half_hitch":
            self.wrap(center, turns=1, normal=normal).lock()
        else:                                              # clove_hitch
            self.wrap(center, turns=1, normal=normal)
            self.wrap(center, turns=1, normal=normal).lock()
        return self

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def build(self, path_type="lashing", closed=False):
        """Return the accumulated points as a RopePath."""
        return RopePath(self._pts, path_type=path_type,
                        closed=closed, tension=self.tension)


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------

def generate_examples(collection=None):
    """
    Generate one rope per path utility and link into collection.
    Placed below rope.py rows, sharing the same grid constants.
    """
    import bpy
    from mathutils import Vector
    from rope.rope import create_rope, _make_label, _grid_place, _grid_label, _grid_header, \
                     _SX, _SY, _PER_ROW

    col    = collection or bpy.context.scene.collection
    # Start below rope.py's rows (6 groups, each at least 1 row)
    base_y = -6 * _SY
    row    = 0

    _grid_header("PATH UTILS", col, row, base_y)

    cases = [
        ("line",       RopePath.line(Vector((0,0,0)), Vector((0,0,0.4)))),
        ("arc",        RopePath.arc(Vector((0,0,0.2)), 0.15, 0, math.pi)),
        ("circle",     RopePath.circle(Vector((0,0,0.1)), 0.10)),
        ("spiral",     RopePath.spiral(Vector((0,0,0)), 0.06, 0.06, 0.35, 2.5)),
        ("bezier",     RopePath.bezier(Vector((0,0,0)), Vector((0.12,0,0.15)),
                                       Vector((-0.12,0,0.25)), Vector((0,0,0.4)))),
        ("catenary",   RopePath.catenary(Vector((0,0,0.35)), Vector((0,0,0.05)),
                                         sag=0.07)),
        ("subdivided", RopePath.line(Vector((0,0,0)), Vector((0,0,0.4)),
                                     points=4).subdivide(4)),
        ("smoothed",   RopePath.bezier(Vector((0,0,0)), Vector((0.15,0,0.1)),
                                       Vector((-0.15,0,0.3)),
                                       Vector((0,0,0.4))).smooth(3)),
        ("reversed",   RopePath.catenary(Vector((0,0,0.35)), Vector((0,0,0.05)),
                                         sag=0.05).reverse()),
        ("composed",   RopePath.line(Vector((0,0,0)), Vector((0,0,0.2)))
                                .append(RopePath.arc(Vector((0,0,0.2)),
                                                     0.08, 0, math.pi))),
    ]

    for i, (label, path) in enumerate(cases):
        if i > 0 and i % _PER_ROW == 0:
            row += 1
            _grid_header("", col, row, base_y)
        col_idx = i % _PER_ROW
        obj = create_rope(path, rope_type="utility", age=0.3, seed=i + 100)
        _grid_place(col, obj, row, col_idx, base_y)
        _grid_label(label, col, row, col_idx, base_y)
        print(f"  path example: {label}")
