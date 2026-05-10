"""
Combat system driven by the AFD in core/afd.py.
All state transitions are validated by the automaton.
"""
import random
from core.afd import CombatAFD, A, S


class CombatResult:
    ONGOING = "ongoing"
    VICTORY = "victory"
    DEFEAT  = "defeat"
    FLED    = "fled"


class LogLine:
    def __init__(self, text: str, color: tuple):
        self.text  = text
        self.color = color


class CombatLog:
    MAX = 9

    def __init__(self):
        self.lines: list[LogLine] = []

    def add(self, text: str, color: tuple = (210, 208, 200)):
        self.lines.append(LogLine(text, color))
        if len(self.lines) > self.MAX:
            self.lines.pop(0)


class CombatSystem:
    def __init__(self, player, enemy):
        self.player   = player
        self.enemy    = enemy
        self.afd      = CombatAFD()
        self.log      = CombatLog()
        self.result   = CombatResult.ONGOING
        self._defending = False
        self._pending_flee = False
        self._last_player_dmg = 0
        self._last_enemy_dmg  = 0

        self.afd.start()
        self.log.add(f">> {enemy.name} aparece! <<", (240, 140,  90))
        self.log.add("Es tu turno - elige una accion.", (180, 180, 180))

    # ── player actions ────────────────────────────────────────────────────────

    def player_attack(self):
        if not self.afd.is_player_turn():
            return
        self._defending = False
        raw = self.player.deal_damage()
        dmg = self.enemy.take_damage(raw)
        self._last_player_dmg = dmg
        self.log.add(f"Atacas a {self.enemy.name}: -{dmg} HP.", (100, 220, 140))

        if not self.enemy.is_alive():
            self.afd.transition(A.ENEMY_DIED)
            self._resolve_victory()
        else:
            self.afd.transition(A.ATTACK)
            self._enemy_turn()

    def player_defend(self):
        if not self.afd.is_player_turn():
            return
        self._defending = True
        self.log.add("Te pones en guardia - defensa doble este turno.", (100, 150, 255))
        self.afd.transition(A.DEFEND)
        self._enemy_turn()

    def player_flee(self):
        if not self.afd.is_player_turn():
            return
        self.log.add("Intentas escapar...", (220, 200,  80))
        self.afd.transition(A.FLEE)
        if random.random() < 0.5:
            self.afd.transition(A.FLED_OK)
            self.log.add("Huyes con exito!", (255, 220,  50))
            self.result = CombatResult.FLED
        else:
            self.afd.transition(A.FLED_FAIL)
            self.log.add("No puedes escapar!", (220,  80,  80))
            self._enemy_turn()

    # ── enemy turn ────────────────────────────────────────────────────────────

    def _enemy_turn(self):
        raw = self.enemy.deal_damage()
        dmg = self.player.take_damage(raw, defending=self._defending)
        self._last_enemy_dmg = dmg

        if self._defending:
            self.log.add(
                f"{self.enemy.name} ataca - bloqueas parte: -{dmg} HP.",
                (220, 130,  80)
            )
        else:
            self.log.add(f"{self.enemy.name} te golpea: -{dmg} HP.", (220, 80, 80))

        self._defending = False

        if not self.player.is_alive():
            self.afd.transition(A.PLAYER_DIED)
            self.result = CombatResult.DEFEAT
            self.log.add("Has caido en batalla...", (190, 40, 40))
        else:
            self.afd.transition(A.ENEMY_ATTACK)
            self.log.add("Tu turno.", (180, 178, 170))

    def _resolve_victory(self):
        coins  = self.enemy.loot()
        leveled = self.player.gain_exp(self.enemy.exp)
        self.player.coins += coins
        self.result = CombatResult.VICTORY
        self.log.add(
            f"VICTORIA! +{self.enemy.exp} EXP  +{coins} monedas.",
            (255, 215,  50)
        )
        if leveled:
            self.log.add(
                f"Nivel {self.player.level}! Stats aumentados.",
                (100, 255, 200)
            )

    # ── state queries ─────────────────────────────────────────────────────────

    def is_finished(self) -> bool:
        return self.afd.is_finished()

    def afd_state(self) -> str:
        return self.afd.state
