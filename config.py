# ─── Screen ───────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1280, 720
FPS = 60
TITLE = "Vertex Valley"

# ─── Game States ──────────────────────────────────────────────────────────────
STATE_TITLE       = "title"
STATE_CHAR_SELECT = "char_select"
STATE_WORLD    = "world"
STATE_DIJKSTRA = "dijkstra"
STATE_TRAVEL   = "travel"
STATE_EXPLORE  = "explore"
STATE_COMBAT   = "combat"
STATE_SHOP     = "shop"
STATE_CHEST    = "chest"
STATE_GAME_OVER= "game_over"
STATE_WIN      = "win"

# ─── Node Types ───────────────────────────────────────────────────────────────
TYPE_VILLAGE  = "village"
TYPE_FOREST   = "forest"
TYPE_CAVE     = "cave"
TYPE_MOUNTAIN = "mountain"
TYPE_LAKE     = "lake"

# ─── Tile Types ───────────────────────────────────────────────────────────────
TILE_GRASS = 0
TILE_WALL  = 1
TILE_WATER = 2
TILE_TREE  = 3
TILE_ROCK  = 4
TILE_FLOOR = 5
TILE_SAND  = 6

TILE_SIZE = 32
MAP_COLS  = 52   # 52 × 32 = 1664 px  >  1280 viewport — always full coverage
MAP_ROWS  = 26   # 26 × 32 =  832 px  >   720 viewport — camera can scroll

# ─── Color Palette (dark professional theme) ──────────────────────────────────
C = {
    # Backgrounds
    "bg":         (10, 10, 16),
    "bg2":        (16, 16, 24),
    "panel":      (22, 22, 32),
    "panel2":     (28, 28, 40),
    "border":     (45, 45, 65),
    "border_hi":  (90, 90, 130),

    # Text
    "text":       (218, 216, 206),
    "text_dim":   (120, 118, 110),
    "text_hi":    (255, 255, 255),
    "text_label": (160, 158, 150),

    # Accent palette
    "green":      ( 93, 202, 165),
    "green_dk":   ( 20, 140,  90),
    "blue":       (100, 160, 255),
    "blue_dk":    ( 40,  90, 180),
    "purple":     (175, 169, 236),
    "purple_dk":  ( 90,  80, 190),
    "orange":     (240, 153, 100),
    "orange_dk":  (160,  75,  30),
    "red":        (220,  70,  70),
    "red_dk":     (130,  25,  25),
    "gold":       (255, 210,  55),
    "gold_dk":    (170, 135,  20),
    "cyan":       ( 80, 220, 210),
    "white":      (255, 255, 255),

    # Node type colours
    "village":    ( 93, 202, 165),
    "forest":     ( 70, 155,  60),
    "cave":       (140, 100, 200),
    "mountain":   (155, 140, 120),
    "lake":       ( 75, 155, 220),

    # Dijkstra visual states
    "dijk_unseen":   ( 38,  38,  55),
    "dijk_frontier": (240, 190,  40),
    "dijk_visited":  ( 50, 160, 110),
    "dijk_path":     (240, 120,  40),
    "dijk_start":    ( 80, 220, 160),
    "dijk_end":      (220,  60,  60),

    # Tiles
    "tile_grass": ( 42,  90,  32),
    "tile_wall":  ( 65,  60,  75),
    "tile_water": ( 28,  75, 155),
    "tile_tree":  ( 22,  75,  22),
    "tile_rock":  ( 85,  80,  75),
    "tile_floor": ( 55,  50,  45),
    "tile_sand":  (155, 135,  85),

    # Combat / UI
    "hp_bar":     (200,  55,  55),
    "hp_bg":      ( 45,  15,  15),
    "exp_bar":    ( 55, 115, 215),
    "exp_bg":     ( 15,  25,  55),
    "shield_bar": ( 55, 140, 215),
}

# ─── Node meta ────────────────────────────────────────────────────────────────
NODE_COLORS = {
    TYPE_VILLAGE:  C["village"],
    TYPE_FOREST:   C["forest"],
    TYPE_CAVE:     C["purple_dk"],
    TYPE_MOUNTAIN: C["mountain"],
    TYPE_LAKE:     C["lake"],
}

NODE_DISPLAY_NAMES = {
    TYPE_VILLAGE:  "Aldea",
    TYPE_FOREST:   "Bosque",
    TYPE_CAVE:     "Cueva",
    TYPE_MOUNTAIN: "Montaña",
    TYPE_LAKE:     "Lago",
}

