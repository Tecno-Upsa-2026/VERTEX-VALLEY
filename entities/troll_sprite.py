"""
Troll sprite sheet loader.
Sheet: enemies/Troll.png  —  608×992 px

Grid layout (measured from pixel content):
  Left section  (cols 0-3): x = 0, 80, 160, 240  (cell_w = 80)
  Right section (cols 4-6): x = 368, 448, 528     (cell_w = 80)
  12 rows, variable heights — see _ROW list below.

Row / animation mapping (front-facing = left-section rows):
  Row  0-2 : Idle (3 directions × 3 frames each)
  Row  3-5 : Walk (3 directions × 4 frames each)
  Row  6-7 : Attack / active
  Row  8   : Hurt
  Row 9-11 : Death sequence (progressive collapse)

Combat uses the front-facing direction (first direction, rows 0/3/6/8/9-11).
"""
import os
import pygame

# ── Column x-starts ────────────────────────────────────────────────────────────
_COL_X = [
    0,  80, 160, 240,   # left section  (cols 0-3, cell_w=80)
    368, 448, 528,      # right section (cols 4-6, cell_w=80)
]
CELL_W = 80

# ── Row definitions: (y_start, height) — derived from transparent-gap analysis ─
_ROW = [
    (0,   88),   #  0  idle-front    frame-group
    (88,  80),   #  1  idle-side     frame-group
    (168, 80),   #  2  idle-back     frame-group
    (248, 80),   #  3  walk-front    frame-group
    (328, 76),   #  4  walk-side     frame-group
    (404, 80),   #  5  walk-back     frame-group
    (484, 78),   #  6  attack phase 1
    (560, 96),   #  7  attack phase 2 (taller — arms raised)
    (656, 80),   #  8  hurt / react
    (736, 80),   #  9  death phase 1
    (816, 82),   # 10  death phase 2
    (896, 80),   # 11  death phase 3 (lying flat)
]

# ── Animation frame mappings: list of (col, row) tuples ───────────────────────
ANIMATIONS = {
    "idle":   [(0, 0), (1, 0), (2, 0)],
    "walk":   [(0, 3), (1, 3), (2, 3), (3, 3)],
    "attack": [(0, 6), (1, 6), (0, 7), (1, 7)],
    "hurt":   [(0, 8), (1, 8)],
    "death":  [(0, 9), (0, 10), (0, 11)],
}

ANIM_FPS = {
    "idle":   3,
    "walk":   6,
    "attack": 7,
    "hurt":   5,
    "death":  2,
}

# ── Module-level state ─────────────────────────────────────────────────────────
_sheet:     "pygame.Surface | None" = None
_loaded     = False
_available  = False
_cache: dict = {}   # (col, row, w, h) → scaled Surface


def _load() -> bool:
    global _sheet, _loaded, _available
    if _loaded:
        return _available
    _loaded = True
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "enemies", "Troll.png")
    )
    try:
        _sheet     = pygame.image.load(path).convert_alpha()
        _available = True
    except Exception:
        _available = False
    return _available


def available() -> bool:
    """True si el sprite sheet se cargó correctamente."""
    return _load()


def get_frame(col: int, row: int, w: int, h: int) -> "pygame.Surface | None":
    """Frame (col, row) escalado a (w, h). None si el PNG no está disponible."""
    if not _load():
        return None
    key = (col, row, w, h)
    if key not in _cache:
        rx       = _COL_X[col]
        ry, rh   = _ROW[row]
        src      = _sheet.subsurface(pygame.Rect(rx, ry, CELL_W, rh))
        _cache[key] = pygame.transform.scale(src, (w, h))
    return _cache[key]


def frame_for_t(anim: str, t: float, w: int, h: int) -> "pygame.Surface | None":
    """Frame surface para la animación `anim` en el tiempo `t`."""
    frames   = ANIMATIONS.get(anim, ANIMATIONS["idle"])
    fps      = ANIM_FPS.get(anim, 4)
    idx      = int(t * fps) % len(frames)
    col, row = frames[idx]
    return get_frame(col, row, w, h)
