"""
rope_joinery.py — Intent-based joinery facade for The Giant Raft.

Imports the four specialised modules and exposes them under one roof,
plus high-level intent constructors that choose the right technique
automatically so builders never need to know the difference between a
square lashing and a Japanese lashing.

Subclass access (when you do want a specific technique):
    Joinery.Lashings.square(a, b)
    Joinery.Knots.clove_hitch(post, radius)
    Joinery.Coils.flat(center, radius, turns)
    Joinery.Utilities.wrapped_handle(center, length, wrap_radius)

Intent API (preferred in builders):
    Joinery.bind_cross_members(beam_a, beam_b, strength="medium")
    Joinery.bind_parallel_members(pole_a, pole_b, strength="medium")
    Joinery.secure_to_post(post_center, post_radius, load="light")
    Joinery.terminate_end(tip_center, radius)

Every method returns a RopePath.  No geometry is generated here.
"""

from rope.rope_lashings  import Lashings
from rope.rope_knots     import Knots
from rope.rope_coils     import Coils
from rope.rope_utilities import Utilities


# ---------------------------------------------------------------------------
# Strength → technique tables
# ---------------------------------------------------------------------------

# bind_cross_members: perpendicular or angled crossing
_CROSS_STRENGTH = {
    "light":  ("square",   dict(turns=3)),
    "medium": ("square",   dict(turns=4)),
    "heavy":  ("japanese", dict(turns=5)),
}

# bind_parallel_members: two parallel spars side by side
_PARALLEL_STRENGTH = {
    "light":  ("shear",      dict(turns=3)),
    "medium": ("shear",      dict(turns=4)),
    "heavy":  ("continuous", dict(turns=6)),
}

# secure_to_post: rope end to a vertical or horizontal post
_POST_LOAD = {
    "light":  ("clove_hitch",  dict()),
    "medium": ("anchor_hitch", dict()),
    "heavy":  ("round_turn",   dict(turns=3)),
}


class Joinery:

    # Subclass namespaces — direct access when a specific technique is needed
    Lashings  = Lashings
    Knots     = Knots
    Coils     = Coils
    Utilities = Utilities

    # ------------------------------------------------------------------
    # Intent API
    # ------------------------------------------------------------------

    @staticmethod
    def bind_cross_members(point_a, point_b, axis_a=(1,0,0), axis_b=(0,1,0),
                           beam_radius=0.04,
                           strength="medium", tension=0.85, clearance=0.002):
        """
        Bind two crossing members at their intersection.

        axis_a / axis_b — long axis of each member.
        strength — "light"  → square lashing, 3 turns
                   "medium" → square lashing, 4 turns   (default)
                   "heavy"  → Japanese lashing, 5 turns
        """
        technique, kwargs = _CROSS_STRENGTH[strength]
        kwargs = dict(beam_radius=beam_radius, tension=tension,
                      clearance=clearance, axis_a=axis_a, axis_b=axis_b,
                      **kwargs)
        if technique == "square":
            return Lashings.square(point_a, point_b, **kwargs)
        return Lashings.japanese(point_a, point_b, **kwargs)

    @staticmethod
    def bind_parallel_members(point_a, point_b, pole_axis=(0,0,1),
                              beam_radius=0.04,
                              strength="medium", tension=0.8, clearance=0.002):
        """
        Bind two parallel members together along their length.

        pole_axis — the shared long axis of both members.
        strength — "light"  → shear lashing, 3 turns
                   "medium" → shear lashing, 4 turns    (default)
                   "heavy"  → continuous lashing, 6 turns
        """
        technique, kwargs = _PARALLEL_STRENGTH[strength]
        kwargs = dict(beam_radius=beam_radius, tension=tension,
                      clearance=clearance, **kwargs)
        if technique == "shear":
            return Lashings.shear(point_a, point_b, pole_axis=pole_axis, **kwargs)
        return Lashings.continuous([point_a, point_b],
                                   member_axis=pole_axis, **kwargs)

    @staticmethod
    def secure_to_post(post_center, post_radius, rope_radius=0.010,
                       load="medium", normal=None, tension=0.85):
        """
        Secure a rope end to a post, leg, or spar.

        load — "light"  → clove hitch
               "medium" → anchor hitch                  (default)
               "heavy"  → round turn (3 turns)

        Returns a RopePath.
        """
        technique, kwargs = _POST_LOAD[load]
        kwargs = dict(post_radius=post_radius, rope_radius=rope_radius,
                      normal=normal, tension=tension, **kwargs)
        if technique == "clove_hitch":
            return Knots.clove_hitch(post_center, **kwargs)
        if technique == "anchor_hitch":
            return Knots.anchor_hitch(post_center, **kwargs)
        return Knots.round_turn(post_center, **kwargs)

    @staticmethod
    def terminate_end(tip_center, radius, style="figure_eight"):
        """
        Add a stopper knot at a rope end.

        style — "figure_eight"  (default)
                "fender_knot"

        Returns a RopePath.
        """
        if style == "fender_knot":
            return Utilities.fender_knot(tip_center, radius)
        return Knots.figure_eight(tip_center, radius)


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------

