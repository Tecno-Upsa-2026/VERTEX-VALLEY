"""
Autómata Finito Determinista (AFD) que controla los estados válidos del combate.

Estados:
  idle → player_turn ↔ enemy_turn → victory | defeat | fled

El AFD garantiza que nunca se ejecute una acción fuera de turno y que sólo
se llegue a un estado terminal desde la transición correcta.
"""


class S:
    """Estado del autómata."""
    IDLE        = "idle"
    PLAYER_TURN = "player_turn"
    ENEMY_TURN  = "enemy_turn"
    VICTORY     = "victory"
    DEFEAT      = "defeat"
    FLED        = "fled"


class A:
    """Símbolos del alfabeto (acciones del sistema)."""
    START        = "start"
    ATTACK       = "attack"
    DEFEND       = "defend"
    FLEE         = "flee"
    ENEMY_ATTACK = "enemy_attack"
    ENEMY_DIED   = "enemy_died"
    PLAYER_DIED  = "player_died"
    FLED_OK      = "fled_ok"
    FLED_FAIL    = "fled_fail"


# δ: (estado, acción) → estado_siguiente
DELTA: dict[tuple, str] = {
    (S.IDLE,        A.START):        S.PLAYER_TURN,

    (S.PLAYER_TURN, A.ATTACK):       S.ENEMY_TURN,
    (S.PLAYER_TURN, A.DEFEND):       S.ENEMY_TURN,
    (S.PLAYER_TURN, A.FLEE):         S.ENEMY_TURN,
    (S.PLAYER_TURN, A.ENEMY_DIED):   S.VICTORY,

    (S.ENEMY_TURN,  A.ENEMY_ATTACK): S.PLAYER_TURN,
    (S.ENEMY_TURN,  A.PLAYER_DIED):  S.DEFEAT,
    (S.ENEMY_TURN,  A.FLED_OK):      S.FLED,
    (S.ENEMY_TURN,  A.FLED_FAIL):    S.PLAYER_TURN,
}

ACCEPTING = {S.VICTORY, S.DEFEAT, S.FLED}

PLAYER_ACTIONS = {A.ATTACK, A.DEFEND, A.FLEE}


class CombatAFD:
    """Instance of the AFD for one combat encounter."""

    def __init__(self):
        self.state   = S.IDLE
        self.history: list[tuple] = []   # (prev, action, next)

    # ── transitions ───────────────────────────────────────────────────────────

    def transition(self, action: str) -> str:
        key = (self.state, action)
        if key not in DELTA:
            raise ValueError(
                f"AFD: transición inválida ({self.state!r}, {action!r})"
            )
        next_state = DELTA[key]
        self.history.append((self.state, action, next_state))
        self.state = next_state
        return next_state

    def start(self):
        return self.transition(A.START)

    # ── queries ───────────────────────────────────────────────────────────────

    def valid_actions(self) -> list[str]:
        return [act for (st, act) in DELTA if st == self.state]

    def is_finished(self) -> bool:
        return self.state in ACCEPTING

    def is_player_turn(self) -> bool:
        return self.state == S.PLAYER_TURN

    def is_enemy_turn(self) -> bool:
        return self.state == S.ENEMY_TURN
