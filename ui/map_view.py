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
    frame = int(anim_t * 7) % 4 if is_moving else 0
    bob   = [0, -1, 0,  1][frame] if is_moving else 0
    L_STRIDE = [(3,-3),(0,0),(-3,3),(0,0)]
    lsd, rsd  = L_STRIDE[frame] if is_moving else (0, 0)
    A_SWING   = [(-3,3),(0,0),(3,-3),(0,0)]
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
        s.set_clip(None)

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
        pygame.draw.rect(s, (_clamp(base[0]-8),)*3, (sx,sy,T,T), 1)
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
        elif obj == "npc":       draw_npc(s, cx_, cy_+2, t=t)
        elif obj == "npc_elder": draw_npc(s, cx_, cy_+2, color=(200,150,80), t=t)
        elif obj == "npc_guard": draw_npc(s, cx_, cy_+2, color=(80,120,200), t=t)
        elif obj == "well":      self._well(s, sx, sy)
        elif obj == "garden":    self._garden(s, sx, sy, t)

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
        _r(s,(142,90,26),sx+5,sy+3,22,22,3)
        pygame.draw.rect(s,(195,145,58),(sx+5,sy+3,22,22),2,border_radius=3)
        gt=self.F["md"].render("$",True,(255,220,60)); s.blit(gt,gt.get_rect(center=(sx+half,sy+half-1)))

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
