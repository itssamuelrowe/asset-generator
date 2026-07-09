"""
rope_coils.py — Coil, loop, and hanging paths for The Giant Raft.

Every coil is written as an explicit program of primitive rope
operations.

All methods return a RopePath.  No geometry is generated here.
"""

from mathutils import Vector
from rope.rope_path import RopeSequence


class Coils:

    @staticmethod
    def flat(center, radius, turns, rope_radius=0.006, tension=0.7):
        """
        Flat coil — rope coiled on a surface with no vertical rise.
        """
        s = RopeSequence(radius, rope_radius, tension)

        s.begin(center)
        for _ in range(int(turns)):
            s.circle(center, radius)
        s.finish("none")

        return s.build("coil_flat")

    @staticmethod
    def helical(center, radius, turns, rise_per_turn,
                rope_radius=0.006, tension=0.7):
        """
        Helical coil — rope coiled on a hook or peg, rising with each turn.
        """
        s = RopeSequence(radius, rope_radius, tension)

        s.begin(center)
        s.spiral(center, radius, rise=rise_per_turn, turns=turns)
        s.finish("none")

        return s.build("coil_helical")

    @staticmethod
    def hanging(top, bottom, sag=0.05, rope_radius=0.006, tension=0.4):
        """
        Hanging rope — catenary sag between two anchor points.
        The rope spirals down from top, drops under gravity, arrives at bottom.
        """
        t, b = Vector(top), Vector(bottom)
        mid  = t.lerp(b, 0.5) - Vector((0, 0, sag))
        s = RopeSequence(0.01, rope_radius, tension)

        s.begin(t)
        s.line_to(mid)
        s.line_to(b)
        s.finish("none")

        return s.build("hanging")

    @staticmethod
    def loop(center, radius, normal=None, rope_radius=0.006, tension=0.8):
        """
        Simple closed loop — handles, rings, tie-downs, lashing anchors.
        """
        n = normal if normal is not None else (0, 0, 1)
        s = RopeSequence(radius, rope_radius, tension)

        s.begin(center)
        s.circle(center, radius, normal=n)
        s.finish("none")

        return s.build("loop")

    @staticmethod
    def hook_loop(hook_tip, loop_radius, drop=0.05,
                  rope_radius=0.006, tension=0.85):
        """
        Loop hanging from a hook tip — droops under its own weight.
        """
        tip  = Vector(hook_tip)
        low  = tip - Vector((0, 0, drop))
        s = RopeSequence(loop_radius, rope_radius, tension)

        s.begin(tip)
        s.loop(low, loop_radius)
        s.finish("none")

        return s.build("hook_loop")
