"""
Procedural 2-D tile map for a single graph node.
Deterministic: same (seed, node_id, node_type) always produces the same map.
"""
import random
from config import (
    TILE_GRASS, TILE_WALL, TILE_WATER, TILE_TREE,
    TILE_ROCK, TILE_FLOOR, TILE_SAND,
    MAP_COLS, MAP_ROWS,
    TYPE_VILLAGE, TYPE_FOREST, TYPE_CAVE, TYPE_MOUNTAIN, TYPE_LAKE,
)


class TileMap:
    def __init__(self, seed: int, node_id: int, node_type: str,
                 cols: int = MAP_COLS, rows: int = MAP_ROWS):
        self.cols      = cols
        self.rows      = rows
        self.node_type = node_type
        self.rng       = random.Random(seed * 9973 + node_id * 31 + 7)
        self.tiles     = [[TILE_GRASS] * cols for _ in range(rows)]
        self.objects: dict[tuple, str] = {}   # (col, row) -> type string
        self.player_start = (cols // 2, rows // 2)
        self.exits: list[tuple] = []
        self._generate()

    # ── public API ───────────────────────────────────────────────────────────

    def get_tile(self, c: int, r: int) -> int:
        if 0 <= c < self.cols and 0 <= r < self.rows:
            return self.tiles[r][c]
        return TILE_ROCK

    def get_object(self, c: int, r: int) -> str | None:
        return self.objects.get((c, r))

    def remove_object(self, c: int, r: int):
        self.objects.pop((c, r), None)

    def is_walkable(self, c: int, r: int) -> bool:
        if not (0 <= c < self.cols and 0 <= r < self.rows):
            return False
        return self.tiles[r][c] not in (TILE_WALL, TILE_ROCK, TILE_WATER, TILE_TREE)

    # ── generation dispatcher ─────────────────────────────────────────────────

    def _generate(self):
        dispatch = {
            TYPE_VILLAGE:  self._gen_village,
            TYPE_FOREST:   self._gen_forest,
            TYPE_CAVE:     self._gen_cave,
            TYPE_MOUNTAIN: self._gen_mountain,
            TYPE_LAKE:     self._gen_lake,
        }
        dispatch.get(self.node_type, self._gen_forest)()
        self._add_exits()
        self._add_chests()
        self._add_enemies()

    # ── biome generators ─────────────────────────────────────────────────────

    def _gen_village(self):
        cx, cy = self.cols // 2, self.rows // 2

        # ── Base: grass everywhere ────────────────────────────────────────────
        for r in range(self.rows):
            for c in range(self.cols):
                self.tiles[r][c] = TILE_GRASS

        # ── Main sand cross-roads ─────────────────────────────────────────────
        for c in range(self.cols):
            for dr in range(-1, 2):
                self._safe_set(cy+dr, c, TILE_SAND)
        for r in range(self.rows):
            for dc in range(-1, 2):
                self._safe_set(r, cx+dc, TILE_SAND)

        # ── Pozo central (3×3 de piedra con agua) ────────────────────────────
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                self._safe_set(cy+dr, cx+dc, TILE_ROCK if abs(dr)+abs(dc)==2 else TILE_WATER)
        self.objects[(cx, cy)] = "well"

        # ── Casas con variedad ────────────────────────────────────────────────
        house_positions = [
            # (bx, by, bw, bh, door_side)
            (cx-18, cy-10, 8, 6, 'S'),   # noroeste grande
            (cx+10, cy-10, 7, 5, 'S'),   # noreste
            (cx-16, cy+5,  6, 5, 'N'),   # suroeste
            (cx+11, cy+5,  8, 6, 'N'),   # sureste grande
            (cx-22, cy-3,  5, 4, 'E'),   # oeste
            (cx+17, cy-2,  5, 4, 'W'),   # este
            (cx-6,  cy-14, 6, 4, 'S'),   # norte centro
            (cx-5,  cy+10, 6, 4, 'N'),   # sur centro
        ]
        for bx, by, bw, bh, door_side in house_positions:
            bx = max(3, min(self.cols-bw-3, bx))
            by = max(3, min(self.rows-bh-3, by))
            # Walls
            for r in range(by, by+bh):
                for c in range(bx, bx+bw):
                    self.tiles[r][c] = TILE_WALL
            # Interior floor
            for r in range(by+1, by+bh-1):
                for c in range(bx+1, bx+bw-1):
                    self.tiles[r][c] = TILE_FLOOR
            # Door
            if door_side == 'S':
                self.tiles[by+bh-1][bx+bw//2] = TILE_FLOOR
                self.tiles[by+bh  ][bx+bw//2] = TILE_SAND if 0<=by+bh<self.rows else TILE_SAND
            elif door_side == 'N':
                self.tiles[by][bx+bw//2] = TILE_FLOOR
            elif door_side == 'E':
                self.tiles[by+bh//2][bx+bw-1] = TILE_FLOOR
            elif door_side == 'W':
                self.tiles[by+bh//2][bx] = TILE_FLOOR

        # ── Jardines de flores en esquinas ───────────────────────────────────
        for gx, gy in [(cx-8, cy-8), (cx+5, cy+4), (cx-9, cy+4), (cx+4, cy-8)]:
            gx = max(0, min(self.cols-3, gx))
            gy = max(0, min(self.rows-3, gy))
            if self.is_walkable(gx, gy):
                self.objects[(gx, gy)] = "garden"

        # ── Tienda (edificio especial con $) ─────────────────────────────────
        sx_, sy_ = cx+3, cy-6
        sx_ = max(3, min(self.cols-9, sx_))
        sy_ = max(3, min(self.rows-7, sy_))
        for r in range(sy_, sy_+5):
            for c in range(sx_, sx_+7):
                self.tiles[r][c] = TILE_WALL
        for r in range(sy_+1, sy_+4):
            for c in range(sx_+1, sx_+6):
                self.tiles[r][c] = TILE_FLOOR
        self.tiles[sy_+4][sx_+3] = TILE_FLOOR  # door
        self.objects[(sx_+3, sy_+2)] = "shop"

        # ── NPCs ─────────────────────────────────────────────────────────────
        npc_spots = [(cx-4, cy-4), (cx+4, cy+3), (cx-3, cy+4), (cx+5, cy-3)]
        npc_types = ["npc_elder", "npc", "npc", "npc_guard"]
        for (nc, nr), ntype in zip(npc_spots, npc_types):
            nc2, nr2 = max(0,min(self.cols-1,nc)), max(0,min(self.rows-1,nr))
            if self.is_walkable(nc2, nr2) and (nc2,nr2) not in self.objects:
                self.objects[(nc2, nr2)] = ntype

        self.player_start = (cx - 4, cy + 4)

    def _gen_forest(self):
        # Dense trees — two winding paths through the forest
        for r in range(self.rows):
            for c in range(self.cols):
                if self.rng.random() < 0.40:
                    self.tiles[r][c] = TILE_TREE
        for path_col_start in [self.cols // 5, self.cols * 3 // 5]:
            pc = path_col_start
            for r in range(self.rows):
                for dc in range(4):
                    nc = max(0, min(self.cols - 1, pc + dc))
                    self.tiles[r][nc] = TILE_GRASS
                pc += self.rng.randint(-1, 1)
                pc = max(2, min(self.cols - 6, pc))
        self.player_start = (self.cols // 5 + 2, self.rows - 4)

    def _gen_cave(self):
        # Cellular automata cave
        for r in range(self.rows):
            for c in range(self.cols):
                self.tiles[r][c] = TILE_ROCK if self.rng.random() < 0.46 else TILE_FLOOR
        for _ in range(5):
            nt = [row[:] for row in self.tiles]
            for r in range(1, self.rows - 1):
                for c in range(1, self.cols - 1):
                    walls = sum(
                        1 for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                        if self.tiles[r + dr][c + dc] == TILE_ROCK
                    )
                    nt[r][c] = TILE_ROCK if walls > 4 else TILE_FLOOR
            self.tiles = nt
        # Solid borders
        for r in range(self.rows):
            self.tiles[r][0] = self.tiles[r][self.cols - 1] = TILE_ROCK
        for c in range(self.cols):
            self.tiles[0][c] = self.tiles[self.rows - 1][c] = TILE_ROCK
        # Clear player spawn
        cx, cy = self.cols // 2, self.rows // 2
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                nr, nc = cy + dr, cx + dc
                if 1 <= nr < self.rows - 1 and 1 <= nc < self.cols - 1:
                    self.tiles[nr][nc] = TILE_FLOOR
        self.player_start = (cx, cy)

    def _gen_mountain(self):
        for r in range(self.rows):
            for c in range(self.cols):
                self.tiles[r][c] = TILE_ROCK if self.rng.random() < 0.32 else TILE_GRASS
        # Rocky ridge
        ridge = self.cols // 2
        for r in range(self.rows):
            for dc in range(-3, 4):
                nc = max(0, min(self.cols - 1, ridge + dc))
                self.tiles[r][nc] = TILE_ROCK
            ridge += self.rng.randint(-1, 1)
            ridge = max(4, min(self.cols - 5, ridge))
        # Clear passage on left
        for r in range(self.rows):
            self.tiles[r][2] = TILE_GRASS
            self.tiles[r][3] = TILE_GRASS
        self.player_start = (3, self.rows - 3)

    def _gen_lake(self):
        cx, cy = self.cols // 2, self.rows // 2
        rx, ry = self.cols // 3, self.rows // 3
        for r in range(self.rows):
            for c in range(self.cols):
                dx, dy = (c - cx) / rx, (r - cy) / ry
                if dx * dx + dy * dy < 1.0:
                    self.tiles[r][c] = TILE_WATER
                elif self.rng.random() < 0.08:
                    self.tiles[r][c] = TILE_SAND
        # Shore path
        for r in range(self.rows):
            self.tiles[r][1] = TILE_GRASS
            self.tiles[r][2] = TILE_GRASS
        self.player_start = (2, 2)

    # ── exits & objects ───────────────────────────────────────────────────────

    def _add_exits(self):
        candidates = [
            (0,             self.rows // 2),
            (self.cols - 1, self.rows // 2),
            (self.cols // 2, self.rows - 1),
            (self.cols // 2, 0),
        ]
        exits = self.rng.sample(candidates, k=3)
        for ex, ey in exits:
            self.objects[(ex, ey)] = "exit"
            # Carve a wide walkable corridor to the exit so it's reachable
            t = TILE_FLOOR if self.node_type == TYPE_CAVE else TILE_GRASS
            if ex == 0:
                for c in range(6):
                    self._safe_set(ey,     c, t)
                    self._safe_set(ey - 1, c, t)
                    self._safe_set(ey + 1, c, t)
            elif ex == self.cols - 1:
                for c in range(self.cols - 6, self.cols):
                    self._safe_set(ey,     c, t)
                    self._safe_set(ey - 1, c, t)
                    self._safe_set(ey + 1, c, t)
            elif ey == self.rows - 1:
                for r in range(self.rows - 6, self.rows):
                    self._safe_set(r, ex,     t)
                    self._safe_set(r, ex - 1, t)
                    self._safe_set(r, ex + 1, t)
            else:
                for r in range(6):
                    self._safe_set(r, ex,     t)
                    self._safe_set(r, ex - 1, t)
                    self._safe_set(r, ex + 1, t)
        self.exits = exits

    def _add_chests(self):
        n = self.rng.randint(3, 6)   # more chests in larger map
        for _ in range(n):
            for _ in range(40):
                c = self.rng.randint(4, self.cols - 5)
                r = self.rng.randint(4, self.rows - 5)
                if (c, r) not in self.objects and self.is_walkable(c, r):
                    self.objects[(c, r)] = "chest"
                    break

    def _add_enemies(self):
        if self.node_type == TYPE_VILLAGE:
            return
        n = {"forest": 5, "cave": 6, "mountain": 6, "lake": 4}.get(self.node_type, 5)
        count = self.rng.randint(max(2, n - 1), n + 2)
        placed = 0
        for _ in range(80):
            c = self.rng.randint(4, self.cols - 5)
            r = self.rng.randint(4, self.rows - 5)
            px, py = self.player_start
            # Minimum 5 tiles away from spawn so player isn't instantly attacked
            if abs(c - px) + abs(r - py) < 5:
                continue
            if (c, r) not in self.objects and self.is_walkable(c, r):
                self.objects[(c, r)] = "enemy"
                placed += 1
                if placed >= count:
                    break

    def _safe_set(self, r: int, c: int, tile: int):
        if 0 <= r < self.rows and 0 <= c < self.cols:
            self.tiles[r][c] = tile
