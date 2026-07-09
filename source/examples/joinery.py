"""
examples/joinery.py — Example generators for lashings, knots, coils, and utilities.

No local imports — all imports are absolute from the source root.
"""

import bpy
from mathutils import Vector

from rope.rope import create_rope, _grid_place, _grid_label, _grid_header, _PER_ROW
from rope.rope_lashings import Lashings
from rope.rope_knots import Knots
from rope.rope_coils import Coils
from rope.rope_utilities import Utilities


def _emit(col, header, cases):
    base_y, row = 0.0, 0
    _grid_header(header, col, row, base_y)
    for i, (label, path) in enumerate(cases):
        col_idx = i % _PER_ROW
        if i > 0 and col_idx == 0:
            row += 1
            _grid_header("", col, row, base_y)
        obj = create_rope(path, rope_type="lashing", age=0.4, seed=i + 200)
        _grid_place(col, obj, row, col_idx, base_y)
        _grid_label(label, col, row, col_idx, base_y)
        print(f"  joinery example: {label}")


_BR = 0.03
_POST = Vector((0, 0, 0))


def lashings(collection=None):
    col = collection or bpy.context.scene.collection
    _emit(col, "LASHINGS", [
        ("square",     Lashings.square(Vector((0, 0, 0)), Vector((0, 0, _BR * 2)),
                                       axis_a=(1, 0, 0), axis_b=(0, 1, 0), turns=3, beam_radius=_BR)),
        ("diagonal",   Lashings.diagonal(Vector((0, 0, 0)), Vector((0, 0, _BR * 2)),
                                         axis_a=(1, 0, 0), axis_b=(0, 1, 0), turns=3, beam_radius=_BR)),
        ("shear",      Lashings.shear(Vector((-_BR * 1.5, 0, 0)), Vector((_BR * 1.5, 0, 0)),
                                      pole_axis=(0, 0, 1), turns=3, beam_radius=_BR)),
        ("tripod",     Lashings.tripod(Vector((_BR * 2.5, 0, 0)),
                                       Vector((-_BR * 1.25, _BR * 2.17, 0)),
                                       Vector((-_BR * 1.25, -_BR * 2.17, 0)),
                                       pole_axis=(0, 0, 1), turns=2, beam_radius=_BR)),
        ("continuous", Lashings.continuous(
                           [Vector((-_BR * 3.3 + k * _BR * 2.2, 0, 0)) for k in range(4)],
                           member_axis=(0, 0, 1), turns=1, beam_radius=_BR)),
        ("japanese",   Lashings.japanese(Vector((0, 0, 0)), Vector((0, 0, _BR * 2)),
                                         axis_a=(1, 0, 0), axis_b=(0, 1, 0), turns=2, beam_radius=_BR)),
    ])


def knots(collection=None):
    col = collection or bpy.context.scene.collection
    _emit(col, "KNOTS", [
        ("clove hitch",  Knots.clove_hitch(_POST, post_radius=0.03)),
        ("half hitch",   Knots.half_hitch(_POST, post_radius=0.03, hitches=3)),
        ("timber hitch", Knots.timber_hitch(_POST, post_radius=0.03)),
        ("anchor hitch", Knots.anchor_hitch(_POST, post_radius=0.03)),
        ("cleat hitch",  Knots.cleat_hitch(_POST, cleat_width=0.06)),
        ("bowline",      Knots.bowline(_POST, loop_radius=0.05)),
        ("figure eight", Knots.figure_eight(Vector((0, 0, 0.1)), radius=0.06)),
        ("round turn",   Knots.round_turn(_POST, post_radius=0.03, turns=2)),
    ])


def coils(collection=None):
    col = collection or bpy.context.scene.collection
    _emit(col, "COILS", [
        ("flat coil",    Coils.flat(Vector((0, 0, 0)), 0.08, 4)),
        ("helical coil", Coils.helical(Vector((0, 0, 0)), 0.06, 4, 0.02)),
        ("hanging",      Coils.hanging(Vector((0, 0, 0.35)), Vector((0, 0, 0.05)), sag=0.08)),
        ("loop",         Coils.loop(Vector((0, 0, 0.1)), 0.06)),
        ("hook loop",    Coils.hook_loop(Vector((0, 0, 0.15)), 0.05)),
    ])


def utilities(collection=None):
    col = collection or bpy.context.scene.collection
    _emit(col, "UTILITIES", [
        ("straight",    Utilities.straight(Vector((0, 0, 0)), Vector((0, 0, 0.4)))),
        ("wrapped hdl", Utilities.wrapped_handle(Vector((0, 0, 0.15)),
                                                 length=0.3, wrap_radius=0.02, turns=6)),
        ("deco wrap",   Utilities.decorative_wrap(Vector((0, 0, 0.1)),
                                                  radius=0.03, turns=4)),
        ("fender knot", Utilities.fender_knot(Vector((0, 0, 0.1)), radius=0.05)),
        ("spiral",      Utilities.spiral(Vector((0, 0, 0)), 0.06, 0.06, 0.35, 2.5)),
    ])
