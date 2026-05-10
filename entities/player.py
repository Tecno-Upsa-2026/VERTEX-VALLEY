import random
from config import ITEMS, CHARACTERS


class Player:
    def __init__(self, x: int, y: int, character: dict | None = None):
        self.x = x
        self.y = y
        # ── Character customisation ───────────────────────────────────────────
        char = character or CHARACTERS[0]
        self.char_id   = char["id"]
        self.shirt_col = char["shirt"]
        self.hair_col  = char["hair"]
        self.pants_col = char.get("pants", (35, 44, 112))
        self.heal_mul  = char.get("heal_mul", 1.0)
        # Stats (from character template)
        self.max_hp  = char["hp"]
        self.hp      = char["hp"]
        self.attack  = char["attack"]
        self.defense = char["defense"]
        self.level   = 1
        self.exp     = 0
        self.exp_next = 20
        self.coins   = 0
        # Equipment
        self.weapon: str | None = None
        self.shield: str | None = None
        # Bag: item_name -> quantity
        self.inventory: dict[str, int] = {}
        # Animation state
        self.facing    = (0, 1)
        self.is_moving = False

    # ── movement ──────────────────────────────────────────────────────────────

    def move(self, dx: int, dy: int, tile_map) -> bool:
        nx, ny = self.x + dx, self.y + dy
        if tile_map.is_walkable(nx, ny):
            self.x, self.y = nx, ny
            if dx != 0 or dy != 0:
                self.facing = (dx, dy)
            self.is_moving = True
            return True
        self.is_moving = False
        return False

    # ── combat interface ──────────────────────────────────────────────────────

    def deal_damage(self) -> int:
        bonus = 0
        if self.weapon and self.weapon in ITEMS:
            bonus = ITEMS[self.weapon]["bonus"]
        return self.attack + bonus + random.randint(-1, 3)

    def take_damage(self, raw: int, defending: bool = False) -> int:
        reduction = self.defense * (2 if defending else 1)
        dmg = max(1, raw - reduction)
        self.hp = max(0, self.hp - dmg)
        return dmg

    def heal(self, amount: int):
        actual = int(amount * self.heal_mul)
        self.hp = min(self.max_hp, self.hp + actual)

    def is_alive(self) -> bool:
        return self.hp > 0

    # ── levelling ─────────────────────────────────────────────────────────────

    def gain_exp(self, amount: int) -> bool:
        self.exp += amount
        leveled = False
        while self.exp >= self.exp_next:
            self.exp -= self.exp_next
            self._level_up()
            leveled = True
        return leveled

    def _level_up(self):
        self.level   += 1
        self.max_hp  += 6
        self.hp       = min(self.hp + 6, self.max_hp)
        self.attack  += 2
        self.defense += 1
        self.exp_next = int(self.exp_next * 1.5)

    # ── inventory ─────────────────────────────────────────────────────────────

    def add_item(self, name: str):
        self.inventory[name] = self.inventory.get(name, 0) + 1

    def use_item(self, name: str) -> int | bool:
        """Returns damage if combat item, True on success, False on failure."""
        if self.inventory.get(name, 0) <= 0:
            return False
        item = ITEMS.get(name)
        if item is None:
            return False
        if item["type"] == "potion":
            self.heal(item["bonus"])
        elif item["type"] == "weapon":
            self.weapon = name
        elif item["type"] == "shield":
            self.shield = name
            self.defense = 3 + item["bonus"]
        elif item["type"] == "maxhp":
            self.max_hp += item["bonus"]
            self.hp = min(self.hp + item["bonus"], self.max_hp)
        elif item["type"] == "combat":
            self.inventory[name] -= 1
            if self.inventory[name] == 0:
                del self.inventory[name]
            return item["bonus"]   # return damage value

        self.inventory[name] -= 1
        if self.inventory[name] == 0:
            del self.inventory[name]
        return True

    def buy(self, name: str) -> bool:
        item = ITEMS.get(name)
        if item and self.coins >= item["cost"]:
            self.coins -= item["cost"]
            self.add_item(name)
            return True
        return False

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp

    @property
    def exp_ratio(self) -> float:
        return self.exp / self.exp_next
