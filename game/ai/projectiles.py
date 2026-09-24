"""Straight-line projectiles resolved through the normal combat rules.

A projectile is aimed at where the target stood at launch, so sidestepping
avoids it; if it reaches the target, ``resolve_attack`` applies dodge,
parry, block and damage at the moment of impact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from game.core.combat import Attack, AttackResult, resolve_attack
from game.core.entity import DeathContext, Entity
from game.core.vector import Vec2

PROJECTILE_RADIUS = 6.0


@dataclass
class Projectile:
    owner: Entity
    target: Entity
    attack: Attack
    position: Vec2
    direction: Vec2
    speed: float
    max_distance: float
    travelled: float = 0.0
    alive: bool = True


@dataclass(frozen=True)
class ProjectileHit:
    projectile: Projectile
    result: AttackResult


def _distance_to_segment(point: Vec2, start: Vec2, end: Vec2) -> float:
    segment = end - start
    length_sq = segment.x * segment.x + segment.y * segment.y
    if length_sq == 0:
        return point.distance_to(start)
    t = ((point.x - start.x) * segment.x + (point.y - start.y) * segment.y) / length_sq
    t = max(0.0, min(1.0, t))
    return point.distance_to(start + segment * t)


class ProjectileSystem:
    def __init__(self) -> None:
        self.projectiles: List[Projectile] = []

    def launch(self, owner: Entity, target: Entity, attack: Attack, speed: float) -> Projectile:
        direction = (target.position - owner.position).normalized()
        if direction.length() == 0:
            direction = Vec2(1.0, 0.0)
        projectile = Projectile(owner, target, attack, owner.position, direction, speed, attack.reach * 1.3)
        self.projectiles.append(projectile)
        return projectile

    def update(
        self,
        dt: float,
        world_time: Optional[float] = None,
        context: Optional[DeathContext] = None,
        context_id: Optional[str] = None,
    ) -> List[ProjectileHit]:
        hits: List[ProjectileHit] = []
        for projectile in self.projectiles:
            step = projectile.speed * dt
            start = projectile.position
            end = start + projectile.direction * step
            projectile.position = end
            projectile.travelled += step
            target = projectile.target
            if target.is_alive:
                # Segment test so fast projectiles cannot tunnel through.
                if _distance_to_segment(target.position, start, end) <= target.size / 2 + PROJECTILE_RADIUS:
                    projectile.alive = False
                    result = resolve_attack(
                        projectile.owner, target, projectile.attack, check_range=False,
                        world_time=world_time, context=context, context_id=context_id,
                    )
                    hits.append(ProjectileHit(projectile, result))
                    continue
            if projectile.travelled >= projectile.max_distance:
                projectile.alive = False
        if hits or any(not p.alive for p in self.projectiles):
            self.projectiles = [p for p in self.projectiles if p.alive]
        return hits

    def clear(self) -> None:
        self.projectiles.clear()
