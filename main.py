"""
main.py — CLI entry point for procedural timber generation.

Run via Blender:
    blender --background --python main.py -- [options]

Options:
    --json     PATH   JSON file describing timbers to generate (see timbers.json)
    --out      PATH   Output .blend file  (default: ./timber_out.blend)
    --count    N      Generate N random variations (ignored when --json is used)
    --seed     N      Base seed for random variations (default: 0)
    --spacing  F      X spacing between objects (default: 0.35)
    --textures PATH   Directory containing PBR textures (overrides default)

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

# Ensure the module directory is on the path so timber_beam is importable
# regardless of where Blender is launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timber_beam import create_timber
from timber_material import assign_timber_material


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


# ---------------------------------------------------------------------------
# Generation modes
# ---------------------------------------------------------------------------

DEFAULT_VARIATIONS = [
    (2.0, 0.22, 0.18), (1.5, 0.18, 0.15), (2.5, 0.25, 0.20),
    (1.8, 0.20, 0.16), (3.0, 0.28, 0.22), (1.2, 0.16, 0.14),
    (2.2, 0.24, 0.19), (1.6, 0.19, 0.17), (2.8, 0.26, 0.21),
    (2.0, 0.21, 0.20),
]


def generate_from_json(path, spacing):
    with open(path) as f:
        entries = json.load(f)

    for i, entry in enumerate(entries):
        params = {
            "length":  entry.get("length",  2.0),
            "width":   entry.get("width",   0.22),
            "height":  entry.get("height",  0.18),
            "seed":    entry.get("seed",    i * 17 + 3),
        }
        loc = entry.get("location", [i * spacing, 0, 0])
        obj = create_timber(**params)
        _link(obj, loc)
        assign_timber_material(obj)
        _print_stats(i, obj, params)


def generate_variations(count, base_seed, spacing):
    import random
    rng = random.Random(base_seed)

    for i in range(count):
        if i < len(DEFAULT_VARIATIONS):
            l, w, h = DEFAULT_VARIATIONS[i]
        else:
            l = rng.uniform(1.0, 3.5)
            w = rng.uniform(0.14, 0.30)
            h = rng.uniform(0.12, 0.26)

        params = {"length": round(l, 3), "width": round(w, 3),
                  "height": round(h, 3), "seed": i * 17 + base_seed}
        obj = create_timber(**params)
        _link(obj, (i * spacing, 0, 0))
        assign_timber_material(obj)
        _print_stats(i, obj, params)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    # Blender passes its own args before '--'; everything after is ours.
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    p = argparse.ArgumentParser(description="Procedural timber generator")
    p.add_argument("--json",     metavar="PATH", help="Input JSON file")
    p.add_argument("--out",      metavar="PATH", default="/home/samuel/projects/models/timber_out.blend")
    p.add_argument("--count",    metavar="N",    type=int, default=10)
    p.add_argument("--seed",     metavar="N",    type=int, default=0)
    p.add_argument("--spacing",  metavar="F",    type=float, default=0.35)
    p.add_argument("--textures", metavar="PATH", help="Texture directory")
    return p.parse_args(argv)


def main():
    args = parse_args()

    _clear_scene()

    if args.textures:
        import timber_material
        timber_material.TEXTURE_DIR = os.path.abspath(args.textures)
        print(f"  Textures: {timber_material.TEXTURE_DIR}")

    print("Generating timbers...")

    if args.json:
        print(f"  Source: {args.json}")
        generate_from_json(args.json, args.spacing)
    else:
        print(f"  Variations: {args.count}  base_seed: {args.seed}")
        generate_variations(args.count, args.seed, args.spacing)

    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
