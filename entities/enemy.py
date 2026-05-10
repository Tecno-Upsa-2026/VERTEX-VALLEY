import random
from config import ENEMY_POOL


class Enemy:
    def __init__(self, name: str, max_hp: int, attack: int, defense: int,
                 exp: int, coin_lo: int, coin_hi: int):
        self.name    = name
        self.max_hp  = max_hp
        self.hp      = max_hp
        self.attack  = attack
        self.defense = defense
        self.exp     = exp
        self.coin_lo = coin_lo
        self.coin_hi = coin_hi

    # ── combat ────────────────────────────────────────────────────────────────

    def take_damage(self, raw: int) -> int:
        dmg = max(1, raw - self.defense)
        self.hp = max(0, self.hp - dmg)
        return dmg

    def deal_damage(self) -> int:
        return self.attack + random.randint(-2, 2)

    def is_alive(self) -> bool:
        return self.hp > 0

    def loot(self) -> int:
        return random.randint(self.coin_lo, self.coin_hi)

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp


def make_enemy(node_type: str, difficulty: float = 1.0) -> Enemy:
    pool = ENEMY_POOL.get(node_type, ENEMY_POOL["forest"])
    tpl  = random.choice(pool)
    name, hp, atk, dfs, exp, clo, chi = tpl
    return Enemy(
        name    = name,
        max_hp  = max(5, int(hp  * difficulty)),
        attack  = max(2, int(atk * difficulty)),
        defense = dfs,
        exp     = max(2, int(exp * difficulty)),
        coin_lo = clo,
        coin_hi = chi,
    )
