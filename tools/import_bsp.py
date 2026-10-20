#!/usr/bin/env python3
"""Convert a Source 1 .bsp into a zombie-zone map document (maps/<id>.json).

    python3 -I tools/import_bsp.py tools/bsp/zs_ravenstreet.json path/to/zs_ravenstreet_v1.bsp [out_dir]
    python3 -I tools/import_bsp.py tools/bsp/zs_ravenstreet.json zs_ravenstreet.json [out_dir]

The second form reads the family's intermediate document (dot-map's `tools/bsp/bsp.py
convert`) instead of the map; the first builds that document in memory. Either way this file
is the game's adapter: reading the format and cutting brushes into boxes are dot-map's
(`tools/bsp/`, found beside this repository or at `$DOTBSP_PATH`), so a reader fix reaches
every game that converts maps.

The game's maps are boxes, not meshes, so this reads the *brushes* (the solid volume the
engine collides with) and writes each as a box, by dot-map's `boxes.decompose`:

  * an axis-aligned brush, a brush turned about the vertical, or an upright prism that fills
    most of a turned rectangle is one box (with `yaw`);
  * anything else (a ramp, a roof, a wedge) is sliced into 0.4 m slabs along its slope, each slab
    a box spanning what the brush covers at the slab's middle. An approximation, kept small;
  * a brush with a sky, clip or all-nodraw side is an invisible wall; glass is `glass`;
  * the author's textures are never used (the game draws its own procedural surfaces): a
    material name maps to the nearest surface by `MATERIALS`.

Entities become spawns (`survivor_class`, `zombie_classes`), items, caches, lights, props
(`prop_models`: model path -> Kenney catalogue id) and barricades (`barricade_class` brush
entities, drawn as boards over their opening). The nav floors are derived from the boxes: every
cell of a half-metre grid with headroom, flood-filled from the survivor spawns across steps a
body climbs, merged into rectangles per height.

The spec JSON (tools/bsp/<id>.json) names the map, author, page and licence; the author and the
removal-on-request line go into `author` and `attribution`. The .bsp itself is never committed.
"""

import json
import math
import os
import re
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _dotbsp_path():
    """dot-map's tools/bsp: $DOTBSP_PATH, else the sibling checkout dot-bootstrap makes."""
    for p in (os.environ.get("DOTBSP_PATH", ""), os.path.join(HERE, "..", "..", "dot-map", "tools", "bsp")):
        if p and os.path.isfile(os.path.join(p, "dotbsp", "reader.py")):
            return os.path.abspath(p)
    sys.exit("import_bsp: dot-map's tools/bsp was not found; clone dot-map beside this "
             "repository (dot-bootstrap does) or set DOTBSP_PATH to its tools/bsp")


sys.path.insert(1, _dotbsp_path())
from dotbsp import boxes as dboxes, intermediate, reader  # noqa: E402


# A map compiled with an empty game lump (no static props) crashes dot-map's reader; the fix
# belongs there, and until it is made this adapter reads such a map as having no props.
_game_lumps = reader.Bsp.game_lumps


def _safe_game_lumps(self):
    try:
        return _game_lumps(self)
    except Exception:
        return {}


reader.Bsp.game_lumps = _safe_game_lumps

S = 0.01905           # metres per Source unit
CELL = 0.5            # nav analysis grid
DROP = 3.0            # a body drops this far
JUMP = 0.9            # and jumps up this far
STEP = 0.42           # a body climbs this between neighbouring cells
THIN_WALLS = False    # set from the spec: see _thin_wall_over
THIN_LINTELS = False   # set from the spec (`thin_lintels`): see _thin_wall_over
GREEDY_FLOORS = False  # set from the spec (`greedy_floors`): see build_nav
MIN_FLOOR_Y = None    # spec min_floor_y: a sump the horde drops into and cannot climb out of is no floor
HEAD = 1.7            # headroom a floor needs
SLAB = 0.4

MATERIALS = [
    (r"glass", "glass"),
    (r"stair", "wood"),
    (r"woodfloor|parquet", "wood_floor"),
    (r"wood", "wood"),
    (r"ceiling", "ceiling"),
    (r"carpet", "carpet"),
    (r"brick", "brick"),
    (r"plaster", "plaster"),
    (r"tile", "tile"),
    (r"metal|rail|vent", "metal"),
    (r"concretefloor", "concrete"),
    (r"concrete", "concrete"),
    (r"asphalt|road", "asphalt"),
    (r"sidewalk|pavement", "sidewalk"),
    (r"grass|nature", "grass"),
    (r"dirt|sand|ground", "dirt"),
    (r"stone|rock|cobble", "stone"),
]


def material_for(name):
    for pat, mat in MATERIALS:
        if re.search(pat, name):
            return mat
    return "concrete"


def r3(v):
    return round(v, 3)


class Brush:
    def __init__(self, planes, pts, contents, sides):
        self.planes, self.pts, self.contents, self.sides = planes, pts, contents, sides


def gpt(p, y0):
    """Source (x, y, z) units to game metres."""
    return (p[0] * S, p[2] * S - y0, -p[1] * S)


def read_brush(doc, rec):
    """One brush record of the intermediate. Its planes and hull are already where the map
    put its entity (the document moves a brush entity's brushes by the entity's origin)."""
    mats = doc["materials"]
    planes = [tuple(sd["plane"]) for sd in rec["sides"]]
    sides = [(tuple(sd["plane"]), sd["flags"], mats[sd["material"]]["name"].lower()) for sd in rec["sides"]]
    return Brush(planes, [tuple(p) for p in rec["hull"]], rec["contents"], sides)


def classify(br):
    """(kind, material): kind is 'solid', 'invisible', 'sky' (the world's own box) or 'glass'."""
    names = [n for _, f, n in br.sides]
    real = [(pl, f, n) for pl, f, n in br.sides if not n.startswith("tools/")]
    if not real:
        return ("sky" if any("skybox" in n for n in names) else "invisible"), "concrete"
    if br.contents & (reader.CONTENTS_PLAYERCLIP | 0x20000):
        return "invisible", "concrete"
    top = [n for pl, f, n in real if pl[2] > 0.5]
    name = (top or [n for _, _, n in real])[0]
    if br.contents & 0x2:
        return "glass", "glass"
    return "solid", material_for(name)


def boxes_from_brush(br, y0):
    out = []
    for b in dboxes.decompose(br.planes, br.pts, slab=SLAB / S, min_size=0.04 / S, max_slabs=40):
        sx, sy, sz = dboxes.size(b)
        out.append({"at": gpt(dboxes.centre(b), y0), "size": (sx * S, sz * S, sy * S), "yaw": b["phi"] % 90.0, "kind": b.get("kind")})
    return out


def parse_vec(s):
    return [float(t) for t in s.split()]


# --- nav floors ---------------------------------------------------------------------------

def inside_box(b, x, z):
    dx, dz = x - b["at"][0], z - b["at"][2]
    yaw = b.get("yaw", 0)
    if yaw:
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        lx, lz = dx * c - dz * s, dx * s + dz * c
    else:
        lx, lz = dx, dz
    return abs(lx) <= b["size"][0] / 2 and abs(lz) <= b["size"][2] / 2


