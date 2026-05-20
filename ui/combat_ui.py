"""
Combat screen: enemy area, log, player controls, AFD diagram.
"""
import math
import pygame
from config import C
from core.afd import S, DELTA
from entities import werewolf_sprite as _wws
from entities import troll_sprite    as _trs
from entities import slime_sprite    as _sls


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
        """Draw enemy sprite — usa sprite sheet para Hombre Lobo, Troll y Slime."""
        if name == "Hombre Lobo":
            self._draw_werewolf_combat(cx, cy, size)
            return
        if name == "Troll":
            self._draw_troll_combat(cx, cy, size)
            return
        if name == "Slime":
            self._draw_slime_combat(cx, cy, size)
            return

        s   = self.screen
        t   = self._anim_t
        hw  = size // 2
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

    def _draw_werewolf_combat(self, cx: int, cy: int, size: int):
        """Renderiza al Hombre Lobo en la pantalla de combate usando el sprite sheet."""
        s  = self.screen
        t  = self._anim_t
        sw = int(size * 0.78)   # tamaño del sprite en pantalla

        # Ciclo de animaciones: rest → charge → attack → rest (6 seg)
        cycle = t % 6.0
        if self._shake > 0.05:
            anim = "scream"
        elif cycle < 2.0:
            anim = "rest"
        elif cycle < 3.0:
            anim = "going_for_attack"
        elif cycle < 5.0:
            anim = "attack"
        else:
            anim = "rest"

        surf = _wws.frame_for_t(anim, t, sw, sw)
        if surf is not None:
            # Glow rojo detrás del sprite
            glow = pygame.Surface((sw + 60, sw + 60), pygame.SRCALPHA)
            ga   = 18 + int(12 * math.sin(t * 2))
            pygame.draw.ellipse(glow, (200, 50, 50, ga), glow.get_rect())
            s.blit(glow, (cx - sw // 2 - 30, cy - sw // 4 - 30))
            s.blit(surf, (cx - sw // 2, cy - sw // 4))
            nt = self.F["lg"].render("Hombre Lobo", True, (220, 80, 80))
            s.blit(nt, nt.get_rect(center=(cx, cy + sw * 3 // 4 + 14)))
            return

        # Fallback si el PNG no está disponible: caja genérica con nombre
        hw  = size // 2
        r   = pygame.Rect(cx - hw, cy, size, int(size * 1.3))
        bob = int(math.sin(t * 1.8) * 4)
        glow = pygame.Surface((size + 40, int(size * 1.3) + 40), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (200, 50, 50, 22), glow.get_rect())
        s.blit(glow, (r.x - 20, r.y - 20))
        pygame.draw.rect(s, (60, 30, 15), r.move(0, bob), border_radius=18)
        pygame.draw.rect(s, (180, 80, 30), r.move(0, bob), 2, border_radius=18)
        ey = cy + int(size * 0.25) + bob
        for ex_off in (-hw // 3, hw // 3):
            pygame.draw.circle(s, (255, 160, 20), (cx + ex_off, ey), 10)
            pygame.draw.circle(s, (20, 5, 5),     (cx + ex_off + 2, ey + 2), 5)
        nt = self.F["lg"].render("Hombre Lobo", True, (220, 100, 40))
        s.blit(nt, nt.get_rect(center=(cx, cy + int(size * 1.35) + bob + 10)))

    # ── helpers: pick animation based on recent hit direction ─────────────────

    def _combat_anim(self, idle: str, attack: str, hurt: str) -> str:
        """Returns the appropriate animation name based on last combat event."""
        if self._last_dmg:
            _val, hit_player, timer = self._last_dmg
            if timer > 0.65:
                return attack if hit_player else hurt
        return idle

    # ── Troll ─────────────────────────────────────────────────────────────────

    def _draw_troll_combat(self, cx: int, cy: int, size: int):
        s   = self.screen
        t   = self._anim_t
        sw  = int(size * 0.65)          # display size — Troll is big

        anim = self._combat_anim("idle", "attack", "hurt")
        surf = _trs.frame_for_t(anim, t, sw, sw)

        if surf is not None:
            glow = pygame.Surface((sw + 60, sw + 60), pygame.SRCALPHA)
            ga   = 16 + int(10 * math.sin(t * 1.8))
            pygame.draw.ellipse(glow, (140, 90, 40, ga), glow.get_rect())
            s.blit(glow, (cx - sw // 2 - 30, cy - sw // 4 - 30))
            s.blit(surf, (cx - sw // 2, cy - sw // 4))
            nt = self.F["lg"].render("Troll", True, (180, 120, 60))
            s.blit(nt, nt.get_rect(center=(cx, cy + sw * 3 // 4 + 14)))
            return

        # Fallback procedural
        hw  = size // 2
        r   = pygame.Rect(cx - hw, cy, size, int(size * 1.2))
        bob = int(math.sin(t * 1.4) * 5)
        pygame.draw.rect(s, (90, 55, 25), r.move(0, bob), border_radius=14)
        pygame.draw.rect(s, (160, 100, 50), r.move(0, bob), 2, border_radius=14)
        nt = self.F["lg"].render("Troll", True, (180, 120, 60))
        s.blit(nt, nt.get_rect(center=(cx, cy + int(size * 1.3) + bob)))

    # ── Slime ─────────────────────────────────────────────────────────────────

    def _draw_slime_combat(self, cx: int, cy: int, size: int):
        s   = self.screen
        t   = self._anim_t
        # Slime frames are wide + short: display as wide rectangle
        sw_w = int(size * 0.72)         # display width
        sw_h = int(sw_w * 0.42)         # ~42 % height keeps natural aspect

        anim = self._combat_anim("idle", "attack", "hurt")
        surf = _sls.frame_for_t(anim, t, sw_w, sw_h)

        if surf is not None:
            glow = pygame.Surface((sw_w + 40, sw_h + 40), pygame.SRCALPHA)
            ga   = 14 + int(8 * math.sin(t * 2.2))
            pygame.draw.ellipse(glow, (60, 160, 40, ga), glow.get_rect())
            # Position: centre the sprite, sit it on "ground" near centre of panel
            sx = cx - sw_w // 2
            sy = cy + int(size * 0.25)
            s.blit(glow, (sx - 20, sy - 20))
            s.blit(surf, (sx, sy))
            nt = self.F["lg"].render("Slime", True, (80, 200, 60))
            s.blit(nt, nt.get_rect(center=(cx, sy + sw_h + 14)))
            return

        # Fallback procedural
        hw  = size // 2
        bob = int(math.sin(t * 2.5) * 3)
        r   = pygame.Rect(cx - hw, cy + int(size * 0.4), size, int(size * 0.5))
        pygame.draw.ellipse(s, (40, 130, 30), r.move(0, bob))
        pygame.draw.ellipse(s, (80, 200, 60), r.move(0, bob), 2)
        nt = self.F["lg"].render("Slime", True, (80, 200, 60))
        s.blit(nt, nt.get_rect(center=(cx, r.bottom + bob + 10)))

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
