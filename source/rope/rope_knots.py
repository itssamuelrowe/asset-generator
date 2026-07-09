"""
rope_knots.py — Knot and hitch paths for The Giant Raft.

Every knot is written as an explicit program of primitive rope
operations.  Read each method top-to-bottom and you are reading the
procedure a rigger would follow.

All methods return a RopePath.  No geometry is generated here.
"""

import math
from mathutils import Vector
from rope.rope_path import RopeSequence


class Knots:

    @staticmethod
    def clove_hitch(post_center, post_radius, rope_radius=0.010,
                    normal=None, tension=0.85):
        """
        Clove hitch — two offset loops that lock against each other.
        The standard knot for starting and finishing a lashing.
        """
        n = normal if normal is not None else (0, 0, 1)
        s = RopeSequence(post_radius, rope_radius, tension)

        s.begin(post_center)
        s.wrap(post_center, turns=1, normal=n)
        s.cross_to(post_center)
        s.wrap(post_center, turns=1, normal=n)
        s.finish("none")

        return s.build("clove_hitch")

    @staticmethod
    def half_hitch(post_center, post_radius, rope_radius=0.010,
                   hitches=2, normal=None, tension=0.8):
        """
        Half hitches — one loop passed under the standing part.
        Often used to finish off a lashing after a round turn.
        """
        n = normal if normal is not None else (0, 0, 1)
        s = RopeSequence(post_radius, rope_radius, tension)

        s.begin(post_center)
        for _ in range(hitches):
            s.wrap(post_center, turns=1, normal=n)
            s.pass_under(post_center, normal=n)
        s.finish("none")

        return s.build("half_hitch")

    @staticmethod
    def timber_hitch(post_center, post_radius, rope_radius=0.010,
                     normal=None, tension=0.8):
        """
        Timber hitch — loop around a log with the tail twisted back on itself.
        Grips tighter under load; used to start a lashing or drag a spar.
        """
        n = normal if normal is not None else (0, 0, 1)
        s = RopeSequence(post_radius, rope_radius, tension)

        s.begin(post_center)
        s.wrap(post_center, turns=1, normal=n)
        s.loop_back = lambda: s.cross_to(post_center)   # tail returns through loop
        s.cross_to(post_center)
        s.twist_self(turns=4)
        s.finish("none")

        return s.build("timber_hitch")

    @staticmethod
    def anchor_hitch(post_center, post_radius, rope_radius=0.012,
                     normal=None, tension=0.9):
        """
        Anchor hitch (fisherman's hitch) — two round turns plus a half hitch.
        Very secure under load; won't jam when wet.
        """
        n = normal if normal is not None else (0, 0, 1)
        s = RopeSequence(post_radius, rope_radius, tension)

        s.begin(post_center)
        s.wrap(post_center, turns=2, normal=n)
        s.half_turn(post_center, normal=n)
        s.finish("half_hitch", member=post_center, normal=n)

        return s.build("anchor_hitch")

    @staticmethod
    def cleat_hitch(cleat_center, cleat_width, rope_radius=0.010, tension=0.9):
        """
        Cleat hitch — figure-eight around a dock cleat's two horns, then locked.
        """
        c     = Vector(cleat_center)
        hw    = cleat_width * 0.5
        horn_a = c + Vector(( hw, 0, 0))
        horn_b = c + Vector((-hw, 0, 0))
        s = RopeSequence(cleat_width * 0.1, rope_radius, tension)

        s.begin(c)
        s.loop(c, cleat_width * 0.5)
        s.cross_to(horn_a)
        s.wrap(horn_a, turns=0.5)
        s.cross_to(horn_b)
        s.wrap(horn_b, turns=0.5)
        s.lock()
        s.finish("none")

        return s.build("cleat_hitch")

    @staticmethod
    def bowline(post_center, loop_radius, rope_radius=0.010, tension=0.85):
        """
        Bowline — fixed loop that won't slip or jam under load.
        "The rabbit comes up through the hole, round the tree, back down the hole."
        """
        c = Vector(post_center)
        s = RopeSequence(loop_radius, rope_radius, tension)

        s.begin(c)
        s.small_loop(c)
        s.cross_to(c + Vector((0, 0, rope_radius * 2)))   # tail up through loop
        s.wrap(c, turns=0.5)                               # round the standing part
        s.cross_to(c)                                      # back down through loop
        s.finish("none")

        return s.build("bowline")

    @staticmethod
    def figure_eight(center, radius, normal=None, tension=0.85):
        """
        Figure-eight knot — stopper knot that prevents a rope end pulling
        through a block or hole.
        """
        n = normal if normal is not None else (0, 0, 1)
        c = Vector(center)
        s = RopeSequence(radius, radius * 0.1, tension)

        s.begin(c)
        s.loop(c, radius, normal=n)
        s.cross_to(c)
        s.wrap(c, turns=0.5, normal=n)
        s.cross_to(c)
        s.finish("none")

        return s.build("figure_eight")

    @staticmethod
    def round_turn(post_center, post_radius, rope_radius=0.010,
                   turns=2, normal=None, tension=0.85):
        """
        Round turn — multiple full loops around a post or bollard.
        Distributes load across the post before the finishing hitch.
        """
        n = normal if normal is not None else (0, 0, 1)
        s = RopeSequence(post_radius, rope_radius, tension)

        s.begin(post_center)
        s.wrap(post_center, turns=turns, normal=n)
        s.finish("half_hitch", member=post_center, normal=n)

        return s.build("round_turn")

    @staticmethod
    def mooring_hitch(post_center, post_radius, rope_radius=0.012,
                      turns=3, normal=None, tension=0.9):
        """
        Mooring hitch — heavy round turns for dock lines and bollards.
        Alias for round_turn with turns=3.
        """
        return Knots.round_turn(post_center, post_radius, rope_radius,
                                turns=turns, normal=normal, tension=tension)
