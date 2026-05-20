"""
Minimap overlay — shown during exploration via TAB key.
Drawn in the bottom-right corner of the screen.
Uses the same fog-of-war rules as GraphView:
  - Unknown edges (both unvisited): hidden
  - Known untraveled: dashed dim grey
  - Traveled: golden solid
  - Unvisited nodes: tiny dark dot
  - Visited nodes: colored dot
  - Player's current node: pulsing bright marker
  - Corridor destination: blinking target marker
"""
import math
import pygame
from config import C, NODE_COLORS


# Panel geometry
_PAD    = 10
_W      = 230
_H      = 190
_MARGIN = 14   # from screen edge


class Minimap:

    # Colors
    _BG          = (8, 6, 4, 210)
    _BORDER      = (100, 80, 40)
    _TRAVELED    = (210, 168, 60)
    _KNOWN_EDGE  = (55, 48, 42)
    _FOG_NODE    = (38, 30, 22)
    _FOG_RING    = (65, 52, 40)
    _DEST_COL    = (220, 80, 60)

    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen  = screen
        self.F       = fonts
        self.pulse_t = 0.0
        self._surf   = pygame.Surface((_W, _H), pygame.SRCALPHA)

    def update(self, dt: float):
        self.pulse_t += dt

    def draw(self, graph, player_node: int, traveled_edges: set,
             corridor_dest: int | None = None):
        s     = self.screen
        sw, sh = s.get_size()
        ox    = sw - _W - _MARGIN
        oy    = sh - _H - _MARGIN

        surf = self._surf
        surf.fill((0, 0, 0, 0))

        # Background panel
        pygame.draw.rect(surf, self._BG, pygame.Rect(0, 0, _W, _H), border_radius=8)
        pygame.draw.rect(surf, self._BORDER, pygame.Rect(0, 0, _W, _H), 1, border_radius=8)

        # Title
        title = self.F["xs"].render("[ M A P A ]", True, (160, 135, 70))
        surf.blit(title, title.get_rect(centerx=_W // 2, y=5))

        # Hint line
        hint = self.F["xs"].render("TAB: cerrar", True, (70, 60, 45))
        surf.blit(hint, hint.get_rect(right=_W - 6, bottom=_H - 4))

        # Exploration stats
        visited = sum(1 for n in graph.nodes.values() if n.visited)
        total   = len(graph.nodes)
        stat    = self.F["xs"].render(f"{visited}/{total} nodos", True, (140, 115, 55))
        surf.blit(stat, (7, 6))

        # Compute scale from graph-space to minimap draw area
        draw_x0 = _PAD
        draw_y0 = 22
        draw_w  = _W - _PAD * 2
        draw_h  = _H - 22 - 16   # leave room for hint at bottom

        xs = [n.x for n in graph.nodes.values()]
        ys = [n.y for n in graph.nodes.values()]
        gx0, gx1 = min(xs), max(xs)
        gy0, gy1 = min(ys), max(ys)
        gw = max(gx1 - gx0, 1)
        gh = max(gy1 - gy0, 1)

        def proj(nx, ny):
            margin = 14
            px = draw_x0 + margin + (nx - gx0) / gw * (draw_w - margin * 2)
            py = draw_y0 + margin + (ny - gy0) / gh * (draw_h - margin * 2)
            return int(px), int(py)

        # Vignette on the draw area
        vig = pygame.Surface((draw_w, draw_h), pygame.SRCALPHA)
        for i in range(3):
            pygame.draw.rect(vig, (0, 0, 0, 20 + i * 12),
                             pygame.Rect(i * 6, i * 5,
                                         draw_w - i * 12, draw_h - i * 10),
                             border_radius=20)
        surf.blit(vig, (draw_x0, draw_y0))

        # ── Edges ──
        for nid, neighbors in graph.adj.items():
            for nb, _w in neighbors:
                if nb <= nid:
                    continue
                na = graph.nodes[nid]
                nb_ = graph.nodes[nb]
                ax, ay = proj(na.x, na.y)
                bx, by = proj(nb_.x, nb_.y)
                key = (min(nid, nb), max(nid, nb))

                if not na.visited and not nb_.visited:
                    continue  # hidden

                if key in traveled_edges:
                    pygame.draw.line(surf, self._TRAVELED, (ax, ay), (bx, by), 2)
                else:
                    self._dashed_line(surf, self._KNOWN_EDGE, (ax, ay), (bx, by))

        # ── Nodes ──
        pulse = (math.sin(self.pulse_t * 3.5) + 1) / 2

        for nid, node in graph.nodes.items():
            px_, py_ = proj(node.x, node.y)

            if nid == player_node:
                # Pulsing player marker — bright ring + fill
                r = int(6 + pulse * 2)
                pygame.draw.circle(surf, (255, 235, 80), (px_, py_), r + 2)
                pygame.draw.circle(surf, (255, 255, 180), (px_, py_), r)
                # Arrow-style cross
                pygame.draw.line(surf, (255, 255, 255), (px_ - 4, py_), (px_ + 4, py_), 1)
                pygame.draw.line(surf, (255, 255, 255), (px_, py_ - 4), (px_, py_ + 4), 1)

            elif nid == corridor_dest:
                # Blinking destination
                alpha = int(180 + 75 * pulse)
                alpha = min(255, alpha)
                col = (*self._DEST_COL, alpha)
                pygame.draw.circle(surf, col, (px_, py_), 6)
                pygame.draw.circle(surf, (255, 120, 100), (px_, py_), 6, 1)
                dt_ = self.F["xs"].render("!", True, (255, 200, 180))
                surf.blit(dt_, dt_.get_rect(center=(px_, py_)))

            elif node.visited:
                base = NODE_COLORS.get(node.type, C["green_dk"])
                pygame.draw.circle(surf, (5, 5, 8), (px_ + 1, py_ + 1), 5)
                pygame.draw.circle(surf, base, (px_, py_), 5)
                pygame.draw.circle(surf, tuple(min(255, int(c * 1.3)) for c in base),
                                   (px_, py_), 5, 1)

            else:
                # Fog node — tiny dark dot
                pygame.draw.circle(surf, self._FOG_NODE, (px_, py_), 4)
                pygame.draw.circle(surf, self._FOG_RING, (px_, py_), 4, 1)

        # Blit final panel onto screen
        s.blit(surf, (ox, oy))

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _dashed_line(surface, color, start, end, dash=5, gap=4):
        x0, y0 = start
        x1, y1 = end
        dx, dy  = x1 - x0, y1 - y0
        length  = math.hypot(dx, dy)
        if length == 0:
            return
        ux, uy = dx / length, dy / length
        seg    = dash + gap
        pos    = 0.0
        while pos < length:
            d1 = min(pos + dash, length)
            sx, sy = int(x0 + ux * pos), int(y0 + uy * pos)
            ex_, ey = int(x0 + ux * d1), int(y0 + uy * d1)
            pygame.draw.line(surface, color, (sx, sy), (ex_, ey), 1)
            pos += seg
