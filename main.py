"""
Vertex Valley — main entry point and game state machine.

States
──────
  title     → world
  world     → dijkstra  (player picks destination)
  dijkstra  → travel    (algorithm finishes)
  travel    → explore   (path traversed)
  explore   → combat    (enemy encounter)
            → shop      (enter shop tile)
            → chest     (open chest)
            → world     (exit tile)
  combat    → explore   (victory / fled)
            → game_over (defeat)
  shop      → explore
  chest     → explore
  game_over → title
  win       → title
"""

import sys
import math
import random
import pygame

from config import (
    WIDTH, HEIGHT, FPS, TITLE, C,
    STATE_TITLE, STATE_CHAR_SELECT, STATE_WORLD, STATE_DIJKSTRA, STATE_TRAVEL,
    STATE_EXPLORE, STATE_COMBAT, STATE_SHOP, STATE_CHEST,
    STATE_GAME_OVER, STATE_WIN,
    TILE_SIZE, NODE_DISPLAY_NAMES, NODE_COLORS, ITEMS, CHARACTERS,
)
from core.graph            import WorldGraph
from core.node_map         import TileMap
from core.travel_corridor  import TravelCorridor
from entities.player import Player
from entities.enemy  import make_enemy
from systems.combat  import CombatSystem, CombatResult
from ui.graph_view   import GraphView
from ui.map_view     import MapView
from ui.hud          import HUD, NodeInfoBar, BottomBar
from ui.combat_ui    import CombatUI
from ui.shop_ui      import ShopUI


# ── Font loader ───────────────────────────────────────────────────────────────

def load_fonts() -> dict:
    def f(size, bold=False):
        # Try display-friendly fonts for a polished look
        candidates = (
            ["impact", "arial black", "segoe ui black", "bahnschrift"],  # bold display
            ["consolas", "courier new", "lucida console", "monospace"],  # mono fallback
        )[0 if bold else 1]
        for name in candidates:
            try:
                font = pygame.font.SysFont(name, size, bold=bold)
                if font:
                    return font
            except Exception:
                pass
        return pygame.font.Font(None, size)

    return {
        "title": f(84, bold=True),   # large bold display font
        "lg":    f(30),
        "md":    f(22),
        "sm":    f(17),
        "xs":    f(13),
    }


# ── Travel event generator ────────────────────────────────────────────────────

def _build_travel_events(graph, path: list[int], seed: int) -> list[dict]:
    """Create one event per edge on the travel path."""
    rng    = random.Random(seed ^ hash(tuple(path)))
    events = []
    for i in range(len(path) - 1):
        a, b    = path[i], path[i + 1]
        weight  = graph.get_edge_weight(a, b) or 5
        node    = graph.nodes[b]
        roll    = rng.random()
        diff    = 0.8 + weight * 0.08      # heavier edge = harder enemies

        if roll < 0.45:
            sample_enemy = make_enemy(node.type, diff)
            events.append({
                "type":       "combat",
                "node_type":  node.type,
                "diff":       diff,
                "enemy_name": sample_enemy.name,
                "edge":       (a, b),
            })
        elif roll < 0.65:
            coins = rng.randint(3, 6 + weight)
            events.append({
                "type":  "chest",
                "coins": coins,
                "edge":  (a, b),
            })
        elif roll < 0.75:
            events.append({
                "type": "obstacle",
                "hp":   rng.randint(2, 5),
                "edge": (a, b),
            })
        else:
            events.append({"type": "clear", "edge": (a, b)})
    return events


# ── Main game class ───────────────────────────────────────────────────────────

