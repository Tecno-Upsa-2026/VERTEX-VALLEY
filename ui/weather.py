"""
Weather system — visual overlay + stat modifiers per node.
Weather is deterministic: seeded from (game_seed XOR node_id).

Draw order (all over the map, before HUD):
  1. Biome tint  — very subtle color wash
  2. Weather FX  — rain / fog / night / storm
  3. Edge vignette — always present, darkens screen borders

Vignette algorithm: draw filled rects from LARGE (edge, dark) → SMALL (center,
transparent). Since each smaller rect overwrites the center of the previous ones,
edges keep their dark alpha while the center ends up transparent. ✓
"""
import math
import random
import pygame


WEATHERS = {
    "clear": {
        "name": "Despejado",   "color": (220, 200, 120),
        "atk_mod": 0, "def_mod": 0,
        "desc": "Sin penalizaciones.", "icon": "*",
    },
    "rain": {
        "name": "Lluvia",      "color": (100, 150, 220),
        "atk_mod": -1, "def_mod": 0,
        "desc": "Lluvia reduce precision: ATK -1", "icon": "~",
    },
    "fog": {
        "name": "Niebla",      "color": (160, 158, 148),
        "atk_mod": -1, "def_mod": -1,
        "desc": "Niebla desorienta: ATK -1, DEF -1", "icon": "=",
    },
    "night": {
        "name": "Noche Cerrada", "color": (70, 80, 160),
        "atk_mod": 0, "def_mod": -2,
        "desc": "Oscuridad vulnera: DEF -2", "icon": ")",
    },
    "storm": {
        "name": "Tormenta",    "color": (60, 80, 130),
        "atk_mod": -2, "def_mod": -1,
        "desc": "Tormenta brutal: ATK -2, DEF -1", "icon": "!",
    },
}

_POOL = (["clear"] * 5 + ["rain"] * 3 + ["fog"] * 3 +
         ["night"] * 2 + ["storm"] * 1)

_BIOME_TINT = {
    "village":  (200, 210, 170,  5),
    "forest":   ( 10,  80,  10,  7),
    "cave":     ( 50,  10,  90, 10),
    "mountain": ( 90,  85,  80,  7),
    "lake":     ( 10,  60, 140,  9),
}


