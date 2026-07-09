"""
main.py — CLI entry point for procedural timber/plank generation.

Run via Blender:
    blender --background --python main.py -- [options]

Options:
    --json     PATH   JSON file describing assets to generate (see timbers.json)
    --out      PATH   Output .blend file  (default: output/<type>_out.blend)
    --count    N      Generate N random variations (ignored when --json is used)
    --seed     N      Base seed for random variations (default: 0)
    --spacing  F      X spacing between objects (default: 0.35)
    --textures PATH   Directory containing PBR textures (overrides default)
    --type     TYPE   Asset type: timber (default), plank, stool, table, rope
    --examples [PATTERN ...]
                      Generate examples matching dotted wildcard patterns.
                      e.g.  rope.*   joinery.lashings   rope.ends
                      Omit patterns to launch the interactive menu.
    --list-examples   Print all available example ids and exit.

JSON schema (array of objects):
    [
      { "length": 2.0, "width": 0.22, "height": 0.18, "seed": 7,
        "location": [0, 0, 0] },
      ...
    ]
All fields are optional; missing ones fall back to defaults.
"""

import sys
import os
import json
import argparse

import bpy

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'source')
sys.path.insert(0, _SRC)

from primitives.timber_beam import create_timber
from materials.timber_material import assign_timber_material
from primitives.plank_beam import create_plank
from builders.stool_builder import create_stool
from builders.table_builder import TableBuilder
from rope.rope import create_rope
from rope.rope_path import RopePath


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=True)
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)


def _link(obj, location=(0, 0, 0)):
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def _print_stats(i, obj, params):
    v = len(obj.data.vertices)
    f = len(obj.data.polygons)
    print(f"  [{i+1:02d}] {v}v {f}f  "
          f"L={params['length']} W={params['width']} H={params['height']} "
          f"seed={params['seed']}")


def _default_out_path(asset_type):
    name = f"{asset_type}_out.blend"
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", name)


# ---------------------------------------------------------------------------
# Generation modes
# ---------------------------------------------------------------------------

DEFAULT_VARIATIONS = [
    (2.0, 0.22, 0.18), (1.5, 0.18, 0.15), (2.5, 0.25, 0.20),
    (1.8, 0.20, 0.16), (3.0, 0.28, 0.22), (1.2, 0.16, 0.14),
    (2.2, 0.24, 0.19), (1.6, 0.19, 0.17), (2.8, 0.26, 0.21),
    (2.0, 0.21, 0.20),
]

TABLE_VARIATIONS = [
    (1.50, 0.80, 0.76, 1),  (1.20, 0.70, 0.74, 2),  (1.80, 0.90, 0.78, 3),
    (1.40, 0.75, 0.76, 4),  (1.60, 0.85, 0.80, 5),  (1.30, 0.72, 0.74, 6),
    (1.70, 0.88, 0.78, 7),  (1.45, 0.78, 0.76, 8),  (1.55, 0.82, 0.76, 9),
    (1.65, 0.92, 0.82, 10),
]

STOOL_VARIATIONS = [
    (42, 'square', True),  (7,  'square', False), (13, 'round',  True),
    (99, 'round',  False), (55, 'square', True),  (23, 'square', True),
    (77, 'round',  True),  (31, 'square', False), (61, 'round',  False),
    (88, 'square', True),
]

PLANK_VARIATIONS = [
    (2.0, 0.25, 0.040), (1.5, 0.22, 0.035), (2.5, 0.28, 0.045),
    (1.8, 0.24, 0.038), (3.0, 0.30, 0.050), (1.2, 0.20, 0.032),
    (2.2, 0.26, 0.042), (1.6, 0.23, 0.036), (2.8, 0.29, 0.048),
    (2.0, 0.25, 0.040),
]

ROPE_VARIATIONS = [
    (1.0, "utility",    0.2, 0.0, 0.0, "cut",     1),
    (1.5, "utility",    0.5, 0.0, 0.0, "cut",     2),
    (2.0, "structural", 0.8, 0.1, 0.0, "frayed",  3),
    (0.8, "mooring",    0.3, 0.0, 0.0, "cut",     4),
    (1.2, "twine",      0.1, 0.0, 0.0, "cut",     5),
    (1.8, "utility",    0.6, 0.3, 0.2, "frayed",  6),
    (2.5, "structural", 0.9, 0.0, 0.0, "burned",  7),
    (1.0, "mooring",    0.4, 0.0, 0.0, "wrapped", 8),
    (1.4, "utility",    0.7, 0.2, 0.1, "frayed",  9),
    (1.6, "decorative", 0.3, 0.0, 0.0, "cut",    10),
]


