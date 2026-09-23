"""Spells an entity knows, the selected spell, and per-spell cooldowns."""

from __future__ import annotations

from typing import Dict, List, Optional

from game.core.combat import Cooldown
from game.magic.spells import Spell


class SpellBook:
    def __init__(self) -> None:
        self._spells: Dict[str, Spell] = {}
        self._cooldowns: Dict[str, Cooldown] = {}
        self.selected_id: Optional[str] = None

    @property
    def spells(self) -> List[Spell]:
        """Known spells in the order they were learned."""
        return list(self._spells.values())

    def learn(self, spell: Spell) -> None:
        """Knowing a spell does not bypass its casting requirements."""
        if spell.spell_id not in self._spells:
            self._spells[spell.spell_id] = spell
            self._cooldowns[spell.spell_id] = Cooldown()
        if self.selected_id is None:
            self.selected_id = spell.spell_id

    def knows(self, spell: Spell) -> bool:
        return self._spells.get(spell.spell_id) == spell

    def select(self, spell_id: str) -> bool:
        if spell_id not in self._spells:
            return False
        self.selected_id = spell_id
        return True

    def select_index(self, index: int) -> bool:
        spells = self.spells
        if 0 <= index < len(spells):
            self.selected_id = spells[index].spell_id
            return True
        return False

    @property
    def selected(self) -> Optional[Spell]:
        return self._spells.get(self.selected_id) if self.selected_id else None

    def cooldown_for(self, spell: Spell) -> Cooldown:
        return self._cooldowns[spell.spell_id]

    def tick(self, dt: float) -> None:
        for cooldown in self._cooldowns.values():
            cooldown.tick(dt)