class WeatherSystem:

    def __init__(self, screen_w: int, screen_h: int):
        self.sw   = screen_w
        self.sh   = screen_h
        self.type = "clear"
        self._t   = 0.0

        self._rain: list = []
        self._lightning_t   = 3.0   # time until next lightning
        self._lightning_dur = 0.0   # current flash remaining time

        self._fog_surf   : pygame.Surface | None = None
        self._night_surf : pygame.Surface | None = None
        self._star_surf  : pygame.Surface | None = None
        self._vignette   : pygame.Surface | None = None
        self._biome_surf : pygame.Surface | None = None

        self._build_vignette()

    # ── public ────────────────────────────────────────────────────────────────

    def setup(self, node_id: int, seed: int, node_type: str = "village"):
        if node_id == 0:
            w = "clear"
        else:
            rng = random.Random(seed ^ node_id ^ 0xDEAD)
            w   = rng.choice(_POOL)
        self.type             = w
        self._t               = 0.0
        self._lightning_t     = random.uniform(2.0, 5.0)
        self._lightning_dur   = 0.0
        self._build_overlays(node_type)
        self._rain = self._make_rain() if w in ("rain", "storm") else []

    @property
    def info(self) -> dict:
        return WEATHERS.get(self.type, WEATHERS["clear"])

    @property
    def atk_mod(self) -> int:
        return self.info["atk_mod"]

    @property
    def def_mod(self) -> int:
        return self.info["def_mod"]

    def update(self, dt: float):
        self._t += dt

        # Rain particle movement
        for p in self._rain:
            p[0] += p[3] * 0.38 * dt * 60
            p[1] += p[3]        * dt * 60
            if p[1] > self.sh + 10:
                p[0] = random.uniform(-40, self.sw + 40)
                p[1] = random.uniform(-50, -4)

        # Storm lightning
        if self.type == "storm":
            if self._lightning_dur > 0:
                self._lightning_dur = max(0.0, self._lightning_dur - dt)
            else:
                self._lightning_t -= dt
                if self._lightning_t <= 0:
                    self._lightning_t   = random.uniform(2.5, 7.0)
                    self._lightning_dur = random.uniform(0.07, 0.16)

    # ── draw ──────────────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface):
        if self._biome_surf:
            screen.blit(self._biome_surf, (0, 0))

        if self.type == "rain":
            self._draw_rain(screen, density=80, alpha=90)
        elif self.type == "fog":
            self._draw_fog(screen)
        elif self.type == "night":
            self._draw_night(screen)
        elif self.type == "storm":
            self._draw_rain(screen, density=120, alpha=130)
            self._draw_night(screen, extra_dark=True)
            self._draw_lightning(screen)

        if self._vignette:
            screen.blit(self._vignette, (0, 0))

    def draw_hud_badge(self, screen: pygame.Surface, font_sm, font_xs,
                       x: int, y: int):
        info    = self.info
        col     = info["color"]
        name    = info["name"]
        icon    = info["icon"]
        mods    = []
        if info["atk_mod"]: mods.append(f"ATK{info['atk_mod']:+d}")
        if info["def_mod"]: mods.append(f"DEF{info['def_mod']:+d}")
        mod_str = "  ".join(mods) if mods else "sin penalizacion"

        bw, bh = 178, 33
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill((6, 5, 3, 185))
        pygame.draw.rect(bg, (*col, 110), pygame.Rect(0, 0, bw, bh), 1, border_radius=5)
        screen.blit(bg, (x, y))

        pulse = (math.sin(self._t * 2.4) + 1) / 2
        ic    = tuple(min(255, int(c * (0.8 + 0.2 * pulse))) for c in col)
        pygame.draw.circle(screen, ic, (x + 15, y + 17), 11)
        pygame.draw.circle(screen, tuple(min(255, c + 50) for c in col),
                           (x + 15, y + 17), 11, 1)
        it = font_xs.render(icon, True, (15, 12, 8))
        screen.blit(it, it.get_rect(center=(x + 15, y + 17)))

        nt = font_xs.render(name, True, col)
        mt = font_xs.render(mod_str, True,
                            (210, 150, 90) if mods else (130, 120, 105))
        screen.blit(nt, (x + 30, y + 5))
        screen.blit(mt, (x + 30, y + 19))

    # ── private builders ──────────────────────────────────────────────────────

    def _build_vignette(self):
        """
        Correct vignette: edges DARK, center TRANSPARENT.
        Strategy: draw filled rects from LARGEST (full screen, dark alpha)
        to SMALLEST (tiny center, alpha 0). Each smaller rect overwrites the
        center pixels of the previous larger rects, leaving edge pixels at their
        original dark alpha unchanged.
        """
        s  = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        cx, cy = self.sw // 2, self.sh // 2
        steps  = 22
        for i in range(steps):
            t     = i / (steps - 1)          # 0 = outermost, 1 = innermost
            alpha = int((1.0 - t) ** 1.6 * 88)   # 88 at edge, 0 at center
            pad_x = int(t * cx * 0.84)
            pad_y = int(t * cy * 0.80)
            rect  = pygame.Rect(pad_x, pad_y,
                                self.sw - pad_x * 2,
                                self.sh - pad_y * 2)
            br = min(int((pad_x + pad_y) * 0.35 + 10), 90)
            pygame.draw.rect(s, (0, 0, 0, alpha), rect, border_radius=br)
        self._vignette = s

    def _build_overlays(self, node_type: str):
        sw, sh = self.sw, self.sh

        # Biome tint (normal surface — set_alpha is efficient)
        tint = _BIOME_TINT.get(node_type)
        if tint and tint[3] > 0:
            bs = pygame.Surface((sw, sh), pygame.SRCALPHA)
            bs.fill(tint)
            self._biome_surf = bs
        else:
            self._biome_surf = None

        # Fog: plain grey surface, alpha controlled via set_alpha
        fs = pygame.Surface((sw, sh))
        fs.fill((188, 183, 172))
        rng = random.Random(0xF09)
        for y in range(0, sh, 38):
            v = rng.randint(-12, 18)
            c = max(0, min(255, 188 + v))
            pygame.draw.rect(fs, (c, c - 2, c - 4), (0, y, sw, 38))
        self._fog_surf = fs

        # Night sky
        ns = pygame.Surface((sw, sh))
        ns.fill((8, 10, 35))
        self._night_surf = ns

        # Star map (pre-rendered SRCALPHA, alpha driven by set_alpha)
        star_s = pygame.Surface((sw, sh), pygame.SRCALPHA)
        rng    = random.Random(0x57A12)
        self._stars = [
            (rng.randint(0, sw - 1), rng.randint(4, sh // 2),
             rng.uniform(1.2, 3.8), rng.randint(1, 2))
            for _ in range(50)
        ]
        # Base star positions baked at full brightness
        for (sx, sy, _freq, radius) in self._stars:
            pygame.draw.circle(star_s, (230, 225, 210, 200), (sx, sy), radius)
        self._star_surf = star_s

    def _make_rain(self) -> list:
        count = 120 if self.type == "storm" else 80
        return [
            [random.uniform(-30, self.sw + 30),
             random.uniform(-self.sh, self.sh),
             random.randint(12, 24),
             random.uniform(9, 16)]
            for _ in range(count)
        ]

    # ── effect renderers ──────────────────────────────────────────────────────

    def _draw_rain(self, screen: pygame.Surface, density: int, alpha: int):
        rs = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        for p in self._rain[:density]:
            x, y, length, _speed = p[0], p[1], p[2], p[3]
            ex = int(x + length * 0.28)
            ey = int(y + length)
            # Main streak
            pygame.draw.line(rs, (190, 210, 240, alpha),
                             (int(x), int(y)), (ex, ey), 1)
            # Faint duplicate for density
            pygame.draw.line(rs, (190, 210, 240, alpha // 3),
                             (int(x) + 2, int(y)), (ex + 2, ey), 1)
        screen.blit(rs, (0, 0))

    def _draw_fog(self, screen: pygame.Surface):
        if not self._fog_surf:
            return
        a = int(42 + 18 * math.sin(self._t * 0.45))
        self._fog_surf.set_alpha(a)
        screen.blit(self._fog_surf, (0, 0))

        # Second drifting layer for depth
        a2 = int(22 + 10 * math.sin(self._t * 0.7 + 1.2))
        self._fog_surf.set_alpha(a2)
        offset = int(self._t * 14) % self.sw
        screen.blit(self._fog_surf, (-offset, 0))
        screen.blit(self._fog_surf, (self.sw - offset, 0))

    def _draw_night(self, screen: pygame.Surface, extra_dark: bool = False):
        if not self._night_surf:
            return
        a = 115 if extra_dark else 80
        self._night_surf.set_alpha(a)
        screen.blit(self._night_surf, (0, 0))

        if self._star_surf:
            t     = self._t
            # Each star twinkles at its own frequency using pulse_t
            star_alpha = int(140 + 80 * math.sin(t * 1.4))
            self._star_surf.set_alpha(star_alpha)
            screen.blit(self._star_surf, (0, 0))

    def _draw_lightning(self, screen: pygame.Surface):
        if self._lightning_dur <= 0:
            return
        a = int(min(200, self._lightning_dur / 0.16 * 200))
        flash = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        flash.fill((215, 225, 255, a))
        screen.blit(flash, (0, 0))
