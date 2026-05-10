"""
HUD — slim semi-transparent overlay at the top of the screen.
The map renders at full 1280×720; this bar is drawn on top.
"""
import math
import pygame
from config import C, NODE_DISPLAY_NAMES, NODE_COLORS


def _gradient_bar(surf, x, y, w, h, ratio, col_hi, col_lo, bg, label, font, r=4):
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=r)
    fw = max(0, int(w * ratio))
    if fw:
        mid = tuple(int(col_lo[i] + (col_hi[i] - col_lo[i]) * ratio) for i in range(3))
        pygame.draw.rect(surf, mid, (x, y, fw, h), border_radius=r)
        shine = tuple(min(255, c + 50) for c in mid)
        pygame.draw.rect(surf, shine, (x + 1, y + 1, max(0, fw - 2), h // 3), border_radius=r)
    pygame.draw.rect(surf, C["border_hi"], (x, y, w, h), 1, border_radius=r)
    if label:
        lt = font.render(label, True, C["text_hi"])
        surf.blit(lt, (x + 4, y + (h - lt.get_height()) // 2))


class HUD:
    BAR_HEIGHT = 42   # total height of the overlay

    def __init__(self, screen: pygame.Surface, fonts: dict,
                 screen_w: int, screen_h: int):
        self.screen = screen
        self.F      = fonts
        self.sw     = screen_w
        self.sh     = screen_h
        self._anim  = 0.0

    def update(self, dt: float):
        self._anim += dt

    def draw(self, player, node_name: str, node_type: str, instructions: str = ""):
        s  = self.screen

        # ── Semi-transparent background ──
        bg = pygame.Surface((self.sw, self.BAR_HEIGHT), pygame.SRCALPHA)
        bg.fill((6, 6, 16, 215))
        s.blit(bg, (0, 0))
        # Bottom accent line with node colour
        ncol = NODE_COLORS.get(node_type, C["green"])
        pygame.draw.line(s, ncol, (0, self.BAR_HEIGHT - 1), (self.sw, self.BAR_HEIGHT - 1), 1)
        # Left accent stripe
        pygame.draw.rect(s, ncol, (0, 0, 4, self.BAR_HEIGHT))

        x = 12   # left margin

        # ── HP bar ──
        _gradient_bar(s, x, 6, 185, 14, player.hp_ratio,
                      (240, 58, 58), (130, 18, 18), C["hp_bg"],
                      f"HP  {player.hp}/{player.max_hp}", self.F["xs"])
        # ── EXP bar ──
        _gradient_bar(s, x, 23, 185, 11, player.exp_ratio,
                      (72, 136, 255), (28, 58, 180), C["exp_bg"],
                      f"Nv.{player.level}", self.F["xs"])

        x += 198

        # ── Coins (pulsing gold) ──
        pulse = int((math.sin(self._anim * 3) + 1) * 8)
        coin_c = (255, min(255, 208 + pulse), min(255, 48 + pulse))
        pygame.draw.circle(s, coin_c, (x + 8, 20), 9)
        pygame.draw.circle(s, (160, 128, 16), (x + 8, 20), 9, 2)
        dc = self.F["xs"].render("$", True, (24, 16, 4))
        s.blit(dc, dc.get_rect(center=(x + 8, 20)))
        ct = self.F["md"].render(str(player.coins), True, coin_c)
        s.blit(ct, (x + 22, 11))

        x += ct.get_width() + 36

        # ── Attack / Defense ──
        atk_bonus = _item_bonus(player.weapon)
        s.blit(self.F["xs"].render(f"ATK {player.attack + atk_bonus}", True, C["orange"]), (x, 7))
        s.blit(self.F["xs"].render(f"DEF {player.defense}", True, C["blue"]),              (x, 22))
        x += 68

        # ── Equipment slots ──
        w_col = C["orange"] if player.weapon else C["text_dim"]
        s_col = C["blue"]   if player.shield else C["text_dim"]
        w_name = player.weapon or "sin arma"
        s_name = player.shield or "sin escudo"
        s.blit(self.F["xs"].render(f"[Atk] {w_name}", True, w_col), (x, 7))
        s.blit(self.F["xs"].render(f"[Def] {s_name}", True, s_col), (x, 22))

        # ── Node name (right) ──
        sym = {"village":"[A]","forest":"[B]","cave":"[C]","mountain":"[M]","lake":"[L]"}.get(node_type,"[?]")
        typ = NODE_DISPLAY_NAMES.get(node_type, node_type)
        nl  = self.F["sm"].render(f"{sym} {typ} — {node_name}", True, ncol)
        s.blit(nl, (self.sw - nl.get_width() - 10, 6))

        # ── Instructions (right, small) ──
        it = self.F["xs"].render(instructions, True, C["text_dim"])
        s.blit(it, (self.sw - it.get_width() - 10, 25))


def _item_bonus(weapon_name) -> int:
    if not weapon_name:
        return 0
    from config import ITEMS
    return ITEMS.get(weapon_name, {}).get("bonus", 0)


# ── BottomBar ─────────────────────────────────────────────────────────────────

class BottomBar:
    HEIGHT = 42

    def __init__(self, screen: pygame.Surface, fonts: dict,
                 screen_w: int, screen_h: int):
        self.screen = screen
        self.F      = fonts
        self.rect   = pygame.Rect(0, screen_h - self.HEIGHT, screen_w, self.HEIGHT)

    def draw(self, text: str):
        s = self.screen
        bg = pygame.Surface((self.rect.w, self.HEIGHT), pygame.SRCALPHA)
        bg.fill((6, 6, 16, 215))
        s.blit(bg, (self.rect.x, self.rect.y))
        pygame.draw.line(s, C["border_hi"],
                         (self.rect.x, self.rect.y),
                         (self.rect.right, self.rect.y), 1)
        t = self.F["sm"].render(text, True, C["text_dim"])
        s.blit(t, (self.rect.x + 20,
                   self.rect.y + (self.HEIGHT - t.get_height()) // 2))


# Keep NodeInfoBar class so any remaining references don't crash
class NodeInfoBar:
    HEIGHT = 0   # now integrated into HUD; height is 0

    def __init__(self, *args, **kwargs):
        pass

    def draw(self, *args, **kwargs):
        pass