def cell_index(boxes):
    grid = {}
    for bi, b in enumerate(boxes):
        if b.get("yaw"):
            r = math.hypot(b["size"][0], b["size"][2]) / 2
            x0, x1, z0, z1 = b["at"][0] - r, b["at"][0] + r, b["at"][2] - r, b["at"][2] + r
        else:
            x0, x1 = b["at"][0] - b["size"][0] / 2, b["at"][0] + b["size"][0] / 2
            z0, z1 = b["at"][2] - b["size"][2] / 2, b["at"][2] + b["size"][2] / 2
        for ix in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for iz in range(int(math.floor(z0 / CELL)), int(math.floor(z1 / CELL)) + 1):
                grid.setdefault((ix, iz), []).append(bi)
    return grid


def _thin_wall_over(b, ix, iz):
    """A wall thinner than a cell that stands over part of it. The flood samples a cell's centre,
    so a one-unit-thick wall (Run For Your Life's dividers are 2 cm) fell between the samples:
    the flood walked through it and the route, items and spawns were put on the far side of a
    wall the body cannot pass. The cell is the wall's when the wall overlaps it at all. A spec opts
    in (`thin_walls`): Nuke's route was authored against the old flood, and its panes of glass and
    clip slivers would seal it until its authoring is redone."""
    if not THIN_WALLS or b.get("yaw") or min(b["size"][0], b["size"][2]) >= CELL:
        return False
    # A thin beam over a doorway (a lintel 7 cm thick, 1.5 m up) is as much in a body's way as a
    # wall; a thin plate on the floor is not. `thin_lintels` opts in, to leave converted maps as were.
    if b["size"][1] <= HEAD and not (THIN_LINTELS and b["at"][1] - b["size"][1] / 2 > 0.8):
        return False
    return (abs(b["at"][0] - (ix + 0.5) * CELL) < (b["size"][0] + CELL) / 2
            and abs(b["at"][2] - (iz + 0.5) * CELL) < (b["size"][2] + CELL) / 2)


def surfaces_at(boxes, grid, ix, iz):
    """Walkable heights in a cell: box tops with headroom."""
    cx, cz = (ix + 0.5) * CELL, (iz + 0.5) * CELL
    spans = []
    for bi in grid.get((ix, iz), ()):
        b = boxes[bi]
        if inside_box(b, cx, cz) or _thin_wall_over(b, ix, iz):
            spans.append((b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2))
    out = []
    for lo, hi in spans:
        if any(l2 < hi + HEAD and h2 > hi + 0.05 for l2, h2 in spans if (l2, h2) != (lo, hi)):
            continue
        out.append(round(hi, 2))
    return sorted(set(out))


def build_nav(boxes, starts, blocked=None, wide=False):
    solid = [b for b in boxes if b.get("solid", True) and b.get("nav", True) is not False and not b.get("_sky")]
    grid = cell_index(solid)
    surf = {}
    for ix, iz in list(grid.keys()):
        s = surfaces_at(solid, grid, ix, iz)
        if s:
            if MIN_FLOOR_Y is not None:
                s = [h for h in s if h >= MIN_FLOOR_Y]
            if s:
                surf[(ix, iz)] = s
    seen = set()
    parent = {}
    dist = {}
    dq = deque()
    blocked = blocked or {}

    def is_open(ix, iz, h):
        return not any(abs(by - h) <= 0.5 for by in blocked.get((ix, iz), ()))

    def is_wide(ix, iz, h):
        """The game's graph is a metre apart: a way narrower than two cells has no point in it, and
        a prop in the middle of a doorway takes the rest. Only a 2x2 block of open cells counts."""
        for ox in (-1, 0):
            for oz in (-1, 0):
                if all(any(abs(h2 - h) <= STEP and is_open(ix + ox + i, iz + oz + j, h2) for h2 in surf.get((ix + ox + i, iz + oz + j), ()))
                       for i in (0, 1) for j in (0, 1)):
                    return True
        return False

    for st in starts:
        ix, iz = int(math.floor(st[0] / CELL)), int(math.floor(st[2] / CELL))
        cands = [h for h in surf.get((ix, iz), []) if h <= st[1] + 0.6]
        if cands:
            h = max(cands)
            seen.add((ix, iz, h))
            dist[(ix, iz, h)] = 0
            dq.append((ix, iz, h))
    links = {}
    while dq:
        ix, iz, h = dq.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for h2 in surf.get((ix + dx, iz + dz), ()):
                dh = h2 - h
                if (-DROP <= dh < -STEP or STEP < dh <= JUMP) and (ix + dx, iz + dz, h2) not in seen and (
                        not wide or (is_open(ix + dx, iz + dz, h2) and is_wide(ix + dx, iz + dz, h2))):
                    # a drop or a jump up: the body crosses it, the zombies by a link
                    key = (ix // 3, iz // 3, round(h, 1), round(h2, 1))
                    if key not in links:
                        links[key] = [r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL), r3((ix + dx + 0.5) * CELL), r3(h2), r3((iz + dz + 0.5) * CELL)]
                if (abs(dh) <= STEP or -DROP <= dh <= JUMP) and (ix + dx, iz + dz, h2) not in seen and (
                        not wide or (is_open(ix + dx, iz + dz, h2) and is_wide(ix + dx, iz + dz, h2))):
                    seen.add((ix + dx, iz + dz, h2))
                    parent[(ix + dx, iz + dz, h2)] = (ix, iz, h)
                    dist[(ix + dx, iz + dz, h2)] = dist[(ix, iz, h)] + 1
                    dq.append((ix + dx, iz + dz, h2))
    # Surfaces within 0.12 m of each other (a kerb, a worn step) are one floor: the game joins
    # nav points by distance, and two floors 0.1 m apart that merely touch are not joined.
    hs = sorted({h for _, _, h in seen})
    snap = {}
    i = 0
    while i < len(hs):
        j = i
        while j + 1 < len(hs) and hs[j + 1] - hs[i] <= 0.12:
            j += 1
        for k in range(i, j + 1):
            snap[hs[k]] = hs[j]
        i = j + 1
    byh = {}
    for ix, iz, h in seen:
        byh.setdefault(snap[h], set()).add((ix, iz))
    floors = []
    if GREEDY_FLOORS:
        # A rectangle cover that takes the longest run from the first free cell and grows it down
        # while the whole run stays free, rather than merging only rows with identical runs: an
        # irregular plan fell into hundreds of slivers, over the document's 800 floors.
        for h, cells in sorted(byh.items()):
            free = set(cells)
            for iz, ix in sorted((c[1], c[0]) for c in cells):
                if (ix, iz) not in free:
                    continue
                xe = ix
                while (xe + 1, iz) in free:
                    xe += 1
                ze = iz
                while all((x, ze + 1) in free for x in range(ix, xe + 1)):
                    ze += 1
                for z in range(iz, ze + 1):
                    for x in range(ix, xe + 1):
                        free.discard((x, z))
                floors.append([r3(ix * CELL + 0.05), r3(iz * CELL + 0.05), r3((xe + 1) * CELL - 0.05), r3((ze + 1) * CELL - 0.05), r3(h)])
        build_nav.links = list(links.values())
        return floors, surf, seen, parent, dist
    for h, cells in sorted(byh.items()):
        rows = {}
        for ix, iz in cells:
            rows.setdefault(iz, []).append(ix)
        runs = {}
        for iz, xs_ in rows.items():
            xs_.sort()
            a = prev = xs_[0]
            for x in xs_[1:] + [None]:
                if x is not None and x == prev + 1:
                    prev = x
                    continue
                runs.setdefault((a, prev), []).append(iz)
                if x is not None:
                    a = prev = x
        for (a, bb), izs in runs.items():
            izs.sort()
            s = p = izs[0]
            for z in izs[1:] + [None]:
                if z is not None and z == p + 1:
                    p = z
                    continue
                floors.append([r3(a * CELL + 0.05), r3(s * CELL + 0.05), r3((bb + 1) * CELL - 0.05), r3((p + 1) * CELL - 0.05), r3(h)])
                if z is not None:
                    s = p = z
    build_nav.links = list(links.values())
    return floors, surf, seen, parent, dist


