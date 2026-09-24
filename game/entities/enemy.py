"""Enemies: shared entity + a pluggable behaviour + the attack lifecycle.

``Enemy.update`` owns only what every enemy has in common:

    DEAD / STAGGERED  ->  attack lifecycle (TELEGRAPH -> ATTACK -> RECOVER)
    -> perception (IDLE / ALERT)  ->  behaviour decision (APPROACH, POSITION,
    RETREAT, or start an attack)

What an enemy *wants* comes from its ``Behavior`` (see ``game.ai.behaviors``).
Damage always goes through ``game.core.combat``. The AI works in abstract
world units; the Pygame layer only draws the result.
"""

from __future__ import annotations

from typing import Optional, Union

from game.ai.attacks import AttackLifecycle, AttackPhase, EnemyAttack
from game.ai.behaviors import Behavior, Decision, MeleeBehavior
from game.ai.coordination import AttackCoordinator
from game.ai.perception import PerceptionConfig, perceive
from game.ai.space import CombatSpace
from game.ai.states import AIState
from game.core.combat import Attack, AttackOutcome, AttackResult, Cooldown, DamageType, attack_interval, resolve_attack
from game.core.entity import Entity
from game.core.stats import Stats
from game.core.vector import Vec2
from game.progression.growth import StatGrowth

# MC-001/MC-002 name for the enemy state enum.
EnemyState = AIState

GOBLIN_CLAW = Attack(
    name="claw",
    damage_type=DamageType.PHYSICAL,
    base_power=5.0,
    scaling=0.8,
    reach=50.0,
    cooldown=1.0,
)

# Telegraph before each claw so parry/dodge timing can be learned.
# PROTOTYPE VALUE - NON-FINAL.
GOBLIN_WINDUP = 0.35

GOBLIN_GROWTH = StatGrowth(
    max_health=10.0,
    max_mana=0.0,
    max_stamina=0.0,
    physical_strength=1.5,
    magic_power=0.0,
    durability=1.0,
    magic_resistance=1.0,
    agility=0.5,
)


