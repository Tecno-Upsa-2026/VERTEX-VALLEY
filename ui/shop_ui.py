"""
Shop screen — scrollable list with categories, coin display, and item preview.
"""
import pygame
from config import C, ITEMS, SHOP_STOCK


CATEGORIES = [
    ("Pociones",  ["Pocion", "Pocion+", "Elixir"]),
    ("Armas",     ["Espada", "Espada+", "Espada Runa"]),
    ("Escudos",   ["Escudo", "Escudo+", "Escudo Acero"]),
    ("Especiales",["Amuleto", "Bomba", "Bomba+"]),
]

CAT_COLORS = {
    "Pociones":   C["red"],
    "Armas":      C["orange"],
    "Escudos":    C["blue"],
    "Especiales": C["purple"],
}

TYPE_LABELS = {
    "potion": "Pocion  (usar en TAB > inventario)",
    "weapon": "Arma    (equipa al comprar)",
    "shield": "Escudo  (equipa al comprar)",
    "maxhp":  "Pasivo  (se aplica al instante)",
    "combat": "Combate (usar con [4] en pelea)",
}


class ShopUI:
    PW, PH = 740, 580

    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen   = screen
        self.F        = fonts
        self.cursor   = 0           # index into SHOP_STOCK
        self._msg     = ""
        self._msg_t   = 0.0
        self._scroll  = 0           # scroll offset for long lists

    # ── public ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        self._msg_t = max(0.0, self._msg_t - dt)

    def handle_key(self, key, player) -> bool:
        """Returns True if the shop should close."""
        if key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_m):
            return True
        if key == pygame.K_UP:
            self.cursor = (self.cursor - 1) % len(SHOP_STOCK)
            self._clamp_scroll()
        if key == pygame.K_DOWN:
            self.cursor = (self.cursor + 1) % len(SHOP_STOCK)
            self._clamp_scroll()
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._buy(player)
        return False

    def draw(self, player):
        s  = self.screen
        sw, sh = s.get_size()

        # Overlay
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((5, 5, 15, 210))
        s.blit(overlay, (0, 0))

        px = (sw - self.PW) // 2
        py = (sh - self.PH) // 2
        panel = pygame.Rect(px, py, self.PW, self.PH)

        # Panel with gradient-like effect
        pygame.draw.rect(s, C["panel"], panel, border_radius=16)
        pygame.draw.rect(s, C["green"], panel, 2, border_radius=16)

        # ── Header ──
        pygame.draw.rect(s, C["panel2"],
                         pygame.Rect(px, py, self.PW, 52), border_radius=16)
        pygame.draw.line(s, C["border_hi"],
                         (px + 16, py + 52), (px + self.PW - 16, py + 52), 1)
        title = self.F["lg"].render("[A]  Tienda de la Aldea", True, C["green"])
        s.blit(title, (px + 20, py + 12))
        ct = self.F["md"].render(f"$ {player.coins} monedas", True, C["gold"])
        s.blit(ct, (px + self.PW - ct.get_width() - 20, py + 16))

        # ── Left: item list ──
        lx = px + 12
        ly = py + 62
        visible = 9
        for i in range(self.cursor - self._scroll,
                       min(len(SHOP_STOCK), self.cursor - self._scroll + visible)):
            if i < 0: continue
            name = SHOP_STOCK[i]
            item = ITEMS[name]
            row_r = pygame.Rect(lx, ly, 380, 46)
            sel   = (i == self.cursor)

            bg = C["panel2"] if sel else C["panel"]
            pygame.draw.rect(s, bg, row_r, border_radius=6)
            if sel:
                cat_col = self._item_color(item["type"])
                pygame.draw.rect(s, cat_col, row_r, 2, border_radius=6)
                # Category dot
                pygame.draw.circle(s, cat_col, (lx + 10, ly + 23), 5)

            # Item name
            nc = C["text_hi"] if sel else C["text"]
            nt = self.F["md"].render(name, True, nc)
            s.blit(nt, (lx + 22, ly + 8))

            # Cost
            aff = player.coins >= item["cost"]
            cc  = C["gold"] if aff else (150, 50, 50)
            cost_t = self.F["sm"].render(f"${item['cost']}", True, cc)
            s.blit(cost_t, (lx + 310, ly + 12))

            # Desc
            dt2 = self.F["xs"].render(item["desc"], True, C["text_dim"])
            s.blit(dt2, (lx + 22, ly + 28))

            ly += 50

        # Scroll indicator
        total = len(SHOP_STOCK)
        if total > visible:
            bar_h = int((visible / total) * 380)
            bar_y = py + 62 + int((self._scroll / total) * 380)
            pygame.draw.rect(s, C["border_hi"],
                             pygame.Rect(lx + 390, py + 62, 4, 380), border_radius=2)
            pygame.draw.rect(s, C["green"],
                             pygame.Rect(lx + 390, bar_y, 4, bar_h), border_radius=2)

        # ── Right: item detail ──
        rx = px + 420
        ry = py + 62
        sel_name = SHOP_STOCK[self.cursor]
        sel_item = ITEMS[sel_name]
        cat_col  = self._item_color(sel_item["type"])

        pygame.draw.rect(s, C["panel2"],
                         pygame.Rect(rx, ry, 300, 430), border_radius=10)
        pygame.draw.rect(s, cat_col,
                         pygame.Rect(rx, ry, 300, 430), 1, border_radius=10)

        # Detail header
        dh = self.F["md"].render(sel_name, True, cat_col)
        s.blit(dh, (rx + 16, ry + 14))

        pygame.draw.line(s, C["border"],
                         (rx + 16, ry + 42), (rx + 284, ry + 42), 1)

        # Stats
        yy = ry + 54
        rows = [
            ("Tipo",  TYPE_LABELS.get(sel_item["type"], sel_item["type"])),
            ("Efecto",sel_item["desc"]),
            ("Precio",f"${sel_item['cost']} monedas"),
            ("Tienes", f"${player.coins} monedas"),
        ]
        for label, val in rows:
            lt = self.F["xs"].render(label, True, C["text_dim"])
            vt = self.F["sm"].render(val,   True, C["text"])
            s.blit(lt, (rx + 16, yy))
            s.blit(vt, (rx + 16, yy + 16))
            yy += 50
            pygame.draw.line(s, C["border"],
                             (rx + 16, yy - 4), (rx + 284, yy - 4), 1)

        # Affordability indicator
        aff  = player.coins >= sel_item["cost"]
        aff_col = C["green"] if aff else (180, 50, 50)
        aff_txt = "COMPRAR  (ENTER)" if aff else "Sin fondos suficientes"
        btn_r = pygame.Rect(rx + 16, ry + 370, 268, 44)
        pygame.draw.rect(s, aff_col if aff else (50, 30, 30), btn_r, border_radius=8)
        pygame.draw.rect(s, aff_col, btn_r, 2, border_radius=8)
        bt = self.F["md"].render(aff_txt, True, C["text_hi"] if aff else (140, 80, 80))
        s.blit(bt, bt.get_rect(center=btn_r.center))

        # Already equipped / owned info
        owned = player.inventory.get(sel_name, 0)
        if owned:
            ot = self.F["xs"].render(f"Tienes {owned} en inventario", True, C["cyan"])
            s.blit(ot, (rx + 16, ry + 420))
        if sel_item["type"] == "weapon" and player.weapon == sel_name:
            et = self.F["xs"].render("[ Equipado ]", True, C["orange"])
            s.blit(et, (rx + 16, ry + 420))
        if sel_item["type"] == "shield" and player.shield == sel_name:
            et = self.F["xs"].render("[ Equipado ]", True, C["blue"])
            s.blit(et, (rx + 16, ry + 420))

        # ── Message ──
        if self._msg_t > 0:
            alpha = int(min(1.0, self._msg_t) * 255)
            mc  = C["green"] if "Compraste" in self._msg else (200, 60, 60)
            mts = self.F["md"].render(self._msg, True, mc)
            msurf = pygame.Surface(mts.get_size(), pygame.SRCALPHA)
            msurf.set_alpha(alpha)
            msurf.blit(mts, (0, 0))
            s.blit(msurf, mts.get_rect(center=(sw // 2, py + self.PH - 28)))

        # ── Footer ──
        ft = self.F["xs"].render(
            "Flechas: navegar   ENTER: comprar   Q/ESC: cerrar", True, C["text_dim"])
        s.blit(ft, ft.get_rect(center=(sw // 2, py + self.PH - 12)))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _buy(self, player):
        name = SHOP_STOCK[self.cursor]
        if player.buy(name):
            item = ITEMS[name]
            # Immediately equip weapons/shields and apply maxhp on purchase
            if item["type"] in ("weapon", "shield", "maxhp"):
                player.use_item(name)  # equips or applies; removes from inventory
                # Potions and combat items stay in inventory for manual use
            self._msg   = f"Compraste: {name}!"
            self._msg_t = 2.5
        else:
            self._msg   = "No tienes suficientes monedas."
            self._msg_t = 2.0

    def _clamp_scroll(self):
        visible = 9
        if self.cursor < self._scroll:
            self._scroll = self.cursor
        if self.cursor >= self._scroll + visible:
            self._scroll = self.cursor - visible + 1

    @staticmethod
    def _item_color(item_type: str) -> tuple:
        return {
            "potion": C["red"],
            "weapon": C["orange"],
            "shield": C["blue"],
            "maxhp":  C["green"],
            "combat": C["purple"],
        }.get(item_type, C["text"])