def generate_examples(collection=None):
    """
    Generate one rope per joinery type, grouped by category.
    Lashing examples include actual timber beams in realistic joint configs.
    Placed below rope_path.py rows, sharing the same grid constants.
    """
    import bpy
    import math
    from mathutils import Vector
    from rope.rope import create_rope, _make_label, _grid_place, _grid_label, \
                     _grid_header, _SX, _SY, _PER_ROW
    from primitives.timber_beam import create_timber
    from materials.timber_material import assign_timber_material

    col    = collection or bpy.context.scene.collection
    base_y = -8 * _SY
    row    = 0

    BR = 0.03   # beam half-width / lashing radius
    BL = 0.22   # beam length for display

    def _calm_timber(length, width, height, seed):
        """
        create_timber with distortion dialled back for display use:
        near-zero bow, minimal twist, gentle taper, low surface noise.
        The beam stays close to its nominal axis so lashing points land
        on the actual surface rather than floating beside it.
        """
        import random
        from primitives.timber_beam import _params, make_log, apply_taper, apply_bow, \
            apply_twist, flatten_sides, hew_faces, distort_cross_section, \
            apply_surface_waviness, wear_edges, shape_ends, apply_knots, \
            _build_mesh
        import bmesh

        p = _params(seed, length, width, height)
        p['bow_x']        = p['bow_x']        * 0.05
        p['bow_y']        = p['bow_y']        * 0.05
        p['twist_deg']    = p['twist_deg']    * 0.1
        p['taper_end']    = max(p['taper_end'], 0.96)
        p['log_noise_amp']= p['log_noise_amp']* 0.15
        p['cs_drift']     = [d * 0.1 for d in p['cs_drift']]
        p['wave_amp']     = [a * 0.2 for a in p['wave_amp']]
        p['hew_facet_depth'] = p['hew_facet_depth'] * 0.3

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

    # All timber helpers build at the local origin (0,0,0).
    # _grid_place moves both the rope and the timbers together.
    pending_timbers = []   # [(obj, location, rotation_deg)]

    def _stage_timber(obj, location, rotation=(0, 0, 0)):
        pending_timbers.append((obj, location, rotation))

    def _place_timbers_at(grid_x, grid_y):
        """Link all staged timbers, offset to the current grid cell."""
        for obj, loc, rot in pending_timbers:
            obj.location = (loc[0] + grid_x, loc[1] + grid_y, loc[2])
            obj.rotation_euler = tuple(math.radians(d) for d in rot)
            assign_timber_material(obj)
            col.objects.link(obj)
        pending_timbers.clear()

    # ------------------------------------------------------------------
    # Timber joint configurations — all built at local origin
    # ------------------------------------------------------------------

    def _cross_timbers(seed_offset=0):
        """
        Two beams crossing at 90° at the origin.
        Beam A runs along X (rotated -90° around Y).
        Beam B runs along Y (rotated +90° around X), raised by BR so
        it sits on top of A.
        Lashing points are the two beam centres at the crossing.
        """
        beam_a = _calm_timber(BL, BR * 2, BR * 2, seed=10 + seed_offset)
        beam_b = _calm_timber(BL, BR * 2, BR * 2, seed=11 + seed_offset)
        _stage_timber(beam_a, (-BL * 0.5, 0, 0),      rotation=(0, -90, 0))
        _stage_timber(beam_b, (0, -BL * 0.5, BR * 2), rotation=(90, 0, 0))
        # A centre at origin; B centre raised by one beam-width
        return Vector((0, 0, 0)), Vector((0, 0, BR * 2))

    def _parallel_timbers(seed_offset=0):
        """
        Two beams running parallel along Z, spaced 2*BR apart along X.
        Both centred at z = BL/2 (timber origin is at one end).
        Lashing points are the mid-length centres of each beam.
        """
        beam_a = _calm_timber(BL, BR * 2, BR * 2, seed=20 + seed_offset)
        beam_b = _calm_timber(BL, BR * 2, BR * 2, seed=21 + seed_offset)
        _stage_timber(beam_a, (-BR * 1.5, 0, -BL * 0.5))
        _stage_timber(beam_b, ( BR * 1.5, 0, -BL * 0.5))
        return Vector((-BR * 1.5, 0, 0)), Vector((BR * 1.5, 0, 0))

    def _tripod_timbers(seed_offset=0):
        """
        Three short poles radiating from the origin at 120° intervals.
        Each pole runs along Z from the origin outward; they are rotated
        so their tips splay apart like a real tripod head.
        Lashing points are the near ends of each pole.
        """
        r = BR * 2.5   # radial offset of each pole centre
        configs = [
            (( r,  0,       0), (0, 20, 0),   30 + seed_offset),
            ((-r * 0.5,  r * 0.87, 0), (0, 20, 120), 31 + seed_offset),
            ((-r * 0.5, -r * 0.87, 0), (0, 20, 240), 32 + seed_offset),
        ]
        pts = []
        for loc, rot, seed in configs:
            b = _calm_timber(BL * 0.7, BR * 1.6, BR * 1.6, seed=seed)
            _stage_timber(b, loc, rotation=rot)
            pts.append(Vector(loc))
        return tuple(pts)

    def _plank_row(count=4, seed_offset=0):
        """
        Row of parallel planks running along Z, evenly spaced along X.
        Lashing points are the mid-length centres of each plank.
        """
        spacing = BR * 2.2
        total_w = spacing * (count - 1)
        centres = []
        for k in range(count):
            x = -total_w * 0.5 + k * spacing
            b = _calm_timber(BL * 0.6, BR * 1.8, BR * 0.8,
                             seed=40 + k + seed_offset)
            _stage_timber(b, (x, 0, -BL * 0.3))
            centres.append(Vector((x, 0, 0)))
        return centres

    # ------------------------------------------------------------------
    # Build lashing cases — timbers and rope both at local origin
    # ------------------------------------------------------------------

    def _lashing_case(label, lashing_fn, timber_fn, *timber_args):
        """
        Build timber geometry, compute joint points, build lashing path,
        return (label, rope_path, pending_timber_list).
        """
        joint_pts = timber_fn(*timber_args)
        path = lashing_fn(*joint_pts) if not isinstance(joint_pts[0], list) \
               else lashing_fn(joint_pts)
        return label, path, list(pending_timbers)

    lashing_cases = []

    ca, cb = _cross_timbers(seed_offset=0)
    lashing_cases.append(("square",   Lashings.square(ca, cb, axis_a=(1,0,0), axis_b=(0,1,0), turns=3, beam_radius=BR),
                          list(pending_timbers)))
    pending_timbers.clear()

    ca, cb = _cross_timbers(seed_offset=2)
    lashing_cases.append(("diagonal", Lashings.diagonal(ca, cb, axis_a=(1,0,0), axis_b=(0,1,0), turns=3, beam_radius=BR),
                          list(pending_timbers)))
    pending_timbers.clear()

    pa, pb = _parallel_timbers(seed_offset=0)
    lashing_cases.append(("shear",    Lashings.shear(pa, pb, pole_axis=(0,0,1), turns=3, beam_radius=BR),
                          list(pending_timbers)))
    pending_timbers.clear()

    ta, tb, tc = _tripod_timbers(seed_offset=0)
    lashing_cases.append(("tripod",   Lashings.tripod(ta, tb, tc, pole_axis=(0,0,1), turns=2, beam_radius=BR),
                          list(pending_timbers)))
    pending_timbers.clear()

    members = _plank_row(count=4, seed_offset=0)
    lashing_cases.append(("continuous", Lashings.continuous(members, member_axis=(0,0,1), turns=1, beam_radius=BR),
                          list(pending_timbers)))
    pending_timbers.clear()

    ca, cb = _cross_timbers(seed_offset=4)
    lashing_cases.append(("japanese", Lashings.japanese(ca, cb, axis_a=(1,0,0), axis_b=(0,1,0), turns=2, beam_radius=BR),
                          list(pending_timbers)))
    pending_timbers.clear()

    post = Vector((0, 0, 0))

    groups = [
        ("LASHINGS", lashing_cases),
        ("KNOTS", [
            ("clove hitch",  Knots.clove_hitch(post, post_radius=0.03),  None),
            ("half hitch",   Knots.half_hitch(post, post_radius=0.03, hitches=3), None),
            ("timber hitch", Knots.timber_hitch(post, post_radius=0.03), None),
            ("anchor hitch", Knots.anchor_hitch(post, post_radius=0.03), None),
            ("cleat hitch",  Knots.cleat_hitch(post, cleat_width=0.06),  None),
            ("bowline",      Knots.bowline(post, loop_radius=0.05),       None),
            ("figure eight", Knots.figure_eight(Vector((0, 0, 0.1)), radius=0.06), None),
            ("round turn",   Knots.round_turn(post, post_radius=0.03, turns=2),    None),
        ]),
        ("COILS", [
            ("flat coil",    Coils.flat(Vector((0, 0, 0)), 0.08, 4),      None),
            ("helical coil", Coils.helical(Vector((0, 0, 0)), 0.06, 4, 0.02), None),
            ("hanging",      Coils.hanging(Vector((0, 0, 0.35)),
                                           Vector((0, 0, 0.05)), sag=0.08), None),
            ("loop",         Coils.loop(Vector((0, 0, 0.1)), 0.06),       None),
            ("hook loop",    Coils.hook_loop(Vector((0, 0, 0.15)), 0.05), None),
        ]),
        ("UTILITIES", [
            ("straight",     Utilities.straight(Vector((0, 0, 0)),
                                                Vector((0, 0, 0.4))),     None),
            ("wrapped hdl",  Utilities.wrapped_handle(Vector((0, 0, 0.15)),
                                                      length=0.3,
                                                      wrap_radius=0.02, turns=6), None),
            ("deco wrap",    Utilities.decorative_wrap(Vector((0, 0, 0.1)),
                                                       radius=0.03, turns=4), None),
            ("fender knot",  Utilities.fender_knot(Vector((0, 0, 0.1)),
                                                   radius=0.05),          None),
            ("spiral",       Utilities.spiral(Vector((0, 0, 0)), 0.06, 0.06,
                                              0.35, 2.5),                 None),
        ]),
    ]

    for header, cases in groups:
        _grid_header(header, col, row, base_y)
        for i, (label, path, timbers) in enumerate(cases):
            if i > 0 and i % _PER_ROW == 0:
                row += 1
                _grid_header("", col, row, base_y)
            col_idx = i % _PER_ROW
            obj = create_rope(path, rope_type="lashing", age=0.4, seed=i + 200)
            gx, gy = _grid_place(col, obj, row, col_idx, base_y)
            if timbers:
                for t_obj, loc, rot in timbers:
                    t_obj.location = (loc[0] + gx, loc[1] + gy, loc[2])
                    t_obj.rotation_euler = tuple(math.radians(d) for d in rot)
                    assign_timber_material(t_obj)
                    col.objects.link(t_obj)
            _grid_label(label, col, row, col_idx, base_y)
            print(f"  joinery example: {label}")
        row += 1
