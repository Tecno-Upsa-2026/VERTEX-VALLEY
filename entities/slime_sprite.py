"""
Slime sprite sheet loader.
Sheet: enemies/Slime creature.png  —  398×1392 px

Grid: 4 columns × 22 row-bands (cell_w = 99 px each).
Each band is one animation direction (4 frames per band across the 4 cols).

Animation groups (each = 4 direction bands, combat uses band-group[0] = front):
  walking : bands  0-3
  spawn   : bands  4-7
  idle    : bands  8-11
  attack  : bands 12-15
  hurt    : bands 16-17
  kill    : bands 18-21
"""
import os
import pygame

# ── Column x-starts ────────────────────────────────────────────────────────────
CELL_W  = 99          # 4 × 99 = 396 ≤ 398 px sheet width
_COL_X  = [0, 99, 198, 297]

# ── Band definitions: (y_start, height) — measured from transparent-gap analysis
_BAND = [
    # walking (bands 0-3)
    (8,    41), (72,   40), (136,  41), (204,  37),
    # spawn   (bands 4-7)
    (268,  37), (328,  41), (376,  42), (444,  37),
    # idle    (bands 8-11)
    (508,  37), (565,  43), (629,  43), (697,  39),
    # attack  (bands 12-15)
    (762,  39), (809,  55), (873,  55), (930,  62),
    # hurt    (bands 16-17)
    (1000, 56), (1081, 39),
    # kill / death (bands 18-21)
    (1145, 42), (1209, 42), (1279, 38), (1343, 35),
]

# ── Animation frame mappings: list of (col, band) tuples ──────────────────────
ANIMATIONS = {
    "idle":   [(0,  8), (1,  8), (2,  8), (3,  8)],
    "walk":   [(0,  0), (1,  0), (2,  0), (3,  0)],
    "attack": [(0, 12), (1, 12), (2, 12), (3, 12)],
    "hurt":   [(0, 16), (1, 16)],
    "death":  [(0, 18), (0, 19), (0, 20), (0, 21)],
}

ANIM_FPS = {
    "idle":   3,
    "walk":   6,
    "attack": 8,
    "hurt":   5,
    "death":  2,
}

# ── Module-level state ─────────────────────────────────────────────────────────
_sheet:     "pygame.Surface | None" = None
_loaded     = False
_available  = False
_cache: dict = {}   # (col, band, w, h) → scaled Surface


def _load() -> bool:
    global _sheet, _loaded, _available
    if _loaded:
        return _available
    _loaded = True
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "enemies", "Slime creature.png")
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


def get_frame(col: int, band: int, w: int, h: int) -> "pygame.Surface | None":
    """Frame (col, band) escalado a (w, h). None si el PNG no está disponible."""
    if not _load():
        return None
    key = (col, band, w, h)
    if key not in _cache:
        bx       = _COL_X[col]
        by, bh   = _BAND[band]
        src      = _sheet.subsurface(pygame.Rect(bx, by, CELL_W, bh))
        _cache[key] = pygame.transform.scale(src, (w, h))
    return _cache[key]


def frame_for_t(anim: str, t: float, w: int, h: int) -> "pygame.Surface | None":
    """Frame surface para la animación `anim` en el tiempo `t`."""
    frames     = ANIMATIONS.get(anim, ANIMATIONS["idle"])
    fps        = ANIM_FPS.get(anim, 4)
    idx        = int(t * fps) % len(frames)
    col, band  = frames[idx]
    return get_frame(col, band, w, h)
