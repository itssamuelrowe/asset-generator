"""
table_structure.py — Data classes describing the canonical work table structure.

A TableStructure fully describes what a table is made of and how it is
assembled.  The builder engine reads this description and generates geometry;
it never hard-codes counts or roles itself.

Coordinate convention (matches table_builder.py):
    Origin  : tabletop surface centre
    +Z      : up
    +X      : along table length
    +Y      : along table width
    Legs    : point down (−Z)
"""

from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Primitive roles
# ---------------------------------------------------------------------------

@dataclass
class TimberRole:
    """One timber in the table with its structural role and placement hints."""
    name: str                        # e.g. "leg_front_left"
    role: str                        # "leg" | "long_rail" | "short_rail" | "stretcher"
    # Placement is resolved by the builder from the solved dimensions;
    # these flags guide that resolution.
    upper: bool = True               # True → upper rail/stretcher, False → lower
    side: str   = ""                 # "left" | "right" | "front" | "rear" | ""


@dataclass
class PlankRole:
    """One plank in the tabletop."""
    name: str                        # e.g. "plank_1"
    index: int                       # 0-based position along Y (width axis)


@dataclass
class LashingSpec:
    """One lashing joining two named members."""
    member_a: str                    # name of first  TimberRole / PlankRole
    member_b: str                    # name of second TimberRole / PlankRole
    style: str = "square"            # "square" | "diagonal"
    strength: str = "medium"         # "light" | "medium" | "heavy"


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------

@dataclass
class TableStructure:
    """
    Complete structural description of a table.

    The builder engine iterates timbers, planks, and lashings in order.
    Adding a new table variant means subclassing or replacing this object;
    the engine stays unchanged.
    """
    timbers:  List[TimberRole]  = field(default_factory=list)
    planks:   List[PlankRole]   = field(default_factory=list)
    lashings: List[LashingSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Factory — canonical work table
# ---------------------------------------------------------------------------

def canonical_work_table(plank_count: int = 5) -> TableStructure:
    """
    Return the structure for the canonical hand-hewn work table:

        4 legs  (front-left, front-right, rear-left, rear-right)
        2 long  rails  (upper, connecting left legs / right legs)
        2 short rails  (upper, connecting front legs / rear legs)
        2 lower stretchers (lower, one per long side)
        N planks (tabletop)

    Lashings:
        4 square lashings at upper frame corners  (leg × long-rail)
        4 square lashings at lower frame corners  (leg × stretcher)
        Tabletop: outer planks lashed to long rails (hidden underside)
    """
    timbers = [
        # Legs
        TimberRole("leg_front_left",  "leg"),
        TimberRole("leg_front_right", "leg"),
        TimberRole("leg_rear_left",   "leg"),
        TimberRole("leg_rear_right",  "leg"),
        # Upper long rails — run along X under the planks, one per Y side (front/rear)
        # Planks rest on and lash to these.
        TimberRole("long_rail_front", "long_rail", upper=True, side="front"),
        TimberRole("long_rail_rear",  "long_rail", upper=True, side="rear"),
        # Upper short rails — connect front-left↔rear-left and front-right↔rear-right
        TimberRole("short_rail_left",  "short_rail", upper=True, side="left"),
        TimberRole("short_rail_right", "short_rail", upper=True, side="right"),
        # Lower stretchers — one per long (front/rear) side, improve silhouette
        TimberRole("stretcher_front", "stretcher", upper=False, side="front"),
        TimberRole("stretcher_rear",  "stretcher", upper=False, side="rear"),
    ]

    planks = [PlankRole(f"plank_{i+1}", i) for i in range(plank_count)]

    lashings = [
        # Upper frame — 4 corners: each leg × the long rail it meets
        # Front legs meet long_rail_front; rear legs meet long_rail_rear.
        LashingSpec("leg_front_left",  "long_rail_front", "square", "medium"),
        LashingSpec("leg_front_right", "long_rail_front", "square", "medium"),
        LashingSpec("leg_rear_left",   "long_rail_rear",  "square", "medium"),
        LashingSpec("leg_rear_right",  "long_rail_rear",  "square", "medium"),
        # Lower frame — 4 corners: each leg × the stretcher on its side
        LashingSpec("leg_front_left",  "stretcher_front", "square", "medium"),
        LashingSpec("leg_front_right", "stretcher_front", "square", "medium"),
        LashingSpec("leg_rear_left",   "stretcher_rear",  "square", "medium"),
        LashingSpec("leg_rear_right",  "stretcher_rear",  "square", "medium"),
        # Tabletop — outer planks lashed from underneath to both long rails
        LashingSpec("plank_1",              "long_rail_front", "square", "light"),
        LashingSpec("plank_1",              "long_rail_rear",  "square", "light"),
        LashingSpec(f"plank_{plank_count}", "long_rail_front", "square", "light"),
        LashingSpec(f"plank_{plank_count}", "long_rail_rear",  "square", "light"),
    ]

    return TableStructure(timbers=timbers, planks=planks, lashings=lashings)
