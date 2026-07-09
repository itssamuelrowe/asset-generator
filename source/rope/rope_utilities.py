"""
rope_utilities.py — Decorative and utility rope paths for The Giant Raft.

Every utility is written as an explicit program of primitive rope
operations.

All methods return a RopePath.  No geometry is generated here.
"""

import math
from mathutils import Vector
from rope.rope_path import RopeSequence


class Utilities:

    @staticmethod
    def straight(start, end, rope_radius=0.006, tension=0.9):
        """
        Straight rope run between two points.
        """
        s = RopeSequence(0.01, rope_radius, tension)

        s.begin(start)
        s.line_to(end)
        s.finish("none")

        return s.build("straight")

    @staticmethod
    def wrapped_handle(center, length, wrap_radius, turns=8,
                       rope_radius=0.006, tension=0.9):
        """
        Tight helical wrap along a grip — tool handles, oar looms, tillers.
        center — midpoint of the handle.
        length — total grip length.
        """
        c     = Vector(center)
        start = c - Vector((0, 0, length * 0.5))
        s = RopeSequence(wrap_radius, rope_radius, tension)

        s.begin(start)
        s.spiral(start, wrap_radius, rise=length / turns, turns=turns)
        s.finish("none")

        return s.build("wrapped_handle")

    @staticmethod
    def decorative_wrap(center, radius, turns=3,
                        rope_radius=0.006, tension=0.85):
        """
        Decorative helical wrap around a cylindrical object.
        Alias for a helical coil with a small rise — mast hoops, spar seizings.
        """
        from rope_coils import Coils
        return Coils.helical(center, radius + rope_radius * 1.1,
                             turns, rise_per_turn=rope_radius * 2.2,
                             rope_radius=rope_radius, tension=tension)

    @staticmethod
    def fender_knot(center, radius, rope_radius=0.006, tension=0.7):
        """
        Fender knot — decorative ball knot used on boat fenders and rope ends.

        Repeated over-under passes that tighten into a sphere.
        """
        c = Vector(center)
        s = RopeSequence(radius, rope_radius, tension)

        s.begin(c)
        for _ in range(4):
            s.pass_over(c)
            s.pass_under(c)
            s.tighten()
        s.finish("none")

        return s.build("fender_knot")

    @staticmethod
    def spiral(center, radius_start, radius_end, height, turns,
               rope_radius=0.006, tension=0.8):
        """
        Helix rising along Z — rigging, coiled springs, decorative spirals.
        """
        s = RopeSequence((radius_start + radius_end) * 0.5, rope_radius, tension)

        s.begin(center)
        s.spiral(center, radius_start, rise=height / turns, turns=turns)
        s.finish("none")

        return s.build("spiral")
