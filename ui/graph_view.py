"""
Renders the world graph and the live Dijkstra animation.

Drawing area (left of screen): x=0..820, y=0..660
Info panel (right):            x=820..1280, y=0..660
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
    GRAPH_RECT = pygame.Rect(0, 0, 820, 660)     # left pane
    INFO_RECT  = pygame.Rect(820, 0, 460, 660)   # right pane
    DRAW_RECT  = pygame.Rect(10, 65, 800, 585)   # graph canvas within left pane

    NODE_R = 26   # default node radius

    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen = screen
        self.F      = fonts
        self.pulse_t = 0.0
        self.hovered: int | None = None

    # ── public ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        self.pulse_t += dt
        mx, my = pygame.mouse.get_pos()
        self.hovered = None   # recalculated by caller via get_node_at

    def draw(self, graph, player_node: int, selected: int | None,
             dijk_data: dict | None, target: int | None):
        self._draw_left_pane(graph, player_node, selected, dijk_data, target)
        self._draw_right_pane(graph, player_node, selected, dijk_data, target)

    # ── left pane (graph) ─────────────────────────────────────────────────────

    def _draw_left_pane(self, graph, player_node, selected, dijk_data, target):
        s = self.screen

        # Background
        pygame.draw.rect(s, C["bg"], self.GRAPH_RECT)
        pygame.draw.rect(s, C["border"], self.GRAPH_RECT, 1)

        # Header
        self._draw_header()

        # Edges (below nodes)
        for nid, neighbors in graph.adj.items():
            for nb, w in neighbors:
                if nb > nid:
                    self._draw_edge(graph, nid, nb, w, dijk_data)

        # Nodes
        for nid, node in graph.nodes.items():
            self._draw_node(graph, nid, node, player_node, selected, dijk_data, target)

    def _draw_header(self):
        s = self.screen
        pygame.draw.rect(s, C["panel"], pygame.Rect(0, 0, 820, 58))
        pygame.draw.line(s, C["border_hi"], (0, 58), (820, 58), 1)

        t1 = self.F["md"].render("VERTEX VALLEY", True, C["green"])
        t2 = self.F["sm"].render("Capa 1 - Mundo Global (Grafo con Dijkstra)", True, C["text_dim"])
        s.blit(t1, (18, 10))
        s.blit(t2, (18, 36))

    def _draw_edge(self, graph, a, b, w, dijk_data):
        na, nb_ = graph.nodes[a], graph.nodes[b]
        ax, ay  = na.x, na.y
        bx, by  = nb_.x, nb_.y

        on_path = self._edge_on_path(a, b, dijk_data)

        if on_path:
            color, width = C["dijk_path"], 3
        elif dijk_data:
            # dim non-path edges during Dijkstra
            color, width = (35, 35, 52), 1
        else:
            color, width = C["border"], 1

        pygame.draw.line(self.screen, color, (ax, ay), (bx, by), width)

        # Weight badge
        mx2, my2 = (ax + bx) // 2, (ay + by) // 2
        wt = self.F["xs"].render(str(w), True, C["text_dim"] if not on_path else C["gold"])
        r = wt.get_rect(center=(mx2, my2))
        pygame.draw.rect(self.screen, C["bg"], r.inflate(6, 4), border_radius=3)
        self.screen.blit(wt, r)

    def _draw_node(self, graph, nid, node, player_node, selected, dijk_data, target):
        s  = self.screen
        x, y = node.x, node.y

        # ── colour logic ──
        base  = NODE_COLORS.get(node.type, C["green_dk"])
        pulse = (math.sin(self.pulse_t * 3.5) + 1) / 2   # 0..1

        if nid == player_node:
            col = lerp_color(base, (255, 240, 100), 0.5 + 0.35 * pulse)
            ring_col = (255, 235, 80)
            radius = 30
        elif nid == target:
            col = lerp_color(C["red"], (255, 140, 120), pulse * 0.4)
            ring_col = C["red"]
            radius = 28
        elif nid == selected:
            col = lerp_color(base, (255, 80, 80), 0.4)
            ring_col = (255, 90, 90)
            radius = 28
        elif nid == self.hovered:
            col = brighten(base, 1.35)
            ring_col = (200, 200, 220)
            radius = 26
        elif dijk_data:
            col, ring_col, radius = self._dijk_node_color(nid, dijk_data, base, pulse)
        else:
            col = base
            ring_col = brighten(base, 1.25)
            radius = self.NODE_R
            if not node.visited:
                col = lerp_color(col, C["bg2"], 0.4)

        # Glow aura
        aura_surf = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
        aura_col  = (*col[:3], 35)
        pygame.draw.circle(aura_surf, aura_col, (radius * 3 // 2, radius * 3 // 2),
                           radius + 10)
        s.blit(aura_surf, (x - radius * 3 // 2, y - radius * 3 // 2))

        # Shadow
        pygame.draw.circle(s, (5, 5, 10), (x + 3, y + 3), radius)
        # Body
        pygame.draw.circle(s, col, (x, y), radius)
        # Ring
        pygame.draw.circle(s, ring_col, (x, y), radius, 2)

        # Symbol
        sym = NODE_SYMBOLS.get(node.type, "?")
        ts  = self.F["sm"].render(sym, True, (230, 228, 220))
        s.blit(ts, ts.get_rect(center=(x, y - 6)))

        # Node id badge
        idb = self.F["xs"].render(str(nid), True, C["text_dim"])
        s.blit(idb, idb.get_rect(center=(x, y + 8)))

        # Distance label (Dijkstra)
        if dijk_data:
            d = dijk_data["dist"].get(nid, float("inf"))
            if d < float("inf"):
                dl = self.F["xs"].render(f"d={d}", True, C["gold"])
                s.blit(dl, (x + radius + 3, y - 8))

        # Name below node
        words = node.name.split()
        for i, word in enumerate(words[:2]):
            wt = self.F["xs"].render(word, True, C["text_dim"])
            s.blit(wt, wt.get_rect(center=(x, y + radius + 10 + i * 13)))

    def _dijk_node_color(self, nid, data, base, pulse):
        current  = data.get("current")
        visited  = data.get("visited", set())
        frontier = data.get("frontier", {})
        path     = data.get("path", [])

        if nid == current:
            col = lerp_color(C["dijk_path"], (255, 180, 80), pulse * 0.4)
            ring = C["dijk_path"]
            r = 28
        elif nid in path and len(path) > 1:
            col = C["dijk_path"]
            ring = brighten(C["dijk_path"], 1.2)
            r = 26
        elif nid in visited:
            col = C["dijk_visited"]
            ring = brighten(C["dijk_visited"], 1.2)
            r = self.NODE_R
        elif nid in frontier:
            col = lerp_color(C["dijk_frontier"], base, 0.35)
            ring = C["dijk_frontier"]
            r = self.NODE_R
        else:
            col = lerp_color(base, C["bg2"], 0.6)
            ring = C["border"]
            r = self.NODE_R
        return col, ring, r

    # ── right pane (info + Dijkstra table) ───────────────────────────────────

    def _draw_right_pane(self, graph, player_node, selected, dijk_data, target):
        s  = self.screen
        rx = self.INFO_RECT.x
        ry = self.INFO_RECT.y

        pygame.draw.rect(s, C["panel"], self.INFO_RECT)
        pygame.draw.rect(s, C["border"], self.INFO_RECT, 1)

        y = ry + 14
        # ── section: algorithm title ──
        title = "Algoritmo de Dijkstra" if dijk_data else "Vista del Grafo"
        t = self.F["md"].render(title, True, C["green"])
        s.blit(t, (rx + 16, y)); y += 32

        # ── section: current node ──
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

        # ── separator ──
        pygame.draw.line(s, C["border_hi"], (rx + 16, y), (rx + 444, y), 1); y += 12

        if dijk_data:
            self._draw_dijk_table(graph, dijk_data, rx, y, player_node, target)
            y += 260
            pygame.draw.line(s, C["border"], (rx + 16, y), (rx + 444, y), 1); y += 12
            self._draw_legend(rx, y)
            y += 140
            self._draw_afd_hint(rx, y)
        else:
            self._draw_adjacency(graph, player_node, rx, y)

    def _draw_dijk_table(self, graph, data, rx, y, player_node, target):
        s = self.screen
        hdr = self.F["sm"].render("Tabla de distancias (desde origen):", True, C["text_label"])
        s.blit(hdr, (rx + 16, y)); y += 24

        # Header row
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
            d = dist.get(nid, float("inf"))
            d_str = str(d) if d < float("inf") else "∞"

            # find prev
            prev_id = None
            for entry in reversed(data.get("visited", set())):
                pass
            prev_str = "—"
            # derive prev from path
            for i, pid in enumerate(path):
                if pid == nid and i > 0:
                    prev_str = str(path[i - 1])
                    break

            # row colour
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

            # coloured dot
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
            pygame.draw.circle(s, col, (rx + 24, y + 6), 5)
            t = self.F["sm"].render(
                f"->  {nn.name}  (w={w})", True, C["text"])
            s.blit(t, (rx + 36, y)); y += 22

        y += 20
        hint = self.F["sm"].render("Clic sobre un nodo para seleccionar destino.", True, C["text_dim"])
        s.blit(hint, (rx + 16, y)); y += 22
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
