"""
Werewolf boss sprite sheet loader.
Sheet: assets/werewolf.png  —  328×328 px per frame, 10 cols × 4 rows.
Returns None frames when the PNG is missing so callers can use a procedural fallback.
"""
import os
import pygame

FRAME_W = 328
FRAME_H = 328

# (col, row) frame indices for each animation (0-indexed)
ANIMATIONS = {
    "rest":             [(6, 3), (7, 3), (8, 3)],
    "scream":           [(3, 3), (0, 3), (2, 3), (5, 3)],
    "going_for_attack": [(9, 0), (8, 0), (7, 0)],
    "attack":           [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0)],
    "attack_2":         [(2, 1), (3, 1), (6, 1), (7, 1), (8, 1), (9, 1)],
    "attack_3":         [(9, 2), (6, 2), (7, 2), (5, 2), (4, 2), (3, 2), (2, 2), (1, 2)],
}

ANIM_FPS = {
    "rest": 4,
    "scream": 7,
    "going_for_attack": 9,
    "attack": 12,
    "attack_2": 12,
    "attack_3": 12,
}

_sheet: "pygame.Surface | None" = None
_loaded    = False
_available = False
_cache: dict = {}   # (col, row, w, h) -> scaled Surface


def _load() -> bool:
    global _sheet, _loaded, _available
    if _loaded:
        return _available
    _loaded = True
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "werewolf.png")
    )
    try:
        _sheet     = pygame.image.load(path).convert_alpha()
        _available = True
    except Exception:
        _available = False
    return _available


def available() -> bool:
    """True si el sprite sheet fue cargado correctamente."""
    return _load()


def get_frame(col: int, row: int, w: int, h: int) -> "pygame.Surface | None":
    """Devuelve un frame escalado a (w, h), o None si el PNG no está disponible."""
    if not _load():
        return None
    key = (col, row, w, h)
    if key not in _cache:
        src    = _sheet.subsurface(pygame.Rect(col * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H))
        _cache[key] = pygame.transform.scale(src, (w, h))
    return _cache[key]


def frame_for_t(anim: str, t: float, w: int, h: int) -> "pygame.Surface | None":
    """Frame surface para la animación `anim` en el tiempo `t`."""
    frames = ANIMATIONS.get(anim, ANIMATIONS["rest"])
    fps    = ANIM_FPS.get(anim, 6)
    idx    = int(t * fps) % len(frames)
    col, row = frames[idx]
    return get_frame(col, row, w, h)