def floor_at(surf, seen, x, z, y):
    ix, iz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
    hs = [h for h in surf.get((ix, iz), []) if (ix, iz, h) in seen and h <= y + 0.8]
    return max(hs) if hs else None


class Source:
    """The intermediate document, indexed the way this importer asks for it."""

    def __init__(self, doc):
        probs = intermediate.check(doc)
        if probs:
            sys.exit("import_bsp: not a usable intermediate document: " + "; ".join(probs[:5]))
        self.doc = doc
        self.entities = [e["keys"] for e in doc["entities"]]
        self.models = {m["index"]: m for m in doc["models"]}
        self.brushes = {b["id"]: b for b in doc["brushes"]}

    def model_bounds(self, model):
        """The model's own bounds, origin-relative as the format stores them."""
        m = self.models[model]
        o = m["origin"]
        return ([m["mins"][k] - o[k] for k in range(3)], [m["maxs"][k] - o[k] for k in range(3)])

    def model_brushes(self, model):
        m = self.models.get(model)
        return [self.brushes[i] for i in m["brushes"]] if m else []


def load_source(path):
    if path.lower().endswith(".json"):
        with open(path) as f:
            return Source(json.load(f))
    return Source(intermediate.build(reader.Bsp(path).load(), name=os.path.splitext(os.path.basename(path))[0]))


def model_boxes(bs, model, y0):
    out = []
    for rec in bs.model_brushes(model):
        if not rec["hull"]:
            continue
        br = read_brush(bs.doc, rec)
        if not br.pts or not (br.contents & (1 | 0x2 | 0x10000)):
            continue
        kind, mat = classify(br)
        made = boxes_from_brush(br, y0)
        # A brush cut into slabs along its slope is a ramp or a stair; how much it rises is how
        # a spec decides whether the horde's graph (a step of half a spacing at most) can use it.
        rise = 0.0
        if made and all(bx["kind"] == "slab" for bx in made):
            rise = max(bx["at"][1] + bx["size"][1] / 2 for bx in made) - min(bx["at"][1] - bx["size"][1] / 2 for bx in made)
        for bx in made:
            b = {"at": [r3(v) for v in bx["at"]], "size": [r3(max(v, 0.02)) for v in bx["size"]], "mat": mat}
            if bx["yaw"]:
                b["yaw"] = r3(bx["yaw"])
            if rise:
                b["_rise"] = r3(rise)
            if kind in ("invisible", "sky"):
                b["visible"] = False
            if kind == "sky":
                b["_sky"] = True
            out.append(b)
    return out


# --- the document ---------------------------------------------------------------------------

