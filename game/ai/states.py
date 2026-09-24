"""Enemy combat states."""

from __future__ import annotations

from enum import Enum


class AIState(str, Enum):
    IDLE = "idle"  # no valid target in perception
    ALERT = "alert"  # just noticed a target; brief reaction delay
    APPROACH = "approach"  # closing distance
    POSITION = "position"  # adjusting/holding at a preferred distance
    TELEGRAPH = "telegraph"  # winding up an attack: the player's cue to react
    ATTACK = "attack"  # the attack resolved (or a projectile launched) this tick
    RECOVER = "recover"  # committed follow-through: the punish window
    RETREAT = "retreat"  # backing away to regain preferred distance
    STAGGERED = "staggered"  # interrupted, e.g. after being parried
    DEAD = "dead"

    # MC-001/MC-002 names, kept as aliases so existing code keeps working.
    CHASING = "approach"
    WINDUP = "telegraph"
    ATTACKING = "attack"