def generate_from_json(path, spacing, asset_type):
    with open(path) as f:
        entries = json.load(f)

    if asset_type == 'rope':
        from mathutils import Vector
        for i, entry in enumerate(entries):
            length = entry.get('length', 1.0)
            loc    = entry.get('location', [i * spacing, 0, 0])
            p      = RopePath.line(Vector(loc), Vector((loc[0], loc[1], loc[2] + length)))
            obj = create_rope(
                path          = p,
                rope_type     = entry.get('rope_type',    'utility'),
                radius        = entry.get('radius',        None),
                twist_density = entry.get('twist_density', 1.0),
                age           = entry.get('age',           0.3),
                wetness       = entry.get('wetness',       0.0),
                fray          = entry.get('fray',          0.0),
                end_style     = entry.get('end_style',     'cut'),
                lod           = entry.get('lod',           0),
                seed          = entry.get('seed',          i * 17 + 3),
            )
            _link(obj, (0, 0, 0))
            print(f"  [{i+1:02d}] rope type={entry.get('rope_type','utility')} seed={entry.get('seed', i*17+3)}")
        return

    if asset_type == 'table':
        for i, entry in enumerate(entries):
            loc = entry.get('location', [i * spacing, 0, 0])
            obj = TableBuilder(
                width               = entry.get('length',  1.50),
                depth               = entry.get('width',   0.80),
                height              = entry.get('height',  0.85),
                plank_count         = entry.get('plank_count', 5),
                tabletop_attachment = entry.get('tabletop_attachment', 'lashing'),
                age                 = entry.get('age',     0.35),
                damage              = entry.get('damage',  0.2),
                wetness             = entry.get('wetness', 0.1),
                seed                = entry.get('seed',    i * 17 + 3),
            ).build()
            obj.location = loc
        return

    if asset_type == 'stool':
        for i, entry in enumerate(entries):
            seed   = entry.get('seed', i * 17 + 3)
            shape  = entry.get('shape', 'square')
            braces = entry.get('braces', True)
            loc    = entry.get('location', [i * spacing, 0, 0])
            obj    = create_stool(seed=seed, shape=shape, braces=braces)
            obj.location = loc
            print(f"  [{i+1:02d}] stool seed={seed} shape={shape} braces={braces}")
        return

    is_plank = asset_type == 'plank'
    creator  = create_plank if is_plank else create_timber

    for i, entry in enumerate(entries):
        params = {
            "length": entry.get("length", 2.0),
            "width":  entry.get("width",  0.25 if is_plank else 0.22),
            "height": entry.get("height", 0.04 if is_plank else 0.18),
            "seed":   entry.get("seed",   i * 17 + 3),
        }
        loc = entry.get("location", [i * spacing, 0, 0])
        obj = creator(**params)
        _link(obj, loc)
        assign_timber_material(obj)
        _print_stats(i, obj, params)


