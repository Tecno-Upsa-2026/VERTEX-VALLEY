"""
World graph: nodes + weighted edges. Provides a Dijkstra step-generator
for live visualization.
"""
import random
import heapq
from config import (
    TYPE_VILLAGE, TYPE_FOREST, TYPE_CAVE, TYPE_MOUNTAIN, TYPE_LAKE,
    NODE_SUFFIXES,
)


class Node:
    def __init__(self, nid: int, name: str, ntype: str, x: int, y: int):
        self.id    = nid
        self.name  = name
        self.type  = ntype
        self.x     = x   # pixel position in graph view
        self.y     = y
        self.visited = False   # has the player been here?

    def __repr__(self):
        return f"Node({self.id}, '{self.name}', {self.type})"


class WorldGraph:
    # Fixed node layout templates — one entry per seed "tier"
    # (type_sequence, positions, edge_list)
    # Positions are (x, y) within the graph drawing area (800×590, offset 10,70)
    _LAYOUT = {
        "types": [
            TYPE_VILLAGE,   # 0 – start
            TYPE_FOREST,    # 1
            TYPE_FOREST,    # 2
            TYPE_CAVE,      # 3
            TYPE_LAKE,      # 4
            TYPE_CAVE,      # 5
            TYPE_MOUNTAIN,  # 6
            TYPE_MOUNTAIN,  # 7
            TYPE_VILLAGE,   # 8  (goal – has boss chest)
        ],
        "positions": [
            (105, 355),   # 0
            (260, 200),   # 1
            (260, 490),   # 2
            (415, 145),   # 3
            (415, 360),   # 4
            (415, 555),   # 5
            (570, 255),   # 6
            (570, 475),   # 7
            (725, 355),   # 8
        ],
        "base_edges": [
            (0, 1), (0, 2),
            (1, 3), (1, 4),
            (2, 4), (2, 5),
            (3, 6), (4, 6), (4, 7),
            (5, 7),
            (6, 8), (7, 8),
            # cross edges for richer graph
            (1, 2), (3, 4), (6, 7),
        ],
    }

    def __init__(self, seed: int):
        self.seed = seed
        self.rng  = random.Random(seed)
        self.nodes: dict[int, Node] = {}
        self.adj:   dict[int, list] = {}   # id -> [(nb_id, weight)]
        self._generate()

    # ── generation ───────────────────────────────────────────────────────────

    def _generate(self):
        layout = self._LAYOUT
        n = len(layout["types"])

        for i, (ntype, (bx, by)) in enumerate(zip(layout["types"], layout["positions"])):
            # slight jitter so each seed looks unique
            jx = self.rng.randint(-18, 18)
            jy = self.rng.randint(-18, 18)
            suffix = self.rng.choice(NODE_SUFFIXES)
            base   = NODE_SUFFIXES   # reuse list
            from config import NODE_DISPLAY_NAMES
            base_name = NODE_DISPLAY_NAMES[ntype]
            name = f"{base_name} {suffix}".strip()
            node = Node(i, name, ntype, bx + jx, by + jy)
            self.nodes[i] = node
            self.adj[i] = []

        # Build edges with seeded weights
        seen = set()
        for (a, b) in layout["base_edges"]:
            if (a, b) not in seen and (b, a) not in seen:
                w = self.rng.randint(1, 9)
                self._add_edge(a, b, w)
                seen.add((a, b))

        # Mark start as visited
        self.nodes[0].visited = True

    def _add_edge(self, a: int, b: int, w: int):
        self.adj[a].append((b, w))
        self.adj[b].append((a, w))

    def get_edge_weight(self, a: int, b: int) -> int | None:
        for nb, w in self.adj[a]:
            if nb == b:
                return w
        return None

    def neighbors(self, node_id: int):
        return self.adj[node_id]

    # ── Dijkstra ─────────────────────────────────────────────────────────────

    def dijkstra(self, start: int, end: int) -> tuple[float, list[int]]:
        """Return (cost, path) for the shortest path."""
        dist = {i: float("inf") for i in self.nodes}
        prev = {i: None        for i in self.nodes}
        dist[start] = 0
        pq = [(0, start)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            if u == end:
                break
            for v, w in self.adj[u]:
                nd = dist[u] + w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))

        path = []
        cur = end
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return dist[end], path

    def dijkstra_steps(self, start: int, end: int):
        """
        Generator yielding one dict per algorithm step for animation.

        Each dict:
          visited   – set of fully-settled nodes
          frontier  – {node_id: tentative_dist} for nodes in the priority queue
          current   – node being relaxed this step
          dist      – full distance table
          path      – best known path to `end` so far
          done      – True once `end` is settled
          final     – True on the last yielded value
        """
        dist = {i: float("inf") for i in self.nodes}
        prev = {i: None         for i in self.nodes}
        dist[start] = 0
        pq = [(0, start)]
        visited: set[int] = set()

        def _reconstruct():
            p = []
            cur = end
            while cur is not None:
                p.append(cur)
                cur = prev[cur]
            p.reverse()
            return p

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            visited.add(u)

            frontier = {
                v: dist[v]
                for v in self.nodes
                if dist[v] < float("inf") and v not in visited
            }
            cur_path = _reconstruct() if dist[end] < float("inf") else [start]

            yield {
                "visited":  set(visited),
                "frontier": dict(frontier),
                "current":  u,
                "dist":     dict(dist),
                "path":     cur_path,
                "done":     u == end,
                "final":    False,
            }

            if u == end:
                break

            for v, w in self.adj[u]:
                nd = dist[u] + w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))

        final_path = _reconstruct()
        yield {
            "visited":  visited,
            "frontier": {},
            "current":  end,
            "dist":     dict(dist),
            "path":     final_path,
            "done":     True,
            "final":    True,
        }
