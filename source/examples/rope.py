"""
examples/rope.py — Example generators for rope types, end styles, path shapes,
age, wetness, and twist density.

Each function generates one sub-group into a Blender collection.
No local imports — all imports are absolute from the source root.
"""

import math
import bpy
from mathutils import Vector

from rope.rope import create_rope, _grid_place, _grid_label, _grid_header, _SX, _SY, _PER_ROW
from rope.rope_path import RopePath


def _emit(col, row, base_y, header, items, make_fn, label_fn):
    _grid_header(header, col, row, base_y)
    for i, item in enumerate(items):
        col_idx = i % _PER_ROW
        if i > 0 and col_idx == 0:
            row += 1
            _grid_header("", col, row, base_y)
        obj = make_fn(item, i)
        _grid_place(col, obj, row, col_idx, base_y)
        _grid_label(label_fn(item), col, row, col_idx, base_y)
    return row + 1


def types(collection=None):
    col, base_y = collection or bpy.context.scene.collection, 0.0
    _emit(col, 0, base_y,
          "ROPE TYPE",
          ["twine", "utility", "structural", "mooring", "palm_fiber", "decorative"],
          lambda rtype, i: create_rope(
              RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.4))),
              rope_type=rtype, age=0.3, seed=i),
          lambda x: x)


def ends(collection=None):
    col, base_y = collection or bpy.context.scene.collection, 0.0
    _emit(col, 0, base_y,
          "END STYLE",
          ["cut", "frayed", "wrapped", "burned", "compressed"],
          lambda style, i: create_rope(
              RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.35))),
              rope_type="utility", end_style=style,
              fray=0.8 if style == "frayed" else 0.0, age=0.4, seed=i + 10),
          lambda x: x)


def paths(collection=None):
    col, base_y = collection or bpy.context.scene.collection, 0.0
    items = [
        ("line",     RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.4)))),
        ("arc",      RopePath.arc(Vector((0, 0, 0.2)), 0.15, 0, math.pi)),
        ("bezier",   RopePath.bezier(Vector((0, 0, 0)), Vector((0.1, 0, 0.15)),
                                     Vector((-0.1, 0, 0.25)), Vector((0, 0, 0.4)))),
        ("catenary", RopePath.catenary(Vector((0, 0, 0.35)), Vector((0, 0, 0.05)), sag=0.06)),
        ("spiral",   RopePath.spiral(Vector((0, 0, 0)), 0.06, 0.06, 0.3, 2)),
    ]
    _emit(col, 0, base_y,
          "PATH SHAPE", items,
          lambda item, i: create_rope(item[1], rope_type="utility", age=0.3, seed=i + 20),
          lambda x: x[0])


def age(collection=None):
    col, base_y = collection or bpy.context.scene.collection, 0.0
    _emit(col, 0, base_y,
          "AGE", [0.0, 0.25, 0.5, 0.75, 1.0],
          lambda a, i: create_rope(
              RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.35))),
              rope_type="utility", age=a, seed=30),
          lambda x: f"{x:.2f}")


def wetness(collection=None):
    col, base_y = collection or bpy.context.scene.collection, 0.0
    _emit(col, 0, base_y,
          "WETNESS", [0.0, 0.25, 0.5, 0.75, 1.0],
          lambda w, i: create_rope(
              RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.35))),
              rope_type="utility", wetness=w, age=0.3, seed=40),
          lambda x: f"{x:.2f}")


def twist(collection=None):
    col, base_y = collection or bpy.context.scene.collection, 0.0
    _emit(col, 0, base_y,
          "TWIST", [0.5, 1.0, 1.5, 2.0, 3.0],
          lambda td, i: create_rope(
              RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.4))),
              rope_type="utility", twist_density=td, age=0.3, seed=50),
          lambda x: f"x{x:.1f}")


def path_utils(collection=None):
    col, base_y = collection or bpy.context.scene.collection, 0.0
    items = [
        ("line",       RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.4)))),
        ("arc",        RopePath.arc(Vector((0, 0, 0.2)), 0.15, 0, math.pi)),
        ("circle",     RopePath.circle(Vector((0, 0, 0.1)), 0.10)),
        ("spiral",     RopePath.spiral(Vector((0, 0, 0)), 0.06, 0.06, 0.35, 2.5)),
        ("bezier",     RopePath.bezier(Vector((0, 0, 0)), Vector((0.12, 0, 0.15)),
                                       Vector((-0.12, 0, 0.25)), Vector((0, 0, 0.4)))),
        ("catenary",   RopePath.catenary(Vector((0, 0, 0.35)), Vector((0, 0, 0.05)), sag=0.07)),
        ("subdivided", RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.4)),
                                     points=4).subdivide(4)),
        ("smoothed",   RopePath.bezier(Vector((0, 0, 0)), Vector((0.15, 0, 0.1)),
                                       Vector((-0.15, 0, 0.3)),
                                       Vector((0, 0, 0.4))).smooth(3)),
        ("reversed",   RopePath.catenary(Vector((0, 0, 0.35)), Vector((0, 0, 0.05)),
                                         sag=0.05).reverse()),
        ("composed",   RopePath.line(Vector((0, 0, 0)), Vector((0, 0, 0.2)))
                                .append(RopePath.arc(Vector((0, 0, 0.2)), 0.08, 0, math.pi))),
    ]
    _emit(col, 0, base_y,
          "PATH UTILS", items,
          lambda item, i: create_rope(item[1], rope_type="utility", age=0.3, seed=i + 100),
          lambda x: x[0])
