"""
rope_lashings.py — Lashing paths for The Giant Raft.

Every lashing is written as an explicit program of primitive rope
operations.  Read each method top-to-bottom and you are reading the
procedure a rigger would follow.

All methods return a RopePath.  No geometry is generated here.

Lashing anatomy
---------------
Every real lashing has two distinct phases:

  1. Wrapping phase — loose enough to place, rope orbits members
  2. Frapping/tightening phase — cinches everything together

The frapping turns are perpendicular to the wraps and use a tighter
radius to visually compress the joint.
"""

import math
from mathutils import Vector
from rope.rope_path import RopeSequence


def _axis(a, b):
    """Unit vector along the line from a to b."""
    d = Vector(b) - Vector(a)
    return d.normalized() if d.length > 1e-6 else Vector((0, 0, 1))


def _perp(v):
    """A unit vector perpendicular to v."""
    v = Vector(v).normalized()
    ref = Vector((0, 0, 1)) if abs(v.dot(Vector((0, 0, 1)))) < 0.9 \
          else Vector((1, 0, 0))
    return v.cross(ref).normalized()


def _perp2(v):
    """A second perpendicular axis (orthogonal to both v and _perp(v))."""
    n = Vector(v).normalized()
    p = _perp(v)
    return n.cross(p).normalized()


