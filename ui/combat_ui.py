"""
Combat screen: enemy area, log, player controls, AFD diagram.
"""
import math
import pygame
from config import C
from core.afd import S, DELTA


class CombatUI:
    # Layout constants
    ENEMY_PANEL = pygame.Rect(0,   0,  760, 660)
    AFD_PANEL   = pygame.Rect(760, 0,  520, 660)
    LOG_RECT    = pygame.Rect(20,  380, 720, 170)
    BTN_Y       = 570
    BTNS        = [
        ("Atacar",   pygame.Rect(30,  570, 180, 52), C["red"],        C["red_dk"]),
        ("Defender", pygame.Rect(220, 570, 180, 52), C["blue"],       C["blue_dk"]),
        ("Huir",     pygame.Rect(410, 570, 180, 52), C["gold"],       C["gold_dk"]),
        ("Ítem",     pygame.Rect(600, 570, 140, 52), C["green"],      C["green_dk"]),
    ]

    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen   = screen
        self.F        = fonts
        self._anim_t  = 0.0
        self._shake   = 0.0
        self._flash   = 0.0
        self._last_dmg: tuple | None = None   # (value, is_player, timer)

    # ── public ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        self._anim_t += dt
        self._shake   = max(0.0, self._shake  - dt * 8)
        self._flash   = max(0.0, self._flash  - dt * 3)
        if self._last_dmg:
            v, ip, tm = self._last_dmg
            tm -= dt
            self._last_dmg = (v, ip, tm) if tm > 0 else None

    def trigger_hit(self, dmg: int, hit_player: bool):
        self._shake = 0.15 if hit_player else 0.08
        self._flash = 0.4  if hit_player else 0.2
        self._last_dmg = (dmg, hit_player, 1.2)

    def draw(self, combat, player):
        self._draw_left(combat, player)
        self._draw_right_afd(combat)
        if self._flash > 0:
            surf = pygame.Surface((760, 660), pygame.SRCALPHA)
            alpha = int(self._flash * 80)
            col   = (180, 40, 40, alpha) if True else (40, 80, 180, alpha)
            surf.fill(col)
            self.screen.blit(surf, (0, 0))

    def get_button(self, mx: int, my: int) -> str | None:
        for label, rect, *_ in self.BTNS:
            if rect.collidepoint(mx, my):
                return label
        return None

    # ── left panel ────────────────────────────────────────────────────────────

    def _draw_left(self, combat, player):
        s = self.screen
        # Semi-transparent panel so arena backdrop shows through
        lp = pygame.Surface((760, 660), pygame.SRCALPHA)
        lp.fill((8, 8, 16, 220))
        s.blit(lp, (0, 0))

        # Header
        hdr = pygame.Surface((760, 56), pygame.SRCALPHA)
        hdr.fill((18, 18, 28, 235))
        s.blit(hdr, (0, 0))
        pygame.draw.line(s, C["border_hi"], (0, 56), (760, 56), 1)
        pygame.draw.line(s, C["border_hi"], (0, 56), (760, 56), 1)
        ht = self.F["md"].render("[ COMBATE ]", True, C["red"])
        s.blit(ht, (20, 14))
        st = self.F["sm"].render(f"AFD estado actual: {combat.afd_state()}", True, C["text_dim"])
        s.blit(st, (200, 20))

        # Enemy name + HP
        e = combat.enemy
        self._draw_bar(s, 20, 70, 380, 22, e.hp_ratio, C["hp_bar"], C["hp_bg"],
                       f"{e.name}   {e.hp}/{e.max_hp} HP")

        # Enemy sprite (ASCII art box + animation)
        shake_off = int(self._shake * 6 * math.sin(self._anim_t * 40)) if self._shake > 0 else 0
        self._draw_enemy_sprite(e.name, 380 + shake_off, 100, 340)

        # Floating damage number
        if self._last_dmg:
            v, ip, tm = self._last_dmg
            alpha_t = min(1.0, tm)
            dy      = int((1.2 - tm) * 30)
            col     = C["red"] if ip else C["gold"]
            dt      = self.F["lg"].render(f"-{v}", True, col)
            surf    = pygame.Surface(dt.get_size(), pygame.SRCALPHA)
            surf.set_alpha(int(255 * alpha_t))
            surf.blit(dt, (0, 0))
            pos = (550 + shake_off, 160 + dy) if not ip else (200, 430 + dy)
            s.blit(surf, pos)

        # Log
        pygame.draw.rect(s, C["panel"], self.LOG_RECT, border_radius=6)
        pygame.draw.rect(s, C["border"], self.LOG_RECT, 1, border_radius=6)
        lx, ly = self.LOG_RECT.x + 10, self.LOG_RECT.y + 8
        for line in combat.log.lines:
            lt = self.F["sm"].render(line.text, True, line.color)
            s.blit(lt, (lx, ly))
            ly += 18

        # Player HP
        self._draw_bar(s, 20, 540, 360, 18, player.hp_ratio, C["hp_bar"], C["hp_bg"],
                       f"Tu HP: {player.hp}/{player.max_hp}")
        self._draw_bar(s, 20, 562, 360, 10, player.exp_ratio, C["exp_bar"], C["exp_bg"],
                       f"Nv.{player.level}")

        # Buttons
        mx, my = pygame.mouse.get_pos()
        for label, rect, col_hi, col_lo in self.BTNS:
            hovered = rect.collidepoint(mx, my)
            bg      = col_lo if hovered else (col_lo[0]//2, col_lo[1]//2, col_lo[2]//2)
            pygame.draw.rect(s, bg, rect, border_radius=8)
            pygame.draw.rect(s, col_hi if hovered else col_lo, rect, 2, border_radius=8)
            bt = self.F["md"].render(label, True, col_hi)
            s.blit(bt, bt.get_rect(center=rect.center))

    def _draw_enemy_sprite(self, name: str, cx: int, cy: int, size: int):
        """Draw a stylised enemy box with pseudo-sprite."""
        s   = self.screen
        t   = self._anim_t
        hw  = size // 2
        hh  = int(size * 0.65)
        r   = pygame.Rect(cx - hw, cy, size, int(size * 1.3))

        # glow
        glow = pygame.Surface((size + 40, int(size * 1.3) + 40), pygame.SRCALPHA)
        gc   = (200, 50, 50, 20 + int(15 * math.sin(t * 2)))
        pygame.draw.ellipse(glow, gc, glow.get_rect())
        s.blit(glow, (r.x - 20, r.y - 20))

        # body
        bob = int(math.sin(t * 1.8) * 4)
        pygame.draw.rect(s, (80, 25, 25), r.move(0, bob), border_radius=18)
        pygame.draw.rect(s, (160, 50, 50), r.move(0, bob), 2, border_radius=18)

        # Eyes
        ey = cy + int(size * 0.25) + bob
        for ex_off in (-hw // 3, hw // 3):
            ec = (255, 220, 50) if math.sin(t * 3 + ex_off) > -0.7 else (80, 20, 20)
            pygame.draw.circle(s, ec, (cx + ex_off, ey), 10)
            pygame.draw.circle(s, (20, 5, 5), (cx + ex_off + 2, ey + 2), 5)

        # Name tag
        nt = self.F["lg"].render(name, True, (220, 80, 80))
        s.blit(nt, nt.get_rect(center=(cx, cy + int(size * 1.35) + bob + 10)))

    def _draw_bar(self, surf, x, y, w, h, ratio, fill, bg, label):
        pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=4)
        fw = max(0, int(w * ratio))
        if fw:
            pygame.draw.rect(surf, fill, (x, y, fw, h), border_radius=4)
        pygame.draw.rect(surf, C["border_hi"], (x, y, w, h), 1, border_radius=4)
        lt = self.F["xs"].render(label, True, C["text"])
        surf.blit(lt, (x + 5, y + (h - lt.get_height()) // 2))

    # ── right panel: AFD diagram ───────────────────────────────────────────────

    def _draw_right_afd(self, combat):
        s   = self.screen
        rx  = self.AFD_PANEL.x
        rp  = pygame.Surface((520, 660), pygame.SRCALPHA)
        rp.fill((12, 10, 22, 225))
        s.blit(rp, (rx, 0))
        pygame.draw.rect(s, C["border"], self.AFD_PANEL, 1)

        y   = 14
        lbl = self.F["md"].render("AFD — Autómata de Combate", True, C["purple"])
        s.blit(lbl, (rx + 16, y)); y += 32

        sub = self.F["xs"].render(
            "Sólo las transiciones del alfabeto δ son válidas.", True, C["text_dim"])
        s.blit(sub, (rx + 16, y)); y += 20

        cur_state = combat.afd_state()

        # Draw states as circles in a vertical column
        STATE_ORDER = [S.IDLE, S.PLAYER_TURN, S.ENEMY_TURN, S.VICTORY, S.DEFEAT, S.FLED]
        STATE_LABELS = {
            S.IDLE:        "idle",
            S.PLAYER_TURN: "player_turn  ← TU TURNO",
            S.ENEMY_TURN:  "enemy_turn   ← TURNO ENEMIGO",
            S.VICTORY:     "victory  [WIN]",
            S.DEFEAT:      "defeat   [LOSE]",
            S.FLED:        "fled     [HUID]",
        }
        STATE_COLS = {
            S.IDLE:        C["text_dim"],
            S.PLAYER_TURN: C["green"],
            S.ENEMY_TURN:  C["red"],
            S.VICTORY:     C["gold"],
            S.DEFEAT:      (180, 30, 30),
            S.FLED:        C["cyan"],
        }
        node_pos = {}
        y += 10
        for st in STATE_ORDER:
            col    = STATE_COLS[st]
            active = st == cur_state
            nx, ny = rx + 50, y

            if active:
                pygame.draw.circle(s, col, (nx, ny + 8), 18)
                pygame.draw.circle(s, (255, 255, 255), (nx, ny + 8), 18, 2)
            else:
                pygame.draw.circle(s, (35, 35, 50), (nx, ny + 8), 14)
                pygame.draw.circle(s, col, (nx, ny + 8), 14, 1)

            lt = self.F["sm"].render(STATE_LABELS[st], True, col if active else C["text_dim"])
            s.blit(lt, (nx + 24, ny))
            node_pos[st] = (nx, ny + 8)
            y += 52

        # Transitions text
        y += 10
        pygame.draw.line(s, C["border"], (rx + 16, y), (rx + 504, y), 1); y += 10
        tl = self.F["sm"].render("Transiciones disponibles:", True, C["text_label"])
        s.blit(tl, (rx + 16, y)); y += 22

        valid = [a for (st, a) in DELTA if st == cur_state]
        for a_sym in valid:
            next_st = DELTA[(cur_state, a_sym)]
            tt = self.F["xs"].render(
                f"  δ({cur_state}, {a_sym!r}) → {next_st}", True, C["green"])
            s.blit(tt, (rx + 16, y)); y += 16

        # History
        y += 10
        pygame.draw.line(s, C["border"], (rx + 16, y), (rx + 504, y), 1); y += 10
        hl = self.F["sm"].render("Historial de transiciones:", True, C["text_label"])
        s.blit(hl, (rx + 16, y)); y += 20
        for prev, act, nxt in combat.afd.history[-6:]:
            ht = self.F["xs"].render(f"  {prev} +[{act}]→ {nxt}", True, C["text_dim"])
            s.blit(ht, (rx + 16, y)); y += 15
