"""
examples/__init__.py — Registry mapping dotted ids to generator functions.

IDs follow the pattern  group.subgroup  e.g.:
    rope.types   rope.ends   rope.paths   rope.age   rope.wetness
    rope.twist   rope.path_utils
    joinery.lashings   joinery.knots   joinery.coils   joinery.utilities

Filtering uses fnmatch wildcards:  rope.*   joinery.lashings   *.knots
"""

import fnmatch
from typing import Callable, Dict, List

import examples.rope as _rope
import examples.joinery as _joinery

_REGISTRY: Dict[str, Callable] = {
    "rope.types":          _rope.types,
    "rope.ends":           _rope.ends,
    "rope.paths":          _rope.paths,
    "rope.age":            _rope.age,
    "rope.wetness":        _rope.wetness,
    "rope.twist":          _rope.twist,
    "rope.path_utils":     _rope.path_utils,
    "joinery.lashings":    _joinery.lashings,
    "joinery.knots":       _joinery.knots,
    "joinery.coils":       _joinery.coils,
    "joinery.utilities":   _joinery.utilities,
}


def list_examples() -> List[str]:
    return sorted(_REGISTRY.keys())


def match_examples(pattern: str) -> List[str]:
    return sorted(k for k in _REGISTRY if fnmatch.fnmatch(k, pattern))


def run(ids: List[str], collection=None):
    for eid in ids:
        print(f"  generating: {eid}")
        _REGISTRY[eid](collection)


def interactive_menu() -> List[str]:
    from collections import OrderedDict

    ids = list_examples()
    groups: Dict[str, list] = OrderedDict()
    for i, eid in enumerate(ids):
        key = eid.rsplit(".", 1)[0]
        groups.setdefault(key, []).append((i + 1, eid))

    print("\nAvailable examples:")
    print("-" * 40)
    for group, members in groups.items():
        print(f"  [{group}]")
        for num, eid in members:
            print(f"    {num:2d}. {eid}")
    print("-" * 40)
    print("Enter: numbers (1,3,5), a wildcard (rope.*), or blank for all")

    raw = input("Selection: ").strip()

    if not raw:
        return ids

    if any(c in raw for c in ("*", "?", "[")):
        matched = match_examples(raw)
        if not matched:
            print(f"  No examples match '{raw}'")
        return matched

    selected = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(ids):
                selected.append(ids[idx])
            else:
                print(f"  Warning: {token} out of range, skipped")
        elif token:
            selected.extend(match_examples(token))
    return selected
