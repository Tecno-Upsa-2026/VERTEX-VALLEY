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
    STATE_EXPLORE, STATE_COMBAT, STATE_SHOP, STATE_CHEST, STATE_EVENT,
    STATE_GAME_OVER, STATE_WIN,
    TILE_SIZE, NODE_DISPLAY_NAMES, NODE_COLORS, ITEMS, CHARACTERS,
)
from core.graph            import WorldGraph
from core.node_map         import TileMap
from core.travel_corridor  import TravelCorridor
from entities.player import Player
from entities.enemy  import make_enemy, make_werewolf
from systems.combat  import CombatSystem, CombatResult
from ui.graph_view   import GraphView
from ui.map_view     import MapView
from ui.hud          import HUD, NodeInfoBar, BottomBar
from ui.combat_ui    import CombatUI
from ui.shop_ui      import ShopUI
from ui.minimap      import Minimap
from ui.weather      import WeatherSystem


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
        self._seed_input    = ""
        self._selected_char = 0
        self._chosen_char   = CHARACTERS[0]
        self._ds_panel_open = False
        self._logo_surf     = self._load_logo()

        # ── Audio ──────────────────────────────────────────────────────────────
        import sounds as _snd
        self._sfx       = _snd.init()   # dict or None if unavailable
        self._cur_music = None          # track name currently playing
        if self._sfx:
            self._play_music('village')

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

        # UI objects must exist before _load_node (which calls weather.setup)
        self.graph_view  = GraphView(self.screen, self.fonts)
        self.map_view    = MapView(
            self.screen, self.fonts,
            pygame.Rect(0, 0, WIDTH, HEIGHT)
        )
        self.hud         = HUD(self.screen, self.fonts, WIDTH, HEIGHT)
        self.bottom_bar  = BottomBar(self.screen, self.fonts, WIDTH, HEIGHT)
        self.combat_ui   = CombatUI(self.screen, self.fonts)
        self.shop_ui     = ShopUI(self.screen, self.fonts)
        self.minimap     = Minimap(self.screen, self.fonts)
        self.weather     = WeatherSystem(WIDTH, HEIGHT)

        self.current_node_id = 0
        self._load_node(0)

        self.state      = STATE_TITLE
        self.state_data: dict = {}

        self._selected_node  : int | None  = None
        self._show_minimap   : bool        = False
        self._pending_event  : dict | None = None
        self._opened_objects: set  = set()
        self._traveled_edges: set  = set()   # (min,max) pairs of traveled graph edges
        self._corridor_path:  list = []       # full path of current corridor
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

        # ── Combat-on-map system ──────────────────────────────────────────────────
        self._map_enemies:  dict  = {}   # (c,r) -> Enemy — HP persistente entre hits
        self._hit_effects:  list  = []   # números de daño flotantes
        self._hurt_tiles:   list  = []   # [(tc,tr,timer,color)] flashes de daño

        # ── Walk particles ─────────────────────────────────────────────────────
        self._walk_particles:  list  = []
        self._footstep_timer:  float = 0.0
        self._enemy_move_timer: float = 0.0  # mover en TODOS los mapas

    def _load_node(self, node_id: int):
        node = self.graph.nodes[node_id]
        is_first = not node.visited
        node.visited = True
        self.tile_map = TileMap(self.seed, node_id, node.type)
        px, py = self.tile_map.player_start
        self.player.x, self.player.y = px, py
        self._opened_objects = set()
        self._map_enemies    = {}
        self._hit_effects    = []
        self.current_node_id = node_id
        self.weather.setup(node_id, self.seed, node.type)
        if is_first:
            self._pending_event = self._roll_node_event(node_id, node.type)

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
            STATE_EVENT:       self._ev_event,
            STATE_GAME_OVER:   self._ev_game_over,
            STATE_WIN:         self._ev_game_over,
        }
        dispatch.get(self.state, lambda e: None)(event)

    def _ev_title(self, e: pygame.event.Event):
        # Controls overlay open — ESC or click closes it
        if self.state_data.get("show_controls"):
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.state_data["show_controls"] = False
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self.state_data["show_controls"] = False
            return

        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.state = STATE_CHAR_SELECT
            elif e.key == pygame.K_BACKSPACE:
                si = self.state_data.get("seed_input", "")
                self.state_data["seed_input"] = si[:-1]
            elif e.unicode.isdigit() and len(self.state_data.get("seed_input", "")) < 8:
                self.state_data.setdefault("seed_input", "")
                self.state_data["seed_input"] += e.unicode

        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            btns = getattr(self, "_title_btns", {})
            if btns.get("start", pygame.Rect(0, 0, 0, 0)).collidepoint(e.pos):
                self.state = STATE_CHAR_SELECT
            elif btns.get("controls", pygame.Rect(0, 0, 0, 0)).collidepoint(e.pos):
                self.state_data["show_controls"] = True
            elif btns.get("quit", pygame.Rect(0, 0, 0, 0)).collidepoint(e.pos):
                pygame.quit()
                sys.exit()

    def _ev_char_select(self, e: pygame.event.Event):
        if e.type != pygame.KEYDOWN:
            return
        # Block input while animation plays
        if getattr(self, '_char_select_anim', None):
            return
        if e.key in (pygame.K_LEFT, pygame.K_a):
            self._selected_char = (self._selected_char - 1) % len(CHARACTERS)
        if e.key in (pygame.K_RIGHT, pygame.K_d):
            self._selected_char = (self._selected_char + 1) % len(CHARACTERS)
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            # Save chosen character and pending seed — setup happens AFTER animation
            self._chosen_char    = CHARACTERS[self._selected_char]
            seed_str = self.state_data.get("seed_input", "")
            self._pending_seed   = int(seed_str) if seed_str.isdigit() else random.randint(1000, 9999)
            self._char_select_anim = {"timer": 2.2, "max": 2.2}
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
            self._quick_attack()
        if key == pygame.K_e:
            self.state_data["show_inv"] = not self.state_data.get("show_inv", False)
        if key == pygame.K_q:
            self._try_open_shop()
        if key == pygame.K_h:
            self._ds_panel_open = not self._ds_panel_open
        if key == pygame.K_TAB:
            self._show_minimap = not self._show_minimap
        if key in (pygame.K_ESCAPE, pygame.K_m):
            self._show_minimap = False
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
        self.minimap.update(dt)
        self.weather.update(dt)

        # Tick floating notifications
        for n in self._notifs:
            n["t"] -= dt
        self._notifs = [n for n in self._notifs if n["t"] > 0]

        # Tick hit effects (floating damage numbers + burst)
        for ef in self._hit_effects:
            ef["t"] -= dt
        self._hit_effects = [ef for ef in self._hit_effects if ef["t"] > 0]

        # Tick character select animation and transition when done
        if self.state == STATE_CHAR_SELECT:
            anim = getattr(self, '_char_select_anim', None)
            if anim:
                anim["timer"] -= dt
                if anim["timer"] <= 0:
                    self._char_select_anim = None
                    self._setup_new_game(self._pending_seed)
                    start_item = self._chosen_char.get("item")
                    if start_item:
                        self.player.add_item(start_item)
                        self.player.use_item(start_item)
                    self.state = STATE_EXPLORE

        if self.state == STATE_DIJKSTRA:
            self._update_dijkstra(dt)

        if self.state == STATE_EXPLORE:
            self._update_movement(dt)
            self._update_map_enemies(dt)    # todos los mapas, no solo corredor
            self._update_music()
            # Walk particles
            for p in self._walk_particles:
                p['life'] -= dt
                p['oy']   += p['voy'] * dt * 60
                p['ox']   += p['vox'] * dt * 30
            self._walk_particles = [p for p in self._walk_particles if p['life'] > 0]
            # Hurt tile flashes (enemy hit / player hit)
            for h in self._hurt_tiles:
                h[2] -= dt
            self._hurt_tiles = [h for h in self._hurt_tiles if h[2] > 0]

    def _update_map_enemies(self, dt: float):
        """
        Mueve los monstruos hacia el jugador en CUALQUIER mapa.
        Aggro range: 12 tiles. Intervalo: 0.6s.
        Cuando alcanza al jugador → auto-ataque directo (sin menú).
        """
        self._enemy_move_timer += dt
        interval = 0.5 if getattr(self.tile_map, 'is_corridor', False) else 0.75
        if self._enemy_move_timer < interval:
            return
        self._enemy_move_timer = 0.0

        px, py  = self.player.x, self.player.y
        enemies = [(c, r, obj) for (c, r), obj in list(self.tile_map.objects.items())
                   if obj in ('enemy', 'werewolf')]

        for ec, er, etype in enemies:
            dist = abs(ec - px) + abs(er - py)
            if dist > 12:
                continue   # fuera del rango de aggro

            dc = 1 if px > ec else (-1 if px < ec else 0)
            dr = 1 if py > er else (-1 if py < er else 0)

            for tdc, tdr in [(dc, 0), (0, dr), (dc, dr)]:
                if tdc == 0 and tdr == 0:
                    continue
                nc, nr = ec + tdc, er + tdr
                if not self.tile_map.is_walkable(nc, nr):
                    continue
                if self.tile_map.get_object(nc, nr) in ('enemy', 'werewolf'):
                    continue
                self.tile_map.objects.pop((ec, er))
                if nc == px and nr == py:
                    # Alcanzó al jugador — preservar tipo al mover
                    self.tile_map.objects[(nc, nr)] = etype
                    self._enemy_auto_attack(nc, nr)
                    return
                self.tile_map.objects[(nc, nr)] = etype
                break

    # mantenemos alias para no romper referencias antiguas
    _update_corridor_enemies = _update_map_enemies

    def _enemy_auto_attack(self, ec: int, er: int):
        """El monstruo alcanza al jugador y lo golpea directamente."""
        if self.tile_map.get_object(ec, er) == 'werewolf':
            self._start_werewolf_combat(ec, er)
            return

        ntype = getattr(self.tile_map, 'node_type',
                        self.graph.nodes[self.current_node_id].type)
        key = (ec, er)
        if key not in self._map_enemies:
            self._map_enemies[key] = make_enemy(ntype, 1.0 + self.player.level * 0.08)

        enemy = self._map_enemies[key]
        raw   = enemy.deal_damage()
        dmg   = self.player.take_damage(raw)
        self._play_sfx('hit_player')
        self.combat_ui._shake = 0.14

        # Número de daño sobre el jugador
        vp   = self.map_view.viewport
        px_s = vp.x + (self.player.x - self.map_view.cam_c)*TILE_SIZE + TILE_SIZE//2
        py_s = vp.y + (self.player.y - self.map_view.cam_r)*TILE_SIZE - 4
        self._hit_effects.append({"x": px_s, "y": py_s, "dmg": dmg,
                                   "col": C["red"], "t": 1.2, "max": 1.2})
        # Flash rojo en el tile del jugador
        self._hurt_tiles.append([self.player.x, self.player.y, 0.28, (220, 40, 40)])

        self._notify(f"  {enemy.name} te ataca: -{dmg} HP", C["red"], 1.0)
        if not self.player.is_alive():
            self.state = STATE_GAME_OVER

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
            self._spawn_walk_dust()
            # Footstep sound every ~2 tiles
            self._footstep_timer += 1
            if self._footstep_timer >= 2:
                self._footstep_timer = 0
                self._play_sfx('footstep')

    # ── Audio helpers ─────────────────────────────────────────────────────────

    def _play_sfx(self, name: str):
        if not self._sfx:
            return
        try:
            snd = self._sfx.get(name)
            if snd:
                snd.play()
        except Exception:
            pass

    def _play_music(self, track: str):
        if not self._sfx or track == self._cur_music:
            return
        try:
            music_buf = self._sfx['_music'].get(track)
            if music_buf:
                music_buf.seek(0)
                pygame.mixer.music.load(music_buf)
                pygame.mixer.music.set_volume(0.38)
                pygame.mixer.music.play(-1)   # loop forever
                self._cur_music = track
        except Exception:
            pass

    def _enemies_nearby(self, radius: int = 7) -> bool:
        """Retorna True si hay algún enemigo a ≤ radius tiles (distancia Manhattan)."""
        px, pr = self.player.x, self.player.y
        for (ec, er), obj in self.tile_map.objects.items():
            if obj == 'enemy':
                if abs(ec - px) + abs(er - pr) <= radius:
                    return True
        # También cuenta los enemigos persistentes del sistema K-attack
        for (ec, er) in self._map_enemies:
            if abs(ec - px) + abs(er - pr) <= radius:
                return True
        return False

    def _update_music(self):
        """
        Música dinámica de 3 niveles:
          danger  — enemigo a ≤ 7 tiles (terror, tempo alto, disonante)
          dungeon — corredor / cueva / montaña  (oscuro)
          village — aldea / bosque / lago       (alegre)
        """
        if not self._sfx:
            return
        if self._enemies_nearby(7):
            self._play_music('danger')
            return
        in_corridor = getattr(self.tile_map, 'is_corridor', False)
        ntype = getattr(self.tile_map, 'node_type',
                        self.graph.nodes[self.current_node_id].type)
        dark = in_corridor or ntype in ('cave', 'mountain')
        self._play_music('dungeon' if dark else 'village')

    # ── Walk dust particles ────────────────────────────────────────────────────

    def _spawn_walk_dust(self):
        from config import TILE_GRASS, TILE_SAND, TILE_FLOOR
        tile = self.tile_map.get_tile(self.player.x, self.player.y)
        col = {
            TILE_GRASS: (75, 118, 52),
            TILE_SAND:  (175, 148, 88),
            TILE_FLOOR: (90, 80, 70),
        }.get(tile)
        if col is None:
            return
        for _ in range(4):
            self._walk_particles.append({
                'c':   self.player.x, 'r': self.player.y,
                'ox':  random.uniform(-10, 10),
                'oy':  random.uniform(-2, 4),
                'vox': random.uniform(-1.5, 1.5),
                'voy': random.uniform(-2.0, -0.5),
                'life': 0.38, 'max': 0.38,
                'col':  col,
                'size': random.uniform(2.0, 4.5),
            })

    def _draw_hurt_tiles(self):
        """Flash de color sobre el tile golpeado (naranja=enemigo, rojo=jugador)."""
        s  = self.screen
        vp = self.map_view.viewport
        T  = TILE_SIZE
        for tc, tr, timer, col in self._hurt_tiles:
            ratio = min(1.0, timer / 0.22)
            alpha = int(ratio * 175)
            px_   = vp.x + (tc - self.map_view.cam_c) * T
            py_   = vp.y + (tr - self.map_view.cam_r) * T
            if vp.x <= px_ < vp.right and vp.y <= py_ < vp.bottom:
                hs = pygame.Surface((T, T), pygame.SRCALPHA)
                hs.fill((*col[:3], alpha))
                s.blit(hs, (px_, py_))

    def _draw_enemy_hp_bars(self):
        """Barra de HP sobre cada enemigo que ya fue golpeado al menos una vez."""
        s  = self.screen
        vp = self.map_view.viewport
        T  = TILE_SIZE
        F  = self.fonts
        for (ec, er), enemy in self._map_enemies.items():
            px_  = vp.x + (ec - self.map_view.cam_c)*T + T//2
            py_  = vp.y + (er - self.map_view.cam_r)*T - 14
            if not (vp.x < px_ < vp.right and vp.y < py_ < vp.bottom):
                continue

            bw = 30
            # Fondo oscuro
            pygame.draw.rect(s, (20, 8, 8), (px_-bw//2-1, py_-1, bw+2, 7), border_radius=3)
            # Barra de HP
            fw = max(0, int(bw * enemy.hp_ratio))
            if fw:
                col = (200, 45, 45) if enemy.hp_ratio < 0.3 else \
                      (230, 140, 30) if enemy.hp_ratio < 0.6 else (60, 190, 70)
                pygame.draw.rect(s, col, (px_-bw//2, py_, fw, 5), border_radius=3)
            pygame.draw.rect(s, (180, 80, 80), (px_-bw//2, py_, bw, 5), 1, border_radius=3)

            # Nombre del monstruo (solo visible al ser golpeado)
            nt = F["xs"].render(enemy.name, True, (220, 170, 170))
            s.blit(nt, nt.get_rect(center=(px_, py_-8)))

    def _draw_walk_particles(self):
        s  = self.screen
        vp = self.map_view.viewport
        T  = TILE_SIZE
        for p in self._walk_particles:
            ratio = p['life'] / p['max']
            alpha = int(ratio * 160)
            size  = max(1, int(p['size'] * ratio))
            px_ = int(vp.x + (p['c'] - self.map_view.cam_c)*T + T//2 + p['ox'])
            py_ = int(vp.y + (p['r'] - self.map_view.cam_r)*T + T - p['oy'])
            if vp.x <= px_ < vp.right and vp.y <= py_ < vp.bottom:
                surf = pygame.Surface((size*2+2, size*2+2), pygame.SRCALPHA)
                pygame.draw.circle(surf, (*p['col'], alpha), (size+1, size+1), size)
                s.blit(surf, (px_-size-1, py_-size-1))

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
            STATE_EVENT:       self._draw_event,
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

    @staticmethod
    def _load_logo() -> "pygame.Surface | None":
        import os, shutil
        assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        # Auto-fix Windows double-extension bug (logo.png.png → logo.png)
        for f in os.listdir(assets):
            for bad in (".png.png", ".png.jpeg", ".png.jpg"):
                if f.endswith(bad):
                    fixed = f[: -len(bad)] + bad[:4]   # keep first ".png"
                    try:
                        shutil.move(os.path.join(assets, f),
                                    os.path.join(assets, fixed))
                    except Exception:
                        pass
        for name in ("logo.png", "logo.jpg", "logo.jpeg"):
            path = os.path.join(assets, name)
            if not os.path.exists(path):
                continue
            try:
                raw = pygame.image.load(path).convert_alpha()
                target_w = 540
                target_h = int(raw.get_height() * target_w / raw.get_width())
                MAX_H = 240
                if target_h > MAX_H:
                    target_h = MAX_H
                    target_w = int(raw.get_width() * MAX_H / raw.get_height())
                return pygame.transform.smoothscale(raw, (target_w, target_h))
            except Exception:
                continue
        return None

    def _title_glow(self, s, text, font, col, cx, cy, glow_r=7):
        """
        Contorno negro puro + texto nítido — SIN glow que tape las letras.
        El glow rellena los espacios entre letras y las hace ilegibles.
        """
        # ── Contorno negro (2-3 px en todas las diagonales) ───────────────────
        outline = font.render(text, True, (0, 0, 0))
        for ox, oy in ((-3, 0),(3, 0),(0,-3),(0, 3),
                       (-2,-2),(2,-2),(-2, 2),(2, 2),
                       (-3,-1),(3,-1),(-3, 1),(3, 1),
                       (-1,-3),(1,-3),(-1, 3),(1, 3),
                       (-2, 0),(2, 0),(0,-2),(0, 2)):
            s.blit(outline, outline.get_rect(center=(cx+ox, cy+oy)))

        # ── Texto principal — color limpio encima del contorno ────────────────
        main = font.render(text, True, col)
        s.blit(main, main.get_rect(center=(cx, cy)))

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

    # ── TecnoUpsa badge ───────────────────────────────────────────────────────

    def _draw_tecnoupsa_badge(self, s, cx, cy):
        """Corona dorada con #1 encima y 'TecnoUpsa' debajo."""
        GOLD  = (255, 210,  50)
        GOLD2 = (220, 170,  20)
        GOLD3 = (255, 238, 120)
        BG    = (30,  22,   8)

        # ── Fondo pill ────────────────────────────────────────────────────────
        pill = pygame.Rect(cx - 52, cy - 4, 104, 60)
        bg   = pygame.Surface((pill.w, pill.h), pygame.SRCALPHA)
        bg.fill((20, 14, 4, 210))
        s.blit(bg, pill.topleft)
        pygame.draw.rect(s, GOLD2, pill, 2, border_radius=10)

        # ── Corona ────────────────────────────────────────────────────────────
        # Base de la corona
        base_r = pygame.Rect(cx - 28, cy + 14, 56, 10)
        pygame.draw.rect(s, GOLD, base_r, border_radius=3)
        pygame.draw.rect(s, GOLD2, base_r, 1, border_radius=3)

        # Dientes de la corona (5 picos)
        crown_pts = [
            (cx - 28, cy + 15),   # esquina izq base
            (cx - 28, cy + 2),    # pico izq exterior
            (cx - 15, cy + 12),   # valle izq-centro
            (cx - 8,  cy - 6),    # pico izq-centro
            (cx,      cy + 10),   # valle centro
            (cx + 8,  cy - 6),    # pico der-centro
            (cx + 15, cy + 12),   # valle der-centro
            (cx + 28, cy + 2),    # pico der exterior
            (cx + 28, cy + 15),   # esquina der base
        ]
        pygame.draw.polygon(s, GOLD,  crown_pts)
        pygame.draw.polygon(s, GOLD2, crown_pts, 1)

        # Brillo en la parte superior de la corona
        pygame.draw.line(s, GOLD3, (cx - 26, cy + 3), (cx + 26, cy + 3), 1)

        # Joyas en los picos (3 círculos de colores)
        for jx, jy, jc in ((cx - 8, cy - 4, (255, 90, 90)),
                            (cx,     cy + 12,(100, 200, 255)),
                            (cx + 8, cy - 4, (90, 255, 140))):
            pygame.draw.circle(s, jc, (jx, jy), 3)
            pygame.draw.circle(s, (255,255,255), (jx-1, jy-1), 1)

        # Número 1 en el centro de la corona
        n1 = self.fonts["sm"].render("#1", True, (40, 28, 4))
        s.blit(n1, n1.get_rect(center=(cx, cy + 19)))

        # ── Texto TecnoUpsa ───────────────────────────────────────────────────
        tu = self.fonts["sm"].render("TecnoUpsa", True, GOLD)
        s.blit(tu, tu.get_rect(center=(cx, cy + 46)))

    # ── Title screen ──────────────────────────────────────────────────────────

    def _draw_title(self):
        s  = self.screen
        t  = self._anim_t
        cx = WIDTH // 2

        # ── Dark night sky ────────────────────────────────────────────────────
        s.fill((4, 6, 14))
        # Subtle horizon glow (green tint near tree line)
        horiz = pygame.Surface((WIDTH, 240), pygame.SRCALPHA)
        for i in range(16):
            frac = i / 16
            pygame.draw.rect(horiz, (8, 20, 8, int(frac * 30)),
                             (0, 240 - int(frac * 240), WIDTH, int(frac * 240) + 1))
        s.blit(horiz, (0, HEIGHT - 240))

        # ── Stars ─────────────────────────────────────────────────────────────
        rng_s = random.Random(42)
        for _ in range(160):
            sx_ = rng_s.randint(0, WIDTH)
            sy_ = rng_s.randint(0, int(HEIGHT * 0.62))
            br  = rng_s.randint(90, 210)
            spd = rng_s.uniform(0.4, 2.2)
            ph  = rng_s.random() * 6.28318
            rad = rng_s.choice((1, 1, 1, 2))
            tw  = int((math.sin(t * spd + ph) + 1) * 38)
            col_s = (min(255, br + tw),) * 3
            pygame.draw.circle(s, col_s, (sx_, sy_), rad)

        # ── Moon ──────────────────────────────────────────────────────────────
        mx_, my_ = int(WIDTH * 0.82), int(HEIGHT * 0.15)
        for r_g, a_g in ((88, 5), (64, 11), (44, 20), (32, 36)):
            gm = pygame.Surface((r_g * 2, r_g * 2), pygame.SRCALPHA)
            pygame.draw.circle(gm, (240, 238, 200, a_g), (r_g, r_g), r_g)
            s.blit(gm, (mx_ - r_g, my_ - r_g))
        pygame.draw.circle(s, (228, 225, 195), (mx_, my_), 38)
        pygame.draw.circle(s, (244, 241, 218), (mx_, my_), 34)
        for mcx, mcy, mcr in ((mx_ - 10, my_ + 7, 6), (mx_ + 13, my_ - 6, 4), (mx_ - 2, my_ - 13, 3)):
            pygame.draw.circle(s, (210, 207, 178), (mcx, mcy), mcr)

        # ── Tree silhouettes at bottom ─────────────────────────────────────────
        t_rng = random.Random(77)
        TREE_COL = (5, 12, 5)
        for _ in range(24):
            tx_  = t_rng.randint(-12, WIDTH + 12)
            th_  = t_rng.randint(110, 230)
            tw_  = t_rng.randint(34, 78)
            n_l  = t_rng.randint(3, 5)
            for lyr in range(n_l):
                lf     = lyr / max(1, n_l - 1)
                tip_y  = HEIGHT - th_ + int(lf * th_ * 0.44)
                base_y = min(HEIGHT, HEIGHT - th_ + int((lf + 1.0 / max(1, n_l - 1)) * th_ * 0.48))
                lw     = int(tw_ * (0.28 + 0.72 * lf)) + 4
                pts    = [
                    (tx_ + t_rng.randint(-4, 4), tip_y),
                    (tx_ - lw // 2 + t_rng.randint(-6, 6), base_y),
                    (tx_ + lw // 2 + t_rng.randint(-6, 6), base_y),
                ]
                pygame.draw.polygon(s, TREE_COL, pts)
            pygame.draw.rect(s, (4, 8, 4), (tx_ - 4, HEIGHT - 28, 8, 28))

        # Ground fog
        fog = pygame.Surface((WIDTH, 60), pygame.SRCALPHA)
        for fi, fa in ((0, 48), (12, 34), (24, 20), (38, 10), (52, 3)):
            pygame.draw.rect(fog, (14, 26, 12, fa), (0, fi, WIDTH, 14))
        s.blit(fog, (0, HEIGHT - 60))

        # ── Logo / Title ──────────────────────────────────────────────────────
        if self._logo_surf:
            lw, lh = self._logo_surf.get_size()
            bob    = int(math.sin(t * 1.1) * 4)
            logo_y = 25 + bob
            # Drop shadow
            shadow = self._logo_surf.copy()
            shadow.set_alpha(55)
            s.blit(shadow, (cx - lw // 2 + 5, logo_y + 7))
            s.blit(self._logo_surf, (cx - lw // 2, logo_y))
            title_y = logo_y + lh + 4
            sub_offset = 12
        else:
            title_y   = 128
            sub_offset = 60
            self._title_glow(s, "VERTEX VALLEY", self.fonts["title"], C["green"], cx, title_y)

        # ── TecnoUpsa badge (top-right, fixed) ───────────────────────────────
        self._draw_tecnoupsa_badge(s, WIDTH - 90, 52)

        # ── Subtitle keywords ─────────────────────────────────────────────────
        sub_y = title_y + sub_offset
        words = [("Grafo", C["green"]), ("  •  ", C["text_dim"]),
                 ("Dijkstra", C["blue"]), ("  •  ", C["text_dim"]),
                 ("AFD", C["purple"]), ("  •  ", C["text_dim"]),
                 ("Procedural", C["orange"])]
        pieces = [self.fonts["md"].render(w, True, c) for w, c in words]
        total_w = sum(p.get_width() for p in pieces)
        x_ = cx - total_w // 2
        for p in pieces:
            s.blit(p, (x_, sub_y - p.get_height() // 2))
            x_ += p.get_width()

        # ── Seed input ────────────────────────────────────────────────────────
        seed_in = self.state_data.get("seed_input", "")
        seed_y  = sub_y + 30
        box_r   = pygame.Rect(cx - 180, seed_y, 360, 38)
        box_bg  = pygame.Surface((360, 38), pygame.SRCALPHA)
        box_bg.fill((4, 10, 20, 215))
        s.blit(box_bg, box_r.topleft)
        pygame.draw.rect(s, C["green"] if seed_in else C["border"], box_r, 1, border_radius=8)
        lbl_s = self.fonts["xs"].render("SEMILLA DEL MUNDO", True, C["text_dim"])
        s.blit(lbl_s, (box_r.x + 10, box_r.y - 14))
        disp_s = self.fonts["sm"].render(
            seed_in or "dejar en blanco = mundo aleatorio",
            True, C["text_hi"] if seed_in else C["text_dim"])
        s.blit(disp_s, disp_s.get_rect(midleft=(box_r.x + 10, box_r.centery)))
        if seed_in and int(t * 2) % 2 == 0:
            pygame.draw.rect(s, C["green"],
                             (box_r.x + 10 + disp_s.get_width() + 2, box_r.y + 6, 2, 26))

        # ── Buttons ───────────────────────────────────────────────────────────
        BW, BH, BGAP = 300, 46, 10
        btn_start_y = seed_y + 54
        BTNS_DEF = [
            ("INICIAR  JUEGO", "start"),
            ("CONTROLES",      "controls"),
            ("SALIR",          "quit"),
        ]
        mx_m, my_m = pygame.mouse.get_pos()
        btn_rects: dict = {}
        show_ctrl = self.state_data.get("show_controls", False)
        for i, (label, key) in enumerate(BTNS_DEF):
            by_ = btn_start_y + i * (BH + BGAP)
            br_ = pygame.Rect(cx - BW // 2, by_, BW, BH)
            btn_rects[key] = br_
            hov = br_.collidepoint(mx_m, my_m) and not show_ctrl
            if hov:
                gw_s = pygame.Surface((BW + 14, BH + 14), pygame.SRCALPHA)
                pygame.draw.rect(gw_s, (*C["green"], 40), gw_s.get_rect(), border_radius=12)
                s.blit(gw_s, (br_.x - 7, br_.y - 7))
            bg_ = pygame.Surface((BW, BH), pygame.SRCALPHA)
            bg_.fill((16, 68, 52, 235) if hov else (6, 20, 16, 205))
            s.blit(bg_, br_.topleft)
            pygame.draw.rect(s, C["green"] if hov else C["border_hi"], br_,
                             2 if hov else 1, border_radius=8)
            bt_ = self.fonts["md"].render(label, True, C["green"] if hov else C["text"])
            s.blit(bt_, bt_.get_rect(center=br_.center))
        self._title_btns = btn_rects

        # ── Footer ────────────────────────────────────────────────────────────
        pygame.draw.line(s, C["border"], (40, HEIGHT - 62), (WIDTH - 40, HEIGHT - 62), 1)
        seed_v = self.seed if hasattr(self, "seed") else "?"
        sv = self.fonts["xs"].render(f"Semilla: {seed_v}", True, C["text_dim"])
        s.blit(sv, (46, HEIGHT - 50))
        made = self.fonts["xs"].render("Made by:", True, C["text_dim"])
        s.blit(made, made.get_rect(center=(cx, HEIGHT - 50)))
        a1 = self.fonts["sm"].render(
            "Flavia Lozada Rueda   ·   Ma. Fernanda Sanchez", True, C["text"])
        a2 = self.fonts["sm"].render(
            "Mateo Soto Gareca   ·   Carlos Zambrana", True, C["text"])
        s.blit(a1, a1.get_rect(center=(cx, HEIGHT - 32)))
        s.blit(a2, a2.get_rect(center=(cx, HEIGHT - 14)))

        # ── Controls overlay ──────────────────────────────────────────────────
        if show_ctrl:
            self._draw_title_controls_overlay(s, cx)

    def _draw_title_controls_overlay(self, s, cx):
        """Panel con controles del juego — se muestra al presionar CONTROLES."""
        dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 175))
        s.blit(dim, (0, 0))

        pw, ph = 780, 430
        pr = pygame.Rect(cx - pw // 2, HEIGHT // 2 - ph // 2, pw, ph)
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((8, 12, 22, 250))
        s.blit(panel, pr.topleft)
        pygame.draw.rect(s, C["green"], pr, 2, border_radius=12)

        tl = self.fonts["md"].render("CONTROLES  Y  FLUJO  DE  JUEGO", True, C["green"])
        s.blit(tl, tl.get_rect(center=(cx, pr.y + 24)))
        pygame.draw.line(s, C["border_hi"],
                         (pr.x + 20, pr.y + 42), (pr.right - 20, pr.y + 42), 1)

        CONTROLS_DATA = [
            ("WASD / Flechas", "moverse por el mapa"),
            ("ENTER / SPACE",  "interactuar (cofres, salidas)"),
            ("E",              "abrir inventario"),
            ("Q",              "abrir tienda cercana"),
            ("M / ESC",        "mapa del mundo (grafo)"),
            ("1 / 2 / 3",      "atacar / defender / huir"),
            ("F11",            "pantalla completa"),
        ]
        FLUJO_DATA = [
            ("Inicio",        "apareces en la Aldea central"),
            ("Explorar",      "WASD por el mapa 2D"),
            ("M o ESC",       "abre el mapa-grafo del mundo"),
            ("Clic + ENTER",  "selecciona destino -> Dijkstra"),
            ("Combate",       "toca el ! o viaja por aristas"),
            ("Victoria",      "llega al nodo final (nodo 8)"),
            ("Semilla",       "mismo numero = mismo mundo"),
        ]
        for ci, (hdr, col_c, rows) in enumerate([
            ("CONTROLES",      C["blue"],   CONTROLS_DATA),
            ("FLUJO  DE  JUEGO", C["orange"], FLUJO_DATA),
        ]):
            x_ = pr.x + 28 + ci * (pw // 2)
            ht = self.fonts["sm"].render(hdr, True, col_c)
            s.blit(ht, (x_, pr.y + 52))
            for j, (key, val) in enumerate(rows):
                iy = pr.y + 76 + j * 22
                kt = self.fonts["xs"].render(key, True, col_c)
                vt = self.fonts["xs"].render(val, True, C["text_dim"])
                s.blit(kt, (x_, iy))
                s.blit(vt, (x_ + kt.get_width() + 8, iy))

        close_t = self.fonts["xs"].render(
            "presiona  ESC  o  clic  para  cerrar", True, C["text_dim"])
        s.blit(close_t, close_t.get_rect(center=(cx, pr.bottom - 18)))

    # ── world / dijkstra screens ──────────────────────────────────────────────

    def _draw_world(self):
        dijk_data = None
        self.graph_view.draw(
            self.graph, self.current_node_id,
            self._selected_node, dijk_data, None,
            traveled_edges=self._traveled_edges
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
            data.get("target"),
            traveled_edges=self._traveled_edges
        )
        step = data.get("step") or {}
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
        """Corredor aterrador — piedra oscura, antorchas rojas, niebla verde."""
        s.fill((4, 3, 3))
        cx, cy = WIDTH // 2, HEIGHT // 2 + 60

        # ── Anillos de perspectiva ────────────────────────────────────────────
        for i in range(10, 0, -1):
            ratio = i / 10.0
            hw = int(WIDTH * 0.52 * ratio)
            hh = int(HEIGHT * 0.42 * ratio)
            x0, y0 = cx - hw, cy - hh
            br = int(5 + (1-ratio)*40)
            red_tint = int((1-ratio)*20)
            col = (br+red_tint, br, br)
            pygame.draw.rect(s, col, (x0, y0, hw*2, hh*2), 3)
            if ratio < 0.6:
                pygame.draw.line(s, (br+6, br+3, br+3),
                                 (x0, y0+hh*2), (x0+hw*2, y0+hh*2), 1)

        # ── Suelo oscuro (piedra mojada) ──────────────────────────────────────
        pygame.draw.polygon(s, (14, 9, 8), [
            (0, HEIGHT), (WIDTH, HEIGHT),
            (cx+int(WIDTH*0.52), cy+int(HEIGHT*0.42)),
            (cx-int(WIDTH*0.52), cy+int(HEIGHT*0.42)),
        ])
        for fi in range(6):
            fy = cy+int(HEIGHT*0.42) + fi*(HEIGHT-cy-int(HEIGHT*0.42))//6
            fw = int(WIDTH*0.52) + fi*(WIDTH//2-int(WIDTH*0.52))//6
            pygame.draw.line(s, (22,15,13),(cx-fw,fy),(cx+fw,fy),1)
        for fv in range(-5,6,2):
            pygame.draw.line(s,(18,12,10),(cx,cy+int(HEIGHT*0.42)),
                             (cx+fv*(WIDTH//10),HEIGHT),1)
        # Manchas oscuras en el suelo
        random.seed(7777)
        for _ in range(8):
            sx2=random.randint(100,WIDTH-100); sy2=random.randint(min(cy+int(HEIGHT*0.42),HEIGHT-40),max(cy+int(HEIGHT*0.42)+1,HEIGHT-20))
            pygame.draw.ellipse(s,(10,6,5),(sx2-20,sy2-6,40,12))
        random.seed()

        # ── Techo oscuro ──────────────────────────────────────────────────────
        pygame.draw.polygon(s,(10,7,6),[
            (0,88),(WIDTH,88),
            (cx+int(WIDTH*0.52),cy-int(HEIGHT*0.42)),
            (cx-int(WIDTH*0.52),cy-int(HEIGHT*0.42)),
        ])

        # ── Paredes laterales con grietas ─────────────────────────────────────
        for side in (-1,1):
            wx  = cx + side*int(WIDTH*0.52)
            wpts= [(cx+side*WIDTH//2,88),(wx,cy-int(HEIGHT*0.42)),
                   (wx,cy+int(HEIGHT*0.42)),(cx+side*WIDTH//2,HEIGHT)]
            pygame.draw.polygon(s,(18,12,10),wpts)
            for bi in range(8):
                by2 = cy-int(HEIGHT*0.42)+bi*(int(HEIGHT*0.84))//8
                mix = bi/8
                bx_ = int(wx + (cx+side*WIDTH//2-wx)*mix)
                pygame.draw.line(s,(28,18,16),(wx,by2),(bx_,HEIGHT if by2>cy else 88),1)
            # Cadenas/raíces en las paredes
            for chain_y in range(cy-80, cy+80, 40):
                csx = int(wx + (cx+side*WIDTH//2-wx)*0.3)
                pygame.draw.line(s,(50,40,35),(csx,chain_y),(csx+side*8,chain_y+20),2)
                pygame.draw.circle(s,(45,35,30),(csx+side*4,chain_y+10),3)

        # ── Antorchas de sangre rojas ─────────────────────────────────────────
        for tx,ty in ((int(cx-WIDTH*0.38),cy-20),(int(cx+WIDTH*0.38),cy-20)):
            self._draw_scary_torch(s, tx, ty, t)

        # ── Niebla verde espeluznante en el punto de fuga ─────────────────────
        for i in range(4):
            fw2 = 120 + i*50; fh2 = 70 + i*30
            fog  = pygame.Surface((fw2,fh2), pygame.SRCALPHA)
            fa   = int(10+math.sin(t*0.5+i)*5)
            pygame.draw.ellipse(fog,(15,60+i*10,25,fa),fog.get_rect())
            s.blit(fog,(cx-fw2//2,cy-fh2//2))

        # ── Viñeta roja pulsante (terror) ─────────────────────────────────────
        pulse  = (math.sin(t*1.4)+1)/2
        red_a  = int(25+pulse*35)
        vig    = pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA)
        for dist in range(120,0,-30):
            a2 = int(red_a*(1-dist/120))
            pygame.draw.rect(vig,(160,8,8,a2),(0,0,dist,HEIGHT))
            pygame.draw.rect(vig,(160,8,8,a2),(WIDTH-dist,0,dist,HEIGHT))
            pygame.draw.rect(vig,(160,8,8,a2),(0,0,WIDTH,dist))
            pygame.draw.rect(vig,(160,8,8,a2),(0,HEIGHT-dist,WIDTH,dist))
        s.blit(vig,(0,0))

    def _draw_scary_torch(self, surf, x, y, t):
        """Antorcha de sangre roja para el corredor aterrador."""
        # Soporte oxidado
        pygame.draw.rect(surf,(65,35,15),(x-3,y,6,14),border_radius=2)
        # Cadena encima
        for cy2 in range(y-8,y,4):
            pygame.draw.circle(surf,(55,48,42),(x,cy2),2)
        # Llama roja-morada
        fw=10+int(math.sin(t*9.5)*3); fh=17+int(math.sin(t*8.2+1)*5)
        pygame.draw.polygon(surf,(160,15,15),[(x,y-fh),(x-fw//2,y),(x+fw//2,y)])
        pygame.draw.polygon(surf,(220,55,8), [(x,y-fh+5),(x-fw//3,y-3),(x+fw//3,y-3)])
        pygame.draw.circle(surf,(255,220,150),(x,y-4),3)
        # Halo rojo-violeta
        gs=pygame.Surface((90,90),pygame.SRCALPHA)
        ga=int(40+math.sin(t*6)*22)
        pygame.draw.circle(gs,(160,15,70,ga),(45,45),45)
        surf.blit(gs,(x-45,y-50))
        # Gotas "sangre"
        for di in range(3):
            dx2=x+(di-1)*4; dy_s=y+12
            dl=int(math.sin(t*2.5+di*1.5)*4)+7
            if dl>3:
                pygame.draw.line(surf,(130,8,8),(dx2,dy_s),(dx2,dy_s+dl),2)
                pygame.draw.circle(surf,(150,12,12),(dx2,dy_s+dl),2)

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
        self._draw_hurt_tiles()
        self._draw_walk_particles()
        self._draw_enemy_hp_bars()
        self._draw_hit_effects()

        # Weather overlay (drawn after map, before HUD)
        self.weather.draw(self.screen)

        if in_corridor:
            dest = self.graph.nodes[self._corridor_dest] if self._corridor_dest is not None else node
            dest_name = f"Corredor -> {dest.name}"
            prog = self.player.x / max(1, self.tile_map.cols - 1)
            self.hud.draw(self.player, dest_name, self.tile_map.node_type,
                          f"WASD:avanzar  ENTER:actuar  TAB:minimapa  [{int(prog*100)}% recorrido]")
            self._draw_corridor_progress(prog)
        else:
            self.hud.draw(
                self.player, node.name, node.type,
                "WASD:mover  ENTER:actuar  E:inv  TAB:minimapa  M/ESC:mapa  F11:full"
            )
        # Weather badge (bottom-left, above corridor bar)
        self.weather.draw_hud_badge(
            self.screen, self.fonts["sm"], self.fonts["xs"],
            x=10, y=HEIGHT - 52
        )

        if self.state_data.get("show_inv"):
            self._draw_inventory()
        if self._show_minimap:
            self.minimap.draw(
                self.graph, self.current_node_id,
                self._traveled_edges,
                self._corridor_dest if in_corridor else None,
            )

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

    # ── world events ─────────────────────────────────────────────────────────

    # Event catalogue — each entry is (weight, builder_fn)
    _EVENT_POOL = None  # built lazily

    def _roll_node_event(self, node_id: int, node_type: str) -> "dict | None":
        rng = random.Random(self.seed ^ node_id ^ 0xCAFE)
        if rng.random() > 0.45:   # 45 % chance of an event on first visit
            return None

        roll = rng.random()
        hp_restore = rng.randint(18, 32)
        trap_dmg   = rng.randint(8, 18)
        bonus_coin = rng.randint(12, 28)

        if roll < 0.30:
            return {
                "kind":   "altar",
                "title":  "Altar Sagrado",
                "flavor": "Una piedra antigua emana luz tenue...\nUna fuerza desconocida restaura tus heridas.",
                "effect": f"+{hp_restore} HP restaurado",
                "color":  (120, 210, 160),
                "hp":     hp_restore,
                "applied": False,
            }
        elif roll < 0.55:
            return {
                "kind":    "merchant",
                "title":   "Mercader Errante",
                "flavor":  "Un extraño mercader surge de las sombras.\n'Tengo cosas interesantes para un viajero...'",
                "effect":  "Visitar su tienda",
                "color":   (240, 190, 60),
                "applied": False,
            }
        elif roll < 0.80:
            return {
                "kind":   "trap",
                "title":  "Trampa Antigua",
                "flavor": "El suelo cede bajo tus pies.\nUn mecanismo oxidado te golpea antes de que reacciones.",
                "effect": f"-{trap_dmg} HP",
                "color":  (220, 80, 60),
                "dmg":    trap_dmg,
                "applied": False,
            }
        else:
            return {
                "kind":   "relic",
                "title":  "Reliquia Misteriosa",
                "flavor": "Una moneda extraña brilla en el suelo.\nParece valiosa... o maldita.",
                "effect": f"+{bonus_coin} monedas",
                "color":  (200, 160, 240),
                "coins":  bonus_coin,
                "applied": False,
            }

    def _ev_event(self, e: pygame.event.Event):
        if e.type != pygame.KEYDOWN:
            return
        if e.key not in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
            return
        ev = self.state_data.get("event", {})
        if not ev.get("applied"):
            self._apply_event(ev)
            ev["applied"] = True
        if ev.get("kind") == "merchant" and e.key != pygame.K_ESCAPE:
            self.state_data = {}
            self.state = STATE_SHOP
        else:
            self.state_data = {}
            self.state = STATE_EXPLORE

    def _apply_event(self, ev: dict):
        kind = ev.get("kind")
        if kind == "altar":
            self.player.heal(ev.get("hp", 20))
        elif kind == "trap":
            self.player.take_damage(ev.get("dmg", 10))
            if not self.player.is_alive():
                self.state = STATE_GAME_OVER
        elif kind == "relic":
            self.player.coins += ev.get("coins", 15)

    def _draw_event(self):
        s  = self.screen
        ev = self.state_data.get("event", {})
        if not ev:
            self.state = STATE_EXPLORE
            return

        # Draw the map underneath (atmosphere)
        self._draw_explore()

        # Dark vignette
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 165))
        s.blit(veil, (0, 0))

        kind  = ev.get("kind", "altar")
        title = ev.get("title", "")
        flavor = ev.get("flavor", "")
        effect = ev.get("effect", "")
        col   = ev.get("color", (200, 200, 200))
        t     = self._anim_t

        # Panel
        pw, ph = 560, 320
        px_, py_ = (WIDTH - pw) // 2, (HEIGHT - ph) // 2
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((10, 8, 6, 230))
        pygame.draw.rect(panel, (*col, 180), pygame.Rect(0, 0, pw, ph), 2, border_radius=10)
        # Corner ornaments
        for cx_, cy_, ax, ay in [(8,8,1,1),(pw-8,8,-1,1),(8,ph-8,1,-1),(pw-8,ph-8,-1,-1)]:
            pygame.draw.line(panel, col, (cx_, cy_), (cx_ + ax*18, cy_), 2)
            pygame.draw.line(panel, col, (cx_, cy_), (cx_, cy_ + ay*18), 2)
        s.blit(panel, (px_, py_))

        # Icon circle (pulsing)
        pulse = (math.sin(t * 2.8) + 1) / 2
        icon_r = int(32 + pulse * 4)
        ix, iy = px_ + pw // 2, py_ + 62
        glow = pygame.Surface((icon_r * 4, icon_r * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, int(30 + 20 * pulse)),
                           (icon_r * 2, icon_r * 2), icon_r + 12)
        s.blit(glow, (ix - icon_r * 2, iy - icon_r * 2))
        pygame.draw.circle(s, tuple(int(c * 0.4) for c in col), (ix, iy), icon_r)
        pygame.draw.circle(s, col, (ix, iy), icon_r, 2)
        icons = {"altar": "+", "merchant": "$", "trap": "!", "relic": "?"}
        it = self.fonts["lg"].render(icons.get(kind, "?"), True, col)
        s.blit(it, it.get_rect(center=(ix, iy)))

        # Title
        tc = tuple(min(255, int(c * (0.85 + 0.15 * pulse))) for c in col)
        tt = self.fonts["md"].render(title, True, tc)
        s.blit(tt, tt.get_rect(centerx=px_ + pw // 2, y=py_ + 108))

        # Horizontal rule
        pygame.draw.line(s, (*col, 100), (px_ + 30, py_ + 138), (px_ + pw - 30, py_ + 138), 1)

        # Flavor text (wrapped manually at ~50 chars)
        lines = flavor.split("\n")
        yy = py_ + 150
        for line in lines:
            ft = self.fonts["xs"].render(line, True, (190, 185, 170))
            s.blit(ft, ft.get_rect(centerx=px_ + pw // 2, y=yy))
            yy += 18

        # Effect badge
        yy += 8
        eff_col = col
        et = self.fonts["sm"].render(effect, True, eff_col)
        s.blit(et, et.get_rect(centerx=px_ + pw // 2, y=yy))

        # Confirm hint (blinking)
        if int(t * 2) % 2 == 0:
            if kind == "merchant":
                hint = "ENTER: visitar tienda   |   ESC: ignorar"
            else:
                hint = "ENTER / ESPACIO: continuar"
            ht = self.fonts["xs"].render(hint, True, (140, 130, 110))
            s.blit(ht, ht.get_rect(centerx=px_ + pw // 2, y=py_ + ph - 28))

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
        cx = WIDTH // 2
        t  = self._anim_t
        s.fill((7, 8, 16))

        # Fondo animado
        random.seed(99)
        for i in range(55):
            sx = random.randint(0, WIDTH); sy = random.randint(0, HEIGHT)
            br = int((math.sin(t*1.5+i)*0.5+0.5)*80)+30
            pygame.draw.circle(s,(br,br,br//2),(sx,sy),1)
        random.seed()

        # ── Título limpio (sin glow exagerado) ────────────────────────────────
        title_y = 68
        tsh = self.fonts["title"].render("ELIGE TU PERSONAJE", True, (0, 20, 10))
        tit = self.fonts["title"].render("ELIGE TU PERSONAJE", True, C["green"])
        s.blit(tsh, tsh.get_rect(center=(cx+3, title_y+4)))
        s.blit(tit, tit.get_rect(center=(cx, title_y)))

        hint = self.fonts["sm"].render(
            "Flechas: cambiar    ENTER: confirmar    ESC: volver", True, C["text_dim"])
        s.blit(hint, hint.get_rect(center=(cx, title_y+54)))

        # ── Tarjetas — anchas y bien contenidas ───────────────────────────────
        card_w  = 490
        card_h  = 430
        gap     = 36
        total   = 2 * card_w + gap
        x0      = cx - total // 2
        card_top= title_y + 82

        for i, char in enumerate(CHARACTERS):
            cx2 = x0 + i*(card_w+gap) + card_w//2
            sel = (i == self._selected_char)
            cr  = pygame.Rect(x0 + i*(card_w+gap), card_top, card_w, card_h)
            col = char["shirt"] if sel else C["border_hi"]

            # Glow exterior si seleccionado
            if sel:
                pulse = (math.sin(t*2.5)+1)/2
                gs = pygame.Surface((card_w+24, card_h+24), pygame.SRCALPHA)
                pygame.draw.rect(gs, (*col[:3], int(18+pulse*28)),
                                 gs.get_rect(), border_radius=18)
                s.blit(gs, (cr.x-12, cr.y-12))

            # Fondo de la tarjeta
            bg = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            bg.fill((10, 12, 28, 235))
            s.blit(bg, cr.topleft)
            pygame.draw.rect(s, col, cr, 3 if sel else 1, border_radius=14)

            # Franja superior del color del personaje
            header = pygame.Rect(cr.x, cr.y, card_w, 10)
            pygame.draw.rect(s, col, header, border_radius=14)

            # Sprite del personaje (animado si seleccionado)
            bob = int(math.sin(t*3.5)*4) if sel else 0
            draw_character(s, cx2, cr.y + 88 + bob, t if sel else 0.0,
                           is_moving=sel, facing=(0,1),
                           shirt_col=char["shirt"], hair_col=char["hair"],
                           pants_col=char.get("pants",(35,44,112)))

            # Nombre
            nt = self.fonts["lg"].render(char["name"], True, col)
            s.blit(nt, nt.get_rect(center=(cx2, cr.y + 118)))

            # Descripción
            for di, dl in enumerate(char["desc"].split("\n")):
                dt = self.fonts["sm"].render(dl, True, C["text_dim"])
                s.blit(dt, dt.get_rect(center=(cx2, cr.y + 152 + di*22)))

            # ── Stats bars (SIEMPRE dentro de la tarjeta) ─────────────────────
            bar_lx  = cr.x + 18          # x donde empieza la etiqueta
            bar_x   = cr.x + 92          # x donde empieza la barra
            bar_max = card_w - 108        # ancho máximo de la barra (cr.right - bar_x - 16)
            stats   = [
                ("HP",  char["hp"],       50, (220, 55, 55)),
                ("ATK", char["attack"],   20, (240, 148, 55)),
                ("DEF", char["defense"],  20, (75, 138, 255)),
            ]
            sy_ = cr.y + 200
            for label, val, mx, sc in stats:
                # Etiqueta
                lt = self.fonts["sm"].render(f"{label} {val}", True, sc)
                s.blit(lt, (bar_lx, sy_ - lt.get_height()//2))
                # Barra (capped at bar_max)
                fw = min(bar_max, int(bar_max * val / mx))
                pygame.draw.rect(s, (24, 24, 38), (bar_x, sy_-5, bar_max, 10), border_radius=4)
                if fw:
                    pygame.draw.rect(s, sc, (bar_x, sy_-5, fw, 10), border_radius=4)
                    shine = tuple(min(255,c+55) for c in sc)
                    pygame.draw.rect(s, shine, (bar_x+1, sy_-5, max(0,fw-2), 4), border_radius=3)
                pygame.draw.rect(s, C["border_hi"], (bar_x, sy_-5, bar_max, 10), 1, border_radius=4)
                sy_ += 32

            # Habilidad especial
            spt = self.fonts["sm"].render(char["special"], True, C["gold"])
            s.blit(spt, spt.get_rect(center=(cx2, cr.y + 318)))

            # Separador
            pygame.draw.line(s, C["border"], (cr.x+20, cr.y+332), (cr.right-20, cr.y+332), 1)

            # SELECCIONADO o instrucción
            if sel:
                si = self.fonts["md"].render("[ SELECCIONADO ]", True, col)
                s.blit(si, si.get_rect(center=(cx2, cr.bottom - 34)))
            else:
                si2 = self.fonts["sm"].render("Flecha para elegir", True, C["text_dim"])
                s.blit(si2, si2.get_rect(center=(cx2, cr.bottom - 34)))

        # ── Animación de selección encima ─────────────────────────────────────
        if getattr(self, '_char_select_anim', None):
            self._draw_char_select_anim(s, cx, t)

    def _draw_char_select_anim(self, s, cx, t):
        """Animación espectacular al confirmar el personaje."""
        from ui.map_view import draw_character
        anim  = self._char_select_anim
        ratio = 1.0 - anim["timer"] / anim["max"]   # 0→1
        char  = self._chosen_char
        cy    = HEIGHT // 2

        # ── Overlay oscuro que aparece progresivamente ────────────────────────
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((5, 5, 15, int(min(1.0, ratio*2)*200)))
        s.blit(ov, (0, 0))

        # ── Flash blanco al inicio ────────────────────────────────────────────
        if ratio < 0.14:
            fa = int((1 - ratio/0.14)*240)
            fl = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fl.fill((255, 255, 255, fa))
            s.blit(fl, (0, 0))

        # ── Personaje grande en el centro, saltando ───────────────────────────
        if ratio > 0.04:
            bob = int(math.sin(ratio * math.pi * 5.5) * 42) if ratio < 0.72 else 0
            # Sombra elíptica debajo
            shad = pygame.Surface((60, 18), pygame.SRCALPHA)
            pygame.draw.ellipse(shad, (0,0,0,80), shad.get_rect())
            s.blit(shad, (cx-30, cy+22))
            draw_character(s, cx, cy - 30 - bob, t*9, is_moving=True, facing=(0,1),
                           shirt_col=char["shirt"], hair_col=char["hair"],
                           pants_col=char.get("pants"))

        # ── Estrellas / confetti que vuelan ───────────────────────────────────
        if ratio > 0.06:
            for i in range(28):
                angle = (i/28)*math.pi*2 + ratio*4
                dist  = ratio * 280
                sx2   = cx + int(math.cos(angle)*dist)
                sy2   = cy - 30 + int(math.sin(angle)*dist)
                sa    = max(0, int((1-ratio**0.6)*255))
                sz    = max(1, int((1-ratio)*5)+1)
                col   = [(255,218,50),(255,120,70),(100,215,255),(160,255,130)][i%4]
                star  = pygame.Surface((sz*2+2, sz*2+2), pygame.SRCALPHA)
                pygame.draw.circle(star, (*col, sa), (sz+1,sz+1), sz)
                s.blit(star, (sx2-sz-1, sy2-sz-1))

        # ── Confetti en cascada ───────────────────────────────────────────────
        if ratio > 0.18:
            random.seed(int(ratio*28))
            for i in range(45):
                cfx = random.randint(10, WIDTH-10)
                cfy = int((ratio-0.18)*HEIGHT*1.6) - random.randint(0, HEIGHT)
                cfy = cfy % HEIGHT
                cfc = random.choice([(255,218,50),(255,90,90),(90,200,255),(160,255,160),(255,160,220)])
                ca  = max(0, int((1.0 - ratio*0.75)*255))
                if ca > 20:
                    cs = pygame.Surface((8, 12), pygame.SRCALPHA)
                    cs.fill((*cfc, ca))
                    s.blit(cs, (cfx, cfy))
            random.seed()

        # ── Texto "¡ELEGIDO!" ─────────────────────────────────────────────────
        if ratio > 0.14:
            ta = int(min(1.0, (ratio-0.14)/0.18)*255)
            shad = self.fonts["title"].render("¡ELEGIDO!", True, (0,0,0))
            main = self.fonts["title"].render("¡ELEGIDO!", True, char["shirt"])
            shad.set_alpha(ta//2); main.set_alpha(ta)
            s.blit(shad, shad.get_rect(center=(cx+3, cy+82)))
            s.blit(main, main.get_rect(center=(cx, cy+80)))

        # ── Nombre del personaje ──────────────────────────────────────────────
        if ratio > 0.25:
            na = int(min(1.0, (ratio-0.25)/0.18)*255)
            nt = self.fonts["lg"].render(char["name"], True, C["gold"])
            nt.set_alpha(na)
            s.blit(nt, nt.get_rect(center=(cx, cy+126)))

        # ── Círculo de halo que se expande ───────────────────────────────────
        if 0.04 < ratio < 0.5:
            hr = int(ratio * 320)
            ha = int((0.5 - ratio) * 2 * 120)
            hsurf = pygame.Surface((hr*2+4, hr*2+4), pygame.SRCALPHA)
            pygame.draw.circle(hsurf, (*char["shirt"][:3], ha), (hr+2,hr+2), hr, 3)
            s.blit(hsurf, (cx-hr-2, cy-30-hr-2))

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

    def _quick_attack(self):
        """K key — golpe directo al monstruo más cercano, sin abrir menú."""
        c, r = self.player.x, self.player.y
        for dc, dr in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
            nc, nr = c+dc, r+dr
            obj = self.tile_map.get_object(nc, nr)
            if obj in ('enemy', 'werewolf') and (nc, nr) not in self._opened_objects:
                if obj == 'werewolf':
                    self._start_werewolf_combat(nc, nr)
                else:
                    self._do_quick_hit(nc, nr)
                return
        self._notify("No hay monstruo cerca  [ K = golpear ]", C["text_dim"], 1.0)

    def _do_quick_hit(self, ec: int, er: int):
        """Un intercambio de golpes rápido — sin menú, con animación."""
        ntype = getattr(self.tile_map, 'node_type',
                        self.graph.nodes[self.current_node_id].type)
        key = (ec, er)
        if key not in self._map_enemies:
            self._map_enemies[key] = make_enemy(ntype, 1.0 + self.player.level * 0.08)

        enemy = self._map_enemies[key]

        # Calcular posición en pantalla del monstruo
        vp     = self.map_view.viewport
        ex_px  = vp.x + (ec - self.map_view.cam_c) * TILE_SIZE + TILE_SIZE // 2
        ey_px  = vp.y + (er - self.map_view.cam_r) * TILE_SIZE
        px_px  = vp.x + (self.player.x - self.map_view.cam_c) * TILE_SIZE + TILE_SIZE // 2
        py_px  = vp.y + (self.player.y - self.map_view.cam_r) * TILE_SIZE

        # ── Jugador golpea al monstruo ────────────────────────────────────────
        pdmg   = self.player.deal_damage()
        actual = enemy.take_damage(pdmg)
        self._hit_effects.append({"x": ex_px, "y": ey_px, "dmg": actual,
                                   "col": C["orange"], "t": 1.3, "max": 1.3})
        self.combat_ui._shake = 0.06
        self._play_sfx('hit_enemy')
        # Flash naranja en el tile del monstruo golpeado
        self._hurt_tiles.append([ec, er, 0.22, (255, 140, 30)])

        if not enemy.is_alive():
            coins   = enemy.loot()
            leveled = self.player.gain_exp(enemy.exp)
            self.player.coins += coins
            self.tile_map.remove_object(ec, er)
            self._opened_objects.add((ec, er))
            del self._map_enemies[key]
            # Burst death effect
            self._hit_effects.append({"x": ex_px, "y": ey_px + 16, "dmg": 0,
                                       "col": C["red"], "t": 0.7, "max": 0.7,
                                       "burst": True})
            self._notify(f"Venciste al {enemy.name}! +{coins}$ +{enemy.exp}EXP", C["gold"], 2.5)
            if leveled:
                self._notify(f"NIVEL {self.player.level}!", C["green"], 2.5)
                self._play_sfx('levelup')
            return

        # Show remaining HP
        hp_pct = int(enemy.hp_ratio * 100)
        self._notify(f"{enemy.name}:  {enemy.hp}/{enemy.max_hp} HP ({hp_pct}%)",
                     C["text_dim"], 0.9)

        # ── Monstruo contraataca ───────────────────────────────────────────────
        edgm    = enemy.deal_damage()
        actual_e= self.player.take_damage(edgm)
        self._play_sfx('hit_player')
        self._hit_effects.append({"x": px_px, "y": py_px, "dmg": actual_e,
                                   "col": C["red"], "t": 1.3, "max": 1.3})
        if not self.player.is_alive():
            self._notify("Has caido...", C["red"], 2.0)
            self.state = STATE_GAME_OVER

    def _draw_hit_effects(self):
        """Dibuja números de daño flotantes y bursts de muerte."""
        s = self.screen
        for ef in self._hit_effects:
            ratio = ef["t"] / ef["max"]
            alpha = int(min(1.0, ratio * 3) * 255)

            if ef.get("burst"):
                # Círculo expandiéndose (muerte)
                r_ = int((1 - ratio) * 32)
                if r_ > 2:
                    bs = pygame.Surface((r_*2+4, r_*2+4), pygame.SRCALPHA)
                    pygame.draw.circle(bs, (*ef["col"][:3], alpha//3), (r_+2, r_+2), r_)
                    pygame.draw.circle(bs, (*ef["col"][:3], alpha//2), (r_+2, r_+2), r_, 2)
                    s.blit(bs, (ef["x"]-r_-2, ef["y"]-r_-2))
                # Stars / sparks
                for i in range(6):
                    angle = i * math.pi / 3 + (1-ratio)*math.pi
                    dist  = r_ + 4
                    sx_   = int(ef["x"] + math.cos(angle)*dist)
                    sy_   = int(ef["y"] + math.sin(angle)*dist)
                    pygame.draw.circle(s, ef["col"], (sx_, sy_), 2)
            else:
                # Número de daño que sube flotando
                fly = int((1 - ratio) * 44)
                txt = self.fonts["lg"].render(f"-{ef['dmg']}", True, ef["col"])
                # Sombra
                sh  = self.fonts["lg"].render(f"-{ef['dmg']}", True, (0,0,0))
                sh.set_alpha(alpha // 2)
                s.blit(sh,  (ef["x"] - txt.get_width()//2 + 2, ef["y"] - 24 - fly + 2))
                txt.set_alpha(alpha)
                s.blit(txt, (ef["x"] - txt.get_width()//2,     ef["y"] - 24 - fly))

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
        step   = data.get("step") or {}
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
        self._corridor_path    = path
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
            for i in range(len(path) - 1):
                a, b = path[i], path[i + 1]
                self._traveled_edges.add((min(a, b), max(a, b)))
            self._load_node(target)
            self._selected_node = None
            if target == len(self.graph.nodes) - 1:
                self.state = STATE_WIN
            elif self._pending_event:
                self.state_data = {"event": self._pending_event}
                self._pending_event = None
                self.state = STATE_EVENT
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
            # Combate directo en el mapa — sin abrir pantalla separada
            self._do_quick_hit(c, r)
        elif obj == "werewolf" and (c, r) not in self._opened_objects:
            self._start_werewolf_combat(c, r)

    def _start_node_combat(self, c: int, r: int):
        self._opened_objects.add((c, r))
        self.tile_map.remove_object(c, r)
        self.player.is_moving = False
        node  = self.graph.nodes[self.current_node_id]
        enemy = make_enemy(node.type, 1.0 + self.player.level * 0.08)
        self._combat   = CombatSystem(self.player, enemy)
        self.state_data = {"post_combat_state": STATE_EXPLORE}
        self.state = STATE_COMBAT

    def _start_werewolf_combat(self, c: int, r: int):
        """Inicia combate completo contra el Hombre Lobo boss."""
        self._opened_objects.add((c, r))
        self.tile_map.remove_object(c, r)
        self.player.is_moving = False
        enemy = make_werewolf(1.0 + self.player.level * 0.12)
        self._combat   = CombatSystem(self.player, enemy)
        self.state_data = {"post_combat_state": STATE_EXPLORE}
        self._notify("¡HOMBRE LOBO! ¡Prepárate!", C["red"], 2.2)
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
        self._corridor_path    = [self.current_node_id, target]
        self._enemy_move_timer = 0.0
        self._map_enemies      = {}
        self._hit_effects      = []
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
        for i in range(len(self._corridor_path) - 1):
            a, b = self._corridor_path[i], self._corridor_path[i + 1]
            self._traveled_edges.add((min(a, b), max(a, b)))
        self._corridor_path = []
        self._load_node(target)
        dest = self.graph.nodes[target]
        self._notify(f"Llegaste a {dest.name}!", C["green"], 3.5)
        self._corridor_dest = None
        if target == len(self.graph.nodes) - 1:
            self.state = STATE_WIN
        elif self._pending_event:
            self.state_data = {"event": self._pending_event}
            self._pending_event = None
            self.state = STATE_EVENT
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
                self._play_sfx('shop_bell')
                self.state = STATE_SHOP; return

    def _try_open_shop(self):
        """Q — open shop if one is nearby."""
        c, r = self.player.x, self.player.y
        for dc, dr in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)):
            if self.tile_map.get_object(c+dc, r+dr) == "shop":
                self._play_sfx('shop_bell')
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
        self._play_sfx('chest')
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