class Lashings:

    @staticmethod
    def square(point_a, point_b, axis_a=(1,0,0), axis_b=(0,1,0),
               turns=4, beam_radius=0.04,
               rope_radius=0.006, tension=0.85, clearance=0.002):
        """
        Square lashing — bind two members crossing at ~90°.

        axis_a / axis_b — long axis of each member (unit vectors).
        The rope orbits each member in the plane perpendicular to its
        own long axis, then crosses to the other member.
        Frapping turns run perpendicular to both axes.
        """
        a, b = Vector(point_a), Vector(point_b)
        na = Vector(axis_a).normalized()   # orbit plane normal = member long axis
        nb = Vector(axis_b).normalized()
        nf = na.cross(nb).normalized()     # frap in the plane of the joint
        if nf.length < 1e-6:
            nf = _perp(na)

        s = RopeSequence(beam_radius, rope_radius, tension, clearance)
        s.begin(a)

        for i in range(turns):
            phase = i * 0.15
            s.wrap(a, turns=1, normal=na, phase=phase)
            s.cross_to(b)
            s.wrap(b, turns=1, normal=nb, phase=phase)
            s.cross_back(a)

        s.pass_between(a, b)
        s.frap(a, b, turns=3, normal=nf)
        s.exit(a)
        s.finish("clove_hitch", member=a, normal=na)
        return s.build("square_lashing")

    @staticmethod
    def diagonal(point_a, point_b, axis_a=(1,0,0), axis_b=(0,1,0),
                 turns=3, beam_radius=0.04,
                 rope_radius=0.006, tension=0.8, clearance=0.002):
        """
        Diagonal lashing — prevent racking at a crossing joint.

        Wraps run at 45° to both member axes, creating a visible X.
        axis_a / axis_b — long axis of each member.
        """
        a, b = Vector(point_a), Vector(point_b)
        na = Vector(axis_a).normalized()
        nb = Vector(axis_b).normalized()
        # Diagonal normals bisect the two member axes
        diag1 = (na + nb).normalized()
        diag2 = (na - nb).normalized()
        nf = na.cross(nb).normalized()
        if nf.length < 1e-6:
            nf = _perp(na)

        s = RopeSequence(beam_radius, rope_radius, tension, clearance)
        s.begin(a)

        for i in range(turns):
            s.wrap(a, turns=1, normal=diag1, phase=i * 0.2)
            s.cross_to(b)
            s.wrap(b, turns=1, normal=diag1, phase=i * 0.2)
            s.cross_back(a)

        for i in range(turns):
            s.wrap(a, turns=1, normal=diag2, phase=i * 0.2 + math.pi * 0.5)
            s.cross_to(b)
            s.wrap(b, turns=1, normal=diag2, phase=i * 0.2 + math.pi * 0.5)
            s.cross_back(a)

        s.pass_between(a, b)
        s.frap(a, b, turns=3, normal=nf)
        s.finish("clove_hitch", member=a, normal=diag1)
        return s.build("diagonal_lashing")

    @staticmethod
    def shear(point_a, point_b, pole_axis=(0,0,1),
              turns=8, beam_radius=0.04,
              rope_radius=0.006, tension=0.8, clearance=0.002):
        """
        Shear lashing — join two PARALLEL poles side-by-side.

        pole_axis — the shared long axis of both poles.
        The bundle wrap orbits in the plane perpendicular to pole_axis.
        Frapping runs along the gap axis (perpendicular to pole_axis,
        in the plane containing both pole centres).
        """
        a, b = Vector(point_a), Vector(point_b)
        pole_dir   = Vector(pole_axis).normalized()
        gap_axis   = _axis(a, b)          # direction from A to B
        # bundle wrap normal = pole long axis
        bundle_normal = pole_dir
        nf = gap_axis                     # frap cinches across the gap

        bundle_center = a.lerp(b, 0.5)
        bundle_radius = (a - b).length * 0.5 + beam_radius

        s = RopeSequence(beam_radius, rope_radius, tension, clearance)
        s.begin(a)

        saved_r = s._r
        s._r = bundle_radius + rope_radius + clearance
        for i in range(turns):
            s.wrap(bundle_center, turns=1, normal=bundle_normal, phase=i * 0.12)
        s._r = saved_r

        s.pass_between(a, b)
        s.frap(a, b, turns=3, normal=nf)
        s.exit(b)
        s.finish("clove_hitch", member=b, normal=bundle_normal)
        return s.build("shear_lashing")

    @staticmethod
    def tripod(p_a, p_b, p_c, pole_axis=(0,0,1),
               turns=6, beam_radius=0.03,
               rope_radius=0.006, tension=0.8, clearance=0.002):
        """
        Tripod lashing — bind three poles at their head.

        pole_axis — the shared long axis of all three poles before splaying.
        Each pole is wrapped with pole_axis as the orbit normal so the
        rope circles the pole cross-section, not the gap between poles.
        """
        a, b, c = Vector(p_a), Vector(p_b), Vector(p_c)
        n = Vector(pole_axis).normalized()
        nf_ab = _axis(a, b)   # frap normals cross the gaps
        nf_bc = _axis(b, c)

        s = RopeSequence(beam_radius, rope_radius, tension, clearance)
        s.begin(a)

        for i in range(turns):
            pitch = i * 0.1
            s.wrap(a, turns=1, normal=n, phase=pitch)
            s.cross_to(b)
            s.wrap(b, turns=1, normal=n, phase=pitch)
            s.cross_to(c)
            s.wrap(c, turns=1, normal=n, phase=pitch)
            s.cross_back(a)

        s.pass_between(a, b)
        s.frap(a, b, turns=2, normal=nf_ab)
        s.cross_to(b)
        s.pass_between(b, c)
        s.frap(b, c, turns=2, normal=nf_bc)

        s.finish("clove_hitch", member=a, normal=n)
        return s.build("tripod_lashing")

    @staticmethod
    def continuous(members, member_axis=(1,0,0),
                   turns=1, beam_radius=0.03,
                   rope_radius=0.006, tension=0.8, clearance=0.002):
        """
        Continuous lashing — bind a sequence of parallel members.

        member_axis — the shared long axis of all members.
        The rope orbits each member in the plane perpendicular to
        member_axis, then crosses to the next.
        """
        members = [Vector(m) for m in members]
        n = Vector(member_axis).normalized()
        s = RopeSequence(beam_radius, rope_radius, tension, clearance)
        s.begin(members[0])
        for i, member in enumerate(members):
            s.wrap(member, turns=turns, normal=n)
            if i < len(members) - 1:
                s.cross_to(members[i + 1])
        s.finish("clove_hitch", member=members[0], normal=n)
        return s.build("continuous_lashing")

    @staticmethod
    def japanese(point_a, point_b, axis_a=(1,0,0), axis_b=(0,1,0),
                 turns=3, beam_radius=0.03,
                 rope_radius=0.006, tension=0.85, clearance=0.002):
        """
        Japanese lashing (kannuki-shime) — very rigid, decorative joint.

        axis_a / axis_b — long axis of each member.
        Primary wraps orbit each member around its own long axis.
        Cross wraps lock perpendicular to the joint plane.
        """
        a, b = Vector(point_a), Vector(point_b)
        na = Vector(axis_a).normalized()
        nb = Vector(axis_b).normalized()
        n_cross = na.cross(nb).normalized()
        if n_cross.length < 1e-6:
            n_cross = _perp(na)
        nf = _perp(n_cross)

        s = RopeSequence(beam_radius, rope_radius, tension, clearance)
        s.begin(a)

        for i in range(turns):
            phase = i * (math.pi * 2.0 / turns) * 0.3
            s.wrap(a, turns=1, normal=na, phase=phase)
            s.cross_to(b)
            s.wrap(b, turns=1, normal=nb, phase=phase)
            s.cross_back(a)

        mid = a.lerp(b, 0.5)
        for i in range(2):
            s.wrap(mid, turns=1, normal=n_cross, phase=i * math.pi)

        s.frap(a, b, turns=2, normal=nf)
        s.lock()
        s.finish("clove_hitch", member=a, normal=na)
        return s.build("japanese_lashing")

    @staticmethod
    def floor(members, member_axis=(1,0,0),
              turns=1, beam_radius=0.03,
              rope_radius=0.006, tension=0.7, clearance=0.002):
        """
        Floor lashing — lash a row of deck planks or joists to a bearer.

        member_axis — the shared long axis of all members.
        """
        members = [Vector(m) for m in members]
        n = Vector(member_axis).normalized()
        s = RopeSequence(beam_radius, rope_radius, tension, clearance)
        s.begin(members[0])
        for i, member in enumerate(members):
            s.wrap(member, turns=turns, normal=n)
            if i < len(members) - 1:
                s.cross_to(members[i + 1])
        s.finish("clove_hitch", member=members[0], normal=n)
        return s.build("floor_lashing")
