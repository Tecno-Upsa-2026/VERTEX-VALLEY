"""
2-D tile map renderer — full-screen, rich pixel-art graphics.
Includes unique monster sprites per biome and animated character.
"""
import math
import random
import pygame
from config import (
    C, TILE_SIZE,
    TILE_GRASS, TILE_WALL, TILE_WATER, TILE_TREE,
    TILE_ROCK, TILE_FLOOR, TILE_SAND,
)
from entities import werewolf_sprite as _wws

T = TILE_SIZE  # 32 px

TILE_BASE = {
    TILE_GRASS: (50, 104, 38),
    TILE_WALL:  (70,  64,  80),
    TILE_WATER: (30,  80, 168),
    TILE_TREE:  (26,  80,  26),
    TILE_ROCK:  (90,  86,  80),
    TILE_FLOOR: (60,  54,  50),
    TILE_SAND:  (165, 142,  90),
}

# Default character palette (can be overridden per player)
_SHIRT_DEFAULT = ( 62, 108, 200)
_HAIR_DEFAULT  = ( 90,  58,  18)
_PANTS_DEFAULT = ( 35,  44, 112)
_BOOTS_DEFAULT = ( 72,  46,  26)
_SKIN          = (235, 188, 148)
_HAND          = (220, 175, 135)
_BELT          = ( 88,  60,  22)


def _r(s, c, x, y, w, h, br=0):
    pygame.draw.rect(s, c, (x, y, w, h), border_radius=br)

def _clamp(v): return max(0, min(255, int(v)))
def _d(col, delta): return (_clamp(col[0]+delta),)*3
def _tile_rng(c, r, salt=0): return random.Random(c*9973+r*31+salt+7)
def _col_hash(c, r): return ((c*1234567+r*7654321)%100)/100.0


# ── Character drawing ──────────────────────────────────────────────────────────

def draw_character(surf, cx, foot_y, anim_t, is_moving, facing=(0,1),
                   shirt_col=None, hair_col=None, pants_col=None):
    sc  = shirt_col or _SHIRT_DEFAULT
    hc  = hair_col  or _HAIR_DEFAULT
    pc  = pants_col or _PANTS_DEFAULT
    frame = int(anim_t * 8) % 4 if is_moving else 0
    bob   = [0, -3, 0,  3][frame] if is_moving else 0   # más pronunciado
    L_STRIDE = [(6,-6),(0,0),(-6,6),(0,0)]              # piernas más separadas
    lsd, rsd  = L_STRIDE[frame] if is_moving else (0, 0)
    A_SWING   = [(-5,5),(0,0),(5,-5),(0,0)]              # brazos más amplios
    las, ras  = A_SWING[frame] if is_moving else (0, 0)
    fy = foot_y + bob
    shad = pygame.Surface((24, 8), pygame.SRCALPHA)
    pygame.draw.ellipse(shad, (0,0,0,80), shad.get_rect())
    surf.blit(shad, (cx-12, foot_y+2))
    _r(surf, _BOOTS_DEFAULT, cx-8, fy-6+lsd,  7, 4, 2)
    _r(surf, _BOOTS_DEFAULT, cx+1, fy-6+rsd,  7, 4, 2)
    _r(surf, pc, cx-8, fy-14+lsd, 6, 9)
    _r(surf, pc, cx+2, fy-14+rsd, 6, 9)
    _r(surf, sc, cx-8, fy-24,    16,11, 2)
    _r(surf, _BELT, cx-8, fy-14, 16, 2)
    _r(surf, sc, cx-13, fy-24+las, 5, 9)
    _r(surf, _HAND, cx-13, fy-16+las, 5, 4, 1)
    _r(surf, sc, cx+8, fy-24+ras, 5, 9)
    _r(surf, _HAND, cx+8, fy-16+ras, 5, 4, 1)
    hx, hy = cx, fy-32
    pygame.draw.circle(surf, _SKIN, (hx, hy), 9)
    pygame.draw.ellipse(surf, hc, (hx-9, hy-8, 18, 13))
    for ex, ey in [(-4, hy),(4, hy)]:
        pygame.draw.circle(surf, (255,255,255), (hx+ex, ey), 3)
        pygame.draw.circle(surf, (55,88,175),   (hx+ex, ey), 2)
        pygame.draw.circle(surf, (15,15,15),    (hx+ex, ey), 1)
    pygame.draw.arc(surf, (175,115,95),
                    pygame.Rect(hx-3, hy+3, 6, 4), math.pi, 2*math.pi, 1)


# ── Monster sprites per biome ─────────────────────────────────────────────────