def generate_variations(count, base_seed, spacing, asset_type):
    import random
    rng = random.Random(base_seed)

    if asset_type == 'rope':
        from mathutils import Vector
        _types = ["utility", "structural", "mooring", "twine", "decorative"]
        for i in range(count):
            if i < len(ROPE_VARIATIONS):
                l, rtype, age, wet, fray, end_style, s = ROPE_VARIATIONS[i]
            else:
                l         = rng.uniform(0.5, 3.0)
                rtype     = rng.choice(_types)
                age       = rng.uniform(0.1, 0.9)
                wet       = rng.uniform(0.0, 0.3)
                fray      = rng.uniform(0.0, 0.4)
                end_style = rng.choice(["cut", "frayed", "wrapped"])
                s         = base_seed + i * 17
            x    = i * spacing
            p    = RopePath.line(Vector((x, 0, 0)), Vector((x, 0, l)))
            obj  = create_rope(path=p, rope_type=rtype, age=age,
                               wetness=wet, fray=fray, end_style=end_style, seed=s)
            _link(obj, (0, 0, 0))
            print(f"  [{i+1:02d}] rope type={rtype} L={l:.2f} seed={s} age={age:.1f}")
        return

    if asset_type == 'table':
        for i in range(count):
            if i < len(TABLE_VARIATIONS):
                l, w, h, s = TABLE_VARIATIONS[i]
            else:
                l = rng.uniform(1.20, 1.80)
                w = rng.uniform(0.70, 0.95)
                h = rng.uniform(0.72, 0.82)
                s = base_seed + i * 17
            obj = TableBuilder(
                width=round(l, 3), depth=round(w, 3), height=round(h, 3), seed=s,
            ).build()
            obj.location = (i * spacing, 0, 0)
        return

    if asset_type == 'stool':
        for i in range(count):
            if i < len(STOOL_VARIATIONS):
                seed, shape, braces = STOOL_VARIATIONS[i]
            else:
                seed   = base_seed + i * 17
                shape  = rng.choice(['square', 'round'])
                braces = rng.choice([True, False])
            obj = create_stool(seed=seed, shape=shape, braces=braces)
            obj.location = (i * spacing, 0, 0)
            print(f"  [{i+1:02d}] stool seed={seed} shape={shape} braces={braces}")
        return

    is_plank = asset_type == 'plank'
    creator  = create_plank if is_plank else create_timber
    defaults = PLANK_VARIATIONS if is_plank else DEFAULT_VARIATIONS

    for i in range(count):
        if i < len(defaults):
            l, w, h = defaults[i]
        else:
            l = rng.uniform(1.0, 3.5)
            w = rng.uniform(0.18, 0.32) if is_plank else rng.uniform(0.14, 0.30)
            h = rng.uniform(0.028, 0.055) if is_plank else rng.uniform(0.12, 0.26)

        params = {"length": round(l, 3), "width": round(w, 3),
                  "height": round(h, 3), "seed": i * 17 + base_seed}
        obj = creator(**params)
        _link(obj, (i * spacing, 0, 0))
        assign_timber_material(obj)
        _print_stats(i, obj, params)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    p = argparse.ArgumentParser(description="Procedural timber/plank generator")
    p.add_argument("--json",     metavar="PATH", help="Input JSON file")
    p.add_argument("--out",      metavar="PATH", default=None,
                   help="Output .blend file (default: output/<type>_out.blend)")
    p.add_argument("--count",    metavar="N",    type=int, default=10)
    p.add_argument("--seed",     metavar="N",    type=int, default=0)
    p.add_argument("--spacing",  metavar="F",    type=float, default=0.35)
    p.add_argument("--textures", metavar="PATH", help="Texture directory")
    p.add_argument("--type",     metavar="TYPE", default="timber",
                   choices=["timber", "plank", "stool", "table", "rope"])
    p.add_argument("--examples", nargs="*", metavar="PATTERN",
                   help="Generate examples matching dotted wildcard patterns "
                        "(e.g. rope.* joinery.lashings). Omit to use interactive menu.")
    p.add_argument("--list-examples", action="store_true",
                   help="Print all available example ids and exit")
    return p.parse_args(argv)


def main():
    args = parse_args()

    from examples import list_examples, match_examples, run, interactive_menu

    if args.list_examples:
        for eid in list_examples():
            print(eid)
        return

    _clear_scene()

    if args.textures:
        from materials import timber_material
        timber_material.set_texture_dir(args.textures)
        print(f"  Textures: {timber_material.TEXTURE_DIR}")

    if args.examples is not None:
        if args.examples:
            # One or more explicit patterns supplied
            selected = []
            for pat in args.examples:
                matched = match_examples(pat)
                if not matched:
                    print(f"  Warning: no examples match '{pat}'")
                selected.extend(matched)
        else:
            # --examples with no arguments → interactive menu
            selected = interactive_menu()

        if not selected:
            print("No examples selected.")
            return

        print(f"Generating examples: {', '.join(selected)}")
        col = bpy.context.scene.collection
        run(selected, col)

        out = os.path.abspath(
            args.out or os.path.join(os.path.dirname(__file__), "output", "examples_out.blend")
        )
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"Saved: {out}")
        return

    print(f"Generating {args.type}s...")

    if args.json:
        print(f"  Source: {args.json}")
        generate_from_json(args.json, args.spacing, args.type)
    else:
        print(f"  Variations: {args.count}  base_seed: {args.seed}")
        generate_variations(args.count, args.seed, args.spacing, args.type)

    out = os.path.abspath(args.out or _default_out_path(args.type))
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