def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    spec = json.load(open(argv[1]))
    global THIN_WALLS, GREEDY_FLOORS, THIN_LINTELS
    THIN_LINTELS = bool(spec.get("thin_lintels"))
    THIN_WALLS = bool(spec.get("thin_walls"))
    GREEDY_FLOORS = bool(spec.get("greedy_floors"))
    global STEP, JUMP, MIN_FLOOR_Y
    MIN_FLOOR_Y = spec.get("min_floor_y")
    if spec.get("flood_step"):
        # The game's graph joins points only when they differ by half a spacing at most, so a body the
        # flood lets jump up 0.9 m reaches a ledge the horde never will: a flood that walks only what
        # the graph can keeps ground nobody can reach out of the map.
        STEP = JUMP = float(spec["flood_step"])
    out_dir = argv[3] if len(argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "maps")
    bs = load_source(argv[2])
    ents = bs.entities
    surv = [e for e in ents if e.get("classname") == spec["survivor_class"]]
    y0 = float(spec.get("y0", 0.0))    # spec y0: metres the source floor sits above the game's y = 0 (the nav is flat at 0)

    boxes, skipped = [], 0
    for b in model_boxes(bs, 0, y0):
        boxes.append(b)

    # brush entities: solid ones are part of the world; gates are held back for the route
    gate_cands = []
    for e in ents:
        m = str(e.get("model", ""))
        if not m.startswith("*"):
            continue
        cls = e.get("classname")
        if cls in spec.get("solid_classes", []):
            boxes.extend(model_boxes(bs, int(m[1:]), y0))
        elif cls in spec.get("gate_classes", []):
            only = spec.get("gate_names")
            gb = model_boxes(bs, int(m[1:]), y0)
            if gb and (only is None or e.get("targetname") in only):
                e = dict(e)
                e.update(only.get(e.get("targetname"), {}) if only else {})
                gate_cands.append((e, gb))

    # Authoring the source could not carry: a moving platform or a puzzle step is a thing the game
    # has no mover for, so a spec adds the boxes that stand in for it (`add_boxes`, game coordinates),
    # cuts the ones that must go (`cut`: regions [x0,y0,z0,x1,y1,z1] whose box centres are removed),
    # and names a gate made of added boxes (`extra_gates`) that opens like a door.
    for c in spec.get("cut", []):
        x0, y0_, z0, x1, y1, z1 = c[:6]
        boxes[:] = [b for b in boxes if not (x0 <= b["at"][0] <= x1 and y0_ <= b["at"][1] <= y1 and z0 <= b["at"][2] <= z1
                                             and (len(c) < 7 or b["mat"] == c[6]))]
    # `crop` [x0, z0, x1, z1]: a map converted only in part (an escape map whose later stages need a
    # lift or a vanishing floor) keeps the boxes that touch this rectangle, game coordinates. What is
    # beyond is a wall of sky and scenery nobody reaches, and it is most of a big map's box count.
    if spec.get("crop"):
        cx0, cz0, cx1, cz1 = spec["crop"]
        n0 = len(boxes)
        boxes[:] = [b for b in boxes if b["at"][0] + b["size"][0] / 2 >= cx0 and b["at"][0] - b["size"][0] / 2 <= cx1
                    and b["at"][2] + b["size"][2] / 2 >= cz0 and b["at"][2] - b["size"][2] / 2 <= cz1]
        print("  cropped %d of %d boxes outside the stage" % (n0 - len(boxes), n0))
    # `clip_y` [lo, hi]: a wall or shaft that runs far past the stage (a trench wall a hundred metres
    # tall) is shortened to this band, and one wholly outside is dropped. It is the same wall to a
    # body, and a frame looking down is no longer blocked by it.
    if spec.get("clip_y"):
        lo_c, hi_c = spec["clip_y"]
        kept = []
        for b in boxes:
            b0, b1 = b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2
            if b1 <= lo_c or b0 >= hi_c:
                continue
            if b0 < lo_c or b1 > hi_c:
                n0, n1 = max(b0, lo_c), min(b1, hi_c)
                b["at"][1], b["size"][1] = r3((n0 + n1) / 2), r3(n1 - n0)
            kept.append(b)
        print("  clip_y: %d boxes kept of %d" % (len(kept), len(boxes)))
        boxes[:] = kept
    # `drop_small` [volume, longest side]: detail too small to matter to a body or the graph (shelf
    # slats, trim, rail posts) is dropped so a big map fits the document's box limit. A box that
    # long is a floor strip or a stair slab, never dropped whatever its volume.
    if spec.get("drop_small"):
        vmax, smax = spec["drop_small"]
        small = [b for b in boxes if b["size"][0] * b["size"][1] * b["size"][2] < vmax and max(b["size"]) < smax]
        boxes[:] = [b for b in boxes if b not in small]
        print("  dropped %d small boxes" % len(small))
    for ab in spec.get("add_boxes", []):
        boxes.append(dict(ab))
    # `stairs`: a flight that stands in for a slope too steep for the graph (a slide, a ladder shaft).
    # [x0, y0, z0, x1, y1, z1, width]: steps from the top (x0, y0, z0) to the foot (x1, y1, z1) along
    # the longer horizontal axis, each rising at most 0.4 m over a run of 1 m or more (under the flood's 0.42 step) (the graph's points are a metre apart), as wide as
    # `width` across, standing on `base` (the lowest y) so there is no gap under a step.
    for st in spec.get("stairs", []):
        x0, y0_, z0, x1, y1_, z1, w = st[:7]
        base = st[7] if len(st) > 7 else min(y0_, y1_) - 1.0
        along_x = abs(x1 - x0) >= abs(z1 - z0)
        length = abs(x1 - x0) if along_x else abs(z1 - z0)
        n = max(1, int(math.ceil(abs(y1_ - y0_) / 0.4)))
        run = length / (n + 1)
        for k in range(n + 1):
            top = y0_ + (y1_ - y0_) * k / n
            t = (k + 0.5) / (n + 1)
            cx, cz = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
            sz = [r3(run), r3(top - base), r3(w)] if along_x else [r3(w), r3(top - base), r3(run)]
            boxes.append({"at": [r3(cx), r3((top + base) / 2), r3(cz)], "size": sz, "mat": st[8] if len(st) > 8 else "metal"})
    if spec.get("drop_buried"):
        # A box wholly inside another solid one adds nothing to collision, but the graph reads its
        # top as an obstacle at a height no floor has: two overlapping terraces left a whole step
        # with no points on it.
        def extent(b):
            return [b["at"][k] - b["size"][k] / 2 for k in range(3)] + [b["at"][k] + b["size"][k] / 2 for k in range(3)]
        ext = [(b, extent(b)) for b in boxes if not b.get("yaw") and b.get("visible", True)]
        buried = set()
        for b, e in ext:
            for c, f in ext:
                if c is not b and id(c) not in buried and all(f[k] <= e[k] + 0.02 for k in range(3)) and all(f[k + 3] >= e[k + 3] - 0.02 for k in range(3)):
                    buried.add(id(b))
                    break
        boxes[:] = [b for b in boxes if id(b) not in buried]
        print("  dropped %d buried box(es)" % len(buried))
    if spec.get("drop_ramps"):
        # The horde's graph joins two points only when they differ by half a spacing at most, so a
        # stair steeper than one in two has no way up for a zombie, and an upper floor it cannot
        # climb to would be a place the team holds for ever. The steep slopes go; what is left of
        # the map is level ground.
        gone = [b for b in boxes if b.get("_rise", 0) >= spec["drop_ramps"]]
        boxes[:] = [b for b in boxes if b not in gone]
        print("  dropped %d ramp slab(s) rising %.1f m or more" % (len(gone), spec["drop_ramps"]))
    for g in spec.get("extra_gates", []):
        gate_cands.append((dict(g), [dict(b) for b in g["boxes"]]))

    # A sky lid (a slab over the whole map, there to keep a player from climbing out) is a floor to the
    # bake: every random route the choke finder walks starts and ends up on it, so the street's
    # traffic is a handful of routes and no place is a choke. Nobody reaches it from the ground.
    if spec.get("drop_lids"):
        lids = [b for b in boxes if b["size"][0] * b["size"][2] > 1500.0 and b["at"][1] - b["size"][1] / 2 > 3.0]
        boxes[:] = [b for b in boxes if b not in lids]
        print("  dropped %d sky lid(s)" % len(lids))

    # Roadblocks across an open street. The choke finder wants narrow places many routes share,
    # and a street nine metres wide has none: the doors are barricaded (off the bake), so the
    # horde's whole way to a house would be open ground. A wrecked-vehicle line with a gap a
    # little over two bodies wide gives it somewhere to be funnelled, and the gap is the choke.
    for x, gap0, gap1 in spec.get("roadblocks", []):
        z0, z1 = spec["street_z"]
        for a, b_ in ((z0, gap0), (gap1, z1)):
            if b_ - a > 0.1:
                boxes.append({"at": [r3(x), 1.1, r3((a + b_) / 2)], "size": [0.8, 2.2, r3(b_ - a)],
                              "mat": "metal", "tint": [0.42, 0.4, 0.38]})

    barricades, bar_boxes, bar_geo = [], [], []
    bc = spec.get("barricade_class")
    for e in ents:
        if bc and e.get("classname") == bc and str(e.get("model", "")).startswith("*"):
            lo, hi = bs.model_bounds(int(e["model"][1:]))
            og = parse_vec(e.get("origin", "0 0 0"))      # a brush entity's model is origin-relative
            lo = [lo[k] + og[k] for k in range(3)]
            hi = [hi[k] + og[k] for k in range(3)]
            a, b_ = gpt(lo, y0), gpt(hi, y0)
            mn = [min(a[k], b_[k]) for k in range(3)]
            mx = [max(a[k], b_[k]) for k in range(3)]
            size = [mx[k] - mn[k] for k in range(3)]
            bid = "bar_%d" % (len(barricades) + 1)
            thin = 0 if size[0] < size[2] else 2
            n = max(2, int(round(size[1] / 0.36)))
            for k in range(n):
                sz = list(size)
                sz[1] = size[1] / n * 0.82
                sz[thin] = max(sz[thin], 0.14)
                bar_boxes.append({
                    "at": [r3((mn[0] + mx[0]) / 2), r3(mn[1] + (k + 0.5) * size[1] / n), r3((mn[2] + mx[2]) / 2)],
                    "size": [r3(v) for v in sz], "mat": "wood", "tint": [0.62 - 0.05 * (k % 3), 0.46 - 0.04 * (k % 3), 0.3],
                    "nav": False, "barricade": bid})
            bar_geo.append((bid, (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2, thin))
            barricades.append({"id": bid, "label": "the boards at x %d z %d" % (round((mn[0] + mx[0]) / 2), round((mn[2] + mx[2]) / 2)),
                               "health": spec.get("barricade_health", 1800)})

    def src_to_game(e):
        return gpt(parse_vec(e["origin"]), y0)

    # A map whose first stage cannot be built from brushes (a lift, a vanishing floor) starts its
    # survivors at a later stage instead: `survivor_start` is a block of spawns at a game position.
    ss = spec.get("survivor_start")
    start_spawns = []
    if ss:
        for r in range(ss.get("rows", 4)):
            for c in range(ss.get("cols", 6)):
                start_spawns.append({"at": [r3(ss["at"][0] + c * ss.get("gap", 1.4)), r3(ss["at"][1] + 0.1), r3(ss["at"][2] + r * ss.get("gap", 1.4))],
                                     "yaw": ss.get("yaw", 0.0)})
    starts = [s_["at"] for s_ in start_spawns] if ss else [src_to_game(e) for e in surv]
    floors, surf, seen, parent, dist = build_nav(boxes, starts)

    # Distant scenery (the original's backdrop pieces, its boundary walls twenty metres tall) is a
    # tall box nobody on the ground can stand beside: with no ground within 0.6 m of its footprint
    # it only gives the navigation bake tops to wander on, and the choke finder's random routes
    # start and end up there (twelve of a hundred and ninety-two found a way) instead of in the street.
    if spec.get("drop_decor"):
        def beside_ground(b, g=0.6):
            x0, x1 = b["at"][0] - b["size"][0] / 2 - g, b["at"][0] + b["size"][0] / 2 + g
            z0, z1 = b["at"][2] - b["size"][2] / 2 - g, b["at"][2] + b["size"][2] / 2 + g
            return any(x0 < f[2] and x1 > f[0] and z0 < f[3] and z1 > f[1] for f in floors)
        far = [b for b in boxes if b["at"][1] + b["size"][1] / 2 > 3.0 and not beside_ground(b)]
        boxes[:] = [b for b in boxes if b not in far]
        print("  dropped %d boxes of distant scenery" % len(far))

    # `drop_ceilings` [min area, y]: a roof or ceiling slab (thin, wide, no walkable top: a body
    # can never stand on it) at least `y` metres above the ground under it is a lid over the stage.
    # It hides the route from the overview and from every frame that looks down, and the horde
    # never needed it: the walls are tall. Dropped after the flood, so a slab that is a floor to
    # somebody (a walkway, a gantry) is kept because its top is ground.
    if spec.get("drop_ceilings"):
        amin, ymin = spec["drop_ceilings"]

        def walkable_top(b):
            top = b["at"][1] + b["size"][1] / 2
            for fx in (-0.4, 0.0, 0.4):
                for fz in (-0.4, 0.0, 0.4):
                    ix = int(math.floor((b["at"][0] + fx * b["size"][0]) / CELL))
                    iz = int(math.floor((b["at"][2] + fz * b["size"][2]) / CELL))
                    if any(abs(h - top) <= 0.3 and (ix, iz, h) in seen for h in surf.get((ix, iz), ())):
                        return True
            return False
        lids = [b for b in boxes if b["size"][1] <= 1.2 and b["size"][0] * b["size"][2] >= amin and b["at"][1] - b["size"][1] / 2 >= ymin
                and not b.get("yaw") and not walkable_top(b)]
        boxes[:] = [b for b in boxes if b not in lids]
        print("  dropped %d ceiling slab(s)" % len(lids))

    # Props are cut out of the game's ground, and a metre-spaced graph has no point in a way
    # narrower than two cells: both left whole rooms (posts, caches, a window's far side) off the
    # horde's ground though the cell flood reached them. So the ground is flooded again with the
    # props as obstacles and 2x2 openings only; a prop that shuts a way the first flood had is
    # dropped (a sofa in a doorway), and what is still cut off is not ground.
    def settle(p, lift=0.0):
        h = floor_at(surf, seen, p[0], p[2], p[1])
        return None if h is None else [r3(p[0]), r3(h + lift), r3(p[2])]

    sizes = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prop_sizes.json")))["props"]
    cand = []
    for e in ents:
        if e.get("classname") in ("prop_physics", "prop_dynamic", "func_physbox", "prop_physics_override", "prop_dynamic_override", "prop_physics_multiplayer"):
            pm = spec.get("prop_models", {})
            cid = pm.get(e.get("model")) or {k.lower(): v for k, v in pm.items()}.get(str(e.get("model", "")).lower())
            p = settle(src_to_game(e)) if cid else None
            if p:
                cand.append({"id": cid, "at": p, "yaw": r3(parse_vec(e.get("angles", "0 0 0"))[1] % 360)})

    # Static props are compiled out of the entity lump (dot-map's intermediate keeps them apart),
    # and in most maps they are the furniture and the wrecks.
    pm_lower = {k.lower(): v for k, v in spec.get("prop_models", {}).items()}
    for sp in getattr(bs, "doc", {}).get("static_props", []) if isinstance(getattr(bs, "doc", None), dict) else []:
        cid = pm_lower.get(str(sp.get("model", "")).lower().replace("//", "/"))
        if not cid:
            continue
        o, a = sp["origin"], sp.get("angles", [0, 0, 0])
        p = settle(src_to_game({"origin": "%f %f %f" % (o[0], o[1], o[2])}))
        if p:
            cand.append({"id": cid, "at": p, "yaw": r3(a[1] % 360)})

    if spec.get("prop_min_y") is not None:
        # Props that settled into a pit the players never reach (a lower level the flood leaves out).
        cand = [c for c in cand if c["at"][1] >= spec["prop_min_y"]]

    def blocks_of(plist):
        out = {}
        for pr in plist:
            sx, sy, sz = sizes[pr["id"]]
            if sy <= 0.5:
                continue
            rad = max(sx, sz) / 2 + 0.3
            for ix in range(int(math.floor((pr["at"][0] - rad) / CELL)), int(math.floor((pr["at"][0] + rad) / CELL)) + 1):
                for iz in range(int(math.floor((pr["at"][2] - rad) / CELL)), int(math.floor((pr["at"][2] + rad) / CELL)) + 1):
                    out.setdefault((ix, iz), []).append(pr["at"][1])
        return out

    def ground_cells(plist):
        r = build_nav(boxes, starts, blocks_of(plist), True)
        return r, {(a, b) for a, b, _ in r[2]}

    keep = list(cand)
    res, have = ground_cells(keep)
    base = {(a, b) for a, b, _ in build_nav(boxes, starts, None, True)[2]}
    for pr in list(cand):
        if sizes[pr["id"]][1] <= 0.5 or have >= base:
            continue
        trial = [q for q in keep if q is not pr]
        r2, h2 = ground_cells(trial)
        # A prop's own footprint is cells the flood loses by definition; only what it cut off
        # beyond that (a room behind it) is a reason to drop it, or every prop on open ground goes.
        if len(h2) - len(have) > len(blocks_of([pr])) + 6:
            keep, res, have = trial, r2, h2
    floors, surf, seen2, parent, dist = build_nav(boxes, starts, blocks_of(keep), True)
    lost = {(a, b) for a, b, _ in seen} - have
    seen = seen2
    print("  ground: %d cells walked without props, %d with; %d of %d props kept" % (len({(a, b) for a, b, _ in seen}) + len(lost), len({(a, b) for a, b, _ in seen}), len(keep), len(cand)))

    # The game's own graph, worked out here (nav_emulate): a doorway a metre wide has no point in
    # it, so the cell flood above reaches rooms the horde cannot. A window's two sides are joined
    # by a link from the nearest point on each; whole rooms the doors alone do not join to the
    # street are joined by a link across the doorway, where the cells say a body walks (every link
    # is across a gap the flood crossed). What is still cut off is not somewhere a post goes.
    import nav_emulate
    G = nav_emulate.Graph(boxes + bar_boxes, keep, sizes, floors)
    links = list(build_nav.links)
    dead = set()
    for bid, cx, cz, thin in bar_geo:
        d = (1.2, 0.0) if thin == 0 else (0.0, 1.2)
        ia, ib = G.nearest(cx + d[0], 0.0, cz + d[1], 2.0), G.nearest(cx - d[0], 0.0, cz - d[1], 2.0)
        if ia < 0 or ib < 0 or G.nearest(cx + d[0], 0.0, cz + d[1], 2.5) < 0 or G.nearest(cx - d[0], 0.0, cz - d[1], 2.5) < 0:
            dead.add(bid)
            continue
        links.append([r3(G.pts[ia][0]), r3(G.pts[ia][1]), r3(G.pts[ia][2]), r3(G.pts[ib][0]), r3(G.pts[ib][1]), r3(G.pts[ib][2])])
        G.union(ia, ib)

    def walkable(a, b_):
        n = max(2, int(math.dist(a, b_) / 0.25))
        for k in range(n + 1):
            t = k / n
            x, y, z = a[0] + (b_[0] - a[0]) * t, a[1] + (b_[1] - a[1]) * t, a[2] + (b_[2] - a[2]) * t
            ix, iz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
            if not any((ix, iz, h) in seen and abs(h - y) <= 0.45 for h in surf.get((ix, iz), ())):
                return False
        return True

    pairs = []
    for i, pa_ in enumerate(G.pts):
        hx, hz = int(math.floor(pa_[0] / 1.5)), int(math.floor(pa_[2] / 1.5))
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for j in G.near.get((hx + dx, hz + dz), ()):
                    if j > i and G.find(i) != G.find(j):
                        dd = math.dist(pa_, G.pts[j])
                        if dd <= 3.2 and abs(pa_[1] - G.pts[j][1]) <= spec.get("link_dy", 0.5):
                            pairs.append((dd, i, j))
    pairs.sort()
    bridged = 0
    for dd, i, j in pairs:
        if G.find(i) != G.find(j) and walkable(G.pts[i], G.pts[j]):
            G.union(i, j)
            bridged += 1
            links.append([r3(G.pts[i][0]), r3(G.pts[i][1]), r3(G.pts[i][2]), r3(G.pts[j][0]), r3(G.pts[j][1]), r3(G.pts[j][2])])
    build_nav.links = links[:600]
    start_pt = G.nearest(starts[0][0], starts[0][1], starts[0][2], 3.0)
    if start_pt < 0:
        sys.exit(f"no ground within 3 m of the survivor start {starts[0]}: the start floats or the map's floor is not brushes (displacements, models)")
    main = G.find(start_pt)
    for bid, cx, cz, thin in bar_geo:
        d = (1.2, 0.0) if thin == 0 else (0.0, 1.2)
        for sgn in (1, -1):
            k = G.nearest(cx + sgn * d[0], 0.0, cz + sgn * d[1], 2.5)
            if k < 0 or G.find(k) != main:
                dead.add(bid)
    barricades = [b for b in barricades if b["id"] not in dead]
    for b in bar_boxes:
        if b["barricade"] in dead:
            del b["barricade"]
            del b["nav"]

    def on_main(x, y, z):
        k = G.nearest(x, y, z, 1.0)
        return k >= 0 and G.find(k) == main

    if os.environ.get("ZZ_DEBUG_POINTS"):
        # What the horde's graph reaches, for a plot: [x, y, z, 1 if on the main ground].
        with open(os.environ["ZZ_DEBUG_POINTS"], "w") as dbg:
            json.dump([[*q, int(G.find(i) == main)] for i, q in enumerate(G.pts)], dbg)
    if os.environ.get("ZZ_DEBUG_CHAIN"):
        lo_, hi_ = [float(t) for t in os.environ["ZZ_DEBUG_CHAIN"].split(",")]
        tgt = [st for st in seen if lo_ <= st[2] <= hi_]
        if tgt:
            st = tgt[len(tgt) // 2]
            chain = [st]
            while chain[-1] in parent:
                chain.append(parent[chain[-1]])
            prev = None
            for c in reversed(chain):
                if prev is None or abs(c[2] - prev[2]) > 0.05:
                    print("   chain", round((c[0] + 0.5) * CELL, 1), round(c[2], 2), round((c[1] + 0.5) * CELL, 1))
                prev = c
    print("  game graph: %d points, %d bridged, %d of %d points on the main ground; %d barricades kept" % (
        len(G.pts), bridged, sum(1 for i in range(len(G.pts)) if G.find(i) == main), len(G.pts), len(barricades)))

    spawns = list(start_spawns)
    for e in ([] if ss else surv):
        p = settle(src_to_game(e), 0.1)
        sr = spec.get("spawn_region")
        if p and sr and not (sr[0] <= p[0] <= sr[2] and sr[1] <= p[2] <= sr[3]):
            continue
        # A spawn a prop stands on is a survivor inside a van (headless_maps names them).
        if p and any(sizes[q["id"]][1] > 0.5 and abs(q["at"][0] - p[0]) < max(sizes[q["id"]][0], sizes[q["id"]][2]) / 2 + 0.6
                     and abs(q["at"][2] - p[2]) < max(sizes[q["id"]][0], sizes[q["id"]][2]) / 2 + 0.6 for q in keep):
            continue
        if p and p[2] <= spec.get("spawn_z_max", 1e9):
            spawns.append({"at": p, "yaw": r3(reader.yaw_to_godot(parse_vec(e.get("angles", "0 0 0"))[1]))})
    zsp = [list(p) for p in spec.get("zombie_start", [])]
    for cls in ([] if spec.get("zombie_start") else spec["zombie_classes"]):
        for e in ents:
            if e.get("classname") == cls:
                p = settle(src_to_game(e))
                if p:
                    zsp.append(p)

    # A start the horde cannot path out of is a zombie idling for the whole wave (an octagon room
    # whose stepped edge the graph cannot climb): zkeep the starts within a metre of the main ground.
    if zsp and G.pts:
        zkeep = [p for p in zsp if any(G.find(i) == main and (q[0] - p[0]) ** 2 + (q[2] - p[2]) ** 2 <= 1.0 and abs(q[1] - p[1]) <= 0.6
                                      for i, q in enumerate(G.pts))]
        if len(zkeep) >= 4:
            if len(zkeep) != len(zsp):
                print("  zombie starts: %d of %d on the main ground" % (len(zkeep), len(zsp)))
            zsp = zkeep

    def settle_any(p):
        ix, iz = int(math.floor(p[0] / CELL)), int(math.floor(p[2] / CELL))
        hs = [h for h in surf.get((ix, iz), []) if abs(h - p[1]) <= 0.6]
        return [r3(p[0]), r3(min(hs, key=lambda h: abs(h - p[1]))), r3(p[2])] if hs else None

    items = []
    kinds = [("weapon", "smg"), ("ammo", None), ("weapon", "shotgun"), ("medkit", None), ("pills", None), ("weapon", "rifle")]
    item_map = spec.get("item_map", {})
    k = 0
    for e in ents:
        cls = e.get("classname")
        if cls == spec.get("item_class") or cls in item_map:
            p = settle_any(src_to_game(e))
            if p:
                if cls in item_map:
                    kind, wid = item_map[cls]
                else:
                    kind, wid = kinds[k % len(kinds)]
                    k += 1
                it = {"kind": kind, "at": p}
                if wid:
                    it["id"] = wid
                items.append(it)
    for kind, wid, x, z in spec.get("items", []):
        p = settle_any([x, spec.get("items_y", 22.3), z])
        if p:
            it = {"kind": kind, "at": p}
            if wid:
                it["id"] = wid
            items.append(it)
    items = items[:60]

    props, cache_src = [], []
    for pr in keep:
        props.append(pr)
        if pr["id"] == "survival_box":
            cache_src.append(pr["at"])

    objectives, route, end_area, gate_boxes = [], [], [], []
    if spec["mode"] == "exodus" and dist:
        if spec.get("end_src"):
            tx, ty, tz = gpt(spec["end_src"], y0)
            end = min(dist, key=lambda st: (st[0] * CELL + CELL / 2 - tx) ** 2 + (st[1] * CELL + CELL / 2 - tz) ** 2 + 4 * (st[2] - ty) ** 2)
        else:
            end = max(dist, key=lambda st: dist[st])
        path = [end]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        path.reverse()
        if spec.get("route_bridge"):
            # A slope the flood climbs can be cut into floors that the graph builder does not join
            # (steps over 0.5 m, 1.5 m ties). Where the walked route crosses between two components,
            # link the points nearest each side; the flood proved a body gets across.
            bl = 0
            prev = None
            for st in path[::2]:
                q = (( st[0] + 0.5) * CELL, st[2], (st[1] + 0.5) * CELL)
                k = G.nearest(q[0], q[1], q[2], 2.0)
                if k < 0:
                    continue
                if prev is not None and G.find(prev) != G.find(k):
                    a_, b_ = G.pts[prev], G.pts[k]
                    G.union(prev, k)
                    build_nav.links.append([r3(a_[0]), r3(a_[1]), r3(a_[2]), r3(b_[0]), r3(b_[1]), r3(b_[2])])
                    bl += 1
                prev = k
            print("  route_bridge: %d links along the route" % bl)

        def wp(st):
            return [r3((st[0] + 0.5) * CELL), r3(st[2]), r3((st[1] + 0.5) * CELL)]

        step = max(8, len(path) // 150 + 1)
        route = [wp(path[i]) for i in range(0, len(path), step)]
        if route[-1] != wp(path[-1]):
            route.append(wp(path[-1]))
        ex, ey, ez = wp(path[-1])
        end_area = [{"min": [r3(ex - 3), r3(ey - 0.6), r3(ez - 3)], "max": [r3(ex + 3), r3(ey + 3), r3(ez + 3)]}]
        found = []
        for e, gb in gate_cands:
            first = None
            for k, st in enumerate(path):
                x, h, z = wp(st)
                for b in gb:
                    lo, hi = b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2
                    if hi >= h - 0.3 and lo <= h + 1.8 and any(inside_box(b, x + dx, z + dz) for dx in (-0.5, 0, 0.5) for dz in (-0.5, 0, 0.5)):
                        first = k
                        break
                if first is not None:
                    break
            if first is not None:
                found.append((first, e, gb))
        found.sort(key=lambda t: t[0])
        for n, (k, e, gb) in enumerate(found):
            gid = "gate_%d" % (n + 1)
            for b in gb:
                b["gate"] = gid
                gate_boxes.append(b)
            x, h, z = wp(path[max(0, k - 3)])
            objectives.append({"id": "obj_%d" % (n + 1), "kind": "use", "at": [x, r3(h + 1.0), z], "label": e.get("label", spec.get("gate_label", "Open the way on")),
                               "seconds": 2, "holdout": e.get("holdout", spec.get("holdout", 20)), "opens": [gid], "prop": "lever",
                               "message": "It is opening. Hold on until it does!"})
        objectives = objectives[:16]

    deep = {}
    for ix, iz, h in seen:
        if all(any((ix + dx, iz + dz, h2) in seen and abs(h2 - h) <= STEP for h2 in surf.get((ix + dx, iz + dz), ()))
               for dx in range(-2, 3) for dz in range(-2, 3)):
            if on_main((ix + 0.5) * CELL, h, (iz + 0.5) * CELL):
                deep.setdefault((ix, iz), h)

    posts, pts = [], [s["at"] for s in spawns]
    # Posts: the spawns, spread. A spec that names a `post_region` ([x0, z0, x1, z1]) puts them
    # inside it instead, on ground well clear of a wall: a team that holds a house is held behind
    # its doors and windows, which is what makes the narrow places the horde must come through
    # (chokes); posts all on an open street have none.
    if spec.get("post_region") and spec["mode"] == "survival":
        x0, z0, x1, z1 = spec["post_region"]
        pts = [[r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL)] for (ix, iz), h in sorted(deep.items())
               if x0 <= (ix + 0.5) * CELL <= x1 and z0 <= (iz + 0.5) * CELL <= z1 and h <= 0.35 and on_main((ix + 0.5) * CELL, h, (iz + 0.5) * CELL)]
    if pts and spec["mode"] == "survival":
        posts.append(pts[0] if not spec.get("post_region") else min(pts, key=lambda q: (q[0] - spec["post_region"][0]) ** 2 + q[2] ** 2))
        while len(posts) < spec.get("posts", 6) and len(posts) < len(pts):
            posts.append(max(pts, key=lambda q: min((q[0] - p[0]) ** 2 + (q[2] - p[2]) ** 2 for p in posts)))
    caches = []
    # A cache goes on open ground the horde certainly has: the nearest cell to the crate whose
    # whole 5x5 neighbourhood is ground (a crate's own cell is cut out, and the edge of a room
    # holds a point the game's graph, a metre apart, may not).
    for p in cache_src:
        near = [(((ix + 0.5) * CELL - p[0]) ** 2 + ((iz + 0.5) * CELL - p[2]) ** 2, ix, iz, h) for (ix, iz), h in deep.items()
                if abs(h - p[1]) < 1.0 and abs((ix + 0.5) * CELL - p[0]) < 4 and abs((iz + 0.5) * CELL - p[2]) < 4]
        if not near:
            continue
        _, ix, iz, h = min(near)
        q = [r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL)]
        cr = spec.get("cache_region") or spec.get("post_region")
        if cr and not (cr[0] <= q[0] <= cr[2] and cr[1] <= q[2] <= cr[3]):
            continue  # a crate outside the players' region is a long walk the horde never makes
        if on_main(q[0], q[1], q[2]) and h <= 0.35 and len(caches) < 8 and all((q[0] - c[0]) ** 2 + (q[2] - c[2]) ** 2 > 36 for c in caches):
            caches.append(q)

    if spec.get("caches_near_posts") and not caches:
        # A map with no supply crates of its own: a cache a few metres from each post, on ground
        # whose whole neighbourhood is open and the horde's, never in the start room's middle.
        for pst in posts:
            near = sorted((((ix + 0.5) * CELL - pst[0]) ** 2 + ((iz + 0.5) * CELL - pst[2]) ** 2, ix, iz, h) for (ix, iz), h in deep.items()
                          if abs(h - pst[1]) < 0.5 and 9 <= ((ix + 0.5) * CELL - pst[0]) ** 2 + ((iz + 0.5) * CELL - pst[2]) ** 2 <= 100)
            for _, ix, iz, h in near:
                q = [r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL)]
                if on_main(q[0], q[1], q[2]) and all((q[0] - c[0]) ** 2 + (q[2] - c[2]) ** 2 > 49 for c in caches):
                    caches.append(q)
                    break
        caches = caches[:8]

    lights = []
    al = spec.get("auto_lights")
    if al:
        # The map had no lamps of its own (it was lit by baked light, which is the author's): a lamp
        # every `spacing` metres over the horde's ground, `height` above the floor, taken in a
        # fixed order so the same map always gets the same lamps.
        sp_ = al.get("spacing", 6.0)
        taken = {}
        for (ix, iz), h in sorted(deep.items()):
            cx, cz = (ix + 0.5) * CELL, (iz + 0.5) * CELL
            key = (int(math.floor(cx / sp_)), int(math.floor(cz / sp_)), round(h))
            if key in taken or not on_main(cx, h, cz):
                continue
            taken[key] = [r3(cx), r3(h + al.get("height", 2.3)), r3(cz)]
        for at in list(taken.values())[:al.get("max", 100)]:
            lights.append({"at": at, "range": al.get("range", 7.0), "energy": al.get("energy", 0.9), "colour": al.get("colour", [1.0, 0.93, 0.8])})
    for e in ents:
        if e.get("classname") in ("light", "light_spot") and len(lights) < 120 and not al:
            col = parse_vec(e.get("_light", "255 255 255 200"))
            br = col[3] if len(col) > 3 else 200
            o = gpt(parse_vec(e["origin"]), y0)
            lights.append({"at": [r3(o[0]), r3(o[1]), r3(o[2])], "range": r3(min(9.0, 3.5 + br / 60.0)), "energy": r3(min(1.6, 0.4 + br / 220.0)),
                           "colour": [r3(c / 255.0) for c in col[:3]]})

    env = {"sky_top": [0.02, 0.03, 0.07], "sky_horizon": [0.08, 0.1, 0.15], "ground": [0.03, 0.03, 0.04], "sun_pitch": -45.0,
           "sun_yaw": 12.0, "sun_energy": 0.22, "sun_colour": [0.45, 0.65, 0.95], "ambient": [0.36, 0.4, 0.52], "ambient_energy": 0.3, "fog": 0.02}

    env.update(spec.get("environment", {}))
    lo, hi = gpt(bs.model_bounds(0)[0], y0), gpt(bs.model_bounds(0)[1], y0)
    doc = {
        "format": 1, "kind": "zombiezone_map", "id": spec["id"], "name": spec["name"],
        "author": "%s (original map, %s, %s); converted. Removed on request." % (spec["author"], spec["page"], spec["licence"]),
        "attribution": "Geometry converted from %s by %s, %s (%s), used non-commercially with credit under the licence. Credit: %s. The original file is not redistributed and its textures and models are not used (the game draws its own surfaces and Kenney CC0 props). This conversion is removed on the author's request." % (
            spec["source"], spec["author"], spec["page"], spec["licence"], spec["author"]),
        "blurb": spec["blurb"], "mode": spec["mode"], "survivors": spec.get("survivors", 0), "next": "",
        "survive_seconds": spec.get("survive_seconds", 0), "kill_y": spec.get("kill_y", r3(min(lo[1], hi[1]) - 12.0)),
        "environment": env,
        "boxes": [{k: v for k, v in b.items() if not k.startswith("_")} for b in boxes + bar_boxes + gate_boxes], "props": props, "lights": lights,
        "spawns": {"survivors": spawns},
        "areas": {"start": [], "end": end_area}, "route": route or ([spawns[0]["at"]] if spawns else []),
        "nav": {"spacing": 1.0, "clearance": 0.35, "floors": floors, "links": build_nav.links[:600] + [list(l) for l in spec.get("extra_links", [])]},
        "items": items, "objectives": objectives, "sleepers": [list(z) for z in spec.get("sleepers", [])], "zombie_spawns": zsp, "posts": posts, "caches": caches,
        "barricades": barricades,
    }
    if spawns:
        sp = [s["at"] for s in spawns]
        doc["areas"]["start"] = [{"min": [r3(min(p[0] for p in sp) - 2), r3(min(p[1] for p in sp) - 0.5), r3(min(p[2] for p in sp) - 2)],
                                  "max": [r3(max(p[0] for p in sp) + 2), r3(max(p[1] for p in sp) + 3), r3(max(p[2] for p in sp) + 2)]}]
    # Toys: loose dot-props, from the spec's hints ([toy, anchor, dx, dz]); build_maps settles each
    # onto clear floor, the same way the hand-built maps' are.
    if spec.get("toys"):
        import build_maps
        hints = [build_maps.toy(t[0], "spawn" if t[1] == "spawn" else tuple(t[1]), t[2], t[3], *t[4:]) for t in spec["toys"]]
        doc["toys"] = build_maps.settle_toys(doc, hints)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, spec["id"] + ".json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print("%s: %d boxes (%d barricade), %d props, %d lights, %d spawns, %d zombie spawns, %d floors, %d items, %d caches, %d posts" % (
        path, len(doc["boxes"]), len(bar_boxes), len(props), len(lights), len(spawns), len(zsp), len(floors), len(items), len(caches), len(posts)))
    print("  route %d points, %d objectives, %d gate boxes, %d cells reachable, end %s" % (len(route), len(objectives), len(gate_boxes), len(seen), end_area[0]["min"] if end_area else None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