def _shadow(s, cx, cy, w=26, h=8):
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0,0,0,70), sh.get_rect())
    s.blit(sh, (cx-w//2, cy))

def draw_wolf(s, cx, cy, t):
    """Lobo gris de ojos rojos — bosque."""
    bob = int(math.sin(t*3)*2)
    y = cy + bob
    _shadow(s, cx, cy+13, 28, 8)
    # Body
    pygame.draw.ellipse(s, (85,82,98), (cx-10, y-2, 20,13))
    # Head
    pygame.draw.circle(s, (100,96,114), (cx, y-12), 8)
    # Ears
    pygame.draw.polygon(s, (110,105,124), [(cx-6,y-19),(cx-10,y-11),(cx-2,y-11)])
    pygame.draw.polygon(s, (110,105,124), [(cx+6,y-19),(cx+10,y-11),(cx+2,y-11)])
    pygame.draw.polygon(s, (170,110,130), [(cx-5,y-17),(cx-8,y-13),(cx-3,y-13)])
    pygame.draw.polygon(s, (170,110,130), [(cx+5,y-17),(cx+8,y-13),(cx+3,y-13)])
    # Snout
    pygame.draw.ellipse(s, (120,115,130), (cx-4,y-8,8,5))
    pygame.draw.circle(s, (30,25,35), (cx-2,y-8), 1)
    pygame.draw.circle(s, (30,25,35), (cx+2,y-8), 1)
    # Glowing red eyes
    rg = int((math.sin(t*5)+1)*25)+180
    for ex in (-3, 3):
        gs = pygame.Surface((8,8), pygame.SRCALPHA)
        pygame.draw.circle(gs, (rg,30,30,100), (4,4), 4)
        s.blit(gs, (cx+ex-4, y-16))
        pygame.draw.circle(s, (rg,30,30), (cx+ex, y-13), 2)
    # Legs
    for lx in (cx-8,cx-3,cx+2,cx+6):
        _r(s, (75,72,88), lx, y+9, 4, 6)
    # Tail
    pygame.draw.arc(s, (95,92,108), (cx+7,y-5,11,12), math.pi/4, math.pi, 3)

def draw_slime(s, cx, cy, t):
    """Slime verde — cueva."""
    pulse = (math.sin(t*3)+1)/2
    rw = int(13+pulse*2)
    rh = int(10-pulse*1)
    y  = cy + int(pulse*2)
    _shadow(s, cx, cy+11, 28, 8)
    col  = (45,185,80)
    dark = (28,128,55)
    pygame.draw.ellipse(s, dark, (cx-rw, y-rh+1, rw*2, rh*2+2))
    pygame.draw.ellipse(s, col,  (cx-rw, y-rh,   rw*2, rh*2))
    # Shine
    pygame.draw.ellipse(s, (80,230,120), (cx-rw+3, y-rh+2, rw-4, rh//2))
    # Top bump
    pygame.draw.circle(s, col, (cx, y-rh), rw//2+1)
    pygame.draw.circle(s, (65,205,100), (cx, y-rh), rw//2)
    # Eyes
    for ex in (-4, 4):
        pygame.draw.circle(s, (255,255,255), (cx+ex, y-3), 3)
        px_ = cx+ex + int(math.sin(t*2)*1)
        pygame.draw.circle(s, (20,20,20), (px_, y-3), 2)
    pygame.draw.circle(s, (150,255,180), (cx-rw//2+2, y-rh//2), 2)

def draw_golem(s, cx, cy, t):
    """Golem de roca — montaña."""
    bob = int(math.sin(t*1.5)*1)
    y   = cy+bob
    _shadow(s, cx, cy+14, 32, 9)
    col = (100,95,90)
    # Body (chunky)
    _r(s, (70,66,62), cx-11, y-1, 22,15, 3)
    _r(s, col,        cx-11, y-2, 22,15, 3)
    pygame.draw.line(s, (60,56,52), (cx-4,y-1), (cx+2,y+6), 1)
    pygame.draw.line(s, (60,56,52), (cx+2,y-2), (cx+5,y+4), 1)
    # Head
    _r(s, col, cx-8, y-17,16,14, 2)
    pygame.draw.rect(s, (80,76,72), (cx-8, y-17,16,14), 1, border_radius=2)
    # Glowing orange eyes
    for ex in (-3,3):
        gs = pygame.Surface((12,12), pygame.SRCALPHA)
        ga = int(140+math.sin(t*4)*50)
        pygame.draw.circle(gs, (255,140,30,ga), (6,6), 6)
        s.blit(gs, (cx+ex-6, y-16))
        pygame.draw.circle(s, (255,180,50), (cx+ex, y-11), 2)
    # Arms
    _r(s, col, cx-17, y,  7,10, 2)
    _r(s, col, cx+10, y,  7,10, 2)
    # Legs
    _r(s, (85,80,76), cx-9, y+12, 7, 8)
    _r(s, (85,80,76), cx+2, y+12, 7, 8)

def draw_serpent(s, cx, cy, t):
    """Serpiente de agua — lago."""
    wave = math.sin(t*3)
    _shadow(s, cx, cy+13, 28, 7)
    col  = (40,165,145)
    dark = (25,115,100)
    offsets = [int(wave*6), int(wave*4), 0, -int(wave*3), -int(wave*5)]
    ys = [cy-10, cy-3, cy+3, cy+8, cy+13]
    for i,(dx,yy) in enumerate(zip(offsets,ys)):
        r_ = 7-i
        pygame.draw.circle(s, dark, (cx+dx+1, yy+1), r_)
        pygame.draw.circle(s, col,  (cx+dx,   yy),   r_)
    # Highlight on body
    pygame.draw.circle(s, (70,210,185), (cx+offsets[1], ys[1]-2), 3)
    hx = cx+offsets[0]
    hy = cy-14
    pygame.draw.circle(s, dark, (hx+1, hy+1), 7)
    pygame.draw.circle(s, col,  (hx,   hy),   7)
    for ex in (-3,3):
        pygame.draw.circle(s, (255,235,55), (hx+ex, hy-1), 2)
        pygame.draw.circle(s, (20,20,20),   (hx+ex, hy-1), 1)
    tw = int(math.sin(t*8)*2)
    pygame.draw.line(s, (215,50,50), (hx, hy+5), (hx, hy+8+tw), 1)
    pygame.draw.line(s, (215,50,50), (hx, hy+8+tw), (hx-2, hy+11+tw), 1)
    pygame.draw.line(s, (215,50,50), (hx, hy+8+tw), (hx+2, hy+11+tw), 1)

def draw_goblin(s, cx, cy, t):
    """Goblin verde — aldea."""
    bob = int(math.sin(t*4)*1.5)
    y   = cy+bob
    _shadow(s, cx, cy+13, 24, 7)
    sk  = (95,150,55)
    dsk = (65,108,38)
    cl  = (55,55,75)
    # Legs
    for lx in (cx-4, cx+1):
        _r(s, dsk, lx, y+7, 4, 7)
    # Body
    _r(s, cl, cx-5, y-4, 10,12, 2)
    # Arms (swing)
    arm_s = int(math.sin(t*4)*3)
    pygame.draw.line(s, sk, (cx-5,y-2), (cx-10,y+3+arm_s), 2)
    pygame.draw.line(s, sk, (cx+5,y-2), (cx+10,y+3-arm_s), 2)
    # Head (big)
    pygame.draw.circle(s, dsk, (cx+1,y-12), 9)
    pygame.draw.circle(s, sk,  (cx,  y-12), 9)
    # Big pointy ears
    pygame.draw.polygon(s, sk, [(cx-8,y-14),(cx-13,y-9),(cx-5,y-9)])
    pygame.draw.polygon(s, sk, [(cx+8,y-14),(cx+13,y-9),(cx+5,y-9)])
    # Eyes (big yellow)
    for ex in (-3,3):
        pygame.draw.circle(s, (230,205,50), (cx+ex, y-13), 3)
        pygame.draw.circle(s, (20,20,20),   (cx+ex, y-13), 1)
    # Teeth
    for tx in (cx-2, cx, cx+2):
        pygame.draw.polygon(s, (240,238,220), [(tx,y-7),(tx+1,y-4),(tx+2,y-7)])

def draw_werewolf(s, cx, cy, t):
    """Hombre Lobo boss — usa sprite sheet si está disponible, si no dibuja proceduralmente."""
    surf = _wws.frame_for_t("rest", t, 80, 80)
    if surf is not None:
        # Aura roja pulsante de boss
        aura = pygame.Surface((100, 100), pygame.SRCALPHA)
        ga = 18 + int(12 * math.sin(t * 2))
        pygame.draw.ellipse(aura, (200, 40, 40, ga), aura.get_rect())
        s.blit(aura, (cx - 50, cy - 76))
        s.blit(surf, (cx - 40, cy - 72))
        return

    # ── Fallback procedural grande y amenazante ────────────────────────────────
    bob = int(math.sin(t * 2.5) * 3)
    y   = cy + bob - 4   # desplazado arriba para ser más alto que un tile

    # Aura roja pulsante de boss
    pulse = (math.sin(t * 3) + 1) / 2
    aura  = pygame.Surface((64, 64), pygame.SRCALPHA)
    pygame.draw.ellipse(aura, (180, 20, 20, int(30 + pulse * 25)), aura.get_rect())
    s.blit(aura, (cx - 32, y - 16))

    # Sombra
    _shadow(s, cx, cy + 14, 44, 11)

    # Cuerpo grande (pecho musculoso)
    pygame.draw.ellipse(s, (52, 38, 30), (cx - 18, y - 6,  38, 22))  # sombra cuerpo
    pygame.draw.ellipse(s, (88, 65, 48), (cx - 17, y - 8,  36, 22))  # cuerpo

    # Brazos con garras
    pygame.draw.ellipse(s, (78, 58, 42), (cx - 28, y - 4, 12, 20))   # brazo izq
    pygame.draw.ellipse(s, (78, 58, 42), (cx + 17, y - 4, 12, 20))   # brazo der
    # Garras izquierda
    for i, gx in enumerate((cx - 28, cx - 24, cx - 20)):
        pygame.draw.line(s, (210, 200, 185), (gx, y + 16), (gx - 2 + i, y + 22), 2)
    # Garras derecha
    for i, gx in enumerate((cx + 19, cx + 23, cx + 27)):
        pygame.draw.line(s, (210, 200, 185), (gx, y + 16), (gx + 2 - i, y + 22), 2)

    # Cabeza grande
    pygame.draw.circle(s, (62, 45, 35), (cx + 1, y - 20), 14)  # sombra cabeza
    pygame.draw.circle(s, (100, 75, 55), (cx,     y - 21), 14)

    # Orejas puntiagudas
    pygame.draw.polygon(s, (110, 82, 60), [(cx-12, y-33), (cx-18, y-20), (cx-5,  y-20)])
    pygame.draw.polygon(s, (110, 82, 60), [(cx+12, y-33), (cx+18, y-20), (cx+5,  y-20)])
    pygame.draw.polygon(s, (175, 80, 80), [(cx-11, y-31), (cx-15, y-23), (cx-6,  y-23)])
    pygame.draw.polygon(s, (175, 80, 80), [(cx+11, y-31), (cx+15, y-23), (cx+6,  y-23)])

    # Hocico
    pygame.draw.ellipse(s, (80, 58, 45), (cx - 6, y - 13, 12, 8))
    pygame.draw.circle(s, (30, 20, 20),  (cx - 2, y - 12), 2)
    pygame.draw.circle(s, (30, 20, 20),  (cx + 2, y - 12), 2)

    # Ojos con brillo ámbar pulsante
    rg = _clamp(int((math.sin(t * 5) + 1) * 30) + 200)
    for ex in (-5, 5):
        gs = pygame.Surface((14, 14), pygame.SRCALPHA)
        pygame.draw.circle(gs, (rg, int(rg * 0.55), 10, 140), (7, 7), 7)
        s.blit(gs, (cx + ex - 7, y - 29))
        pygame.draw.circle(s, (rg, int(rg * 0.55), 10), (cx + ex, y - 24), 4)
        pygame.draw.circle(s, (15, 5, 5), (cx + ex + 1, y - 24), 2)

    # Patas
    for lx in (cx - 13, cx - 5, cx + 3, cx + 10):
        _r(s, (65, 48, 36), lx, y + 13, 7, 10)
    # Cola
    pygame.draw.arc(s, (88, 65, 48), (cx + 14, y - 10, 18, 20), math.pi / 4, math.pi, 5)


_MONSTER_DRAW = {
    "forest":   draw_wolf,
    "cave":     draw_slime,
    "mountain": draw_golem,
    "lake":     draw_serpent,
    "village":  draw_goblin,
}

def draw_monster(surf, cx, cy, node_type, anim_t):
    fn = _MONSTER_DRAW.get(node_type, draw_goblin)
    fn(surf, cx, cy, anim_t)


# ── NPC drawing ───────────────────────────────────────────────────────────────

def draw_npc(surf, cx, cy, color=(200,180,140), t=0.0):
    """Small static villager NPC."""
    bob = int(math.sin(t*2+cx)*0.8)
    y = cy + bob
    _shadow(surf, cx, cy+8, 18, 6)
    shirt = color
    pygame.draw.circle(surf, _SKIN, (cx, y-8), 6)
    pygame.draw.ellipse(surf, (80,60,20), (cx-6, y-13, 12, 8))
    _r(surf, shirt, cx-5, y-3, 10, 8, 2)
    for lx in (cx-4, cx+1):
        _r(surf, (40,35,80), lx, y+4, 4, 6)


# ── MapView ───────────────────────────────────────────────────────────────────

class MapView:
    def __init__(self, screen, fonts, viewport):
        self.screen   = screen
        self.F        = fonts
        self.viewport = viewport
        self.cam_c    = 0
        self.cam_r    = 0
        self._t       = 0.0

    def update(self, dt):
        self._t += dt

    def center_camera(self, pc, pr, tile_map):
        vw = self.viewport.width  // T
        vh = self.viewport.height // T
        self.cam_c = max(0, min(tile_map.cols - vw, pc - vw // 2))
        self.cam_r = max(0, min(tile_map.rows - vh, pr - vh // 2))

    def draw(self, tile_map, player, opened):
        s  = self.screen
        vp = self.viewport
        s.set_clip(vp)

        _BIOME_BG = {
            "village":  TILE_BASE[TILE_GRASS],
            "forest":   TILE_BASE[TILE_GRASS],
            "cave":     TILE_BASE[TILE_FLOOR],
            "mountain": TILE_BASE[TILE_ROCK],
            "lake":     TILE_BASE[TILE_WATER],
        }
        pygame.draw.rect(s, _BIOME_BG.get(tile_map.node_type,(20,20,28)), vp)

        vw = vp.width  // T + 2
        vh = vp.height // T + 2
        node_type = getattr(tile_map, 'node_type', 'forest')

        for r in range(self.cam_r, min(self.cam_r+vh, tile_map.rows)):
            for c in range(self.cam_c, min(self.cam_c+vw, tile_map.cols)):
                tile = tile_map.get_tile(c, r)
                sx   = vp.x + (c-self.cam_c)*T
                sy   = vp.y + (r-self.cam_r)*T
                self._tile(tile, sx, sy, c, r)
                obj = tile_map.get_object(c, r)
                if obj and (c, r) not in opened:
                    self._obj(obj, sx, sy, node_type)

        px = vp.x + (player.x-self.cam_c)*T
        py = vp.y + (player.y-self.cam_r)*T
        draw_character(s, px+T//2, py+T-2,
                       self._t, player.is_moving, player.facing,
                       shirt_col=getattr(player,'shirt_col',None),
                       hair_col =getattr(player,'hair_col', None),
                       pants_col=getattr(player,'pants_col',None))

        # Atmospheric overlay for corridors (scary red vignette + fog)
        if getattr(tile_map, 'is_corridor', False):
            self._corridor_atmosphere(s, vp)

        s.set_clip(None)

    def _corridor_atmosphere(self, s, vp):
        """Rojo pulsante en los bordes del corredor para sensación de peligro."""
        t = self._t
        pulse = (math.sin(t*1.6)+1)/2
        alpha = int(18 + pulse*28)
        vig   = pygame.Surface((vp.width, vp.height), pygame.SRCALPHA)
        for d in range(90, 0, -22):
            a2 = int(alpha*(1-d/90))
            pygame.draw.rect(vig,(180,10,10,a2),(0,0,d,vp.height))
            pygame.draw.rect(vig,(180,10,10,a2),(vp.width-d,0,d,vp.height))
        s.blit(vig,(vp.x,vp.y))
        # Niebla baja en el suelo
        for i in range(5):
            phase = t*0.4 + i*0.9
            fx = vp.x + int((math.sin(phase)*0.35+0.5)*vp.width)
            fy = vp.y + vp.height - 20 + int(math.sin(phase*1.2)*8)
            fs = pygame.Surface((50,18),pygame.SRCALPHA)
            fa = int(12+math.sin(phase*2)*5)
            pygame.draw.ellipse(fs,(30,25,40,fa),fs.get_rect())
            s.blit(fs,(fx-25,fy-9))

    # ── tile renderer ─────────────────────────────────────────────────────────

    def _tile(self, tile, sx, sy, col, row):
        t = self._t; b = TILE_BASE.get(tile, C["bg"]); s = self.screen
        if tile == TILE_GRASS:   self._grass(s, sx, sy, col, row, b)
        elif tile == TILE_WATER: self._water(s, sx, sy, b, t)
        elif tile == TILE_SAND:  self._sand(s, sx, sy, col, row, b)
        elif tile == TILE_ROCK:  self._rock(s, sx, sy, b)
        elif tile == TILE_WALL:  self._wall(s, sx, sy, col, row, b)
        elif tile == TILE_FLOOR: self._floor(s, sx, sy, col, row, b)
        elif tile == TILE_TREE:
            self._grass(s, sx, sy, col, row, TILE_BASE[TILE_GRASS])
            self._tree(s, sx, sy, col, row)
        else:
            pygame.draw.rect(s, b, (sx, sy, T, T))

    def _grass(self, s, sx, sy, col, row, base):
        pygame.draw.rect(s, base, (sx, sy, T, T))
        border = (_clamp(base[0]-10), _clamp(base[1]-10), _clamp(base[2]-8))
        pygame.draw.rect(s, border, (sx, sy, T, T), 1)
        rng = _tile_rng(col, row)
        vtype = rng.randint(0,9)
        for _ in range(rng.randint(3,7)):
            gx=sx+rng.randint(2,T-3); gy=sy+rng.randint(T//2,T-2)
            bh=rng.randint(4,9); lean=rng.randint(-2,2)
            gc=(_clamp(base[0]+rng.randint(-6,22)),_clamp(base[1]+rng.randint(6,30)),_clamp(base[2]+rng.randint(-4,8)))
            pygame.draw.line(s,gc,(gx,gy),(gx+lean,gy-bh),1)
        if vtype==0:
            fc=rng.choice([(255,218,80),(255,130,180),(180,145,255),(255,200,120)])
            fx=sx+rng.randint(4,T-5); fy=sy+rng.randint(4,T-5)
            for dx,dy in [(0,0),(3,1),(-2,2),(1,-3)]:
                pygame.draw.circle(s,fc,(fx+dx,fy+dy),2)
        elif vtype==1:
            bx=sx+rng.randint(5,T-6); by=sy+rng.randint(5,T-6)
            dark=(_clamp(base[0]-10),_clamp(base[1]+10),_clamp(base[2]-5))
            pygame.draw.circle(s,dark,(bx,by),5)

    def _water(self, s, sx, sy, base, t):
        pygame.draw.rect(s, base, (sx, sy, T, T))
        for i in range(4):
            wy=sy+5+i*7; phase=t*1.6+_col_hash(sx//T,sy//T)*0.4+i*0.8
            offset=int(math.sin(phase)*2.5); bright=(_clamp(base[0]+42),_clamp(base[1]+42),_clamp(base[2]+30))
            pygame.draw.line(s,bright,(sx+4,wy+offset),(sx+T-5,wy+offset),2)
        pygame.draw.rect(s,(_clamp(base[0]+22),_clamp(base[1]+22),_clamp(base[2]+15)),(sx,sy,T,2))

    def _sand(self, s, sx, sy, col, row, base):
        pygame.draw.rect(s,base,(sx,sy,T,T))
        rng=_tile_rng(col,row)
        for _ in range(5):
            pygame.draw.circle(s,(_clamp(base[0]-20),)*3,(sx+rng.randint(2,T-3),sy+rng.randint(2,T-3)),1)

    def _rock(self, s, sx, sy, base):
        pygame.draw.rect(s,base,(sx,sy,T,T))
        pygame.draw.rect(s,(_clamp(base[0]-24),)*3,(sx,sy+T-3,T,3))
        pygame.draw.rect(s,(_clamp(base[0]-24),)*3,(sx+T-3,sy,3,T))
        pygame.draw.rect(s,(_clamp(base[0]+32),_clamp(base[1]+28),_clamp(base[2]+25)),(sx,sy,T,3))
        pygame.draw.rect(s,(_clamp(base[0]+32),_clamp(base[1]+28),_clamp(base[2]+25)),(sx,sy,3,T))
        mx,my=sx+T//2,sy+T//2
        pygame.draw.line(s,(_clamp(base[0]-14),)*3,(mx-5,my-3),(mx+4,my+5),1)

    def _wall(self, s, sx, sy, col, row, base):
        pygame.draw.rect(s,base,(sx,sy,T,T))
        dark=(_clamp(base[0]-28),)*3; light=(_clamp(base[0]+18),_clamp(base[1]+18),_clamp(base[2]+18))
        pygame.draw.rect(s,dark,(sx,sy,T,T),1)
        half=T//2
        pygame.draw.line(s,dark,(sx,sy+half),(sx+T,sy+half),1)
        if (col+row)%2==0: pygame.draw.line(s,dark,(sx+half,sy),(sx+half,sy+half),1)
        else: pygame.draw.line(s,dark,(sx+half,sy+half),(sx+half,sy+T),1)
        pygame.draw.rect(s,light,(sx,sy,T,2))

    def _floor(self, s, sx, sy, col, row, base):
        pygame.draw.rect(s,base,(sx,sy,T,T))
        pygame.draw.rect(s,(_clamp(base[0]-12),)*3,(sx,sy,T,T),1)
        if (col+row)%2==0:
            _r(s,(_clamp(base[0]+10),_clamp(base[1]+8),_clamp(base[2]+8)),sx+1,sy+1,T-2,T//2-1)
        rng=_tile_rng(col,row,99)
        if rng.random()<0.04:
            mx,my=sx+rng.randint(6,T-7),sy+rng.randint(8,T-6)
            if rng.random()<0.5:
                cap=(200,60,60) if rng.random()<0.6 else (140,80,200)
                _r(s,(180,160,130),mx-1,my,3,5)
                pygame.draw.circle(s,cap,(mx,my),4)
            else:
                bc=(80,130,230)
                pygame.draw.polygon(s,bc,[(mx,my-6),(mx+3,my),(mx-3,my)])

    def _tree(self, s, sx, sy, col, row):
        cx_=sx+T//2
        rng=_tile_rng(col,row,55)
        base_g=(28,92,28)
        G=[(_clamp(base_g[0]+rng.randint(-6,8)),_clamp(base_g[1]+rng.randint(-8,12)),_clamp(base_g[2]+rng.randint(-4,6)))]
        G+=[ (_clamp(G[0][0]+12),_clamp(G[0][1]+12),_clamp(G[0][2]+10)),
             (_clamp(G[0][0]+22),_clamp(G[0][1]+22),_clamp(G[0][2]+18)),
             (_clamp(G[0][0]+34),_clamp(G[0][1]+34),_clamp(G[0][2]+28)) ]
        sh=pygame.Surface((22,10),pygame.SRCALPHA)
        pygame.draw.ellipse(sh,(0,0,0,55),sh.get_rect())
        s.blit(sh,(cx_-11,sy+T-8))
        _r(s,(100,64,28),cx_-3,sy+T-13,6,13)
        _r(s,(80,50,20), cx_-3,sy+T-13,2,13)
        for ly,lr,lc in [(sy+T-22,13,G[0]),(sy+T-27,11,G[1]),(sy+T-33,9,G[2]),(sy+T-38,7,G[3])]:
            pygame.draw.circle(s,lc,(cx_,ly),lr)
            pygame.draw.circle(s,(_clamp(lc[0]+18),_clamp(lc[1]+18),_clamp(lc[2]+15)),(cx_-2,ly-2),lr//2)
        pygame.draw.circle(s,(_clamp(G[0][0]-20),_clamp(G[0][1]-20),_clamp(G[0][2]-15)),(cx_,sy+T-22),13,1)

    # ── object icons ──────────────────────────────────────────────────────────

    def _obj(self, obj, sx, sy, node_type='forest'):
        half=T//2; s=self.screen; t=self._t
        cx_=sx+half; cy_=sy+half
        if obj == "chest":       self._chest(s,sx,sy,t)
        elif obj == "exit":      self._exit(s,sx,sy,t,half)
        elif obj == "shop":      self._shop(s,sx,sy,half)
        elif obj == "enemy":
            # Dibujar monstruo real según bioma
            draw_monster(s, cx_, cy_-4, node_type, t)
        elif obj == "werewolf":
            draw_werewolf(s, cx_, cy_-4, t)
            pulse = (math.sin(t * 3.5) + 1) / 2
            lc = (_clamp(200 + int(pulse * 55)), 40, 40)
            wt = self.F["xs"].render("! JEFE !", True, lc)
            s.blit(wt, wt.get_rect(center=(cx_, sy - 66)))
        elif obj == "npc":       draw_npc(s, cx_, cy_+2, t=t)
        elif obj == "npc_elder": draw_npc(s, cx_, cy_+2, color=(200,150,80), t=t)
        elif obj == "npc_guard": draw_npc(s, cx_, cy_+2, color=(80,120,200), t=t)
        elif obj == "well":      self._well(s, sx, sy)
        elif obj == "garden":    self._garden(s, sx, sy, t)
        elif obj == "upsa_sign": self._upsa_sign(s, sx, sy, t)

    def _chest(self, s, sx, sy, t):
        sh=pygame.Surface((26,8),pygame.SRCALPHA); pygame.draw.ellipse(sh,(0,0,0,60),sh.get_rect())
        s.blit(sh,(sx+3,sy+T-6))
        _r(s,(105,70,18),sx+4,sy+12,24,14,2); _r(s,(148,102,28),sx+4,sy+10,24,9,2)
        pygame.draw.rect(s,(205,168,62),(sx+4,sy+10,24,14),2,border_radius=2)
        _r(s,(215,185,78),sx+12,sy+14,8,6,1)
        g=int((math.sin(t*4)+1)*28)+175; pygame.draw.circle(s,(g,g,82),(sx+7,sy+13),3)

    def _exit(self, s, sx, sy, t, half):
        ST=(80,74,68); ST_L=(108,100,92); ST_D=(52,47,43); DARK=(10,8,6)
        pygame.draw.rect(s,(46,40,34),(sx,sy,T,T))
        pygame.draw.rect(s,DARK,(sx+7,sy+5,18,20))
        pygame.draw.rect(s,ST,(sx+2,sy+2,28,6)); pygame.draw.rect(s,ST_L,(sx+2,sy+2,28,2))
        pygame.draw.rect(s,ST,(sx+2,sy+6,6,18));  pygame.draw.rect(s,ST_L,(sx+2,sy+6,2,18))
        pygame.draw.rect(s,ST,(sx+24,sy+6,6,18)); pygame.draw.rect(s,ST_D,(sx+28,sy+6,2,18))
        pygame.draw.rect(s,ST_D,(sx+2,sy+24,28,6)); pygame.draw.rect(s,ST,(sx+8,sy+24,16,4))
        pulse=(math.sin(t*2.8)+1)/2; gal=int(55+pulse*55)
        gs=pygame.Surface((18,18),pygame.SRCALPHA); pygame.draw.ellipse(gs,(60,200,130,gal),gs.get_rect())
        s.blit(gs,(sx+7,sy+5))
        at=self.F["xs"].render(">>",True,(120,230,170)); s.blit(at,at.get_rect(center=(sx+half,sy+14)))

    def _shop(self, s, sx, sy, half):
        """Tiendita con toldo a rayas, vitrinas y puerta."""
        t = self._t

        # ── Pared de la tienda ────────────────────────────────────────────────
        _r(s, (140, 105, 72), sx+1, sy+8, 30, 22)   # paredes beige-marrón
        _r(s, (120,  88, 58), sx+1, sy+8,  2, 22)   # sombra lateral izq
        _r(s, (120,  88, 58), sx+1, sy+28, 30,  2)  # sombra inferior

        # ── Toldo con rayas rojo-amarillo ─────────────────────────────────────
        stripe_w = 4
        colors   = [(210, 45, 38), (245, 210, 60)]
        for i in range(8):
            _r(s, colors[i % 2], sx + i*stripe_w, sy+2, stripe_w, 7)
        # Borde del toldo
        pygame.draw.rect(s, (160, 28, 22), (sx, sy+2, T, 7), 1)
        # Flecos del toldo (pequeños triángulos colgantes)
        for fx in range(sx+2, sx+T-1, 5):
            pygame.draw.polygon(s, (185, 35, 28), [(fx, sy+9),(fx+2,sy+12),(fx+4,sy+9)])

        # ── Cartel con "$" y nombre ───────────────────────────────────────────
        _r(s, (255, 215, 40), sx+8, sy+3, 16, 5, 1)  # fondo cartel dorado
        pygame.draw.rect(s, (180, 138, 15), (sx+8, sy+3, 16, 5), 1, border_radius=1)
        gt = self.F["xs"].render("$", True, (55, 28, 4))
        s.blit(gt, gt.get_rect(center=(sx+half, sy+6)))

        # ── Ventana izquierda ─────────────────────────────────────────────────
        _r(s, (155, 210, 240), sx+3, sy+11, 9, 9)
        pygame.draw.line(s, (100, 165, 205), (sx+7, sy+11), (sx+7, sy+20), 1)
        pygame.draw.line(s, (100, 165, 205), (sx+3, sy+15), (sx+12, sy+15), 1)
        pygame.draw.rect(s, (90, 62, 35), (sx+3, sy+11, 9, 9), 1)

        # ── Ventana derecha ───────────────────────────────────────────────────
        _r(s, (155, 210, 240), sx+20, sy+11, 9, 9)
        pygame.draw.line(s, (100, 165, 205), (sx+24, sy+11), (sx+24, sy+20), 1)
        pygame.draw.line(s, (100, 165, 205), (sx+20, sy+15), (sx+29, sy+15), 1)
        pygame.draw.rect(s, (90, 62, 35), (sx+20, sy+11, 9, 9), 1)

        # ── Puerta central ────────────────────────────────────────────────────
        _r(s, (88, 56, 30), sx+12, sy+20, 8, 10, 1)    # puerta
        pygame.draw.circle(s, (200, 160, 48), (sx+18, sy+26), 1)  # pomo

        # ── Brillo animado en vitrinas ────────────────────────────────────────
        pulse = (math.sin(t * 2.5) + 1) / 2
        sh    = pygame.Surface((6, 5), pygame.SRCALPHA)
        sh.fill((230, 248, 255, int(25 + pulse*22)))
        s.blit(sh, (sx+4, sy+12))
        s.blit(sh, (sx+21, sy+12))

    def _well(self, s, sx, sy):
        """Pozo de piedra."""
        cx_=sx+T//2; cy_=sy+T//2
        pygame.draw.circle(s,(80,75,70),(cx_,cy_),12)
        pygame.draw.circle(s,(55,50,48),(cx_,cy_),12,2)
        pygame.draw.circle(s,(30,60,120),(cx_,cy_),8)
        pygame.draw.circle(s,(50,100,180),(cx_,cy_),8,1)
        _r(s,(100,90,80),cx_-12,cy_-14,24,4,1)
        pygame.draw.line(s,(120,110,100),(cx_,cy_-12),(cx_,cy_-4),2)

    def _garden(self, s, sx, sy, t):
        """Pequeño jardín con flores."""
        rng=_tile_rng(sx//T,sy//T,42)
        pygame.draw.rect(s,TILE_BASE[TILE_GRASS],(sx,sy,T,T))
        for _ in range(5):
            fx=sx+rng.randint(4,T-5); fy=sy+rng.randint(4,T-5)
            fc=rng.choice([(255,218,80),(255,130,180),(180,145,255)])
            pygame.draw.circle(s,fc,(fx,fy),3)
            pygame.draw.circle(s,(255,255,200),(fx,fy),1)

    def _upsa_sign(self, s, sx, sy, t):
        """Cartel luminoso de la UPSA sobre el edificio principal."""
        half = T // 2
        # Fondo del cartel (azul institucional UPSA)
        UPSA_BLUE = (0, 60, 140)
        UPSA_GOLD = (255, 200, 30)
        _r(s, UPSA_BLUE, sx+2, sy+4, 28, 22, 3)
        pygame.draw.rect(s, UPSA_GOLD, (sx+2, sy+4, 28, 22), 2, border_radius=3)
        # Texto UPSA
        ut = self.F["xs"].render("UPSA", True, UPSA_GOLD)
        s.blit(ut, ut.get_rect(center=(sx+half, sy+12)))
        # Subtexto pequeño
        sub = self.F["xs"].render("Univ.", True, (200, 220, 255))
        s.blit(sub, sub.get_rect(center=(sx+half, sy+22)))
        # Brillo pulsante
        pulse = (math.sin(t*2)+1)/2
        gs = pygame.Surface((32, 28), pygame.SRCALPHA)
        pygame.draw.rect(gs, (*UPSA_GOLD, int(20+pulse*25)), gs.get_rect(), border_radius=4)
        s.blit(gs, (sx, sy+3))
