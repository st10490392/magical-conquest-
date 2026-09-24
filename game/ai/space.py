"""The shared combat space enemies act in."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from game.ai.coordination import AttackCoordinator
from game.ai.projectiles import ProjectileSystem
from game.core.entity import DeathContext
from game.core.vector import Vec2

Bounds = Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)


@dataclass
class CombatSpace:
    """What an enemy may use while acting: arena bounds, the projectile
    system, attack coordination and the death context for its hits."""

    bounds: Optional[Bounds] = None
    projectiles: Optional[ProjectileSystem] = None
    coordinator: Optional[AttackCoordinator] = None
    context: Optional[DeathContext] = None
    context_id: Optional[str] = None

    def contains(self, point: Vec2, margin: float = 0.0) -> bool:
        if self.bounds is None:
            return True
        min_x, min_y, max_x, max_y = self.bounds
        return min_x + margin <= point.x <= max_x - margin and min_y + margin <= point.y <= max_y - margin

