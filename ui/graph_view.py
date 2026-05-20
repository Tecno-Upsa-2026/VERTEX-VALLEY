"""
Renders the world graph with fog-of-war and the live Dijkstra animation.

Drawing area (left of screen): x=0..820, y=0..660
Info panel (right):            x=820..1280, y=0..660

Fog of war states:
  - Edge unknown  (both endpoints unvisited): hidden completely
  - Edge known    (one+ endpoint visited, not traveled): dashed dim grey, no weight
  - Edge traveled (in _traveled_edges): golden solid line with weight badge
  - Node unvisited: dark silhouette + "?" symbol
  - Node visited:   full colour display
"""
import math
import pygame
from config import C, NODE_COLORS, NODE_SYMBOLS, NODE_DISPLAY_NAMES


# ── helpers ───────────────────────────────────────────────────────────────────

def lerp_color(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def brighten(col: tuple, factor: float = 1.3) -> tuple:
    return tuple(min(255, int(c * factor)) for c in col)


# ── GraphView ─────────────────────────────────────────────────────────────────

class GraphView:
    GRAPH_RECT = pygame.Rect(0, 0, 820, 660)
    INFO_RECT  = pygame.Rect(820, 0, 460, 660)
    DRAW_RECT  = pygame.Rect(10, 65, 800, 585)

    NODE_R = 26

    # Medieval dark palette additions
    _FOG_NODE    = (28, 22, 18)       # unvisited node fill
    _FOG_RING    = (55, 45, 35)       # unvisited node ring
    _TRAVELED    = (210, 168, 60)     # golden traveled road
    _KNOWN_EDGE  = (60, 55, 50)       # known-but-untraveled edge
    _BG_DARK     = (8, 7, 5)          # medieval parchment-dark bg
    _PANEL_DARK  = (12, 10, 8)        # right panel bg

    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen = screen
        self.F      = fonts
        self.pulse_t = 0.0
        self.hovered: int | None = None

    # ── public ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        self.pulse_t += dt
        self.hovered = None

    def draw(self, graph, player_node: int, selected: int | None,
             dijk_data: dict | None, target: int | None,
             traveled_edges: set | None = None):
        te = traveled_edges or set()
        self._draw_left_pane(graph, player_node, selected, dijk_data, target, te)
        self._draw_right_pane(graph, player_node, selected, dijk_data, target, te)

    # ── left pane ─────────────────────────────────────────────────────────────

    def _draw_left_pane(self, graph, player_node, selected, dijk_data, target, traveled_edges):
        s = self.screen

        pygame.draw.rect(s, self._BG_DARK, self.GRAPH_RECT)
        self._draw_subtle_grid(s)
        self._draw_vignette(s)
        pygame.draw.rect(s, C["border"], self.GRAPH_RECT, 1)

        self._draw_header(graph, traveled_edges)

        # Edges first (below nodes)
        for nid, neighbors in graph.adj.items():
            for nb, w in neighbors:
                if nb > nid:
                    self._draw_edge(graph, nid, nb, w, dijk_data, traveled_edges)

        # Nodes
        for nid, node in graph.nodes.items():
            self._draw_node(graph, nid, node, player_node, selected, dijk_data, target, traveled_edges)

    def _draw_subtle_grid(self, s):
        for x in range(0, 820, 60):
            pygame.draw.line(s, (14, 12, 10), (x, 0), (x, 660), 1)
        for y in range(0, 660, 60):
            pygame.draw.line(s, (14, 12, 10), (0, y), (820, y), 1)

    def _draw_vignette(self, s):
        vig = pygame.Surface((820, 660), pygame.SRCALPHA)
        for i, rad in enumerate([420, 360, 300]):
            alpha = 18 + i * 14
            pygame.draw.rect(vig, (0, 0, 0, alpha),
                             pygame.Rect(0, 0, 820, 660).inflate(-i * 60, -i * 50),
                             border_radius=rad)
        s.blit(vig, (0, 0))

    def _draw_header(self, graph, traveled_edges):
        s = self.screen
        pygame.draw.rect(s, (10, 8, 6), pygame.Rect(0, 0, 820, 58))
        pygame.draw.line(s, (80, 65, 40), (0, 58), (820, 58), 1)

        t1 = self.F["md"].render("VERTEX VALLEY", True, C["green"])
        s.blit(t1, (18, 10))

        visited_count = sum(1 for n in graph.nodes.values() if n.visited)
        total = len(graph.nodes)
        pct   = int(visited_count / total * 100)
        exp_text = f"Explorado: {visited_count}/{total} nodos  ({pct}%)"
        t2 = self.F["sm"].render(exp_text, True, (160, 140, 80))
        s.blit(t2, (18, 36))

        # Small progress bar
        bar_x, bar_y, bar_w, bar_h = 340, 40, 200, 10
        pygame.draw.rect(s, (30, 25, 18), pygame.Rect(bar_x, bar_y, bar_w, bar_h), border_radius=4)
        fill_w = int(bar_w * visited_count / total)
        if fill_w > 0:
            pygame.draw.rect(s, self._TRAVELED, pygame.Rect(bar_x, bar_y, fill_w, bar_h), border_radius=4)
        pygame.draw.rect(s, (80, 65, 40), pygame.Rect(bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)

        # Traveled edge count
        total_edges = sum(len(nb) for nb in graph.adj.values()) // 2
        trav_count  = len(traveled_edges)
        et = self.F["xs"].render(f"Caminos: {trav_count}/{total_edges}", True, (120, 100, 55))
        s.blit(et, (560, 36))

    # ── edge drawing ──────────────────────────────────────────────────────────

    def _draw_edge(self, graph, a, b, w, dijk_data, traveled_edges):
        na, nb_ = graph.nodes[a], graph.nodes[b]
        ax, ay  = na.x, na.y
        bx, by  = nb_.x, nb_.y

        key = (min(a, b), max(a, b))
        a_vis = na.visited
        b_vis = nb_.visited

        if not a_vis and not b_vis:
            return  # completely hidden

        on_path = self._edge_on_path(a, b, dijk_data)

        if on_path:
            pygame.draw.line(self.screen, C["dijk_path"], (ax, ay), (bx, by), 3)
            self._draw_weight_badge(ax, ay, bx, by, w, C["gold"])
            return

        if key in traveled_edges:
            # Golden traveled road — thick with glow
            glow_surf = pygame.Surface((820, 660), pygame.SRCALPHA)
            pygame.draw.line(glow_surf, (*self._TRAVELED[:3], 40), (ax, ay), (bx, by), 6)
            self.screen.blit(glow_surf, (0, 0))
            pygame.draw.line(self.screen, self._TRAVELED, (ax, ay), (bx, by), 2)
            self._draw_weight_badge(ax, ay, bx, by, w, self._TRAVELED)
        else:
            # Known but untraveled — dashed dim
            self._dashed_line(self.screen, self._KNOWN_EDGE, (ax, ay), (bx, by), dash=8, gap=6)

    def _draw_weight_badge(self, ax, ay, bx, by, w, text_col):
        mx2, my2 = (ax + bx) // 2, (ay + by) // 2
        wt = self.F["xs"].render(str(w), True, text_col)
        r  = wt.get_rect(center=(mx2, my2))
        pygame.draw.rect(self.screen, self._BG_DARK, r.inflate(6, 4), border_radius=3)
        self.screen.blit(wt, r)

    @staticmethod
    def _dashed_line(surface, color, start, end, dash=8, gap=5):
        x0, y0 = start
        x1, y1 = end
        dx, dy  = x1 - x0, y1 - y0
        length  = math.hypot(dx, dy)
        if length == 0:
            return
        ux, uy  = dx / length, dy / length
        seg     = dash + gap
        pos     = 0.0
        while pos < length:
            d0 = pos
            d1 = min(pos + dash, length)
            sx, sy = int(x0 + ux * d0), int(y0 + uy * d0)
            ex_, ey = int(x0 + ux * d1), int(y0 + uy * d1)
            pygame.draw.line(surface, color, (sx, sy), (ex_, ey), 1)
            pos += seg

    # ── node drawing ──────────────────────────────────────────────────────────

    def _draw_node(self, graph, nid, node, player_node, selected, dijk_data, target, traveled_edges):
        s    = self.screen
        x, y = node.x, node.y
        base = NODE_COLORS.get(node.type, C["green_dk"])
        pulse = (math.sin(self.pulse_t * 3.5) + 1) / 2

        is_fog = not node.visited and nid != player_node

        if is_fog:
            self._draw_fog_node(s, x, y, pulse)
            return

        # ── colour logic (visited nodes) ──
        if nid == player_node:
            col      = lerp_color(base, (255, 240, 100), 0.5 + 0.35 * pulse)
            ring_col = (255, 235, 80)
            radius   = 30
        elif nid == target:
            col      = lerp_color(C["red"], (255, 140, 120), pulse * 0.4)
            ring_col = C["red"]
            radius   = 28
        elif nid == selected:
            col      = lerp_color(base, (255, 80, 80), 0.4)
            ring_col = (255, 90, 90)
            radius   = 28
        elif nid == self.hovered:
            col      = brighten(base, 1.35)
            ring_col = (200, 200, 220)
            radius   = 26
        elif dijk_data:
            col, ring_col, radius = self._dijk_node_color(nid, dijk_data, base, pulse)
        else:
            col      = base
            ring_col = brighten(base, 1.25)
            radius   = self.NODE_R

        # Glow aura
        aura_surf = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
        aura_col  = (*col[:3], 35)
        pygame.draw.circle(aura_surf, aura_col,
                           (radius * 3 // 2, radius * 3 // 2), radius + 10)
        s.blit(aura_surf, (x - radius * 3 // 2, y - radius * 3 // 2))

        pygame.draw.circle(s, (5, 5, 10), (x + 3, y + 3), radius)
        pygame.draw.circle(s, col, (x, y), radius)
        pygame.draw.circle(s, ring_col, (x, y), radius, 2)

        sym = NODE_SYMBOLS.get(node.type, "?")
        ts  = self.F["sm"].render(sym, True, (230, 228, 220))
        s.blit(ts, ts.get_rect(center=(x, y - 6)))

        idb = self.F["xs"].render(str(nid), True, C["text_dim"])
        s.blit(idb, idb.get_rect(center=(x, y + 8)))

        if dijk_data:
            d = dijk_data["dist"].get(nid, float("inf"))
            if d < float("inf"):
                dl = self.F["xs"].render(f"d={d}", True, C["gold"])
                s.blit(dl, (x + radius + 3, y - 8))

        words = node.name.split()
        for i, word in enumerate(words[:2]):
            wt = self.F["xs"].render(word, True, C["text_dim"])
            s.blit(wt, wt.get_rect(center=(x, y + radius + 10 + i * 13)))

    def _draw_fog_node(self, s, x, y, pulse):
        radius = self.NODE_R
        fog_a  = int(15 + 10 * pulse)
        aura   = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
        pygame.draw.circle(aura, (*self._FOG_NODE, fog_a),
                           (radius * 3 // 2, radius * 3 // 2), radius + 8)
        s.blit(aura, (x - radius * 3 // 2, y - radius * 3 // 2))

        pygame.draw.circle(s, (3, 3, 4), (x + 2, y + 2), radius)
        pygame.draw.circle(s, self._FOG_NODE, (x, y), radius)
        ring_alpha = int(80 + 40 * pulse)
        ring_col   = (min(255, self._FOG_RING[0] + ring_alpha // 4),
                      self._FOG_RING[1], self._FOG_RING[2])
        pygame.draw.circle(s, ring_col, (x, y), radius, 2)

        qt = self.F["sm"].render("?", True, (90, 75, 55))
        s.blit(qt, qt.get_rect(center=(x, y)))

    def _dijk_node_color(self, nid, data, base, pulse):
        current  = data.get("current")
        visited  = data.get("visited", set())
        frontier = data.get("frontier", {})
        path     = data.get("path", [])

        if nid == current:
            col  = lerp_color(C["dijk_path"], (255, 180, 80), pulse * 0.4)
            ring = C["dijk_path"]
            r    = 28
        elif nid in path and len(path) > 1:
            col  = C["dijk_path"]
            ring = brighten(C["dijk_path"], 1.2)
            r    = 26
        elif nid in visited:
            col  = C["dijk_visited"]
            ring = brighten(C["dijk_visited"], 1.2)
            r    = self.NODE_R
        elif nid in frontier:
            col  = lerp_color(C["dijk_frontier"], base, 0.35)
            ring = C["dijk_frontier"]
            r    = self.NODE_R
        else:
            col  = lerp_color(base, C["bg2"], 0.6)
            ring = C["border"]
            r    = self.NODE_R
        return col, ring, r

    # ── right pane ────────────────────────────────────────────────────────────

    def _draw_right_pane(self, graph, player_node, selected, dijk_data, target, traveled_edges):
        s  = self.screen
        rx = self.INFO_RECT.x
        ry = self.INFO_RECT.y

        pygame.draw.rect(s, self._PANEL_DARK, self.INFO_RECT)
        pygame.draw.rect(s, (50, 40, 25), self.INFO_RECT, 1)

        y = ry + 14
        title = "Algoritmo de Dijkstra" if dijk_data else "Mapa del Mundo"
        t = self.F["md"].render(title, True, C["green"])
        s.blit(t, (rx + 16, y)); y += 32

        pn   = graph.nodes[player_node]
        info = self.F["sm"].render(
            f"Posición: {NODE_DISPLAY_NAMES[pn.type]} — {pn.name}", True, C["text"])
        s.blit(info, (rx + 16, y)); y += 22

        if target is not None:
            tn = graph.nodes[target]
            ti = self.F["sm"].render(
                f"Destino: {NODE_DISPLAY_NAMES[tn.type]} — {tn.name}", True, C["orange"])
            s.blit(ti, (rx + 16, y))
        y += 30

        pygame.draw.line(s, (60, 50, 30), (rx + 16, y), (rx + 444, y), 1); y += 12

        if dijk_data:
            self._draw_dijk_table(graph, dijk_data, rx, y, player_node, target)
            y += 260
            pygame.draw.line(s, C["border"], (rx + 16, y), (rx + 444, y), 1); y += 12
            self._draw_legend(rx, y)
            y += 140
            self._draw_afd_hint(rx, y)
        else:
            self._draw_exploration_panel(graph, traveled_edges, rx, y)
            y_adj = y + 180
            pygame.draw.line(s, (50, 40, 25), (rx + 16, y_adj), (rx + 444, y_adj), 1)
            self._draw_adjacency(graph, player_node, rx, y_adj + 12)

    def _draw_exploration_panel(self, graph, traveled_edges, rx, y):
        s = self.screen
        lbl = self.F["sm"].render("Progreso de exploración:", True, (160, 140, 80))
        s.blit(lbl, (rx + 16, y)); y += 26

        visited_count = sum(1 for n in graph.nodes.values() if n.visited)
        total_nodes   = len(graph.nodes)
        total_edges   = sum(len(nb) for nb in graph.adj.values()) // 2
        trav_count    = len(traveled_edges)

        # Nodes progress bar
        nt = self.F["xs"].render(f"Nodos visitados:  {visited_count} / {total_nodes}", True, C["text"])
        s.blit(nt, (rx + 16, y)); y += 16
        self._progress_bar(s, rx + 16, y, 420, 10, visited_count / total_nodes,
                           (80, 160, 80), (25, 22, 18))
        y += 18

        # Edges progress bar
        et = self.F["xs"].render(f"Caminos recorridos: {trav_count} / {total_edges}", True, C["text"])
        s.blit(et, (rx + 16, y)); y += 16
        ratio = trav_count / total_edges if total_edges else 0
        self._progress_bar(s, rx + 16, y, 420, 10, ratio,
                           self._TRAVELED, (25, 22, 18))
        y += 22

        # Node list with fog status
        lbl2 = self.F["xs"].render("Estado de los nodos:", True, (120, 100, 55))
        s.blit(lbl2, (rx + 16, y)); y += 16

        for nid, node in graph.nodes.items():
            if node.visited:
                dot_col = NODE_COLORS.get(node.type, C["green_dk"])
                txt_col = C["text"]
                status  = NODE_DISPLAY_NAMES.get(node.type, "?")
            else:
                dot_col = self._FOG_RING
                txt_col = (70, 60, 50)
                status  = "???"
            pygame.draw.circle(s, dot_col, (rx + 24, y + 5), 4)
            row_t = self.F["xs"].render(f"{nid}: {node.name[:14]}  [{status}]", True, txt_col)
            s.blit(row_t, (rx + 34, y)); y += 15

    @staticmethod
    def _progress_bar(s, x, y, w, h, ratio, fill_col, bg_col):
        pygame.draw.rect(s, bg_col, pygame.Rect(x, y, w, h), border_radius=4)
        fw = int(w * max(0.0, min(1.0, ratio)))
        if fw > 0:
            pygame.draw.rect(s, fill_col, pygame.Rect(x, y, fw, h), border_radius=4)
        pygame.draw.rect(s, (80, 65, 40), pygame.Rect(x, y, w, h), 1, border_radius=4)

    def _draw_dijk_table(self, graph, data, rx, y, player_node, target):
        s = self.screen
        hdr = self.F["sm"].render("Tabla de distancias (desde origen):", True, C["text_label"])
        s.blit(hdr, (rx + 16, y)); y += 24

        col_w = [140, 70, 70]
        hcols = ["Nodo", "Distancia", "Prev"]
        xc    = rx + 16
        for i, h in enumerate(hcols):
            ht = self.F["xs"].render(h, True, C["text_dim"])
            s.blit(ht, (xc, y))
            xc += col_w[i]
        y += 18

        visited  = data.get("visited", set())
        frontier = data.get("frontier", {})
        path     = data.get("path", [])
        dist     = data.get("dist", {})

        for nid, node in graph.nodes.items():
            d     = dist.get(nid, float("inf"))
            d_str = str(d) if d < float("inf") else "∞"

            prev_str = "—"
            for i, pid in enumerate(path):
                if pid == nid and i > 0:
                    prev_str = str(path[i - 1])
                    break

            if nid in path and len(path) > 1:
                row_col = C["dijk_path"]
            elif nid in visited:
                row_col = C["dijk_visited"]
            elif nid in frontier:
                row_col = C["dijk_frontier"]
            elif nid == player_node:
                row_col = C["dijk_start"]
            else:
                row_col = C["text_dim"]

            pygame.draw.circle(s, row_col, (rx + 22, y + 6), 5)
            xc = rx + 32
            for txt, w in zip(
                [f"{nid}: {node.name[:12]}", d_str, prev_str],
                col_w
            ):
                rt = self.F["xs"].render(txt, True, row_col)
                s.blit(rt, (xc, y))
                xc += w
            y += 17

    def _draw_legend(self, rx, y):
        s = self.screen
        lbl = self.F["sm"].render("Leyenda de colores:", True, C["text_label"])
        s.blit(lbl, (rx + 16, y)); y += 22

        items = [
            (C["dijk_start"],    "Origen  (inicio)"),
            (C["dijk_frontier"], "Frontera (siguiente en cola)"),
            (C["dijk_visited"],  "Visitado (ya asentado)"),
            (C["dijk_path"],     "Ruta óptima encontrada"),
            (C["dijk_end"],      "Destino"),
        ]
        for col, desc in items:
            pygame.draw.rect(s, col, pygame.Rect(rx + 16, y + 1, 14, 12), border_radius=2)
            dt = self.F["xs"].render(desc, True, C["text"])
            s.blit(dt, (rx + 36, y))
            y += 18

    def _draw_afd_hint(self, rx, y):
        s = self.screen
        pygame.draw.line(s, C["border"], (rx + 16, y), (rx + 444, y), 1); y += 10
        lbl = self.F["sm"].render("AFD Combate — estados válidos:", True, C["text_label"])
        s.blit(lbl, (rx + 16, y)); y += 20
        states = [
            ("idle → player_turn",  C["text_dim"]),
            ("player_turn → (attack|defend|flee) → enemy_turn", C["blue"]),
            ("enemy_turn → player_turn  |  victory  |  defeat  |  fled", C["orange"]),
        ]
        for txt, col in states:
            t = self.F["xs"].render(txt, True, col)
            s.blit(t, (rx + 16, y)); y += 16

    def _draw_adjacency(self, graph, player_node, rx, y):
        s = self.screen
        lbl = self.F["sm"].render("Vecinos del nodo actual:", True, C["text_label"])
        s.blit(lbl, (rx + 16, y)); y += 24
        for nb, w in graph.neighbors(player_node):
            nn  = graph.nodes[nb]
            col = NODE_COLORS.get(nn.type, C["green_dk"])
            if not nn.visited:
                col = self._FOG_RING
            pygame.draw.circle(s, col, (rx + 24, y + 6), 5)
            name_display = nn.name if nn.visited else "???"
            t = self.F["sm"].render(
                f"->  {name_display}  (w={w})", True, C["text"] if nn.visited else (70, 60, 50))
            s.blit(t, (rx + 36, y)); y += 22

        y += 16
        hint = self.F["sm"].render("Clic sobre un nodo para seleccionar destino.", True, C["text_dim"])
        s.blit(hint, (rx + 16, y)); y += 20
        hint2 = self.F["sm"].render("ENTER para confirmar y calcular ruta.", True, C["text_dim"])
        s.blit(hint2, (rx + 16, y))

    # ── hit-test ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_node_at(graph, mx: int, my: int) -> int | None:
        for nid, node in graph.nodes.items():
            dx, dy = mx - node.x, my - node.y
            if dx * dx + dy * dy <= (GraphView.NODE_R + 4) ** 2:
                return nid
        return None

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _edge_on_path(a: int, b: int, dijk_data: dict | None) -> bool:
        if not dijk_data:
            return False
        path = dijk_data.get("path", [])
        for i in range(len(path) - 1):
            if (path[i] == a and path[i + 1] == b) or (path[i] == b and path[i + 1] == a):
                return True
        return False
