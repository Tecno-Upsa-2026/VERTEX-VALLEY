"""
Corredor de viaje — mapa lineal angosto entre dos nodos.
El jugador lo recorre caminando con WASD; los enemigos se acercan hacia él.
Al llegar al extremo derecho (exit), el nodo destino se carga.
"""
import random
from config import (
    TILE_GRASS, TILE_ROCK, TILE_TREE, TILE_FLOOR, TILE_SAND,
    TYPE_FOREST, TYPE_CAVE, TYPE_MOUNTAIN, TYPE_LAKE, TYPE_VILLAGE,
)

# Tiles de pared y suelo por bioma
_WALL = {
    TYPE_FOREST:   TILE_TREE,
    TYPE_CAVE:     TILE_ROCK,
    TYPE_MOUNTAIN: TILE_ROCK,
    TYPE_LAKE:     TILE_ROCK,
    TYPE_VILLAGE:  TILE_ROCK,
}
_FLOOR = {
    TYPE_FOREST:   TILE_GRASS,
    TYPE_CAVE:     TILE_FLOOR,
    TYPE_MOUNTAIN: TILE_GRASS,
    TYPE_LAKE:     TILE_SAND,
    TYPE_VILLAGE:  TILE_GRASS,
}


class TravelCorridor:
    """
    Mapa horizontal angosto:
      rows = 9  (2 pared + 5 caminable + 2 pared)
      cols = 20 + total_weight * 4
    Reutiliza la misma interfaz que TileMap para funcionar con todo el engine.
    """
    WALL_H = 2
    WALK_H = 5
    ROWS   = 9       # WALL_H*2 + WALK_H

    def __init__(self, seed: int, total_weight: int,
                 source_type: str, dest_type: str):
        length = max(22, 16 + total_weight * 4)

        self.cols        = length
        self.rows        = self.ROWS
        self.node_type   = source_type
        self.dest_type   = dest_type
        self.is_corridor = True     # flag que distingue corridors de nodos normales

        rng = random.Random(seed ^ (total_weight * 997) ^ 0xC0FFEE)

        W = _WALL.get(source_type,  TILE_ROCK)
        F = _FLOOR.get(source_type, TILE_GRASS)
        self._walk_tile = F
        self._wall_tile = W

        # ── Tiles ───────────────────────────────────────────────────────────
        self.tiles = []
        for r in range(self.ROWS):
            row = []
            for c in range(length):
                is_wall_row = (r < self.WALL_H or r >= self.ROWS - self.WALL_H)
                if is_wall_row:
                    row.append(W)
                else:
                    # Obstáculo raro para que el corredor no sea totalmente recto
                    if 5 < c < length - 5 and rng.random() < 0.03:
                        row.append(W)
                    else:
                        row.append(F)
            self.tiles.append(row)

        # Despejar entrada (columnas 0-2)
        for r in range(self.ROWS):
            for c in range(3):
                self.tiles[r][c] = F

        # Despejar salida (últimas 2 columnas)
        for r in range(self.ROWS):
            self.tiles[r][length - 1] = F
            self.tiles[r][length - 2] = F

        self.objects: dict = {}
        mid = self.ROWS // 2

        # Jugador aparece en el extremo izquierdo, centro vertical
        self.player_start = (1, mid)

        # Exit (portal destino) en el extremo derecho
        self.objects[(length - 1, mid)] = 'exit'
        self.exits = [(length - 1, mid)]

        # ── Enemigos ────────────────────────────────────────────────────────
        n_enemies = max(2, total_weight // 3 + rng.randint(1, 3))
        spacing   = max(4, (length - 10) // (n_enemies + 1))
        for i in range(n_enemies):
            for _ in range(20):
                ec = 6 + (i + 1) * spacing + rng.randint(-2, 2)
                er = self.WALL_H + rng.randint(0, self.WALK_H - 1)
                if self.is_walkable(ec, er) and (ec, er) not in self.objects:
                    self.objects[(ec, er)] = 'enemy'
                    break

        # ── Un cofre en el tercio medio ──────────────────────────────────────
        for _ in range(25):
            cc = rng.randint(length // 4, 3 * length // 4)
            cr = self.WALL_H + rng.randint(0, self.WALK_H - 1)
            if self.is_walkable(cc, cr) and (cc, cr) not in self.objects:
                self.objects[(cc, cr)] = 'chest'
                break

    # ── Interfaz igual a TileMap ─────────────────────────────────────────────

    def get_tile(self, c: int, r: int) -> int:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.tiles[r][c]
        return TILE_ROCK

    def get_object(self, c: int, r: int):
        return self.objects.get((c, r))

    def remove_object(self, c: int, r: int):
        self.objects.pop((c, r), None)

    def is_walkable(self, c: int, r: int) -> bool:
        if not (0 <= c < self.cols and 0 <= r < self.rows):
            return False
        return self.tiles[r][c] not in (TILE_ROCK, TILE_TREE)