class Game:

    DIJK_STEP_DELAY = 0.38   # seconds between Dijkstra animation steps
    TRAVEL_MSG_DELAY = 2.2   # seconds per travel event message

    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        # _display  = real pygame window  (changes on fullscreen toggle)
        # screen    = fixed 1280×720 render surface (always this resolution)
        self._display    = pygame.display.set_mode((WIDTH, HEIGHT))
        self.screen      = pygame.Surface((WIDTH, HEIGHT))
        self._fullscreen = False
        self.clock  = pygame.time.Clock()
        self.fonts  = load_fonts()
        self._seed_input   = ""
        self._selected_char = 0          # index into CHARACTERS list
        self._chosen_char   = CHARACTERS[0]
        self._ds_panel_open = False      # toggle with H
        self._setup_new_game(random.randint(1000, 9999))

    def toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            info = pygame.display.Info()
            self._display = pygame.display.set_mode(
                (info.current_w, info.current_h), pygame.FULLSCREEN)
        else:
            self._display = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption(TITLE)

    # ── initialisation ────────────────────────────────────────────────────────

    def _setup_new_game(self, seed: int):
        self.seed   = seed
        self.graph  = WorldGraph(seed)
        self.player = Player(0, 0, character=self._chosen_char)

        self.current_node_id = 0
        self._load_node(0)

        self.state      = STATE_TITLE
        self.state_data: dict = {}

        # UI objects (recreated once per game)
        self.graph_view  = GraphView(self.screen, self.fonts)
        # Map uses the FULL screen — HUD is drawn as overlay on top
        self.map_view    = MapView(
            self.screen, self.fonts,
            pygame.Rect(0, 0, WIDTH, HEIGHT)
        )
        self.hud         = HUD(self.screen, self.fonts, WIDTH, HEIGHT)
        self.bottom_bar  = BottomBar(self.screen, self.fonts, WIDTH, HEIGHT)
        self.combat_ui   = CombatUI(self.screen, self.fonts)
        self.shop_ui     = ShopUI(self.screen, self.fonts)

        self._selected_node : int | None = None
        self._opened_objects: set  = set()
        self._combat: CombatSystem | None = None
        self._anim_t = 0.0

        # Floating notifications
        self._notifs: list[dict] = []

        # ── Travel corridor state ──────────────────────────────────────────────
        self._corridor_dest    : int | None = None   # target node id
        self._enemy_move_timer : float = 0.0         # timer for AI movement

        # ── DAS movement (Delayed Auto Shift) ─────────────────────────────────
        self._move_dir       = (0, 0)
        self._move_timer     = 0.0
        self._move_repeating = False
        self._MOVE_DAS       = 0.20
        self._MOVE_ARR       = 0.07

    def _load_node(self, node_id: int):
        node = self.graph.nodes[node_id]
        node.visited = True
        self.tile_map = TileMap(self.seed, node_id, node.type)
        px, py = self.tile_map.player_start
        self.player.x, self.player.y = px, py
        self._opened_objects = set()
        self.current_node_id = node_id

    # ── main loop ─────────────────────────────────────────────────────────────

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self._anim_t += dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                self._handle_event(event)

            self._update(dt)
            self._draw()

            # Scale render surface to display (supports fullscreen)
            if self._fullscreen:
                scaled = pygame.transform.smoothscale(
                    self.screen, self._display.get_size())
                self._display.blit(scaled, (0, 0))
            else:
                self._display.blit(self.screen, (0, 0))
            pygame.display.flip()

    # ── event dispatch ────────────────────────────────────────────────────────

    def _handle_event(self, event: pygame.event.Event):
        dispatch = {
            STATE_TITLE:       self._ev_title,
            STATE_CHAR_SELECT: self._ev_char_select,
            STATE_WORLD:       self._ev_world,
            STATE_DIJKSTRA:    self._ev_dijkstra,
            STATE_TRAVEL:      self._ev_travel,
            STATE_EXPLORE:     self._ev_explore,
            STATE_COMBAT:      self._ev_combat,
            STATE_SHOP:        self._ev_shop,
            STATE_GAME_OVER:   self._ev_game_over,
            STATE_WIN:         self._ev_game_over,
        }
        dispatch.get(self.state, lambda e: None)(event)

    def _ev_title(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                # Go to character selection first
                self.state = STATE_CHAR_SELECT
            elif e.key == pygame.K_BACKSPACE:
                si = self.state_data.get("seed_input", "")
                self.state_data["seed_input"] = si[:-1]
            elif e.unicode.isdigit() and len(self.state_data.get("seed_input","")) < 8:
                self.state_data.setdefault("seed_input", "")
                self.state_data["seed_input"] += e.unicode

    def _ev_char_select(self, e: pygame.event.Event):
        if e.type != pygame.KEYDOWN:
            return
        if e.key in (pygame.K_LEFT, pygame.K_a):
            self._selected_char = (self._selected_char - 1) % len(CHARACTERS)
        if e.key in (pygame.K_RIGHT, pygame.K_d):
            self._selected_char = (self._selected_char + 1) % len(CHARACTERS)
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._chosen_char = CHARACTERS[self._selected_char]
            seed_str = self.state_data.get("seed_input", "")
            seed = int(seed_str) if seed_str.isdigit() else random.randint(1000, 9999)
            self._setup_new_game(seed)
            # Give starting item
            start_item = self._chosen_char.get("item")
            if start_item:
                self.player.add_item(start_item)
                self.player.use_item(start_item)
            self.state = STATE_EXPLORE
        if e.key == pygame.K_ESCAPE:
            self.state = STATE_TITLE

    def _ev_world(self, e: pygame.event.Event):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            nid = GraphView.get_node_at(self.graph, *e.pos)
            if nid is not None and nid != self.current_node_id:
                self._selected_node = nid
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self._selected_node is not None:
                self._start_dijkstra(self._selected_node)
            if e.key == pygame.K_ESCAPE:
                # Return to map if we came from explore
                self._selected_node = None
                self.state = STATE_EXPLORE
        if e.type == pygame.MOUSEMOTION:
            self.graph_view.hovered = GraphView.get_node_at(self.graph, *e.pos)

    def _ev_dijkstra(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
            # skip animation
            data = self.state_data
            while not (data.get("step") or {}).get("final", False):
                try:
                    data["step"] = next(data["gen"])
                except StopIteration:
                    break
            self._finish_dijkstra()

    def _ev_travel(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._advance_travel()

    def _ev_explore(self, e: pygame.event.Event):
        if e.type != pygame.KEYDOWN:
            return
        key = e.key
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._try_interact()
        if key == pygame.K_k:
            # K = atacar monstruo adyacente
            self._attack_adjacent_monster()
        if key == pygame.K_e:
            self.state_data["show_inv"] = not self.state_data.get("show_inv", False)
        if key == pygame.K_q:
            self._try_open_shop()
        if key == pygame.K_h:
            self._ds_panel_open = not self._ds_panel_open
        if key in (pygame.K_ESCAPE, pygame.K_m):
            if getattr(self.tile_map, 'is_corridor', False):
                self._notify("Completa el corredor para acceder al mapa mundo", C["text_dim"], 1.8)
            else:
                self.state_data.pop("show_inv", None)
                self._selected_node = None
                self.player.is_moving = False
                self.state = STATE_WORLD

    def _ev_combat(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN:
            c = self._combat
            if c and not c.is_finished():
                if e.key == pygame.K_1: self._do_attack()
                if e.key == pygame.K_2: self._do_defend()
                if e.key == pygame.K_3: self._do_flee()
                if e.key == pygame.K_4: self._open_combat_item()
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            btn = self.combat_ui.get_button(*e.pos)
            if btn == "Atacar":   self._do_attack()
            if btn == "Defender": self._do_defend()
            if btn == "Huir":     self._do_flee()
            if btn == "Ítem":     self._open_combat_item()
            c = self._combat
            if c and c.is_finished():
                self._end_combat()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
            c = self._combat
            if c and c.is_finished():
                self._end_combat()

    def _ev_shop(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN:
            if self.shop_ui.handle_key(e.key, self.player):
                self.state = STATE_EXPLORE

    def _ev_chest(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
            self.state = STATE_EXPLORE

    def _ev_game_over(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
            self.state_data = {}
            self.state = STATE_TITLE

    # ── update dispatch ───────────────────────────────────────────────────────

    def _update(self, dt: float):
        self.graph_view.update(dt)
        self.map_view.update(dt)
        self.combat_ui.update(dt)
        self.shop_ui.update(dt)
        self.hud.update(dt)

        # Tick floating notifications
        for n in self._notifs:
            n["t"] -= dt
        self._notifs = [n for n in self._notifs if n["t"] > 0]

        if self.state == STATE_DIJKSTRA:
            self._update_dijkstra(dt)

        if self.state == STATE_EXPLORE:
            self._update_movement(dt)
            self._update_corridor_enemies(dt)

    def _update_corridor_enemies(self, dt: float):
        """Move enemies toward the player every 0.65s while in a corridor."""
        if not getattr(self.tile_map, 'is_corridor', False):
            return
        self._enemy_move_timer += dt
        if self._enemy_move_timer < 0.65:
            return
        self._enemy_move_timer = 0.0

        px, py   = self.player.x, self.player.y
        enemies  = [(c, r) for (c, r), obj in list(self.tile_map.objects.items())
                    if obj == 'enemy']

        for ec, er in enemies:
            dc = 1 if px > ec else (-1 if px < ec else 0)
            dr = 1 if py > er else (-1 if py < er else 0)

            # Try horizontal first (corridor is horizontal), then vertical
            moved = False
            for tdc, tdr in [(dc, 0), (0, dr), (dc, dr)]:
                if tdc == 0 and tdr == 0:
                    continue
                nc, nr = ec + tdc, er + tdr
                if not self.tile_map.is_walkable(nc, nr):
                    continue
                if self.tile_map.get_object(nc, nr) == 'enemy':
                    continue  # blocked by another enemy
                # Move the enemy
                self.tile_map.objects.pop((ec, er))
                if nc == px and nr == py:
                    # Reached the player — trigger combat
                    self.tile_map.objects[(nc, nr)] = 'enemy'
                    self._start_node_combat(nc, nr)
                    return   # only one combat at a time
                self.tile_map.objects[(nc, nr)] = 'enemy'
                moved = True
                break

    def _update_movement(self, dt: float):
        """DAS (Delayed Auto Shift) continuous movement while key is held."""
        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: dx = -1
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]: dx =  1
        if keys[pygame.K_UP]    or keys[pygame.K_w]: dy = -1
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]: dy =  1

        new_dir = (dx, dy)

        if new_dir == (0, 0):
            # No key held — reset state, mark player as not moving
            if self._move_dir != (0, 0):
                self.player.is_moving = False
            self._move_dir       = (0, 0)
            self._move_timer     = 0.0
            self._move_repeating = False
            return

        self.player.is_moving = True

        if new_dir != self._move_dir:
            # Direction changed: move immediately, reset DAS timer
            self._move_dir       = new_dir
            self._move_timer     = 0.0
            self._move_repeating = False
            self._do_player_move(dx, dy)
        else:
            # Same direction — apply DAS
            self._move_timer += dt
            if not self._move_repeating:
                if self._move_timer >= self._MOVE_DAS:
                    self._move_repeating = True
                    self._move_timer     = 0.0
                    self._do_player_move(dx, dy)
            else:
                if self._move_timer >= self._MOVE_ARR:
                    self._move_timer -= self._MOVE_ARR
                    self._do_player_move(dx, dy)

    def _do_player_move(self, dx: int, dy: int):
        moved = self.player.move(dx, dy, self.tile_map)
        if moved:
            self._check_tile_interaction()

    def _update_dijkstra(self, dt: float):
        data = self.state_data
        data["timer"] = data.get("timer", 0.0) + dt
        if data["timer"] >= self.DIJK_STEP_DELAY:
            data["timer"] = 0.0
            try:
                data["step"] = next(data["gen"])
                if data["step"].get("final"):
                    self._finish_dijkstra()
            except StopIteration:
                self._finish_dijkstra()

    # ── draw dispatch ─────────────────────────────────────────────────────────

    def _draw(self):
        self.screen.fill(C["bg"])
        dispatch = {
            STATE_TITLE:       self._draw_title,
            STATE_CHAR_SELECT: self._draw_char_select,
            STATE_WORLD:       self._draw_world,
            STATE_DIJKSTRA:    self._draw_dijkstra,
            STATE_TRAVEL:      self._draw_travel,
            STATE_EXPLORE:     self._draw_explore,
            STATE_COMBAT:      self._draw_combat,
            STATE_SHOP:        self._draw_explore,
            STATE_GAME_OVER:   self._draw_game_over,
            STATE_WIN:         self._draw_win,
        }
        draw_fn = dispatch.get(self.state)
        if draw_fn:
            draw_fn()
        if self.state == STATE_SHOP:
            self.shop_ui.draw(self.player)
        # Data structures panel (H to toggle, always visible in explore/world)
        if self._ds_panel_open or self.state in (STATE_EXPLORE, STATE_WORLD, STATE_DIJKSTRA):
            self._draw_ds_badge()
        if self._ds_panel_open:
            self._draw_ds_panel()
        self._draw_notifications()

    # ── title screen ──────────────────────────────────────────────────────────

    # ── Title-screen helpers ──────────────────────────────────────────────────

    def _title_glow(self, s, text, font, col, cx, cy, glow_r=14):
        """Render text with a multi-pass glow + drop shadow."""
        ts = font.render(text, True, col)
        rect = ts.get_rect(center=(cx, cy))
        # Drop shadow
        sh = font.render(text, True, (0, 0, 0))
        s.blit(sh, rect.move(4, 5))
        # Glow passes (outer → inner)
        for r in range(glow_r, 2, -3):
            alpha = int(110 * (1 - r / glow_r))
            ts.set_alpha(alpha)
            for dx, dy in [(-r,0),(r,0),(0,-r),(0,r),(-r//2,-r//2),(r//2,r//2)]:
                s.blit(ts, rect.move(dx, dy))
        ts.set_alpha(255)
        s.blit(ts, rect)

    def _title_bg_graph(self, s, t):
        """Animated floating graph nodes in the background."""
        from config import NODE_COLORS
        random.seed(3141)
        _types   = ["village","forest","cave","mountain","lake",
                    "forest","mountain","village","cave","lake"]
        _specs   = []
        for i in range(10):
            bx = random.randint(90, WIDTH  - 90)
            by = random.randint(55, HEIGHT - 55)
            nt = _types[i]
            col  = NODE_COLORS.get(nt, C["green_dk"])
            size = random.randint(10, 22)
            sp   = random.uniform(0.18, 0.44)
            ph   = random.uniform(0, 6.28)
            _specs.append((bx, by, col, size, sp, ph))
        random.seed()

        # Animated positions
        pts = [(bx + math.sin(t*sp+ph)*30,
                by + math.cos(t*sp*0.72+ph)*20)
               for bx, by, _, _, sp, ph in _specs]

        # Edges
        edge_s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for i in range(len(pts)):
            for j in range(i+1, len(pts)):
                dx = pts[i][0] - pts[j][0]
                dy = pts[i][1] - pts[j][1]
                dist = (dx*dx + dy*dy) ** 0.5
                if dist < 260:
                    a = int((1 - dist/260) * 32)
                    pygame.draw.line(edge_s, (93, 202, 165, a),
                                     (int(pts[i][0]), int(pts[i][1])),
                                     (int(pts[j][0]), int(pts[j][1])), 1)
        s.blit(edge_s, (0, 0))

        # Nodes
        for i, (ax, ay) in enumerate(pts):
            _, _, col, size, _, _ = _specs[i]
            # Halo
            ha = size * 3
            hs = pygame.Surface((ha*2, ha*2), pygame.SRCALPHA)
            pygame.draw.circle(hs, (*col[:3], 20), (ha, ha), ha)
            s.blit(hs, (int(ax)-ha, int(ay)-ha))
            # Outline + body
            pygame.draw.circle(s, (5, 5, 12), (int(ax), int(ay)), size+2)
            pygame.draw.circle(s, col,        (int(ax), int(ay)), size)
            ring = tuple(min(255, c+65) for c in col[:3])
            pygame.draw.circle(s, ring,       (int(ax), int(ay)), size, 2)

    # ── Title screen ──────────────────────────────────────────────────────────

    def _draw_title(self):
        s  = self.screen
        t  = self._anim_t
        cx = WIDTH // 2

        # ── Background ────────────────────────────────────────────────────────
        s.fill((7, 8, 16))
        # Subtle radial glow at centre
        for rad, alpha in ((500, 10), (350, 10), (200, 8)):
            gs = pygame.Surface((rad*2, rad*2), pygame.SRCALPHA)
            pygame.draw.circle(gs, (25, 45, 70, alpha), (rad, rad), rad)
            s.blit(gs, (cx - rad, HEIGHT//2 - rad))

        # Animated graph in background
        self._title_bg_graph(s, t)

        # ── Title "VERTEX VALLEY" with glow ───────────────────────────────────
        title_y = 108
        self._title_glow(s, "VERTEX VALLEY", self.fonts["title"], C["green"], cx, title_y, glow_r=18)

        # ── Coloured subtitle words ───────────────────────────────────────────
        sub_y = title_y + 80
        words = [("Grafo",      C["green"]),
                 ("  •  ",      C["text_dim"]),
                 ("Dijkstra",   C["blue"]),
                 ("  •  ",      C["text_dim"]),
                 ("AFD",        C["purple"]),
                 ("  •  ",      C["text_dim"]),
                 ("Procedural", C["orange"])]
        pieces = [(self.fonts["md"].render(w, True, c), c) for w, c in words]
        total_w = sum(p.get_width() for p, _ in pieces)
        sx = cx - total_w // 2
        for p, _ in pieces:
            s.blit(p, (sx, sub_y - p.get_height()//2))
            sx += p.get_width()

        # Decorative divider
        div_y = sub_y + 26
        pygame.draw.line(s, C["green_dk"], (cx-280, div_y), (cx+280, div_y), 1)
        for dot_x in (cx-280, cx-140, cx, cx+140, cx+280):
            pygame.draw.circle(s, C["green_dk"], (dot_x, div_y), 3)

        # ── Seed input ────────────────────────────────────────────────────────
        seed_in = self.state_data.get("seed_input", "")
        seed_y  = div_y + 28
        box_r   = pygame.Rect(cx - 215, seed_y, 430, 48)
        box_bg  = pygame.Surface((430, 48), pygame.SRCALPHA)
        box_bg.fill((10, 16, 30, 225))
        s.blit(box_bg, box_r.topleft)
        bc = C["green"] if seed_in else C["border_hi"]
        pygame.draw.rect(s, bc, box_r, 2, border_radius=10)
        lbl = self.fonts["xs"].render("SEMILLA DEL MUNDO", True, C["text_dim"])
        s.blit(lbl, (box_r.x + 12, box_r.y - 17))
        disp = seed_in or "dejar en blanco = mundo aleatorio"
        dc   = C["text_hi"] if seed_in else C["text_dim"]
        dt   = self.fonts["md"].render(disp, True, dc)
        s.blit(dt, (box_r.x + 14, box_r.y + (48 - dt.get_height())//2))
        if seed_in and int(t * 2) % 2 == 0:
            pygame.draw.rect(s, C["green"],
                             (box_r.x + 14 + dt.get_width() + 3, box_r.y + 10, 2, 28))

        # ── Play button (glowing) ─────────────────────────────────────────────
        btn_y   = seed_y + 64
        btn_r   = pygame.Rect(cx - 230, btn_y, 460, 52)
        pulse   = (math.sin(t * 2.5) + 1) / 2
        # Outer glow
        gr      = int(18 + pulse * 10)
        gsurf   = pygame.Surface((btn_r.w + gr*2, btn_r.h + gr*2), pygame.SRCALPHA)
        pygame.draw.rect(gsurf, (*C["green"], int(28 + pulse * 36)),
                         gsurf.get_rect(), border_radius=18)
        s.blit(gsurf, (btn_r.x - gr, btn_r.y - gr))
        # Button face
        btn_bg  = pygame.Surface((btn_r.w, btn_r.h), pygame.SRCALPHA)
        btn_bg.fill((12, 60, 42, 240))
        s.blit(btn_bg, btn_r.topleft)
        pygame.draw.rect(s, C["green"], btn_r, 2, border_radius=10)
        # Bright top edge (bevel)
        pygame.draw.line(s, tuple(min(255,c+80) for c in C["green"]),
                         (btn_r.x+6, btn_r.y+2), (btn_r.right-6, btn_r.y+2), 1)
        # Text — render at sm size so it always fits inside the button
        enter_c = C["green"] if int(t*1.5)%2==0 else tuple(min(255,c+60) for c in C["green"])
        et = self.fonts["md"].render(">>  PRESIONA  ENTER  PARA  JUGAR  <<", True, enter_c)
        # Fallback: if still wider than button, clip to button width
        if et.get_width() > btn_r.w - 16:
            et = self.fonts["sm"].render(">>  PRESIONA  ENTER  PARA  JUGAR  <<", True, enter_c)
        s.blit(et, et.get_rect(center=btn_r.center))

        # ── Info cards ────────────────────────────────────────────────────────
        card_y = btn_y + 74
        CARDS  = [
            ("CONTROLES", C["blue"], [
                ("WASD / Flechas", "moverse por el mapa"),
                ("ENTER / SPACE",  "interactuar (cofres, salidas)"),
                ("E",              "abrir inventario"),
                ("Q",              "abrir tienda cercana"),
                ("M / ESC",        "mapa del mundo (grafo)"),
                ("1 / 2 / 3",      "atacar / defender / huir"),
                ("F11",            "pantalla completa"),
            ]),
            ("FLUJO DE JUEGO", C["orange"], [
                ("Inicio",         "apareces en la Aldea central"),
                ("Explorar",       "WASD por el mapa 2D"),
                ("M o ESC",        "abre el mapa-grafo del mundo"),
                ("Clic + ENTER",   "selecciona destino -> Dijkstra"),
                ("Combate",        "toca el ! o viaja por aristas"),
                ("Victoria",       "llega al nodo final (nodo 8)"),
                ("Semilla",        "mismo numero = mismo mundo"),
            ]),
        ]
        card_w = 390
        gap    = 28
        total_cw = len(CARDS) * card_w + (len(CARDS)-1) * gap
        cx0    = cx - total_cw // 2

        for i, (c_title, c_col, c_items) in enumerate(CARDS):
            card_h = 36 + len(c_items) * 20 + 14
            cr     = pygame.Rect(cx0 + i*(card_w+gap), card_y, card_w, card_h)
            # Background
            bg_ = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            bg_.fill((8, 10, 24, 215))
            s.blit(bg_, cr.topleft)
            # Coloured header strip
            pygame.draw.rect(s, c_col, pygame.Rect(cr.x, cr.y, card_w, 30), border_radius=7)
            pygame.draw.rect(s, tuple(min(255,c+50) for c in c_col),
                             pygame.Rect(cr.x+2, cr.y+1, card_w-4, 12), border_radius=6)
            ct_ = self.fonts["sm"].render(c_title, True, (6, 8, 18))
            s.blit(ct_, ct_.get_rect(center=(cr.x + card_w//2, cr.y + 15)))
            # Border
            pygame.draw.rect(s, c_col, cr, 1, border_radius=8)
            # Items
            for j, (key, val) in enumerate(c_items):
                iy = cr.y + 36 + j * 20
                kt = self.fonts["xs"].render(key, True, c_col)
                vt = self.fonts["xs"].render(val, True, C["text_dim"])
                s.blit(kt, (cr.x + 12, iy))
                s.blit(vt, (cr.x + 12 + kt.get_width() + 8, iy))

        # ── Footer ────────────────────────────────────────────────────────────
        seed_v = self.seed if hasattr(self, "seed") else "?"
        pygame.draw.line(s, C["border"], (40, HEIGHT-42), (WIDTH-40, HEIGHT-42), 1)
        ft = self.fonts["xs"].render(
            f"Semilla actual: {seed_v}    |    "
            "El mismo numero siempre genera el mismo mundo",
            True, C["text_dim"])
        s.blit(ft, ft.get_rect(center=(cx, HEIGHT - 22)))

    # ── world / dijkstra screens ──────────────────────────────────────────────

    def _draw_world(self):
        dijk_data = None
        self.graph_view.draw(
            self.graph, self.current_node_id,
            self._selected_node, dijk_data, None
        )
        if self._selected_node is None:
            hint = "CLIC en un nodo para seleccionar destino   |   ESC: volver al mapa de exploracion"
        else:
            dest = self.graph.nodes[self._selected_node]
            hint = f"Destino: {dest.name}   |   ENTER: confirmar y ejecutar Dijkstra   |   ESC: cancelar"
        self.bottom_bar.draw(hint)

    def _draw_dijkstra(self):
        data = self.state_data
        self.graph_view.draw(
            self.graph, self.current_node_id,
            self._selected_node, data.get("step"),
            data.get("target")
        )
        step = data.get("step", {})
        if step.get("done"):
            hint = "Ruta óptima encontrada.  ESPACIO: continuar"
        else:
            hint = "Ejecutando Dijkstra…  ESPACIO: saltar animación"
        self.bottom_bar.draw(hint)

    # ── travel screen ─────────────────────────────────────────────────────────

    def _draw_travel(self):
        s    = self.screen
        data = self.state_data
        t    = self._anim_t
        cx   = WIDTH // 2

        # ── 1. Perspective tunnel corridor background ─────────────────────────
        self._draw_tunnel_corridor(s, t)

        # ── 2. Route map strip (top) ──────────────────────────────────────────
        # Semi-transparent route bar
        route_bg = pygame.Surface((WIDTH, 88), pygame.SRCALPHA)
        route_bg.fill((6, 6, 14, 210))
        s.blit(route_bg, (0, 0))

        path  = data.get("path", [])
        evt_i = data.get("event_index", 0)

        title_col = C["orange"]
        title = self.fonts["sm"].render("RECORRIDO  (Dijkstra):", True, C["text_dim"])
        s.blit(title, (20, 10))

        # Path nodes in strip
        node_spacing = min(110, (WIDTH - 80) // max(1, len(path)))
        nx_start     = cx - (len(path) - 1) * node_spacing // 2
        for i, nid in enumerate(path):
            node = self.graph.nodes[nid]
            nc   = NODE_COLORS.get(node.type, C["green"])
            x    = nx_start + i * node_spacing
            done = i < evt_i + 1
            r    = 18 if done else 14
            bg   = nc if done else (28, 28, 42)
            pygame.draw.circle(s, bg, (x, 44), r)
            pygame.draw.circle(s, nc, (x, 44), r, 2)
            # Current edge progress marker
            if i == evt_i and i < len(path) - 1:
                pulse = (math.sin(t * 5) + 1) / 2
                pygame.draw.circle(s, tuple(min(255,c+100) for c in nc), (x, 44), r + int(pulse*5), 2)
            nt = self.fonts["xs"].render(node.name[:9], True, nc if done else C["text_dim"])
            s.blit(nt, nt.get_rect(center=(x, 44 + r + 9)))
            if i < len(path) - 1:
                w   = self.graph.get_edge_weight(nid, path[i+1]) or 0
                lc  = C["dijk_path"] if done else (50, 50, 70)
                lw  = 3 if done else 1
                pygame.draw.line(s, lc, (x + r, 44), (x + node_spacing - r, 44), lw)
                wt  = self.fonts["xs"].render(f"w={w}", True, lc)
                s.blit(wt, (x + r + 4, 36))

        pygame.draw.line(s, C["border_hi"], (0, 88), (WIDTH, 88), 1)

        # ── 3. Event panel (centre screen) ────────────────────────────────────
        events = data.get("events", [])
        if evt_i < len(events):
            ev   = events[evt_i]
            msg, ev_col = self._event_description(ev)
            self._draw_event_panel(s, t, ev, msg, ev_col, cx)
        else:
            # Arrived!
            dest = self.graph.nodes[path[-1]]
            self._draw_arrival_panel(s, t, dest, cx)

        # ── 4. Mini-HUD ───────────────────────────────────────────────────────
        self._draw_mini_hud(s, 30, HEIGHT - 58)

    def _draw_tunnel_corridor(self, s, t):
        """3-D perspective stone corridor — background for the travel screen."""
        s.fill((8, 6, 5))
        cx, cy = WIDTH // 2, HEIGHT // 2 + 60

        # Vanishing-point rings (back → front)
        for i in range(10, 0, -1):
            ratio = i / 10.0
            hw    = int(WIDTH  * 0.52 * ratio)
            hh    = int(HEIGHT * 0.42 * ratio)
            x0, y0 = cx - hw, cy - hh
            br = int(10 + (1 - ratio) * 55)
            col = (br, br - 2, br - 4)
            pygame.draw.rect(s, col, (x0, y0, hw*2, hh*2), 3)
            # Floor tiles inside the ring
            if ratio < 0.6:
                pygame.draw.line(s, (br+8, br+6, br+4),
                                 (x0, y0 + hh*2), (x0 + hw*2, y0 + hh*2), 1)

        # Floor (dark trapezoid)
        pygame.draw.polygon(s, (22, 18, 15), [
            (0, HEIGHT), (WIDTH, HEIGHT),
            (cx + int(WIDTH*0.52), cy + int(HEIGHT*0.42)),
            (cx - int(WIDTH*0.52), cy + int(HEIGHT*0.42)),
        ])
        # Floor grid lines
        for fi in range(6):
            fy  = cy + int(HEIGHT * 0.42) + fi * (HEIGHT - cy - int(HEIGHT*0.42)) // 6
            fw  = int(WIDTH * 0.52) + fi * (WIDTH//2 - int(WIDTH*0.52)) // 6
            pygame.draw.line(s, (32, 28, 24),
                             (cx - fw, fy), (cx + fw, fy), 1)
        # Perspective lines on floor
        for fv in range(-5, 6, 2):
            ex = cx + fv * (WIDTH // 10)
            pygame.draw.line(s, (28, 24, 20),
                             (cx, cy + int(HEIGHT*0.42)),
                             (ex, HEIGHT), 1)

        # Ceiling (dark trapezoid)
        pygame.draw.polygon(s, (18, 14, 12), [
            (0, 88), (WIDTH, 88),
            (cx + int(WIDTH*0.52), cy - int(HEIGHT*0.42)),
            (cx - int(WIDTH*0.52), cy - int(HEIGHT*0.42)),
        ])

        # Left and right walls
        for side in (-1, 1):
            wx  = cx + side * int(WIDTH * 0.52)
            wpts = [(cx + side * WIDTH//2, 88), (wx, cy - int(HEIGHT*0.42)),
                    (wx, cy + int(HEIGHT*0.42)), (cx + side * WIDTH//2, HEIGHT)]
            pygame.draw.polygon(s, (28, 24, 20), wpts)
            # Wall brick lines
            for bi in range(6):
                by = cy - int(HEIGHT*0.42) + bi * (int(HEIGHT*0.84)) // 6
                bx_inner = wx
                bx_outer = cx + side * WIDTH // 2
                mix = bi / 6
                bx  = int(bx_inner + (bx_outer - bx_inner) * mix)
                pygame.draw.line(s, (38, 33, 28), (bx_inner, by), (bx, HEIGHT if by > cy else 88), 1)

        # Animated torches on side walls
        for tx, ty in ((int(cx - WIDTH*0.38), cy - 20), (int(cx + WIDTH*0.38), cy - 20)):
            self._draw_torch(s, tx, ty, t)

        # Atmospheric fog / end glow (vanishing point)
        fog = pygame.Surface((300, 180), pygame.SRCALPHA)
        fa  = int(18 + math.sin(t*0.7)*8)
        pygame.draw.ellipse(fog, (70, 110, 80, fa), fog.get_rect())
        s.blit(fog, (cx - 150, cy - 90))

    def _draw_event_panel(self, s, t, ev, msg, ev_col, cx):
        """Floating event card in the middle of the tunnel."""
        cy   = HEIGHT // 2 + 30
        pw, ph = 540, 160
        pr   = pygame.Rect(cx - pw//2, cy - ph//2, pw, ph)

        # Panel
        bg   = pygame.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill((8, 6, 12, 230))
        s.blit(bg, pr.topleft)
        pulse = (math.sin(t * 3) + 1) / 2
        border_col = tuple(min(255, c + int(pulse*50)) for c in ev_col)
        pygame.draw.rect(s, border_col, pr, 2, border_radius=10)

        # Event type icon strip
        icon_map = {"combat": "! COMBATE !", "chest": "$ COFRE $",
                    "obstacle": "~ OBSTACULO ~", "clear": ". CAMINO LIBRE ."}
        icon_txt = icon_map.get(ev.get("type",""), "?")
        it = self.fonts["sm"].render(icon_txt, True, ev_col)
        pygame.draw.rect(s, ev_col, pygame.Rect(pr.x, pr.y, pw, 28), border_radius=9)
        pygame.draw.rect(s, (6,4,10), pygame.Rect(pr.x, pr.y+14, pw, 14), border_radius=9)
        s.blit(it, it.get_rect(center=(cx, pr.y + 14)))

        # Main message
        mt = self.fonts["md"].render(msg, True, C["text_hi"])
        s.blit(mt, mt.get_rect(center=(cx, pr.y + 70)))

        # Prompt
        blink_col = C["text_dim"] if int(t*2)%2==0 else C["text"]
        pt = self.fonts["sm"].render("ENTER / ESPACIO  para continuar", True, blink_col)
        s.blit(pt, pt.get_rect(center=(cx, pr.y + 118)))

    def _draw_arrival_panel(self, s, t, dest, cx):
        """Arrival panel when all travel events are cleared."""
        cy = HEIGHT // 2 + 30
        dc = NODE_COLORS.get(dest.type, C["green"])
        pw, ph = 460, 130
        pr = pygame.Rect(cx - pw//2, cy - ph//2, pw, ph)
        bg = pygame.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill((6, 20, 12, 235))
        s.blit(bg, pr.topleft)
        pulse = (math.sin(t * 2.5) + 1) / 2
        pygame.draw.rect(s, dc, pr, 2, border_radius=10)
        pygame.draw.rect(s, tuple(min(255,c+80) for c in dc),
                         pygame.Rect(pr.x+1, pr.y+1, pw-2, 3), border_radius=9)
        at = self.fonts["lg"].render(f"Llegaste a {dest.name}!", True, dc)
        s.blit(at, at.get_rect(center=(cx, cy - 18)))
        ht = self.fonts["sm"].render("ENTER para explorar el nuevo nodo", True, C["text_dim"])
        s.blit(ht, ht.get_rect(center=(cx, cy + 22)))

    def _event_description(self, ev: dict) -> tuple[str, tuple]:
        t = ev["type"]
        if t == "combat":
            return f"¡Un {ev.get('enemy_name', 'monstruo')} bloquea el camino!", C["red"]
        if t == "chest":
            return f"Encuentras un cofre: +{ev['coins']} monedas", C["gold"]
        if t == "obstacle":
            return f"Un obstáculo te hiere: -{ev['hp']} HP", C["orange"]
        return "El camino está despejado.", C["green"]

    def _draw_mini_hud(self, s, x, y):
        hp_t  = self.fonts["sm"].render(
            f"HP {self.player.hp}/{self.player.max_hp}   $ {self.player.coins} monedas", True, C["text"])
        pygame.draw.rect(s, C["panel"], (x - 10, y - 8, hp_t.get_width() + 20, 36), border_radius=6)
        s.blit(hp_t, (x, y))

    # ── explore screen ────────────────────────────────────────────────────────

    def _draw_explore(self):
        node = self.graph.nodes[self.current_node_id]
        in_corridor = getattr(self.tile_map, 'is_corridor', False)

        self.map_view.center_camera(self.player.x, self.player.y, self.tile_map)
        self.map_view.draw(self.tile_map, self.player, self._opened_objects)

        if in_corridor:
            # Show progress bar and corridor-specific HUD
            dest = self.graph.nodes[self._corridor_dest] if self._corridor_dest is not None else node
            dest_name = f"Corredor -> {dest.name}"
            prog = self.player.x / max(1, self.tile_map.cols - 1)
            self.hud.draw(self.player, dest_name, self.tile_map.node_type,
                          f"WASD:avanzar  ENTER:actuar  [{int(prog*100)}% recorrido]")
            self._draw_corridor_progress(prog)
        else:
            self.hud.draw(
                self.player, node.name, node.type,
                "WASD:mover  ENTER:actuar  E:inv  Q:tienda  M/ESC:mapa  F11:pantalla-completa"
            )
        if self.state_data.get("show_inv"):
            self._draw_inventory()

    def _draw_corridor_progress(self, progress: float):
        """Thin progress bar at bottom showing how far through the corridor the player is."""
        s  = self.screen
        bw = WIDTH - 40
        bh = 6
        bx, by = 20, HEIGHT - 10
        pygame.draw.rect(s, (30, 28, 26), (bx, by, bw, bh), border_radius=3)
        fw = max(0, int(bw * progress))
        if fw:
            col = C["green"] if progress < 0.85 else C["gold"]
            pygame.draw.rect(s, col, (bx, by, fw, bh), border_radius=3)
        pygame.draw.rect(s, C["border_hi"], (bx, by, bw, bh), 1, border_radius=3)
        # End marker
        pygame.draw.rect(s, C["gold"], (bx + bw - 4, by - 2, 4, bh + 4), border_radius=2)

    def _draw_inventory(self):
        s  = self.screen
        sw, sh = s.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((5, 5, 15, 180))
        s.blit(overlay, (0, 0))

        pw, ph = 400, 360
        px, py = (sw - pw) // 2, (sh - ph) // 2
        panel  = pygame.Rect(px, py, pw, ph)
        pygame.draw.rect(s, C["panel"], panel, border_radius=12)
        pygame.draw.rect(s, C["purple"], panel, 2, border_radius=12)

        t = self.fonts["lg"].render("Inventario", True, C["purple"])
        s.blit(t, (px + 20, py + 14))

        iy = py + 52
        if not self.player.inventory:
            empty = self.fonts["md"].render("(vacío)", True, C["text_dim"])
            s.blit(empty, (px + 20, iy))
        else:
            for name, qty in self.player.inventory.items():
                item = ITEMS.get(name, {})
                lt = self.fonts["md"].render(f"{name} x{qty}  — {item.get('desc','')}", True, C["text"])
                s.blit(lt, (px + 20, iy)); iy += 30

        ft = self.fonts["xs"].render("TAB cerrar   U+nombre usar ítem", True, C["text_dim"])
        s.blit(ft, (px + 20, py + ph - 28))

    # ── combat screen ─────────────────────────────────────────────────────────

    def _draw_combat(self):
        self._draw_arena_backdrop()
        self.combat_ui.draw(self._combat, self.player)

    def _draw_arena_backdrop(self):
        """Tiled stone dungeon floor as combat background."""
        s    = self.screen
        node = self.graph.nodes[self.current_node_id]
        t    = self._anim_t

        # Biome-themed floor colours
        _ARENA = {
            "cave":     ((50, 46, 44), (40, 36, 34)),
            "forest":   ((32, 60, 26), (26, 48, 20)),
            "mountain": ((62, 58, 54), (50, 46, 42)),
            "lake":     ((26, 50, 100), (20, 40, 80)),
            "village":  ((52, 48, 44), (42, 38, 34)),
        }
        c1, c2 = _ARENA.get(node.type, ((50, 46, 44), (40, 36, 34)))

        # Tiled floor
        for row in range(HEIGHT // 32 + 1):
            for col in range(WIDTH // 32 + 1):
                sx, sy = col * 32, row * 32
                col_pick = c1 if (col + row) % 2 == 0 else c2
                pygame.draw.rect(s, col_pick, (sx, sy, 32, 32))
                pygame.draw.rect(s, (28, 25, 24), (sx, sy, 32, 32), 1)

        # Vignette (darker edges for atmosphere)
        for dist, alpha in [(80, 60), (50, 80), (25, 100)]:
            vig = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(vig, (0, 0, 0, alpha),
                             pygame.Rect(0, 0, dist, HEIGHT))
            pygame.draw.rect(vig, (0, 0, 0, alpha),
                             pygame.Rect(WIDTH - dist, 0, dist, HEIGHT))
            pygame.draw.rect(vig, (0, 0, 0, alpha),
                             pygame.Rect(0, 0, WIDTH, dist))
            pygame.draw.rect(vig, (0, 0, 0, alpha),
                             pygame.Rect(0, HEIGHT - dist, WIDTH, dist))
            s.blit(vig, (0, 0))

        # Animated torches on the walls (top)
        for tx in (160, 640, 1120):
            self._draw_torch(s, tx, 18, t)

    def _draw_torch(self, surf, x, y, t):
        # Wall mount
        pygame.draw.rect(surf, (88, 60, 22), (x - 3, y, 6, 14), border_radius=2)
        # Flame shape
        fw  = 9 + int(math.sin(t * 8.5) * 2)
        fh  = 15 + int(math.sin(t * 9.2 + 1) * 4)
        col = (255, 195, 50) if int(t * 7) % 2 == 0 else (255, 115, 30)
        pygame.draw.polygon(surf, col, [
            (x,       y - fh),
            (x - fw // 2, y),
            (x + fw // 2, y),
        ])
        # Inner bright
        pygame.draw.polygon(surf, (255, 240, 180), [
            (x,          y - fh + 4),
            (x - fw // 4, y - 4),
            (x + fw // 4, y - 4),
        ])
        # Glow halo
        gs    = pygame.Surface((60, 60), pygame.SRCALPHA)
        gal   = int(55 + math.sin(t * 6) * 20)
        pygame.draw.circle(gs, (255, 190, 60, gal), (30, 30), 30)
        surf.blit(gs, (x - 30, y - 30))

    # ── chest popup ───────────────────────────────────────────────────────────

    def _draw_chest_popup(self):
        s   = self.screen
        data = self.state_data
        sw, sh = s.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((5, 5, 15, 190))
        s.blit(overlay, (0, 0))

        pw, ph = 420, 260
        px, py = (sw - pw) // 2, (sh - ph) // 2
        panel  = pygame.Rect(px, py, pw, ph)
        pygame.draw.rect(s, C["panel"], panel, border_radius=12)
        pygame.draw.rect(s, C["gold"], panel, 2, border_radius=12)

        t = self.fonts["lg"].render("[COFRE]", True, C["gold"])
        s.blit(t, t.get_rect(center=(sw // 2, py + 36)))

        coins = data.get("coins", 0)
        item  = data.get("item")
        if coins:
            ct = self.fonts["md"].render(f"+{coins} monedas", True, C["gold"])
            s.blit(ct, ct.get_rect(center=(sw // 2, py + 90)))
        if item:
            it2 = self.fonts["md"].render(f"Encontraste: {item}", True, C["cyan"])
            s.blit(it2, it2.get_rect(center=(sw // 2, py + 122)))

        ft = self.fonts["sm"].render("ENTER — cerrar", True, C["text_dim"])
        s.blit(ft, ft.get_rect(center=(sw // 2, py + ph - 30)))

    # ── game over / win ───────────────────────────────────────────────────────

    def _draw_game_over(self):
        s  = self.screen
        cx, cy = WIDTH // 2, HEIGHT // 2
        t  = self.fonts["title"].render("DERROTA", True, (200, 40, 40))
        s.blit(t, t.get_rect(center=(cx, cy - 80)))
        sub = self.fonts["lg"].render(
            f"Llegaste al nivel {self.player.level}   $ {self.player.coins} monedas",
            True, C["text"])
        s.blit(sub, sub.get_rect(center=(cx, cy)))
        ft = self.fonts["md"].render("ENTER — volver al menú", True, C["text_dim"])
        s.blit(ft, ft.get_rect(center=(cx, cy + 60)))

    def _draw_win(self):
        s  = self.screen
        t  = self._anim_t
        cx, cy = WIDTH // 2, HEIGHT // 2
        # Rainbow hue cycle
        hue = (t * 60) % 360
        col = pygame.Color(0)
        col.hsva = (hue, 80, 100, 100)
        wt = self.fonts["title"].render("¡VICTORIA!", True, col)
        s.blit(wt, wt.get_rect(center=(cx, cy - 90)))
        sub = self.fonts["lg"].render(
            f"Semilla: {self.seed}   Nivel {self.player.level}   $ {self.player.coins} monedas",
            True, C["gold"])
        s.blit(sub, sub.get_rect(center=(cx, cy - 20)))
        for i, line in enumerate([
            "Completaste Vertex Valley usando Dijkstra para navegar el grafo",
            "y un AFD para controlar los estados de combate.",
        ]):
            lt = self.fonts["md"].render(line, True, C["text_dim"])
            s.blit(lt, lt.get_rect(center=(cx, cy + 40 + i * 28)))
        ft = self.fonts["md"].render("ENTER — menú principal", True, C["text_dim"])
        s.blit(ft, ft.get_rect(center=(cx, cy + 120)))

    # ── Character select screen ───────────────────────────────────────────────

    def _draw_char_select(self):
        from ui.map_view import draw_character
        s  = self.screen
        cx, cy = WIDTH // 2, HEIGHT // 2
        t  = self._anim_t
        s.fill((8, 8, 18))
        # Animated bg dots
        random.seed(99)
        for i in range(60):
            sx = random.randint(0, WIDTH); sy = random.randint(0, HEIGHT)
            br = int((math.sin(t*1.5+i)*0.5+0.5)*80)+30
            pygame.draw.circle(s,(br,br,br//2),(sx,sy),1)
        random.seed()
        # Title
        self._title_glow(s,"ELIGE TU PERSONAJE",self.fonts["title"],C["green"],cx,100,16)
        hint=self.fonts["sm"].render("Flechas: cambiar   ENTER: confirmar   ESC: volver",True,C["text_dim"])
        s.blit(hint,hint.get_rect(center=(cx,148)))
        # Characters
        card_w, card_h = 360, 420
        spacing = 80
        total   = len(CHARACTERS)*card_w + (len(CHARACTERS)-1)*spacing
        x0 = cx - total//2
        for i, char in enumerate(CHARACTERS):
            cx2 = x0 + i*(card_w+spacing) + card_w//2
            cy2 = cy + 30
            sel = (i == self._selected_char)
            cr  = pygame.Rect(cx2-card_w//2, cy2-card_h//2, card_w, card_h)
            bg  = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            bg.fill((10,12,28,220))
            s.blit(bg, cr.topleft)
            col = char["shirt"] if sel else C["border_hi"]
            pygame.draw.rect(s, col, cr, 3 if sel else 1, border_radius=12)
            if sel:
                gs = pygame.Surface((card_w+20,card_h+20),pygame.SRCALPHA)
                pygame.draw.rect(gs,(*col[:3],30),gs.get_rect(),border_radius=16)
                s.blit(gs,(cr.x-10,cr.y-10))
            # Character sprite (big)
            spr_x, spr_y = cx2, cr.y+90
            draw_character(s, spr_x, spr_y, t if sel else 0.0,
                           is_moving=sel, facing=(0,1),
                           shirt_col=char["shirt"],hair_col=char["hair"],
                           pants_col=char.get("pants",(35,44,112)))
            # Name
            nt = self.fonts["lg"].render(char["name"],True,col)
            s.blit(nt,nt.get_rect(center=(cx2, cr.y+130)))
            # Desc
            for di,dl in enumerate(char["desc"].split("\n")):
                dt = self.fonts["sm"].render(dl,True,C["text_dim"])
                s.blit(dt,dt.get_rect(center=(cx2, cr.y+160+di*22)))
            # Stats bars
            stats = [("HP",char["hp"],50,C["hp_bar"]),("ATK",char["attack"],20,C["orange"]),
                     ("DEF",char["defense"],20,C["blue"])]
            sy_ = cr.y + 220
            for label,val,mx,sc in stats:
                lt = self.fonts["xs"].render(f"{label} {val}",True,sc)
                s.blit(lt,(cr.x+20, sy_))
                bw = card_w-50
                pygame.draw.rect(s,(30,30,42),(cr.x+80,sy_,bw,10),border_radius=4)
                fw = int(bw*val/mx)
                pygame.draw.rect(s,sc,(cr.x+80,sy_,fw,10),border_radius=4)
                sy_ += 26
            # Special
            spt = self.fonts["sm"].render(char["special"],True,C["gold"])
            s.blit(spt,spt.get_rect(center=(cx2,cr.y+330)))
            # SELECCIONADO indicator
            if sel:
                st2 = self.fonts["md"].render("[ SELECCIONADO ]",True,col)
                s.blit(st2,st2.get_rect(center=(cx2,cr.bottom-30)))

    # ── Data Structures panel ─────────────────────────────────────────────────

    def _draw_ds_badge(self):
        """Tiny badge bottom-right — always visible during gameplay."""
        s   = self.screen
        txt = self.fonts["xs"].render("H = Estructuras de datos", True, C["text_dim"])
        bg  = pygame.Surface((txt.get_width()+14, txt.get_height()+6), pygame.SRCALPHA)
        bg.fill((8,8,20,180))
        pygame.draw.rect(bg, C["border"], bg.get_rect(), 1, border_radius=3)
        s.blit(bg,  (WIDTH-bg.get_width()-6, HEIGHT-bg.get_height()-6))
        s.blit(txt, (WIDTH-txt.get_width()-13, HEIGHT-txt.get_height()-9))

    def _draw_ds_panel(self):
        """Full data structures panel — press H to toggle."""
        s  = self.screen
        pw, ph = 560, 420
        px, py = WIDTH-pw-10, HEIGHT//2-ph//2
        bg = pygame.Surface((pw,ph),pygame.SRCALPHA)
        bg.fill((6,8,20,238))
        s.blit(bg,(px,py))
        pygame.draw.rect(s,C["green"],pygame.Rect(px,py,pw,ph),2,border_radius=10)
        pygame.draw.rect(s,C["green"],pygame.Rect(px,py,pw,36),border_radius=10)
        pygame.draw.rect(s,(6,8,20),pygame.Rect(px,py+18,pw,18))
        t_=self.fonts["md"].render("ESTRUCTURAS DE DATOS APLICADAS",True,(6,8,20))
        s.blit(t_,t_.get_rect(center=(px+pw//2,py+18)))
        entries = [
            ("Grafo",       "Lista de adyacencia",  f"{len(self.graph.nodes)} nodos, {sum(len(v) for v in self.graph.adj.values())//2} aristas", C["green"]),
            ("Dijkstra",    "Cola de prioridad",    "Min-heap (heapq Python)", C["blue"]),
            ("Combate",     "AFD - Automata Finito","5 estados, 9 transiciones delta", C["purple"]),
            ("Mapas 2D",    "Tabla hash",           "seed ^ (node_id * 31) — reproducible", C["orange"]),
            ("Inventario",  "Diccionario Python",   "O(1) lookup, dinamico", C["gold"]),
            ("Corredor",    "Generacion procedural","TravelCorridor seeded — linear O(n)", C["cyan"]),
            ("Monstruos",   "Patron Strategy",      "draw_fn por bioma — polimorfismo", C["red"]),
        ]
        y = py + 46
        for name, struct, detail, col in entries:
            pygame.draw.rect(s, (*col[:3], 25), pygame.Rect(px+8, y, pw-16, 44), border_radius=5)
            pygame.draw.rect(s, col, pygame.Rect(px+8, y, 4, 44), border_radius=2)
            nt = self.fonts["sm"].render(f"{name}: {struct}", True, col)
            dt = self.fonts["xs"].render(detail, True, C["text_dim"])
            s.blit(nt, (px+18, y+5))
            s.blit(dt, (px+18, y+25))
            y += 50
        ft = self.fonts["xs"].render("H para cerrar", True, C["text_dim"])
        s.blit(ft, ft.get_rect(center=(px+pw//2, py+ph-16)))

    # ── K key: attack adjacent monster ───────────────────────────────────────

    def _attack_adjacent_monster(self):
        c, r = self.player.x, self.player.y
        for dc, dr in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
            nc, nr = c+dc, r+dr
            obj = self.tile_map.get_object(nc, nr)
            if obj == "enemy" and (nc, nr) not in self._opened_objects:
                self._start_node_combat(nc, nr)
                return
        self._notify("No hay monstruos cerca. (K para atacar)", C["text_dim"], 1.2)

    # ── game logic helpers ────────────────────────────────────────────────────

    def _start_dijkstra(self, target: int):
        gen = self.graph.dijkstra_steps(self.current_node_id, target)
        self.state_data = {
            "target": target,
            "gen":    gen,
            "step":   None,
            "timer":  0.0,
        }
        self.state = STATE_DIJKSTRA

    def _finish_dijkstra(self):
        data   = self.state_data
        step   = data.get("step", {})
        path   = step.get("path", [self.current_node_id, data["target"]])
        target = path[-1]

        # Total weight of path → determines corridor length and difficulty
        total_w = sum(
            self.graph.get_edge_weight(path[i], path[i+1]) or 1
            for i in range(len(path) - 1)
        )

        # Build the travel corridor
        src_type  = self.graph.nodes[self.current_node_id].type
        dest_type = self.graph.nodes[target].type
        corridor  = TravelCorridor(
            seed         = self.seed ^ hash(tuple(path)),
            total_weight = total_w,
            source_type  = src_type,
            dest_type    = dest_type,
        )

        # Load corridor as the active map
        self._corridor_dest    = target
        self._enemy_move_timer = 0.0
        self.tile_map          = corridor
        px, py                 = corridor.player_start
        self.player.x, self.player.y = px, py
        self._opened_objects   = set()
        self.player.is_moving  = False
        self._selected_node    = None
        self.state_data        = {}

        dest = self.graph.nodes[target]
        self._notify(f"Corredor -> {dest.name}  |  llega al final!", C["orange"], 3.5)
        self.state = STATE_EXPLORE

    def _advance_travel(self):
        data  = self.state_data
        events = data.get("events", [])
        idx    = data.get("event_index", 0)

        if idx >= len(events):
            # Travel complete — load destination
            path   = data["path"]
            target = path[-1]
            self._load_node(target)
            self._selected_node = None
            node   = self.graph.nodes[target]
            # Win condition: reach node 8 (the final node)
            if target == len(self.graph.nodes) - 1:
                self.state = STATE_WIN
            else:
                self.state = STATE_EXPLORE
            return

        ev = events[idx]
        data["event_index"] = idx + 1

        if ev["type"] == "combat":
            self._start_travel_combat(ev, data)
        elif ev["type"] == "chest":
            coins = ev["coins"]
            self.player.coins += coins
            # Travel event chest: just show in message, no popup
        elif ev["type"] == "obstacle":
            self.player.take_damage(ev["hp"])
            if not self.player.is_alive():
                self.state = STATE_GAME_OVER

    def _start_travel_combat(self, ev: dict, travel_data: dict):
        enemy = make_enemy(ev["node_type"], ev.get("diff", 1.0))
        self._combat   = CombatSystem(self.player, enemy)
        self.state_data = {**travel_data, "post_combat_state": STATE_TRAVEL}
        self.state = STATE_COMBAT

    def _check_tile_interaction(self):
        c, r = self.player.x, self.player.y
        obj  = self.tile_map.get_object(c, r)
        if obj == "exit":
            self.player.is_moving = False
            if getattr(self.tile_map, 'is_corridor', False):
                self._arrive_at_destination()   # fin del corredor → nodo destino
            else:
                self._exit_to_nearest()         # salida del nodo → auto-iniciar viaje
        elif obj == "chest" and (c, r) not in self._opened_objects:
            self._open_chest(c, r)
        elif obj == "enemy" and (c, r) not in self._opened_objects:
            self._start_node_combat(c, r)

    def _start_node_combat(self, c: int, r: int):
        self._opened_objects.add((c, r))
        self.tile_map.remove_object(c, r)
        self.player.is_moving = False
        node  = self.graph.nodes[self.current_node_id]
        enemy = make_enemy(node.type, 1.0 + self.player.level * 0.08)
        self._combat   = CombatSystem(self.player, enemy)
        self.state_data = {"post_combat_state": STATE_EXPLORE}
        self.state = STATE_COMBAT

    def _exit_to_nearest(self):
        """Pisar >> carga el corredor de inmediato — sin pantalla de Dijkstra."""
        adj = self.graph.adj.get(self.current_node_id, [])
        if not adj:
            self._notify("Sin conexiones desde este nodo.", C["text_dim"])
            return

        # Elegir destino: primero no visitados, luego el más cercano
        unvisited = sorted((w, nb) for nb, w in adj if not self.graph.nodes[nb].visited)
        all_adj   = sorted((w, nb) for nb, w in adj)
        weight, target = (unvisited + all_adj)[0]

        # Cargar el corredor DIRECTAMENTE (sin Dijkstra en pantalla)
        src_type  = self.graph.nodes[self.current_node_id].type
        dest_type = self.graph.nodes[target].type
        corridor  = TravelCorridor(
            seed         = self.seed ^ hash((self.current_node_id, target)),
            total_weight = weight,
            source_type  = src_type,
            dest_type    = dest_type,
        )

        self._corridor_dest    = target
        self._enemy_move_timer = 0.0
        self.tile_map          = corridor
        px, py                 = corridor.player_start
        self.player.x, self.player.y = px, py
        self._opened_objects   = set()
        self.player.is_moving  = False
        self._selected_node    = None
        self.state_data        = {}

        dest = self.graph.nodes[target]
        self._notify(f"Corredor hacia {dest.name} — pelea o esquiva!", C["orange"], 3.0)
        self.state = STATE_EXPLORE

    def _arrive_at_destination(self):
        """Final del corredor — cargar el nodo destino."""
        target = self._corridor_dest
        if target is None:
            return
        self._load_node(target)
        dest = self.graph.nodes[target]
        self._notify(f"Llegaste a {dest.name}!", C["green"], 3.5)
        self._corridor_dest = None
        if target == len(self.graph.nodes) - 1:
            self.state = STATE_WIN
        else:
            self.state = STATE_EXPLORE

    def _try_interact(self):
        """ENTER/SPACE — interactuar con cofres y tiendas adyacentes.
        Los exits se manejan solos al pisarlos (_check_tile_interaction).
        """
        c, r = self.player.x, self.player.y
        in_corridor = getattr(self.tile_map, 'is_corridor', False)
        obj = self.tile_map.get_object(c, r)

        # Cofre en la misma posición
        if obj == "chest" and (c, r) not in self._opened_objects:
            self._open_chest(c, r); return

        # Objetos adyacentes
        for dc, dr in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            ao = self.tile_map.get_object(c + dc, r + dr)
            if ao == "chest" and (c+dc, r+dr) not in self._opened_objects:
                self._open_chest(c+dc, r+dr); return
            if ao == "shop" and not in_corridor:
                self.state = STATE_SHOP; return

    def _try_open_shop(self):
        """Q — open shop if one is nearby."""
        c, r = self.player.x, self.player.y
        for dc, dr in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)):
            if self.tile_map.get_object(c+dc, r+dr) == "shop":
                self.state = STATE_SHOP
                return
        self._notify("No hay tienda cerca.", C["text_dim"], 1.5)

    def _open_chest(self, c: int, r: int):
        rng   = random.Random(self.seed ^ (c * 97 + r * 31) ^ self.current_node_id)
        coins = rng.randint(5, 22)
        item  = rng.choice(["Pocion", "Pocion+", "Espada", "Escudo", None, None, None])
        self.player.coins += coins
        if item:
            self.player.add_item(item)
        self._opened_objects.add((c, r))
        self.tile_map.remove_object(c, r)
        # Small floating notifications — no big popup
        self._notify(f"+{coins} monedas", C["gold"], 2.2)
        if item:
            self._notify(f"Encontraste: {item}", C["cyan"], 3.0)

    def _notify(self, text: str, col: tuple | None = None, duration: float = 2.5):
        if col is None:
            col = C["gold"]
        self._notifs.insert(0, {"text": text, "col": col, "t": duration, "max": duration})
        del self._notifs[6:]   # cap at 6

    def _draw_notifications(self):
        s = self.screen
        for i, n in enumerate(self._notifs):
            ratio  = n["t"] / n["max"]
            alpha  = int(min(1.0, ratio * 4) * 255)
            fly_y  = int((1.0 - ratio) * 22)
            text_s = self.fonts["md"].render(n["text"], True, n["col"])
            bw     = text_s.get_width() + 22
            bh     = text_s.get_height() + 8
            bg     = pygame.Surface((bw, bh), pygame.SRCALPHA)
            bg.fill((8, 8, 20, min(alpha, 200)))
            pygame.draw.rect(bg, (*n["col"][:3], min(alpha, 230)),
                             bg.get_rect(), 1, border_radius=5)
            x = WIDTH // 2 - bw // 2
            y = HUD.BAR_HEIGHT + 10 + i * 36 - fly_y
            bg.set_alpha(alpha)
            s.blit(bg, (x, y))
            text_s.set_alpha(alpha)
            s.blit(text_s, (x + 11, y + 4))

    # ── combat action helpers ─────────────────────────────────────────────────

    def _do_attack(self):
        c = self._combat
        if c and not c.is_finished():
            prev_hp = c.enemy.hp
            c.player_attack()
            dmg = prev_hp - c.enemy.hp
            self.combat_ui.trigger_hit(max(0, dmg), hit_player=False)
            if c.is_finished():
                self._end_combat()

    def _do_defend(self):
        c = self._combat
        if c and not c.is_finished():
            c.player_defend()

    def _do_flee(self):
        c = self._combat
        if c and not c.is_finished():
            c.player_flee()
            if c.is_finished():
                self._end_combat()

    def _open_combat_item(self):
        cbt = self._combat
        if not cbt or cbt.is_finished():
            return
        # Priority: combat items first, then potions
        for name in list(self.player.inventory):
            item = ITEMS.get(name, {})
            if item.get("type") == "combat":
                dmg = self.player.use_item(name)
                if isinstance(dmg, int):
                    actual = cbt.enemy.take_damage(dmg)
                    cbt.log.add(f"Usas {name}: -{actual} HP al enemigo!", (220, 80, 80))
                    self.combat_ui.trigger_hit(actual, hit_player=False)
                    if not cbt.enemy.is_alive():
                        from core.afd import A
                        cbt.afd.transition(A.ENEMY_DIED)
                        cbt._resolve_victory()
                        self._end_combat()
                return
        for name in list(self.player.inventory):
            item = ITEMS.get(name, {})
            if item.get("type") == "potion":
                self.player.use_item(name)
                cbt.log.add(f"Usas {name}: +{item['bonus']} HP", (80, 220, 140))
                return
        cbt.log.add("No tienes items utiles.", C["text_dim"])

    def _end_combat(self):
        c = self._combat
        if c is None:
            return
        post = self.state_data.get("post_combat_state", STATE_EXPLORE)
        if c.result == CombatResult.DEFEAT:
            self.state = STATE_GAME_OVER
        else:
            # Restore pre-combat state_data if traveling
            if post == STATE_TRAVEL:
                # Keep travel data intact
                self.state = STATE_TRAVEL
            else:
                self.state = STATE_EXPLORE
        self._combat = None

    # ── node encounter ────────────────────────────────────────────────────────

    def _maybe_spawn_encounter(self):
        """Random enemy encounter when entering an explore node (not village)."""
        node = self.graph.nodes[self.current_node_id]
        if node.type == "village":
            return
        if random.random() < 0.3:
            enemy = make_enemy(node.type, 1.0)
            self._combat   = CombatSystem(self.player, enemy)
            self.state_data = {"post_combat_state": STATE_EXPLORE}
            self.state = STATE_COMBAT


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    game = Game()
    game.run()