NODE_SYMBOLS = {
    TYPE_VILLAGE:  "⌂",
    TYPE_FOREST:   "♣",
    TYPE_CAVE:     "◆",
    TYPE_MOUNTAIN: "▲",
    TYPE_LAKE:     "≈",
}

NODE_SUFFIXES = [
    "Norte", "Sur", "Este", "Oeste", "Central",
    "Oscuro", "Antiguo", "Perdido", "Sagrado", "",
]

# Enemies available per node type: (name, base_hp, base_atk, defense, exp, coin_lo, coin_hi)
ENEMY_POOL = {
    TYPE_VILLAGE:  [("Ladrón",        10,  5, 1,  5,  3,  8)],
    TYPE_FOREST:   [("Lobo",          15,  7, 2,  8,  4, 10),
                    ("Jabalí",        12,  6, 3,  7,  3,  8)],
    TYPE_CAVE:     [("Esqueleto",     18,  9, 3, 12,  6, 15),
                    ("Slime",         12,  4, 1,  8,  4, 10),
                    ("Murciélago",    10,  6, 2,  7,  3,  8)],
    TYPE_MOUNTAIN: [("Troll",         26, 12, 4, 18,  8, 20),
                    ("Águila Gigante",16,  9, 2, 12,  5, 12)],
    TYPE_LAKE:     [("Serpiente",     16,  7, 2, 10,  5, 12),
                    ("Rana Gigante",  13,  6, 1,  8,  4, 10)],
}

# Shop items: name -> {type, bonus, cost, desc}
# type: potion|weapon|shield|maxhp|combat
ITEMS = {
    # Pociones
    "Pocion":       {"type": "potion",  "bonus": 15, "cost":  8, "desc": "Restaura 15 HP"},
    "Pocion+":      {"type": "potion",  "bonus": 35, "cost": 20, "desc": "Restaura 35 HP"},
    "Elixir":       {"type": "potion",  "bonus": 70, "cost": 45, "desc": "Restaura 70 HP"},
    # Armas
    "Espada":       {"type": "weapon",  "bonus":  5, "cost": 15, "desc": "+5 ataque"},
    "Espada+":      {"type": "weapon",  "bonus": 12, "cost": 35, "desc": "+12 ataque"},
    "Espada Runa":  {"type": "weapon",  "bonus": 22, "cost": 65, "desc": "+22 ataque"},
    # Escudos
    "Escudo":       {"type": "shield",  "bonus":  4, "cost": 15, "desc": "+4 defensa"},
    "Escudo+":      {"type": "shield",  "bonus":  9, "cost": 35, "desc": "+9 defensa"},
    "Escudo Acero": {"type": "shield",  "bonus": 16, "cost": 65, "desc": "+16 defensa"},
    # Especiales
    "Amuleto":      {"type": "maxhp",   "bonus": 20, "cost": 30, "desc": "+20 HP maximo"},
    "Bomba":        {"type": "combat",  "bonus": 45, "cost": 18, "desc": "45 dano al enemigo"},
    "Bomba+":       {"type": "combat",  "bonus": 90, "cost": 38, "desc": "90 dano al enemigo"},
}

SHOP_STOCK = [
    "Pocion", "Pocion+", "Elixir",
    "Espada", "Espada+", "Espada Runa",
    "Escudo", "Escudo+", "Escudo Acero",
    "Amuleto", "Bomba", "Bomba+",
]

# ─── Personajes seleccionables ────────────────────────────────────────────────
CHARACTERS = [
    {
        "id":       "guerrero",
        "name":     "Guerrero",
        "desc":     "Fuerte en combate cuerpo a cuerpo.\nEmpieza con espada.",
        "hp":       38, "attack": 11, "defense": 5,
        "shirt":    ( 62, 108, 200),
        "hair":     ( 90,  58,  18),
        "pants":    ( 35,  44, 112),
        "special":  "Empieza con Espada",
        "item":     "Espada",
        "heal_mul": 1.0,
    },
    {
        "id":       "maga",
        "name":     "Maga",
        "desc":     "Experta en pociones y magia.\nPociones curan 75%% mas.",
        "hp":       28, "attack": 7, "defense": 8,
        "shirt":    (160,  60, 200),
        "hair":     ( 30,  20, 100),
        "pants":    ( 60,  20, 120),
        "special":  "Pociones curan +75%%",
        "item":     "Pocion+",
        "heal_mul": 1.75,
    },
]