class Enemy(Entity):
    def __init__(
        self,
        name: str,
        stats: Stats,
        attack: Union[Attack, EnemyAttack],
        level: int = 1,
        aggro_range: float = 400.0,
        xp_reward: int = 50,
        entity_id: Optional[str] = None,
        position: Optional[Vec2] = None,
        windup: float = 0.0,
        *,
        recovery: float = 0.0,
        behavior: Optional[Behavior] = None,
        perception: Optional[PerceptionConfig] = None,
        alert_time: float = 0.0,
        parry_stagger: float = 0.0,
        archetype: str = "basic",
        size: float = 40.0,
    ) -> None:
        super().__init__(name, stats, level=level, entity_id=entity_id, position=position, size=size)
        if windup < 0 or alert_time < 0 or parry_stagger < 0:
            raise ValueError("windup, alert_time and parry_stagger must not be negative")
        if isinstance(attack, EnemyAttack):
            self.attack_profile = attack
        else:
            self.attack_profile = EnemyAttack(attack, telegraph=windup, recovery=recovery)
        self.behavior = behavior or MeleeBehavior(spacing=0.9)
        self.perception = perception or PerceptionConfig(aggro_range, aggro_range)
        self.alert_time = alert_time
        self.parry_stagger = parry_stagger
        self.archetype = archetype
        self.xp_reward = xp_reward

        self.state = AIState.IDLE
        self.attack_cooldown = Cooldown()
        self.lifecycle = AttackLifecycle()
        self.engaged = False
        self.alert_remaining = 0.0
        self.stagger_remaining = 0.0
        self.aim_point: Optional[Vec2] = None
        self.last_result: Optional[AttackResult] = None
        self._token: Optional[AttackCoordinator] = None

    # ------------------------------------------------------------ properties
    @property
    def attack(self) -> Attack:
        return self.attack_profile.attack

    @property
    def windup(self) -> float:
        return self.attack_profile.telegraph

    @property
    def windup_remaining(self) -> float:
        return self.lifecycle.remaining if self.lifecycle.phase is AttackPhase.TELEGRAPH else 0.0

    @property
    def telegraph_progress(self) -> float:
        """0 at wind-up start, 1 at release; 0 when not winding up."""
        if self.lifecycle.phase is not AttackPhase.TELEGRAPH or self.windup <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - self.lifecycle.remaining / self.windup))

    @property
    def aggro_range(self) -> float:
        return self.perception.detection_range

    # ---------------------------------------------------------------- update
    def update(
        self,
        dt: float,
        target: Optional[Entity],
        world_time: Optional[float] = None,
        space: Optional[CombatSpace] = None,
    ) -> Optional[AttackResult]:
        """Advance the AI by ``dt`` seconds.

        Returns the ``AttackResult`` when a melee attack (or a ranged attack
        without a projectile system) resolves this tick, else ``None``.
        Projectile hits are reported by the ``ProjectileSystem`` instead.
        """
        self.attack_cooldown.tick(dt)
        self.defense.tick(dt)
        if not self.is_alive:
            self._abort_attack()
            self.state = AIState.DEAD
            return None
        if self.stagger_remaining > 0:
            self.stagger_remaining = max(0.0, self.stagger_remaining - dt)
            if self.stagger_remaining > 0:
                self.state = AIState.STAGGERED
                return None

        was_engaged = self.engaged
        percept = perceive(self, target, self.perception, was_engaged)
        self.engaged = percept.engaged

        lifecycle = self.lifecycle
        if lifecycle.phase is AttackPhase.TELEGRAPH:
            if not percept.valid:
                self._abort_attack()
                self.state = AIState.IDLE
                return None
            motion = self.behavior.telegraph_motion(self, percept)
            if motion is not None:
                self._move(motion, dt, space)
            if not lifecycle.tick_telegraph(dt):
                self.state = AIState.TELEGRAPH
                return None
            return self._strike(percept, world_time, space)
        if lifecycle.phase is AttackPhase.RECOVERY:
            if not lifecycle.tick_recovery(dt):
                self.state = AIState.RECOVER
                return None

        if not percept.engaged:
            self.alert_remaining = 0.0
            self.state = AIState.IDLE
            return None
        if not was_engaged:
            self.alert_remaining = self.alert_time
        if self.alert_remaining > 0:
            self.alert_remaining = max(0.0, self.alert_remaining - dt)
            self.state = AIState.ALERT
            return None

        decision = self.behavior.decide(self, percept, space)
        if decision.attack:
            if self._begin_attack(percept, space):
                if self.windup <= 0:
                    return self._strike(percept, world_time, space)
                self.state = AIState.TELEGRAPH
                return None
            decision = Decision(AIState.POSITION)  # waiting for cooldown or a token
        self._move(decision, dt, space)
        self.state = decision.state
        return None

    # ---------------------------------------------------------------- pieces
    def _begin_attack(self, percept, space: Optional[CombatSpace]) -> bool:
        if not self.attack_cooldown.ready:
            return False
        coordinator = space.coordinator if space else None
        if self.attack_profile.is_melee and coordinator is not None:
            if not coordinator.try_acquire(self):
                return False
            self._token = coordinator
        self.lifecycle.start(self.attack_profile)
        self.behavior.on_telegraph_start(self, percept)
        return True

    def _strike(self, percept, world_time: Optional[float], space: Optional[CombatSpace]) -> Optional[AttackResult]:
        profile = self.lifecycle.current
        self.behavior.before_strike(self, percept)
        if space is not None and space.bounds is not None:
            self.position = self._clamp(self.position, space)
        self.attack_cooldown.start(attack_interval(profile.attack, self.stats.agility))
        self.state = AIState.ATTACK
        context = space.context if space else None
        context_id = space.context_id if space else None
        result: Optional[AttackResult] = None
        if not profile.is_melee and space is not None and space.projectiles is not None:
            space.projectiles.launch(self, percept.target, profile.attack, profile.projectile_speed)
        else:
            result = resolve_attack(
                self, percept.target, profile.attack, world_time=world_time, context=context, context_id=context_id
            )
        self.lifecycle.begin_recovery()
        self._release_token()
        self.aim_point = None
        self.last_result = result
        if result is not None and result.outcome is AttackOutcome.PARRIED and profile.is_melee:
            self.stagger(self.parry_stagger)
        return result

    def alert(self) -> None:
        """Become engaged without seeing the target (e.g. a group member
        spotted it). The normal alert delay still applies."""
        if not self.engaged and self.is_alive:
            self.engaged = True
            self.alert_remaining = self.alert_time

    def stagger(self, seconds: float) -> None:
        """Interrupt the enemy (e.g. after being parried). Cancels any attack."""
        if seconds <= 0:
            return
        self._abort_attack()
        self.stagger_remaining = max(self.stagger_remaining, seconds)
        self.state = AIState.STAGGERED

    def _abort_attack(self) -> None:
        self.lifecycle.cancel()
        self.aim_point = None
        self._release_token()

    def _release_token(self) -> None:
        if self._token is not None:
            self._token.release(self)
            self._token = None

    def _move(self, decision: Decision, dt: float, space: Optional[CombatSpace]) -> None:
        step = min(self.stats.speed * decision.speed_scale * dt, max(0.0, decision.max_step))
        if step <= 0 or decision.direction.length() == 0:
            return
        self.position = self.position + decision.direction.normalized() * step
        if space is not None and space.bounds is not None:
            self.position = self._clamp(self.position, space)

    def _clamp(self, position: Vec2, space: CombatSpace) -> Vec2:
        min_x, min_y, max_x, max_y = space.bounds
        half = self.size / 2
        return position.clamped(min_x + half, min_y + half, max_x - half, max_y - half)


def create_goblin(level: int = 1, position: Optional[Vec2] = None) -> Enemy:
    """The MC-001/MC-002 test enemy, scaled by level through stat growth."""
    stats = Stats(
        max_health=60.0,
        max_mana=0.0,
        max_stamina=0.0,
        physical_strength=6.0,
        magic_power=0.0,
        magic_resistance=0.0,
        durability=2.0,
        speed=130.0,
        agility=0.0,
    )
    GOBLIN_GROWTH.apply(stats, level - 1)
    return Enemy(
        "Goblin",
        stats,
        GOBLIN_CLAW,
        level=level,
        aggro_range=500.0,
        windup=GOBLIN_WINDUP,
        xp_reward=40 + 15 * (level - 1),
        position=position,
        archetype="goblin",
    )
