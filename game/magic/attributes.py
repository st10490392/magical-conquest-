"""Magic attributes (elements) an entity can possess.

Adding an attribute means adding an enum member here. Combat never branches
on the element, so no combat code has to change.

Wind and Air are distinct attributes, as are Lightning and Thunder.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Set


class MagicAttribute(str, Enum):
    FIRE = "fire"
    WATER = "water"
    ICE = "ice"
    WIND = "wind"
    AIR = "air"
    EARTH = "earth"
    LIGHTNING = "lightning"
    THUNDER = "thunder"
    LIGHT = "light"

    @property
    def label(self) -> str:
        return self.value.capitalize()


def parse_attributes(values: Iterable[str]) -> Set[MagicAttribute]:
    """Convert stored strings to attributes; raises ``ValueError`` on unknown ones."""
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple, set, frozenset)):
        raise TypeError("magic attributes must be a list of strings")
    return {MagicAttribute(value) for value in values}
