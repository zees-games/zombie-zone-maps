#!/usr/bin/env python3
"""Writes every map in maps/ from the plans below.

A map is a JSON document (see game-zombie-zone's game/zz_map_doc.gd and maps/README.md), and
nothing stops a mapper writing one by hand. These are generated because a street of buildings
is hundreds of boxes that have to meet, and the zombies' ground has to be exactly the floor the
survivors walk on. So a map here is a list of REGIONS — rectangles a person can stand in — and
everything else follows from them:

- the floor of each region, in its material;
- the walls: every edge of the union of regions that faces nothing gets a wall, outside the
  edge, as high as the region says (a street's facades, a room's walls, a pier's railing);
- the ceiling of an indoor region;
- a lintel over a doorway, which is a narrow region bridging the half-metre gap left between
  a room and a street;
- the nav floors the zombies walk, which are the regions themselves.

A region that should not touch its neighbour is kept half a metre away from it, and the gap
fills with wall from both sides. A door is a region across that gap.

    tools/build_maps.py                 # rewrite every map
    tools/build_maps.py --check         # fail if a file on disk is not what this would write
    tools/build_maps.py --sync-sizes    # copy prop sizes from ../game-zombie-zone

Conventions:

- Metres, degrees. y is up and every floor's top is at y 0.
- Every region corner is on the half-metre grid: the walls are found on that grid.
- A box's `at` is its centre. A prop's `at` is the middle of its footprint ON the floor.
- The route runs from the start room to the end room, and the director spawns AHEAD along it.
"""

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ambient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAPS = os.path.join(ROOT, "maps")
SIZES_FILE = os.path.join(HERE, "prop_sizes.json")
GAME_CATALOGUE = os.path.join(ROOT, "..", "game-zombie-zone", "props", "catalogue.json")

CELL = 0.5          # the grid walls are found on
WALL = 0.3          # how thick a generated wall is
DOOR_H = 2.4        # a doorway's height
RAIL = 1.3          # a railing: higher than a survivor jumps
AUTHOR = "zombie-zone-maps"

NIGHT = {
    "sky_top": [0.02, 0.025, 0.05], "sky_horizon": [0.07, 0.07, 0.1], "ground": [0.03, 0.03, 0.03],
    "sun_pitch": -40.0, "sun_yaw": 140.0, "sun_energy": 0.12, "sun_colour": [0.6, 0.7, 1.0],
    "ambient": [0.35, 0.38, 0.5], "ambient_energy": 0.22, "fog": 0.025,
}
DUSK = {
    "sky_top": [0.12, 0.1, 0.2], "sky_horizon": [0.65, 0.32, 0.18], "ground": [0.06, 0.05, 0.05],
    "sun_pitch": -8.0, "sun_yaw": 250.0, "sun_energy": 0.45, "sun_colour": [1.0, 0.55, 0.3],
    "ambient": [0.45, 0.38, 0.42], "ambient_energy": 0.3, "fog": 0.018,
}
FOG_NIGHT = dict(NIGHT, fog=0.05, ambient=[0.32, 0.36, 0.4], ambient_energy=0.25)

WARM = [1.0, 0.92, 0.75]
SODIUM = [1.0, 0.78, 0.45]
COLD = [0.75, 0.85, 1.0]


def r(v):
    return round(v + 0.0, 3)


def load_sizes():
    if not os.path.exists(SIZES_FILE):
        return {}
    with open(SIZES_FILE) as f:
        return json.load(f)["props"]


SIZES = load_sizes()


def size_of(pid):
    s = SIZES.get(pid)
    if s is None:
        raise SystemExit("unknown prop %s (run --sync-sizes?)" % pid)
    return s


class Region:
    def __init__(self, x0, z0, x1, z1, floor, height, indoor=False, wall="brick", tint=None, rail=0.0, nav=True,
                 facade=None, facade_tint=None):
        for v in (x0, z0, x1, z1):
            if abs(v / CELL - round(v / CELL)) > 1e-6:
                raise SystemExit("region corner %s is off the %.1f m grid" % (v, CELL))
        self.x0, self.z0, self.x1, self.z1 = min(x0, x1), min(z0, z1), max(x0, x1), max(z0, z1)
        self.floor = floor
        self.height = height
        self.indoor = indoor
        self.wall = wall
        self.tint = tint
        self.rail = rail          # > 0: the edges facing nothing are a railing this high, not a wall
        self.nav = nav
        self.door = False
        # What an indoor region looks like from outdoors across the half-metre gap: the
        # outdoor side's wall takes this instead of the outdoor region's own (a car park's
        # perimeter is a fence; the school it surrounds is brick). None keeps the outdoor
        # region's own wall, which is what the street maps were built with.
        self.facade = facade
        self.facade_tint = facade_tint

    def contains(self, x, z):
        return self.x0 <= x < self.x1 and self.z0 <= z < self.z1


class Map:
    def __init__(self, mid, name, blurb, mode, environment, next_map="", survive_seconds=0.0, survivors=4,
                 day=None, spacing=1.0):
        self.doc = {
            "format": 1, "kind": "zombiezone_map", "id": mid, "name": name, "author": AUTHOR,
            "blurb": blurb, "mode": mode, "environment": environment, "kill_y": -20.0,
        }
        if survivors != 4:
            self.doc["survivors"] = survivors
        if day:
            self.doc["day_environment"] = day
        self.spacing = spacing
        # Whether every door gets a nav link through it (see build). On for the maps built
        # for survival; the street maps were checked without and are left byte-for-byte.
        self.survival_links = mode == "survival" and survivors != 4
        self.posts = []
        self.caches = []
        self.barricades = []
        if next_map:
            self.doc["next"] = next_map
        if survive_seconds > 0.0:
            self.doc["survive_seconds"] = survive_seconds
        self.regions = []
        self.boxes = []
        self.props = []
        self.lights = []
        self.spawns = []
        self.areas = {"start": [], "end": []}
        self.route = []
        self.items = []
        self.objectives = []
        self.sleepers = []
        self.zombie_spawns = []
        self.links = []

    # --- Ground ------------------------------------------------------------------------

    def region(self, x0, z0, x1, z1, floor="asphalt", height=8.0, **kw):
        reg = Region(x0, z0, x1, z1, floor, height, **kw)
        self.regions.append(reg)
        return reg

    def room(self, x0, z0, x1, z1, floor="tile", height=3.0, wall="plaster", light=WARM, **kw):
        reg = self.region(x0, z0, x1, z1, floor, height, indoor=True, wall=wall, **kw)
        if light is not None:
            self.light((x0 + x1) / 2, height - 0.3, (z0 + z1) / 2, rng=max(x1 - x0, z1 - z0) * 0.9 + 2.0, energy=1.2, colour=light)
        return reg

    def door(self, x0, z0, x1, z1, floor="tile", gate=None, gate_mat="metal", gate_tint=None, barricade=None,
             label="the door", strength=None, boards="door"):
        """A doorway across a half-metre gap. With `gate`, a door an objective opens; with
        `barricade`, one the horde breaks down and the survivors mend (`boards`: "door" planks to
        the lintel, "window" to chest height, "shutter" one steel sheet)."""
        reg = self.region(x0, z0, x1, z1, floor, DOOR_H, indoor=True, wall="plaster")
        reg.door = True
        if barricade:
            self.board_up(barricade, x0, z0, x1, z1, label, strength, boards)
        if gate:
            box = {"at": [r((x0 + x1) / 2), DOOR_H / 2, r((z0 + z1) / 2)], "size": [r(x1 - x0), DOOR_H, r(z1 - z0)],
                   "mat": gate_mat, "gate": gate}
            if gate_tint:
                box["tint"] = gate_tint
            self.boxes.append(box)
        return reg

    def gate(self, gid, x0, z0, x1, z1, height=3.0, mat="metal", tint=None, look=None):
        """A gate across open ground (a fence, a shutter) that an objective opens. `look`
        "chain_link" draws it as a see-through fence (the collision is still the box)."""
        box = {"at": [r((x0 + x1) / 2), height / 2, r((z0 + z1) / 2)], "size": [r(x1 - x0), height, r(z1 - z0)],
               "mat": mat, "gate": gid}
        if tint:
            box["tint"] = tint
        if look:
            box["look"] = look
        self.boxes.append(box)

    def block(self, x, z, sx, sz, h, mat="metal", tint=None, yaw=0.0, y=0.0):
        """Something solid standing on the floor: a container, a rack, a counter."""
        box = {"at": [r(x), r(y + h / 2), r(z)], "size": [r(sx), r(h), r(sz)], "mat": mat}
        if tint:
            box["tint"] = tint
        if yaw:
            box["yaw"] = r(yaw)
        self.boxes.append(box)

    def flat(self, x0, z0, x1, z1, mat, y=-0.5, solid=False):
        """A surface outside the regions that is only to be looked at: water, a lawn beyond a wall."""
        box = {"at": [r((x0 + x1) / 2), y, r((z0 + z1) / 2)], "size": [r(x1 - x0), 0.2, r(z1 - z0)], "mat": mat}
        if not solid:
            box["solid"] = False
        self.boxes.append(box)

    def board_up(self, bid, x0, z0, x1, z1, label, strength=None, boards="door"):
        """A barricade across a doorway's gap: planks with finger gaps (shots and sight pass
        between them), or one steel shutter. Solid, but left on the zombies' ground (`nav`
        false), so the horde comes to it and tears it down."""
        crosses_z = (z1 - z0) < (x1 - x0)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        span = (x1 - x0) if crosses_z else (z1 - z0)
        entry = {"id": bid, "label": label}
        if strength:
            entry["health"] = strength
        self.barricades.append(entry)

        def plank(y0, y1, mat, tint, thick=0.14):
            sx, sz = (span + 0.1, thick) if crosses_z else (thick, span + 0.1)
            self.boxes.append({"at": [r(cx), r((y0 + y1) / 2), r(cz)], "size": [r(sx), r(y1 - y0), r(sz)],
                               "mat": mat, "tint": tint, "nav": False, "barricade": bid})

        if boards == "shutter":
            plank(0.0, DOOR_H, "metal", [0.62, 0.64, 0.66], 0.1)
            return
        top = DOOR_H - 0.05 if boards == "door" else 1.5
        y = 0.05
        wood = ([0.62, 0.46, 0.3], [0.55, 0.4, 0.26], [0.68, 0.52, 0.34])
        i = 0
        while y + 0.3 <= top + 0.001:
            plank(y, y + 0.3, "wood", wood[i % 3])
            y += 0.38
            i += 1

    def wall_lamp(self, x, z, y=3.0, colour=SODIUM, rng=13.0, energy=1.5):
        """A lamp on a building's outside wall: what lights the horde at the windows."""
        self.boxes.append({"at": [r(x), r(y), r(z)], "size": [0.35, 0.18, 0.35], "mat": "glass",
                           "tint": [1.0, 0.85, 0.55], "solid": False, "nav": False})
        self.light(x, y - 0.2, z, rng, energy, colour)

    def post(self, x, z):
        """Where a survivor holds on a survival map; stand-ins share them out."""
        self.posts.append([r(x), 0.0, r(z)])

    def cache(self, x, z, table=True):
        """A survival map's supply cache: a table the breathers restock."""
        if table:
            self.prop("furniture_table", x, z)
        self.caches.append([r(x), 0.82 if table else 0.0, r(z)])

    def lights_grid(self, x0, z0, x1, z1, step, y, rng, energy=1.1, colour=WARM):
        """Lamps over a big floor in rows: one per chunk of the renderer's twelve metres, so no
        batched mesh is lit by more than its eight nearest."""
        nx = max(int(round((x1 - x0) / step)), 1)
        nz = max(int(round((z1 - z0) / step)), 1)
        for i in range(nx):
            for k in range(nz):
                self.light(x0 + (i + 0.5) * (x1 - x0) / nx, y, z0 + (k + 0.5) * (z1 - z0) / nz, rng, energy, colour)

    # --- Things --------------------------------------------------------------------------

    def prop(self, pid, x, z, yaw=0.0):
        size_of(pid)
        p = {"id": pid, "at": [r(x), 0.0, r(z)]}
        if yaw:
            p["yaw"] = r(yaw)
        self.props.append(p)

    def light(self, x, y, z, rng=12.0, energy=1.3, colour=SODIUM):
        self.lights.append({"at": [r(x), r(y), r(z)], "range": r(rng), "energy": r(energy), "colour": colour})

    def lamp(self, x, z, yaw, colour=SODIUM):
        """A street light: the post, and the light it gives."""
        self.prop("urban_detail-light-single", x, z, yaw)
        self.light(x + (1.4 if yaw == -90 else -1.4 if yaw == 90 else 0.0), 3.8, z, 14.0, 1.4, colour)

    def spawn(self, x, z, yaw=0.0):
        self.spawns.append({"at": [r(x), 0.1, r(z)], "yaw": r(yaw)})

    def start(self, x0, z0, x1, z1):
        self.areas["start"].append({"min": [r(x0), -0.5, r(z0)], "max": [r(x1), 3.0, r(z1)]})

    def end(self, x0, z0, x1, z1):
        self.areas["end"].append({"min": [r(x0), -0.5, r(z0)], "max": [r(x1), 3.0, r(z1)]})

    def item(self, kind, x, y, z, iid=None):
        it = {"kind": kind, "at": [r(x), r(y), r(z)]}
        if iid:
            it["id"] = iid
        self.items.append(it)

    def table_of(self, x, z, things, yaw=0.0):
        """A table with things laid on it along its length."""
        self.prop("furniture_table", x, z, yaw)
        n = len(things)
        for i, (kind, iid) in enumerate(things):
            off = (i - (n - 1) / 2) * 0.5
            self.item(kind, x + off, 0.82, z, iid)

    def objective(self, oid, kind, x, y, z, label, seconds=2.0, holdout=0.0, opens=(), message="", radius=2.0,
                  prop=None, yaw=0.0):
        """`prop` is what it is, drawn: "padlock" (hung on the gate it opens), "lever", "radio"."""
        o = {"id": oid, "kind": kind, "at": [r(x), r(y), r(z)], "label": label, "seconds": seconds,
             "holdout": holdout, "opens": list(opens), "message": message}
        if kind == "reach":
            o["radius"] = radius
        if prop:
            o["prop"] = prop
            if yaw:
                o["yaw"] = r(yaw)
        self.objectives.append(o)

    def sleeper(self, x, z, yaw=0.0):
        self.sleepers.append([r(x), 0.0, r(z), r(yaw)])

    def hint(self, x, z):
        self.zombie_spawns.append([r(x), 0.0, r(z)])

    def path(self, *points):
        self.route = [[r(x), 0.0, r(z)] for x, z in points]

    # --- Building --------------------------------------------------------------------------

    def _walkable(self, x, z):
        for reg in self.regions:
            if reg.contains(x, z):
                return reg
        return None

    def _walls(self):
        """Every edge of the regions' union that faces nothing, merged into runs, as boxes."""
        xs = [reg.x0 for reg in self.regions] + [reg.x1 for reg in self.regions]
        zs = [reg.z0 for reg in self.regions] + [reg.z1 for reg in self.regions]
        gx0, gx1, gz0, gz1 = min(xs) - 1, max(xs) + 1, min(zs) - 1, max(zs) + 1
        nx, nz = int(round((gx1 - gx0) / CELL)), int(round((gz1 - gz0) / CELL))
        grid = [[None] * nz for _ in range(nx)]
        for i in range(nx):
            for k in range(nz):
                grid[i][k] = self._walkable(gx0 + (i + 0.5) * CELL, gz0 + (k + 0.5) * CELL)

        def at(i, k):
            return grid[i][k] if 0 <= i < nx and 0 <= k < nz else None

        def face(i, k, dx, dz, reg):
            """How the wall on this cell's edge looks: its own region's wall, unless it is an
            outdoor cell looking across the gap at a building, which shows the building."""
            across = at(i + 2 * dx, k + 2 * dz)
            if across is None or not across.facade or across.door:
                # Opposite the half-metre gap between two rooms there is no room, but the facade
                # runs on: the room beside it decides, or the wall there is a slot of fence.
                ex, ez = (1, 0) if dx == 0 else (0, 1)
                across = at(i + 2 * dx + ex, k + 2 * dz + ez) or at(i + 2 * dx - ex, k + 2 * dz - ez)
            if not reg.indoor and not reg.rail and across is not None and not across.door and across.facade \
                    and across is not reg:
                return (across.facade, tuple(across.facade_tint) if across.facade_tint else None,
                        max(across.height + 0.4, reg.height), False, 0.0)
            return (reg.wall, tuple(reg.tint) if reg.tint else None, reg.height, reg.indoor, reg.rail)

        def key(f):
            return f

        boxes = []
        # Edges along x (a wall facing -z or +z), then along z.
        for direction in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            dx, dz = direction
            along_x = dx == 0
            outer = range(nz) if along_x else range(nx)
            for line in outer:
                run = None
                for step in list(range(nx if along_x else nz)) + [None]:
                    f = None
                    if step is not None:
                        i, k = (step, line) if along_x else (line, step)
                        here = at(i, k)
                        if here is not None and at(i + dx, k + dz) is None:
                            f = face(i, k, dx, dz, here)
                    if run is not None and (f is None or key(f) != key(run[0])):
                        boxes.append(self._wall_box(run, along_x, line, direction, gx0, gz0, at))
                        run = None
                    if f is not None:
                        if run is None:
                            run = [f, step, step]
                        else:
                            run[2] = step
        # Over every doorway, up to the taller side (and a building's facade, when it has one).
        for reg in self.regions:
            if reg.door:
                top = DOOR_H
                for other in self.regions:
                    if other is not reg and not other.door and self._touches(reg, other):
                        top = max(top, other.height if not other.rail else 0.0)
                        if other.indoor and other.facade:
                            top = max(top, other.height + 0.4)
                if top <= DOOR_H:
                    continue
                inside = next((o for o in self.regions if o is not reg and not o.door and o.indoor and o.facade
                               and self._touches(reg, o)), None)
                if inside is None:
                    boxes.append({"at": [r((reg.x0 + reg.x1) / 2), r((DOOR_H + top) / 2), r((reg.z0 + reg.z1) / 2)],
                                  "size": [r(reg.x1 - reg.x0 + 0.02), r(top - DOOR_H), r(reg.z1 - reg.z0 + 0.02)], "mat": "brick"})
                    continue
                # A building's opening onto its grounds: the lintel is two halves, the room's own
                # wall inside and the facade outside, or a classroom's window has a strip of
                # brick over it.
                crosses_z = (reg.z1 - reg.z0) < (reg.x1 - reg.x0)
                cx, cz = (reg.x0 + reg.x1) / 2, (reg.z0 + reg.z1) / 2
                inner_side = (1 if (inside.z0 + inside.z1) / 2 > cz else -1) if crosses_z else \
                    (1 if (inside.x0 + inside.x1) / 2 > cx else -1)
                depth = (reg.z1 - reg.z0) if crosses_z else (reg.x1 - reg.x0)
                for side, mat, tint in ((inner_side, inside.wall, inside.tint), (-inner_side, inside.facade, inside.facade_tint)):
                    off = side * depth / 4
                    at = [r(cx), r((DOOR_H + top) / 2), r(cz + off)] if crosses_z else [r(cx + off), r((DOOR_H + top) / 2), r(cz)]
                    size = [r(reg.x1 - reg.x0 + 0.02), r(top - DOOR_H), r(depth / 2 + 0.01)] if crosses_z else \
                        [r(depth / 2 + 0.01), r(top - DOOR_H), r(reg.z1 - reg.z0 + 0.02)]
                    box = {"at": at, "size": size, "mat": mat}
                    if tint:
                        box["tint"] = list(tint)
                    boxes.append(box)
        return boxes

    @staticmethod
    def _touches(a, b):
        return a.x0 <= b.x1 and b.x0 <= a.x1 and a.z0 <= b.z1 and b.z0 <= a.z1

    def _wall_box(self, run, along_x, line, direction, gx0, gz0, at):
        f, first, last = run
        mat, tint, height, _indoor, rail = f
        dx, dz = direction
        height = rail if rail else height
        # Reach past a convex corner so two walls meet; never into ground somebody stands on.
        lo_ext = WALL
        hi_ext = WALL
        if along_x:
            if at(first - 1, line) is not None:
                lo_ext = 0.0
            if at(last + 1, line) is not None:
                hi_ext = 0.0
            a0 = gx0 + first * CELL - lo_ext
            a1 = gx0 + (last + 1) * CELL + hi_ext
            edge = gz0 + (line + (1 if dz > 0 else 0)) * CELL
            centre_z = edge + dz * WALL / 2
            box = {"at": [r((a0 + a1) / 2), r(height / 2), r(centre_z)], "size": [r(a1 - a0), r(height), WALL]}
        else:
            if at(line, first - 1) is not None:
                lo_ext = 0.0
            if at(line, last + 1) is not None:
                hi_ext = 0.0
            a0 = gz0 + first * CELL - lo_ext
            a1 = gz0 + (last + 1) * CELL + hi_ext
            edge = gx0 + (line + (1 if dx > 0 else 0)) * CELL
            centre_x = edge + dx * WALL / 2
            box = {"at": [r(centre_x), r(height / 2), r((a0 + a1) / 2)], "size": [WALL, r(height), r(a1 - a0)]}
        box["mat"] = "wood" if rail else mat
        if tint:
            box["tint"] = list(tint)
        return box

    def build(self):
        boxes = []
        for reg in self.regions:
            cx, cz = (reg.x0 + reg.x1) / 2, (reg.z0 + reg.z1) / 2
            sx, sz = reg.x1 - reg.x0, reg.z1 - reg.z0
            boxes.append({"at": [r(cx), -0.1, r(cz)], "size": [r(sx), 0.2, r(sz)], "mat": reg.floor, "nav": False})
            if reg.indoor and not reg.door:
                boxes.append({"at": [r(cx), r(reg.height + 0.1), r(cz)], "size": [r(sx + 2 * WALL), 0.2, r(sz + 2 * WALL)],
                              "mat": "ceiling", "nav": False})
                # A building seen from its grounds has a roof, not the underside of a ceiling.
                if reg.facade:
                    boxes.append({"at": [r(cx), r(reg.height + 0.25), r(cz)], "size": [r(sx + 2 * WALL), 0.1, r(sz + 2 * WALL)],
                                  "mat": "roof", "tint": [0.55, 0.56, 0.6], "nav": False})
        boxes.extend(self._walls())
        boxes.extend(self.boxes)

        floors = [[r(reg.x0 + 0.05), r(reg.z0 + 0.05), r(reg.x1 - 0.05), r(reg.z1 - 0.05), 0.0]
                  for reg in self.regions if reg.nav]
        # A doorway's floor reaches into the rooms either side, so the graph joins across it.
        for reg in self.regions:
            if reg.door:
                # The gap is the door's short side: a door half a metre deep in z joins rooms
                # to its north and south, so its floor reaches along z.
                crosses_z = (reg.z1 - reg.z0) < (reg.x1 - reg.x0)
                if crosses_z:
                    floors.append([r(reg.x0 + 0.05), r(reg.z0 - 0.6), r(reg.x1 - 0.05), r(reg.z1 + 0.6), 0.0])
                else:
                    floors.append([r(reg.x0 - 0.6), r(reg.z0 + 0.05), r(reg.x1 + 0.6), r(reg.z1 - 0.05), 0.0])
                # And a link straight through it, room to room. The graph drops a door's own
                # points where they land within half a spacing of a room's, and a door that
                # loses them all joins nothing: the school's gym doors did, and the hallway
                # reached the gym through the kitchen, the loading bay and the car park.
                if self.survival_links:
                    cx, cz = (reg.x0 + reg.x1) / 2, (reg.z0 + reg.z1) / 2
                    reach = 1.0 + 0.5 * self.spacing
                    if crosses_z:
                        self.links.append([r(cx), 0.0, r(cz - reach), r(cx), 0.0, r(cz + reach)])
                    else:
                        self.links.append([r(cx - reach), 0.0, r(cz), r(cx + reach), 0.0, r(cz)])

        doc = dict(self.doc)
        doc.update({
            "boxes": boxes,
            "props": self.props,
            "lights": self.lights,
            "spawns": {"survivors": self.spawns},
            "areas": self.areas,
            "route": self.route,
            "nav": {"spacing": self.spacing, "clearance": 0.35, "floors": floors, "links": self.links},
            "items": self.items,
            "objectives": self.objectives,
            "sleepers": self.sleepers,
            "zombie_spawns": self.zombie_spawns,
        })
        if self.posts:
            doc["posts"] = self.posts
        if self.caches:
            doc["caches"] = self.caches
        if self.barricades:
            doc["barricades"] = self.barricades
        return doc


# --- Pieces every map uses -----------------------------------------------------------------

def safe_room(m, x0, z0, x1, z1, door, start=True, loadout=True):
    """A safe room: tiled, lit warm, a table of guns and pills, and its door onto the map.

    `door` is (x0, z0, x1, z1) of the doorway region across the gap."""
    m.room(x0, z0, x1, z1, floor="tile", wall="paint", tint=[0.72, 0.78, 0.7])
    m.door(*door, floor="tile")
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    if start:
        m.start(x0, z0, x1, z1)
        for i, (dx, dz) in enumerate(((-1.5, -1.0), (1.5, -1.0), (-1.5, 1.0), (1.5, 1.0))):
            m.spawn(cx + dx, cz + dz, 180.0 if door[1] > z0 else 0.0)
    else:
        m.end(x0, z0, x1, z1)
    back = z0 + 1.0 if door[1] > z0 else z1 - 1.0
    if loadout:
        m.table_of(x0 + 2.0, back, [("weapon", "smg"), ("weapon", "shotgun"), ("pills", None)])
        m.table_of(x1 - 2.0, back, [("weapon", "rifle"), ("ammo", None), ("medkit", None)])
    else:
        m.table_of(x0 + 2.0, back, [("medkit", None), ("medkit", None), ("ammo", None)])
        m.table_of(x1 - 2.0, back, [("pills", None), ("pills", None), ("ammo", None)])


def scatter_cars(m, rng, x0, z0, x1, z1, count, kinds=("cars_sedan", "cars_taxi", "cars_suv", "cars_hatchback-sports", "cars_van", "cars_police")):
    """Abandoned cars, at angles, along a street. Kept off its middle third so the way is open."""
    width = x1 - x0
    for i in range(count):
        z = z0 + (i + 0.5) * (z1 - z0) / count + rng.uniform(-2.0, 2.0)
        side = -1 if i % 2 == 0 else 1
        x = (x0 + x1) / 2 + side * width * rng.uniform(0.22, 0.3)
        m.prop(rng.choice(kinds), x, z, rng.choice((0.0, 180.0)) + rng.uniform(-25.0, 25.0))


def debris(m, rng, x0, z0, x1, z1, count):
    """Small things on the ground that are not in anybody's way."""
    kinds = ("graveyard_debris", "graveyard_debris-wood", "cars_debris-tire", "cars_debris-door", "urban_detail-bricks-type-a")
    for _ in range(count):
        m.prop(rng.choice(kinds), rng.uniform(x0, x1), rng.uniform(z0, z1), rng.uniform(0.0, 360.0))


# --- The maps --------------------------------------------------------------------------------

def blackout_1():
    m = Map("zz_blackout_1", "Blackout 1: Corner Shop",
            "The power went out a week ago. Get from the corner shop to the flats across the square.",
            "exodus", NIGHT, next_map="zz_blackout_2")
    rng = random.Random(101)

    safe_room(m, -4, -10, 4, -2, (-1, -2, 1, -1.5))
    # The high street, north to the square.
    m.region(-8, -1.5, 8, 60, floor="asphalt", height=8.0, tint=[0.82, 0.76, 0.72])
    # A dead-end alley west, with somebody's stash in it.
    m.region(-20, 20, -8, 24.5, floor="concrete", height=7.0, wall="concrete")
    # A laundromat east, through its door.
    m.door(8, 33, 8.5, 35)
    m.room(8.5, 30, 18, 40, floor="tile_check", wall="paint", tint=[0.8, 0.85, 0.9], light=COLD)
    # The square, split by a locked fence at x 18.
    m.region(-8, 60, 30, 72.5, floor="sidewalk", height=9.0, tint=[0.7, 0.72, 0.78])
    m.gate("fence", 18.0, 60.0, 18.4, 72.5, 3.2, "metal", [0.55, 0.58, 0.6], look="chain_link")
    # North out of the square to the flats.
    m.region(22, 72.5, 30, 90, floor="asphalt", height=8.0, tint=[0.78, 0.74, 0.7])
    safe_room(m, 22, 90.5, 30, 98, (25, 90, 27, 90.5), start=False)

    scatter_cars(m, rng, -8, 4, 8, 56, 6)
    debris(m, rng, -7, 2, 7, 58, 10)
    for z in (4, 22, 40, 56):
        m.lamp(-7.4 if z % 4 == 0 else 7.4, z, 90 if z % 4 == 0 else -90)
    m.prop("urban_detail-dumpster-closed", -18.5, 22.2, 90)
    m.prop("urban_detail-dumpster-open", -7.2, 12.0, 90)
    m.prop("survival_barrel", 7.3, 26.0)
    m.prop("survival_barrel", 7.0, 27.0)
    m.prop("roads_construction-barrier", -4.0, 50.0, 10)
    m.prop("roads_construction-cone", 2.0, 46.0)
    m.prop("roads_construction-cone", 3.0, 47.0)
    # The laundromat's machines are boxes along its back wall; a sleeper among them.
    for i in range(5):
        m.block(10.0 + i * 1.6, 39.2, 1.2, 1.0, 1.2, "metal", [0.88, 0.9, 0.92])
    m.sleeper(15.5, 33.0, 270)
    m.item("box", 16.5, 0.0, 37.0, "mystery")
    m.item("ammo", 10.0, 0.0, 31.0)
    # The alley's stash.
    m.item("weapon", -19.0, 0.0, 21.0, "hunting_rifle")
    m.item("throwable", -19.0, 0.0, 23.5, "molotov")
    m.item("box", -15.0, 0.0, 23.8)
    m.sleeper(-12.0, 21.0, 90)
    # The square: benches, trees, the fence and its lock.
    for x in (-4, 4, 10):
        m.prop("urban_detail-bench", x, 71.4, 180)
    m.prop("urban_tree-park-large", 0.0, 66.0)
    m.prop("urban_tree-park-large", 12.0, 64.0)
    m.prop("cars_firetruck", -4.0, 63.0, 80)
    m.light(4.0, 4.5, 66.0, 18.0, 1.2, SODIUM)
    m.light(25.0, 4.5, 66.0, 16.0, 1.2, SODIUM)
    m.objective("fence", "use", 17.3, 1.0, 66.0, "Cut the fence lock", seconds=3.0, holdout=35.0,
                opens=["fence"], message="The lock is screaming. Here they come — hold on!", prop="padlock")
    m.item("ammo", 14.0, 0.0, 61.0)
    m.item("throwable", 14.5, 0.0, 61.0, "pipe_bomb")
    scatter_cars(m, rng, 22, 74, 30, 88, 2, ("cars_sedan", "cars_delivery"))
    m.lamp(29.4, 80, -90)
    m.sleeper(23.0, 84.0, 180)

    m.path((0, -6), (0, 0), (0, 30), (0, 62), (10, 66), (20, 66), (26, 74), (26, 94))
    m.hint(-19.0, 22.0)
    m.hint(13.0, 35.0)
    m.hint(-6.0, 70.0)
    m.hint(28.0, 88.0)
    return m


def blackout_2():
    m = Map("zz_blackout_2", "Blackout 2: The Depot",
            "Through the container yard and the warehouse. The loading shutter only opens from inside.",
            "exodus", NIGHT, next_map="zz_blackout_3")
    rng = random.Random(202)

    safe_room(m, -4, -10, 4, -2, (-1, -2, 1, -1.5))
    m.region(-16, -1.5, 16, 40, floor="concrete", height=6.0, wall="concrete", tint=[0.7, 0.7, 0.72])
    m.door(-2, 40, 2, 40.5, floor="concrete")
    m.room(-20, 40.5, 20, 80, floor="concrete", height=7.0, wall="metal", tint=[0.55, 0.6, 0.62], light=None)
    m.door(-3, 80, 3, 80.5, floor="concrete", gate="shutter", gate_tint=[0.75, 0.6, 0.25])
    m.region(-12, 80.5, 12, 100, floor="asphalt", height=6.0, wall="concrete", tint=[0.65, 0.65, 0.68])
    safe_room(m, -4, 100.5, 4, 108, (-1, 100, 1, 100.5), start=False)

    # Containers in the yard: stacks you go round, and one you can see over.
    colours = ([0.6, 0.18, 0.15], [0.15, 0.32, 0.55], [0.2, 0.45, 0.25], [0.7, 0.5, 0.15])
    for i, (x, z, yaw) in enumerate(((-11.0, 8.0, 0), (11.0, 10.0, 0), (-9.0, 22.0, 90), (7.5, 26.0, 90), (-12.0, 33.0, 0), (12.0, 34.0, 0))):
        sx, sz = (2.6, 6.2) if yaw == 0 else (6.2, 2.6)
        m.block(x, z, sx, sz, 2.6, "metal", colours[i % len(colours)])
        if i % 2 == 0:
            m.block(x, z, sx, sz, 2.6, "metal", colours[(i + 1) % len(colours)], y=2.6)
    m.prop("urban_truck-grey-cargo", 2.0, 16.0, 20)
    m.prop("urban_pallet", -3.0, 30.0)
    m.prop("urban_pallet-small", -4.2, 31.0, 30)
    m.prop("survival_barrel", 14.5, 3.0)
    m.prop("survival_barrel-open", 14.2, 4.2)
    for x, z in ((-14.0, 15.0), (14.0, 20.0), (-14.0, 36.0)):
        m.light(x, 5.0, z, 16.0, 1.2, SODIUM)
    m.sleeper(12.5, 28.0, 270)
    m.item("box", -14.5, 0.0, 26.0)
    m.item("ammo", 3.5, 0.0, 38.5)

    # The warehouse: racks in rows, with aisles between; lit by a few cold lamps.
    for row in range(4):
        z = 47.0 + row * 8.0
        for x in (-14.0, -5.0, 5.0, 14.0):
            m.block(x, z, 6.0, 1.2, 3.2, "metal", [0.35, 0.4, 0.55])
    for x, z in ((-10.0, 52.0), (10.0, 52.0), (-10.0, 70.0), (10.0, 70.0), (0.0, 61.0)):
        m.light(x, 6.4, z, 14.0, 1.1, COLD)
    for x, z in ((-17.5, 44.0), (17.0, 60.0), (-16.0, 76.0)):
        m.prop("survival_box-large", x, z, rng.uniform(0, 90))
    m.prop("survival_box", 1.0, 43.0)
    m.prop("survival_box-open", 2.0, 43.4, 20)
    m.prop("urban_pallet", -1.0, 66.0)
    m.sleeper(-17.0, 56.0, 90)
    m.sleeper(17.5, 70.0, 270)
    m.item("weapon", 9.5, 0.0, 43.0, "pump_shotgun")
    m.item("medkit", -9.5, 0.0, 66.0)
    m.item("throwable", 0.0, 0.0, 74.0, "frag")
    m.item("box", 18.0, 0.0, 47.0, "explosive")
    m.objective("shutter", "use", 6.0, 1.0, 79.2, "Raise the loading shutter", seconds=2.5, holdout=45.0,
                opens=["shutter"], message="The motor is grinding. Everything heard that.", prop="lever", yaw=180)

    # The loading dock: trucks backed up to it.
    m.prop("cars_truck", -8.0, 90.0, 0)
    m.prop("cars_garbage-truck", 8.0, 92.0, 180)
    m.prop("cars_delivery", -2.0, 96.0, 75)
    m.light(0.0, 5.0, 90.0, 18.0, 1.3, SODIUM)
    m.item("pills", 10.5, 0.0, 84.0)

    m.path((0, -6), (0, 0), (0, 38), (0, 42), (0, 60), (0, 79), (0, 82), (0, 104))
    m.hint(-15.0, 2.0)
    m.hint(15.0, 38.0)
    m.hint(-19.0, 78.0)
    m.hint(11.0, 98.0)
    return m


def blackout_3():
    m = Map("zz_blackout_3", "Blackout 3: The Pier",
            "Down to the water. Radio the boat from the end of the pier and live long enough to board it.",
            "exodus", DUSK)
    rng = random.Random(303)

    safe_room(m, -4, -10, 4, -2, (-1, -2, 1, -1.5))
    m.region(-6, -1.5, 6, 30, floor="asphalt", height=8.0, tint=[0.85, 0.8, 0.72])
    # The front: sand, and a railing on the water side.
    m.region(-30, 30, 30, 53, floor="sand", height=6.0, wall="stone", tint=[0.8, 0.78, 0.72])
    # The promenade along the water, railed, so the sea is seen from the front.
    m.region(-30, 53, 30, 55, floor="wood_floor", height=0.0, rail=RAIL)
    # The pier, railed, out over the water; the boat at its end behind a gate.
    m.region(-4, 55, 4, 100, floor="wood_floor", height=0.0, rail=RAIL)
    m.door(-2, 100, 2, 100.5, floor="wood_floor", gate="boat", gate_mat="wood", gate_tint=[0.5, 0.35, 0.2])
    m.region(-6, 100.5, 6, 110, floor="wood_floor", height=0.0, rail=RAIL)
    m.end(-6, 100.5, 6, 110)
    m.flat(-60, 55.3, 60, 150, "water", y=-1.5)

    scatter_cars(m, rng, -6, 4, 6, 28, 3, ("cars_sedan", "cars_taxi", "cars_ambulance"))
    m.lamp(-5.4, 10, 90)
    m.lamp(5.4, 24, -90)
    for x in (-24, -12, 12, 24):
        m.prop("survival_tent-canvas" if x < 0 else "survival_tent", x, 40.0, rng.uniform(0, 360))
    m.prop("survival_campfire-pit", -18.0, 46.0)
    m.light(-18.0, 1.0, 46.0, 9.0, 1.6, [1.0, 0.6, 0.3])
    m.prop("survival_bedroll", -16.0, 44.0, 30)
    m.prop("cars_firetruck", 18.0, 49.0, 100)
    m.prop("urban_detail-bench", -6.0, 53.8, 180)
    m.prop("urban_detail-bench", 6.0, 53.8, 180)
    for z in (62, 76, 90):
        m.prop("graveyard_lightpost-single", -3.4, z, 90)
        m.light(-2.8, 3.0, z, 10.0, 1.1, SODIUM)
    m.prop("survival_barrel", 3.3, 70.0)
    m.prop("survival_box", 3.2, 84.0)
    m.prop("survival_box-large", -5.0, 108.5)
    m.sleeper(24.0, 33.0, 0)
    m.sleeper(-26.0, 52.0, 90)

    m.item("weapon", -22.0, 0.0, 38.5, "grenade_launcher")
    m.item("box", 22.0, 0.0, 34.0, "medical")
    m.item("box", 0.0, 0.0, 50.0)
    m.item("ammo", 2.5, 0.0, 95.0)
    m.item("ammo", -2.5, 0.0, 95.0)
    m.item("throwable", 2.5, 0.0, 92.0, "molotov")
    m.item("medkit", -2.5, 0.0, 92.0)
    m.objective("radio", "use", 0.0, 1.0, 98.5, "Radio the boat", seconds=3.0, holdout=90.0,
                opens=["boat"], message="They heard you. Ninety seconds — hold the pier!", prop="radio", yaw=180)

    m.path((0, -6), (0, 0), (0, 30), (0, 54), (0, 80), (0, 98), (0, 105))
    m.hint(-28.0, 32.0)
    m.hint(28.0, 32.0)
    m.hint(-28.0, 53.0)
    m.hint(28.0, 53.0)
    return m


def lot():
    m = Map("zz_lot", "Parking Lot", "A walled car park with a kiosk in the middle. Hold it until the clock runs out.",
            "survival", NIGHT, survive_seconds=300.0)
    rng = random.Random(404)

    m.region(-30, -30, 30, 30, floor="asphalt", height=4.0, wall="concrete", tint=[0.6, 0.6, 0.62])
    # The kiosk, open on two sides.
    m.door(-1, -4.5, 1, -4, floor="tile")
    m.door(-1, 4, 1, 4.5, floor="tile")
    m.room(-4, -4, 4, 4, floor="tile", wall="paint", tint=[0.78, 0.74, 0.62], light=WARM)
    m.start(-4, -4, 4, 4)
    for dx, dz in ((-1.5, -1.5), (1.5, -1.5), (-1.5, 1.5), (1.5, 1.5)):
        m.spawn(dx, dz, 0.0)
    m.table_of(-2.5, 0.0, [("weapon", "smg"), ("weapon", "shotgun")], 90.0)
    m.table_of(2.5, 0.0, [("weapon", "rifle"), ("ammo", None)], 90.0)
    m.item("pills", -3.2, 0.0, 3.2)
    m.item("medkit", 3.2, 0.0, 3.2)

    # Rows of parked cars, with lanes between.
    kinds = ("cars_sedan", "cars_suv", "cars_hatchback-sports", "cars_van", "cars_suv-luxury", "cars_taxi")
    for x in (-24.0, -16.0, 16.0, 24.0):
        for z in range(-24, 25, 6):
            if rng.random() < 0.75:
                m.prop(rng.choice(kinds), x, z, 90.0 + rng.choice((0.0, 180.0)) + rng.uniform(-6, 6))
    for z in (-20.0, 20.0):
        for x in range(-8, 9, 8):
            m.prop(rng.choice(kinds), x, z, rng.choice((0.0, 180.0)) + rng.uniform(-8, 8))
    for x, z in ((-12.0, -12.0), (12.0, 12.0), (-12.0, 12.0), (12.0, -12.0)):
        m.prop("roads_light-square", x, z)
        m.light(x, 5.5, z, 18.0, 1.4, SODIUM)
    m.prop("urban_detail-dumpster-closed", -28.6, 0.0, 90)
    m.prop("urban_detail-dumpster-open", 28.6, 4.0, -90)
    debris(m, rng, -28, -28, 28, 28, 14)

    for x, z, kind, iid in ((-27.0, -27.0, "box", None), (27.0, 27.0, "box", None), (27.0, -27.0, "ammo", None),
                            (-27.0, 27.0, "ammo", None), (0.0, -27.0, "weapon", "drum_shotgun"),
                            (0.0, 27.0, "weapon", "machine_gun"), (-27.0, 8.0, "throwable", "pipe_bomb"),
                            (27.0, -8.0, "throwable", "molotov"), (-10.0, 25.0, "medkit", None)):
        m.item(kind, x, 0.0, z, iid)

    for x, z in ((0.0, -6.0), (0.0, 6.0), (-8.0, 0.0), (8.0, 0.0), (-12.0, -12.0), (12.0, 12.0)):
        m.post(x, z)
    m.caches.append([-2.5, 0.82, 0.0])
    m.caches.append([2.5, 0.82, 0.0])
    m.path((0, 0))
    for x, z in ((-29, -29), (29, -29), (-29, 29), (29, 29), (0, -29), (0, 29), (-29, 0), (29, 0)):
        m.hint(x, z)
    return m


def chapel():
    m = Map("zz_chapel", "Chapel Yard", "A graveyard in fog and a chapel with two doors. Six minutes.",
            "survival", FOG_NIGHT, survive_seconds=360.0)
    rng = random.Random(505)

    m.region(-28, -28, 28, 28, floor="grass", height=3.0, wall="stone", tint=[0.6, 0.62, 0.6])
    m.door(-1, -8.5, 1, -8, floor="wood_floor", barricade="south_door", label="the chapel's south door", strength=1200)
    m.door(-1, 8, 1, 8.5, floor="wood_floor", barricade="north_door", label="the chapel's north door", strength=1200)
    m.room(-6, -8, 6, 8, floor="wood_floor", height=6.0, wall="stone", tint=[0.78, 0.76, 0.7], light=[1.0, 0.8, 0.55])
    m.start(-6, -8, 6, 8)
    for dx, dz in ((-1.5, -1.5), (1.5, -1.5), (-1.5, 1.5), (1.5, 1.5)):
        m.spawn(dx, dz, 0.0)
    # Pews in two rows, an aisle down the middle.
    for z in (-5.0, -3.0, -1.0, 3.0, 5.0):
        m.block(-3.6, z, 3.4, 0.6, 0.9, "wood", [0.45, 0.3, 0.2])
        m.block(3.6, z, 3.4, 0.6, 0.9, "wood", [0.45, 0.3, 0.2])
    m.table_of(0.0, 1.2, [("weapon", "smg"), ("weapon", "shotgun"), ("ammo", None)], 0.0)
    m.item("pills", -5.3, 0.0, 7.3)
    m.item("medkit", 5.3, 0.0, -7.3)

    # The graves: rows of stones, and a few crypts to put your back to.
    stones = ("graveyard_gravestone-round", "graveyard_gravestone-cross", "graveyard_gravestone-bevel",
              "graveyard_gravestone-broken", "graveyard_gravestone-wide", "graveyard_gravestone-decorative")
    for x in range(-24, 25, 4):
        for z in (-22, -17, 17, 22):
            if rng.random() < 0.8:
                m.prop(rng.choice(stones), x + rng.uniform(-0.4, 0.4), z, rng.uniform(-10, 10))
    for x, z, yaw in ((-18.0, 0.0, 90.0), (18.0, 0.0, -90.0)):
        m.prop("graveyard_crypt-small", x, z, yaw)
    for x, z in ((-12.0, -12.0), (12.0, 12.0), (-22.0, 10.0), (22.0, -10.0), (14.0, -24.0), (-14.0, 24.0)):
        m.prop(rng.choice(("graveyard_pine", "graveyard_pine-crooked")), x, z, rng.uniform(0, 360))
    for x, z in ((-10.0, -10.0), (10.0, 10.0), (10.0, -10.0), (-10.0, 10.0)):
        m.prop("graveyard_lightpost-single", x, z)
        m.light(x, 3.0, z, 12.0, 1.0, SODIUM)
    m.prop("graveyard_fire-basket", 0.0, -12.0)
    m.light(0.0, 1.2, -12.0, 8.0, 1.5, [1.0, 0.6, 0.3])

    for x, z, kind, iid in ((-25.0, -25.0, "box", None), (25.0, 25.0, "box", None), (25.0, -25.0, "box", "explosive"),
                            (-25.0, 25.0, "ammo", None), (25.0, 0.0, "ammo", None), (-25.0, 0.0, "weapon", "sawed_off"),
                            (0.0, 25.0, "throwable", "molotov"), (0.0, -25.0, "throwable", "pipe_bomb")):
        m.item(kind, x, 0.0, z, iid)
    m.sleeper(-22.0, -4.0, 90)
    m.sleeper(22.0, 4.0, 270)
    for x, z in ((0.0, -6.5), (0.0, 6.5), (-4.5, 0.0), (4.5, 0.0)):
        m.post(x, z)
    m.caches.append([0.0, 0.82, 1.2])

    m.path((0, 0))
    for x, z in ((-27, -27), (27, -27), (-27, 27), (27, 27), (0, -27), (0, 27), (-27, 0), (27, 0)):
        m.hint(x, z)
    return m

# --- Survival maps built for a crowd ----------------------------------------------------------
#
# The first play test: "There should be many survivors, but it would require the map to be much
# larger." These are. Each is held by a dozen or more (`survivors`, which stand-ins fill to), with
# posts a team spreads over, caches the breathers restock, and doors and windows boarded up for
# the horde to break down and the survivors to mend. The horde comes from the map's edges (its
# `zombie_spawns`): the car park, the outfield, the tree line.

DAY = {
    "sky_top": [0.36, 0.52, 0.76], "sky_horizon": [0.74, 0.8, 0.86], "ground": [0.3, 0.29, 0.27],
    "sun_pitch": -50.0, "sun_yaw": 35.0, "sun_energy": 1.0, "sun_colour": [1.0, 0.96, 0.9],
    "ambient": [0.62, 0.66, 0.72], "ambient_energy": 0.55, "fog": 0.006,
}
CAMPUS_NIGHT = dict(NIGHT, ambient=[0.36, 0.4, 0.52], ambient_energy=0.3, fog=0.012, sun_energy=0.16)
FLOODLIT = {
    "sky_top": [0.03, 0.035, 0.07], "sky_horizon": [0.12, 0.11, 0.16], "ground": [0.04, 0.04, 0.04],
    "sun_pitch": -60.0, "sun_yaw": 120.0, "sun_energy": 0.18, "sun_colour": [0.7, 0.78, 1.0],
    "ambient": [0.4, 0.42, 0.5], "ambient_energy": 0.34, "fog": 0.008,
}
FLOOD = [1.0, 0.97, 0.9]
FENCE = [0.55, 0.58, 0.6]
BRICK_RED = [0.86, 0.62, 0.52]
CREAM = [0.95, 0.9, 0.78]


def ring(m, box, outer, floors=("asphalt", "grass", "grass", "asphalt"), height=3.0, wall="metal", tint=FENCE):
    """The grounds round a building: four outdoor strips (south, north, west, east) half a metre
    off the building's outline, touching each other at the corners so they are one walkable ring.
    `box` and `outer` are (x0, z0, x1, z1)."""
    bx0, bz0, bx1, bz1 = box
    ox0, oz0, ox1, oz1 = outer
    south = m.region(ox0, oz0, ox1, bz0 - 0.5, floors[0], height, wall=wall, tint=tint)
    north = m.region(ox0, bz1 + 0.5, ox1, oz1, floors[1], height, wall=wall, tint=tint)
    west = m.region(ox0, bz0 - 0.5, bx0 - 0.5, bz1 + 0.5, floors[2], height, wall=wall, tint=tint)
    east = m.region(bx1 + 0.5, bz0 - 0.5, ox1, bz1 + 0.5, floors[3], height, wall=wall, tint=tint)
    return south, north, west, east


def parked(m, rng, x0, x1, z, step=3.2, yaw=0.0, fill=0.7,
           kinds=("cars_sedan", "cars_suv", "cars_hatchback-sports", "cars_van", "cars_taxi", "cars_suv-luxury")):
    """A row of parked cars, nose to the aisle, with gaps."""
    x = x0
    while x <= x1:
        if rng.random() < fill:
            m.prop(rng.choice(kinds), x, z, 90.0 + yaw + rng.uniform(-4.0, 4.0))
        x += step


def light_pole(m, x, z, colour=SODIUM, rng_m=22.0, energy=1.6):
    m.prop("roads_light-square", x, z)
    m.light(x, 6.0, z, rng_m, energy, colour)


def stands(m, x0, z0, x1, z1, rows, toward, rise=0.75, start=0.0, mat="concrete", tint=(0.72, 0.72, 0.76),
           seat=(0.42, 0.52, 0.72)):
    """Tiered seating as solid steps, highest at the back. `toward` is the side the seats face
    ("n", "s", "e", "w"); each row a step of `rise`, with a coloured seat strip on its front."""
    depth = ((z1 - z0) if toward in "ns" else (x1 - x0)) / rows
    for i in range(rows):
        h = start + rise * (i + 1)
        if toward == "n":
            a0, a1 = z1 - (i + 1) * depth, z1 - i * depth
            m.block((x0 + x1) / 2, (a0 + a1) / 2, x1 - x0, depth, h - start, mat, list(tint), y=start)
            m.block((x0 + x1) / 2, a0 + 0.25, x1 - x0 - 0.2, 0.35, h + 0.25 - start, "flat", list(seat), y=start)
        elif toward == "s":
            a0, a1 = z0 + i * depth, z0 + (i + 1) * depth
            m.block((x0 + x1) / 2, (a0 + a1) / 2, x1 - x0, depth, h - start, mat, list(tint), y=start)
            m.block((x0 + x1) / 2, a1 - 0.25, x1 - x0 - 0.2, 0.35, h + 0.25 - start, "flat", list(seat), y=start)
        elif toward == "e":
            a0, a1 = x1 - (i + 1) * depth, x1 - i * depth
            m.block((a0 + a1) / 2, (z0 + z1) / 2, depth, z1 - z0, h - start, mat, list(tint), y=start)
            m.block(a0 + 0.25, (z0 + z1) / 2, 0.35, z1 - z0 - 0.2, h + 0.25 - start, "flat", list(seat), y=start)
        else:
            a0, a1 = x0 + i * depth, x0 + (i + 1) * depth
            m.block((a0 + a1) / 2, (z0 + z1) / 2, depth, z1 - z0, h - start, mat, list(tint), y=start)
            m.block(a1 - 0.25, (z0 + z1) / 2, 0.35, z1 - z0 - 0.2, h + 0.25 - start, "flat", list(seat), y=start)


def paint(m, x0, z0, x1, z1, mat="line", y=0.005, tint=None):
    """A marking on a floor: drawn, not solid, not in anybody's way."""
    box = {"at": [r((x0 + x1) / 2), y, r((z0 + z1) / 2)], "size": [r(x1 - x0), 0.01, r(z1 - z0)], "mat": mat,
           "solid": False, "nav": False}
    if tint:
        box["tint"] = tint
    m.boxes.append(box)


def bus(m, x, z, yaw=0.0):
    """A school bus: a long yellow box, a dark band of windows, black wheels under it."""
    along_x = abs(yaw) == 90.0
    sx, sz = (11.0, 2.6) if along_x else (2.6, 11.0)
    m.block(x, z, sx, sz, 2.9, "metal", [0.98, 0.74, 0.12], y=0.35)
    m.block(x, z, sx + 0.04, sz + 0.04, 0.7, "glass", [0.2, 0.24, 0.3], y=1.9)
    for t in (-3.8, 3.8):
        wx, wz = (x + t, z) if along_x else (x, z + t)
        m.block(wx, wz, 1.0 if along_x else 2.7, 2.7 if along_x else 1.0, 0.9, "rubber", [0.12, 0.12, 0.12])


def classroom(m, rng, x0, z0, x1, z1, board_wall="w"):
    """Desks in rows facing a board."""
    cx = (x0 + x1) / 2
    for row in range(3):
        for col in range(4):
            x = x0 + 2.3 + col * ((x1 - x0) - 4.6) / 3
            z = z0 + 2.6 + row * 2.4
            m.prop("furniture_desk", x, z, 0.0)
            m.prop("furniture_chair_desk", x, z - 0.9, 180.0)
    m.prop("furniture_desk", cx, z1 - 1.3, 180.0)
    m.prop("furniture_bookcase_open", x1 - 0.5, z1 - 1.2, -90.0)
    if board_wall == "w":
        m.block(x0 + 0.04, (z0 + z1) / 2, 0.06, 4.0, 1.2, "chalkboard", None, y=1.0)
    else:
        m.block(x1 - 0.04, (z0 + z1) / 2, 0.06, 4.0, 1.2, "whiteboard", None, y=1.0)


def lockers(m, x0, x1, z, skip, depth=0.5):
    """A run of lockers against a wall, broken where a doorway is."""
    x = x0
    while x + 2.0 <= x1:
        if not any(abs(x + 1.0 - s) < 2.4 for s in skip):
            m.block(x + 1.0, z, 2.0, depth, 2.0, "locker", [0.36, 0.46, 0.66])
        x += 2.0


def high_school():
    m = Map("zz_high_school", "Westbrook High",
            "A school at night, every door and window boarded. Hold the halls, mend the boards, "
            "and keep them out of the gym.", "survival", CAMPUS_NIGHT, survivors=12, day=DAY)
    rng = random.Random(606)
    wall_in = dict(wall="paint", tint=[0.86, 0.88, 0.8], facade="brick", facade_tint=BRICK_RED)

    # The building: x -40..40.5, z -22..14, one hallway east to west through it.
    m.room(-40, -2.5, 40.5, 3.5, floor="tile_check", height=3.6, light=None, **wall_in)
    m.lights_grid(-40, -2.5, 40.5, 3.5, 10.0, 3.2, 11.0, 1.2, [1.0, 0.95, 0.85])
    north = [(-40, -27), (-26.5, -13.5), (-13, 0), (0.5, 13.5), (14, 27), (27.5, 40.5)]
    for i, (x0, x1) in enumerate(north):
        cx = (x0 + x1) / 2
        m.room(x0, 4, x1, 14, floor="tile", height=3.4, light=WARM, **wall_in)
        m.door(cx - 1, 3.5, cx + 1, 4, floor="tile")
        for wx in (cx - 3.5, cx + 3.5):
            m.door(wx - 1, 14, wx + 1, 14.5, floor="tile", barricade="n%d_%s" % (i, "w" if wx < cx else "e"),
                   label="a classroom window", boards="window")
        classroom(m, rng, x0, 4, x1, 14, "w" if i % 2 == 0 else "e")
        m.post(cx, 10.5)
    # South: two classrooms, the library behind them, the gym, the cafeteria and its kitchen.
    for i, (x0, x1) in enumerate(((-40, -27), (-26.5, -13.5))):
        cx = (x0 + x1) / 2
        m.room(x0, -14, x1, -3, floor="tile", height=3.4, light=WARM, **wall_in)
        m.door(cx - 1, -3, cx + 1, -2.5, floor="tile")
        m.post(cx, -9.0)
    m.door(-40.5, -9.5, -40, -7.5, floor="tile", barricade="s0_w", label="a classroom window", boards="window")
    for row in range(2):
        for col in range(4):
            m.prop("furniture_desk", -37.2 + col * 2.6, -11.6 + row * 2.6, 180.0)
            m.prop("furniture_desk", -23.7 + col * 2.6, -11.6 + row * 2.6, 180.0)
    m.block(-33.5, -13.94, 4.0, 0.06, 1.2, "chalkboard", None, y=1.0)
    # Beside the library door, not across it: a board over a doorway is a bar at head height
    # nothing on the floor plan knows about, and a stand-in stood against it for a minute.
    m.block(-24.25, -13.94, 3.5, 0.06, 1.2, "whiteboard", None, y=1.0)
    m.room(-40, -22, -13.5, -14.5, floor="carpet", height=3.4, light=None, **wall_in)
    m.light(-33.0, 3.0, -18.2, 12.0, 1.1, WARM)
    m.light(-20.0, 3.0, -18.2, 12.0, 1.1, WARM)
    m.door(-21, -14.5, -19, -14, floor="carpet")
    for wx in (-35.0, -24.0):
        m.door(wx - 1, -22.5, wx + 1, -22, floor="carpet", barricade="lib_%d" % int(-wx), label="a library window",
               boards="window")
    for x in (-37.5, -33.5, -29.5):
        m.prop("furniture_bookcase_closed_wide", x, -21.4, 0.0)
    for x in (-37.5, -33.5):
        m.prop("furniture_bookcase_closed_wide", x, -17.6, 180.0)
    m.prop("furniture_table", -23.0, -18.0, 90.0)
    m.prop("furniture_table", -17.0, -18.0, 90.0)
    m.cache(-27.5, -18.0)
    m.post(-30.0, -18.5)

    # The gym: tall, its floor lined, a door at each end of the hallway side and the big doors out.
    m.room(-13, -22, 13.5, -3, floor="gym", height=7.0, light=None, **wall_in)
    m.lights_grid(-13, -22, 13.5, -3, 11.0, 6.4, 14.0, 1.3, [1.0, 0.97, 0.9])
    for dx in (-6.5, 6.5):
        m.door(dx - 1.5, -3, dx + 1.5, -2.5, floor="gym")
    m.door(-2, -22.5, 2, -22, floor="gym", barricade="gym_doors", label="the gym doors", strength=1600)
    paint(m, -11.5, -12.55, 12.0, -12.45)
    paint(m, 0.2, -21.5, 0.3, -3.5)
    for x in (-11.8, 12.3):
        m.block(x, -12.5, 0.25, 0.25, 3.0, "metal", [0.4, 0.4, 0.42])
        m.block(x + (0.4 if x < 0 else -0.4), -12.5, 0.1, 1.8, 1.1, "whiteboard", None, y=2.9)
    stands(m, -12.8, -21.6, -8.6, -14.0, 4, "e", rise=0.5)
    m.cache(0.0, -6.0)
    m.post(-5.0, -17.0)
    m.post(5.0, -17.0)
    m.sleeper(11.0, -20.5, 270)

    # The cafeteria and the kitchen behind it.
    m.room(14, -15, 40.5, -3, floor="tile_small", height=4.0, light=None, **wall_in)
    m.lights_grid(14, -15, 40.5, -3, 9.0, 3.6, 11.0, 1.1, WARM)
    for dx in (21.5, 33.5):
        m.door(dx - 1.5, -3, dx + 1.5, -2.5, floor="tile_small")
    for wz in (-11.0, -6.5):
        m.door(40.5, wz - 1, 41, wz + 1, floor="tile_small", barricade="caf_%d" % int(-wz), label="a cafeteria window",
               boards="window")
    for row in range(3):
        for col in range(4):
            m.prop("furniture_table_cross", 17.5 + col * 5.6, -12.5 + row * 3.6, 0.0)
    m.cache(27.0, -4.6)
    m.post(27.0, -8.5)
    m.post(38.0, -9.0)
    m.room(14, -22, 40.5, -15.5, floor="tile", height=3.4, light=COLD, **wall_in)
    m.door(26, -15.5, 28, -15, floor="tile")
    m.door(33, -22.5, 36, -22, floor="concrete", barricade="loading", label="the loading door", boards="shutter",
           strength=1800)
    for x in (16.0, 17.2, 18.4):
        m.prop("furniture_kitchen_stove", x, -21.4)
    m.prop("furniture_kitchen_fridge_large", 20.5, -21.3)
    m.prop("furniture_kitchen_fridge_large", 21.9, -21.3)
    for x in (16.5, 17.7, 18.9, 20.1):
        m.prop("furniture_kitchen_cabinet", x, -17.0, 180.0)
    m.post(30.0, -19.5)

    # The hallway's two ends are the front doors.
    m.door(-40.5, -0.5, -40, 1.5, floor="tile_check", barricade="west_doors", label="the west doors", strength=1400)
    m.door(40.5, -0.5, 41, 1.5, floor="tile_check", barricade="main_doors", label="the main entrance", strength=1400)
    lockers(m, -39.0, 39.5, 3.25, [(a + b) / 2 for a, b in north])
    lockers(m, -39.0, 39.5, -2.25, (-33.5, -20.0, -6.5, 6.5, 21.5, 33.5))
    m.post(-37.0, 0.5)
    m.post(37.5, 0.5)
    m.cache(-6.5, 0.5, table=False)
    m.cache(14.0, 0.5, table=False)
    for i in range(14):
        m.spawn(-26.0 + i * 4.0, 0.5 + (0.9 if i % 2 else -0.9), 90.0 if i < 7 else -90.0)

    # The grounds: the car park and the bus loop south, the football field north.
    s_, n_, w_, e_ = ring(m, (-40, -22, 40.5, 14), (-76, -68, 77, 64), ("asphalt", "grass", "sidewalk", "asphalt"))
    for z, yaw in ((-31.0, 0.0), (-47.0, 0.0), (-52.5, 180.0)):
        parked(m, rng, -70.0, 70.0, z, 3.3, yaw, 0.4)
    # Lamps on the outside walls, over the windows: the horde at the boards is seen.
    for x in range(-36, 41, 12):
        m.wall_lamp(x, 14.9)
    for x in (-34.0, -22.0, -6.0, 6.0, 20.0, 34.0):
        m.wall_lamp(x, -22.9)
    for z in (-12.0, 0.5, 10.0):
        m.wall_lamp(41.4, z)
        m.wall_lamp(-40.9, z)
    for x in (-60.0, -30.0, 0.0, 30.0, 60.0):
        light_pole(m, x, -41.8)
        light_pole(m, x, -57.8)
    for x in (52.0, 64.0):
        bus(m, x, -2.0)
    bus(m, 58.0, 11.0, 90.0)
    light_pole(m, 46.0, -10.0)
    light_pole(m, 70.0, 6.0)
    paint(m, -69.0, -41.9, 69.0, -41.7, tint=[0.9, 0.85, 0.3])
    paint(m, -69.0, -57.9, 69.0, -57.7, tint=[0.9, 0.85, 0.3])
    # The field: its lines, its posts, its stands, its lights.
    for x in range(-45, 50, 10):
        paint(m, x - 0.06, 23.0, x + 0.06, 55.0)
    paint(m, -48.0, 22.9, 48.0, 23.1)
    paint(m, -48.0, 54.9, 48.0, 55.1)
    for x in (-48.5, 48.5):
        m.block(x, 39.0, 0.25, 0.25, 3.2, "metal", [0.95, 0.85, 0.2])
        m.block(x, 37.3, 0.2, 0.2, 6.0, "metal", [0.95, 0.85, 0.2])
        m.block(x, 40.7, 0.2, 0.2, 6.0, "metal", [0.95, 0.85, 0.2])
        m.block(x, 39.0, 0.2, 3.6, 0.2, "metal", [0.95, 0.85, 0.2], y=3.0)
    stands(m, -30.0, 57.5, 30.0, 63.5, 6, "s", rise=0.55)
    for x in (-55.0, 55.0):
        for z in (26.0, 52.0):
            m.block(x, z, 0.6, 0.6, 12.0, "metal", [0.5, 0.52, 0.55])
            m.light(x, 11.0, z, 40.0, 3.2, FLOOD)
    for x, z in ((-62.0, 30.0), (-66.0, 46.0), (62.0, 34.0), (66.0, 50.0), (-58.0, 18.0), (60.0, 18.0)):
        m.prop(rng.choice(("nature_tree_oak", "nature_tree_default", "nature_tree_fat")), x, z, rng.uniform(0, 360))
    for z in (-14.0, -4.0, 6.0):
        m.prop("nature_tree_oak", -60.0, z, rng.uniform(0, 360))
    light_pole(m, -50.0, -2.0)
    m.prop("urban_detail-dumpster-closed", 37.0, -24.2, 0)
    m.prop("urban_detail-dumpster-open", 31.0, -24.2, 0)
    m.prop("roads_construction-barrier", -44.0, 0.5, 90)
    debris(m, rng, -70.0, -66.0, 70.0, -24.0, 18)

    for x, z in ((-70.0, -66.0), (-35.0, -66.0), (0.0, -66.0), (35.0, -66.0), (70.0, -66.0),
                 (-72.0, -10.0), (-72.0, 10.0), (72.0, -18.0), (73.0, 8.0),
                 (-60.0, 61.0), (0.0, 56.5), (60.0, 61.0), (-72.0, 40.0), (72.0, 40.0)):
        m.hint(x, z)
    m.path((0.0, 0.5))
    return m


def mark(m, cx, cz, sx, sz, yaw, mat="line", y=0.006, tint=None):
    """A turned marking on a floor (a baseline, an infield): drawn, not solid."""
    box = {"at": [r(cx), y, r(cz)], "size": [r(sx), 0.01, r(sz)], "mat": mat, "solid": False, "nav": False}
    if yaw:
        box["yaw"] = r(yaw)
    if tint:
        box["tint"] = tint
    m.boxes.append(box)


SHOPS = ("grocery", "furniture", "electronics", "books", "toys", "clothes", "pharmacy", "diner")


def shop(m, rng, x0, z0, x1, z1, kind, front_z):
    """One shop's floor: what it sells, in rows that leave an aisle to the front."""
    cx = (x0 + x1) / 2
    back = z1 - 1.2 if front_z < z0 else z0 + 1.2
    face = 180.0 if front_z < z0 else 0.0
    rows = [z0 + 4.0 + i * 3.6 for i in range(int((z1 - z0 - 7.0) / 3.6))]
    if kind == "grocery":
        for z in rows:
            for x in (x0 + 2.5, cx - 2.2, cx + 2.2, x1 - 2.5):
                m.prop(rng.choice(("market_shelf-boxes", "market_shelf-bags")), x, z, 90.0)
        for x in (x0 + 2.0, x0 + 4.6, x1 - 4.6, x1 - 2.0):
            m.prop("market_freezers-standing", x, back, face)
        m.prop("market_cash-register", cx - 2.0, front_z + (-2.0 if front_z > z1 - 1 else 2.0), 0.0)
        m.prop("market_shopping-cart", cx + 2.6, front_z + (-2.4 if front_z > z1 - 1 else 2.4), 30.0)
        m.prop("market_display-fruit", cx + 4.0, (z0 + z1) / 2, 0.0)
    elif kind == "pharmacy":
        for z in rows[:3]:
            for x in (x0 + 2.5, cx, x1 - 2.5):
                m.prop("market_shelf-end", x, z, 0.0)
        m.prop("market_cash-register", cx, back, face)
    elif kind == "furniture":
        for i, z in enumerate(rows):
            m.prop(("furniture_lounge_sofa_long", "furniture_bed_double", "furniture_lounge_design_sofa")[i % 3], x0 + 3.0, z, 90.0)
            m.prop("furniture_table_coffee", cx, z, 0.0)
            m.prop(("furniture_bed_single", "furniture_lounge_sofa", "furniture_bookcase_open")[i % 3], x1 - 3.0, z, -90.0)
    elif kind == "electronics":
        for z in rows:
            m.prop("furniture_cabinet_television", x0 + 2.5, z, 90.0)
            m.prop("furniture_desk", cx, z, 0.0)
            m.prop("furniture_cabinet_television", x1 - 2.5, z, -90.0)
        for x in (x0 + 2.0, cx, x1 - 2.0):
            m.prop("furniture_speaker", x, back, face)
    elif kind == "books":
        for z in rows:
            for x in (x0 + 2.2, cx - 2.0, cx + 2.0, x1 - 2.2):
                m.prop("furniture_bookcase_closed_wide", x, z, 0.0)
    elif kind == "toys":
        for z in rows:
            m.prop("furniture_table", x0 + 3.0, z, 0.0)
            m.prop("furniture_table", x1 - 3.0, z, 0.0)
        for i in range(6):
            m.prop("furniture_bear", x0 + 2.0 + i * (x1 - x0 - 4.0) / 5, back, face)
    elif kind == "clothes":
        for z in rows:
            for x in (x0 + 2.0, cx - 1.6, cx + 1.6, x1 - 2.0):
                m.prop("furniture_coat_rack_standing", x, z, rng.uniform(0, 90))
    else:
        for z in rows:
            m.prop("furniture_table_round", x0 + 3.0, z, 0.0)
            m.prop("furniture_table_round", x1 - 3.0, z, 0.0)
        inward = 1.0 if back < (z0 + z1) / 2 else -1.0
        for x in (x0 + 1.5, x0 + 3.0, x0 + 4.5):
            m.prop("furniture_stool_bar", x, back + inward * 1.2, 0.0)
        m.prop("furniture_kitchen_bar", x0 + 3.0, back, face)
        m.prop("furniture_kitchen_fridge", x1 - 1.6, back, face)


def mall():
    m = Map("zz_mall", "Riverside Galleria",
            "A shopping mall after closing time, its shutters down and the car park full of them. Sixteen "
            "shops, a food court, and eight ways in.", "survival", CAMPUS_NIGHT, survivors=14, day=DAY, spacing=1.25)
    rng = random.Random(707)
    inside = dict(wall="paint", tint=CREAM, facade="concrete", facade_tint=[0.78, 0.76, 0.72])

    # The concourse, east to west, and the food court across its middle.
    m.room(-75, -6, 75, 6, floor="tile", height=8.0, light=None, **inside)
    m.lights_grid(-75, -6, 75, 6, 12.5, 7.4, 15.0, 1.4, WARM)
    m.room(-15, 6, 15, 27, floor="tile_check", height=8.0, light=None, **inside)
    m.room(-15, -27, 15, -6, floor="tile_check", height=8.0, light=None, **inside)
    m.lights_grid(-15, 6, 15, 27, 11.0, 7.4, 14.0, 1.3, WARM)
    m.lights_grid(-15, -27, 15, -6, 11.0, 7.4, 14.0, 1.3, WARM)

    spans = [(-75, -60.5), (-60, -45.5), (-45, -30.5), (-30, -15.5), (15.5, 30), (30.5, 45), (45.5, 60), (60.5, 75)]
    kinds = list(SHOPS)
    for i, (x0, x1) in enumerate(spans):
        cx = round((x0 + x1)) / 2.0
        tint = [[0.9, 0.86, 0.8], [0.82, 0.88, 0.92], [0.92, 0.84, 0.86], [0.84, 0.9, 0.82]][i % 4]
        m.room(x0, 6.5, x1, 27, floor="parquet" if i % 2 else "tile_small", height=5.0, light=WARM,
               wall="paint", tint=tint, facade="concrete", facade_tint=[0.78, 0.76, 0.72])
        m.door(cx - 4, 6, cx + 4, 6.5, floor="tile")
        shop(m, rng, x0, 6.5, x1, 27, kinds[i % len(kinds)], 6.5)
        m.room(x0, -27, x1, -6.5, floor="tile_small" if i % 2 else "parquet", height=5.0, light=WARM,
               wall="paint", tint=tint, facade="concrete", facade_tint=[0.78, 0.76, 0.72])
        m.door(cx - 4, -6.5, cx + 4, -6, floor="tile")
        shop(m, rng, x0, -27, x1, -6.5, kinds[(i + 3) % len(kinds)], -6.5)
        # The shop's sign over its front, in its own colour.
        m.block(cx, 6.75, 7.0, 0.3, 0.9, "flat", [0.3 + 0.6 * (i % 3) / 2, 0.45, 0.85 - 0.25 * (i % 2)], y=3.0)
        m.block(cx, -6.75, 7.0, 0.3, 0.9, "flat", [0.85 - 0.25 * (i % 2), 0.4 + 0.2 * (i % 3), 0.35], y=3.0)

    # Eight ways in: the two ends and the food court's two sides (wide steel shutters), and the
    # service doors at the back of the corner shops.
    # The four entrances are barricaded chest high (benches, boards, a planter on its side), so
    # the team shoots over them; a steel shutter there was a wave nobody could see, let alone
    # kill, until it broke.
    m.door(-75.5, -4, -75, 4, floor="tile", barricade="west_entrance", label="the west entrance", boards="window", strength=2200)
    m.door(75, -4, 75.5, 4, floor="tile", barricade="east_entrance", label="the east entrance", boards="window", strength=2200)
    m.door(-5, 27, 5, 27.5, floor="tile_check", barricade="north_entrance", label="the north entrance", boards="window", strength=2400)
    m.door(-5, -27.5, 5, -27, floor="tile_check", barricade="south_entrance", label="the south entrance", boards="window", strength=2400)
    for bid, x, z0, z1 in (("nw_service", -69.0, 27, 27.5), ("ne_service", 69.0, 27, 27.5),
                           ("sw_service", -69.0, -27.5, -27), ("se_service", 69.0, -27.5, -27)):
        m.door(x - 1, z0, x + 1, z1, floor="concrete", barricade=bid, label="a service door", strength=1200)

    # The food court: tables round a fountain, planters down the concourse, benches between.
    for side in (1, -1):
        m.block(0.0, side * 17.0, 6.0, 6.0, 0.6, "stone", [0.78, 0.76, 0.72])
        m.block(0.0, side * 17.0, 5.2, 5.2, 0.62, "water", [0.4, 0.6, 0.8])
        m.light(0.0, 1.5, side * 17.0, 7.0, 1.4, COLD)
        for x in (-10.0, -5.0, 5.0, 10.0):
            for z in (side * 10.5, side * 23.0):
                m.prop("furniture_table_round", x, z)
                m.prop("furniture_chair", x + 1.2, z, -90.0)
                m.prop("furniture_chair", x - 1.2, z, 90.0)
        m.cache(-11.0, side * 17.0)
    for x in range(-66, 67, 12):
        if abs(x) < 16:
            continue
        # A planter: a stone kerb round a bed of earth, and a bush in it.
        for dx, dz, sx, sz in ((0.0, -0.9, 2.0, 0.2), (0.0, 0.9, 2.0, 0.2), (-0.9, 0.0, 0.2, 1.6), (0.9, 0.0, 0.2, 1.6)):
            m.block(x + dx, dz, sx, sz, 0.55, "stone", [0.74, 0.72, 0.68])
        paint(m, x - 0.8, -0.8, x + 0.8, 0.8, "dirt", 0.3, [0.4, 0.3, 0.22])
        m.prop("nature_plant_bush_detailed", x, 0.0)
        m.prop("urban_detail-bench", x + 3.5, 0.0, 90.0)
    for x in (-48.0, 48.0):
        m.block(x, 0.0, 3.0, 2.0, 1.1, "wood", [0.55, 0.36, 0.22])
        m.block(x, 0.0, 3.2, 2.2, 0.1, "flat", [0.85, 0.3, 0.25], y=2.6)
        m.block(x - 1.4, 0.9, 0.1, 0.1, 2.6, "metal", [0.6, 0.6, 0.62])
        m.block(x + 1.4, -0.9, 0.1, 0.1, 2.6, "metal", [0.6, 0.6, 0.62])
    m.cache(-62.0, 0.0, table=False)
    m.cache(62.0, 0.0, table=False)
    m.cache(-67.75, 16.0, table=False)

    for x, z in ((-71.0, 0.0), (71.0, 0.0), (0.0, 23.0), (0.0, -23.0), (-69.0, 23.0), (69.0, 23.0), (-69.0, -23.0),
                 (69.0, -23.0), (-40.0, 2.5), (40.0, -2.5), (-22.0, 0.0), (22.0, 0.0), (8.0, 12.0), (-8.0, -12.0)):
        m.post(x, z)
    for i in range(16):
        m.spawn(-14.0 + (i % 8) * 4.0, -2.5 if i < 8 else 2.5, 0.0 if i < 8 else 180.0)

    # The car park all round, its lamps, and the cars nobody came back for.
    ring(m, (-75, -27, 75, 27), (-112, -62, 112, 62), ("asphalt", "asphalt", "asphalt", "asphalt"))
    for z, yaw in ((-36.0, 0.0), (-41.5, 180.0), (-52.0, 0.0), (36.0, 180.0), (41.5, 0.0), (52.0, 180.0)):
        parked(m, rng, -104.0, 104.0, z, 3.3, yaw, 0.45)
    for x in (-90.0, -60.0, -30.0, 0.0, 30.0, 60.0, 90.0):
        light_pole(m, x, -46.8)
        light_pole(m, x, 46.8)
    for z in (-15.0, 15.0):
        light_pole(m, -95.0, z)
        light_pole(m, 95.0, z)
    for x in (-80.0, 80.0):
        m.wall_lamp(x, 0.0 + (-5.0 if x < 0 else 5.0), 4.0)
    for z in (-29.0, 29.0):
        m.wall_lamp(-8.0, z, 4.0)
        m.wall_lamp(8.0, z, 4.0)
        for x in (-69.0, 69.0):
            m.wall_lamp(x + 2.6, z, 3.4)
    for x in (-58.0, -86.0, 86.0, 58.0):
        paint(m, x - 0.1, -58.0, x + 0.1, -30.0, tint=[0.9, 0.85, 0.3])
        paint(m, x - 0.1, 30.0, x + 0.1, 58.0, tint=[0.9, 0.85, 0.3])
    m.prop("urban_truck-grey-cargo", -66.0, 31.0, 90)
    m.prop("urban_truck-grey", 66.0, -31.5, -90)
    m.prop("urban_detail-dumpster-closed", -72.0, 29.0, 0)
    m.prop("urban_detail-dumpster-open", 72.0, -29.0, 180)
    debris(m, rng, -104.0, -58.0, 104.0, -30.0, 14)
    debris(m, rng, -104.0, 30.0, 104.0, 58.0, 14)

    for x, z in ((-108.0, -58.0), (-54.0, -59.0), (0.0, -59.0), (54.0, -59.0), (108.0, -58.0),
                 (-108.0, 58.0), (-54.0, 59.0), (0.0, 59.0), (54.0, 59.0), (108.0, 58.0),
                 (-109.0, 0.0), (109.0, 0.0)):
        m.hint(x, z)
    m.path((0.0, 0.0))
    return m



def tower(m, x, z, height=22.0, colour=FLOOD, rng_m=80.0, energy=3.6):
    """A floodlight mast: a steel pole, a bank of lamps, and the light it throws."""
    m.block(x, z, 0.9, 0.9, height, "metal", [0.45, 0.47, 0.5])
    m.block(x, z, 5.0, 1.2, 2.4, "metal", [0.35, 0.36, 0.4], y=height)
    m.boxes.append({"at": [r(x), r(height + 1.2), r(z)], "size": [4.6, 2.0, 1.4], "mat": "glass",
                    "tint": [1.0, 0.98, 0.9], "solid": False, "nav": False})
    m.light(x, height - 0.5, z, rng_m, energy, colour)


def stadium():
    m = Map("zz_stadium", "Harbor Park",
            "A ballpark under its floodlights. The concourse is theirs; the field is yours, for as long as "
            "the tunnels hold.", "survival", FLOODLIT, survivors=16, day=DAY, spacing=1.5)
    rng = random.Random(808)
    concourse = dict(wall="paint", tint=[0.8, 0.8, 0.76], facade="concrete", facade_tint=[0.72, 0.72, 0.74])

    # The field: grass to a padded wall, the diamond at its south end.
    m.region(-55, -45, 55, 60, floor="grass", height=3.0, wall="flat", tint=[0.18, 0.4, 0.26])
    mark(m, 0.0, -20.6, 30.0, 30.0, 45.0, "dirt", 0.004, [0.86, 0.66, 0.5])
    mark(m, 0.0, -20.6, 23.0, 23.0, 45.0, "grass", 0.006)
    mark(m, 0.0, -21.5, 4.6, 4.6, 45.0, "dirt", 0.008, [0.86, 0.66, 0.5])
    mark(m, 0.0, -40.0, 7.0, 7.0, 45.0, "dirt", 0.008, [0.86, 0.66, 0.5])
    for bx, bz in ((19.4, -20.6), (0.0, -1.2), (-19.4, -20.6), (0.0, -40.0)):
        mark(m, bx, bz, 0.6, 0.6, 45.0, "line", 0.012)
    mark(m, -27.5, -12.5, 0.15, 77.8, -45.0, "line", 0.01)
    mark(m, 27.5, -12.5, 0.15, 77.8, 45.0, "line", 0.01)
    paint(m, -54.8, 56.5, 54.8, 59.8, "dirt", 0.004, [0.8, 0.62, 0.48])
    paint(m, -54.8, -44.8, -51.5, 56.5, "dirt", 0.004, [0.8, 0.62, 0.48])
    paint(m, 51.5, -44.8, 54.8, 56.5, "dirt", 0.004, [0.8, 0.62, 0.48])
    for x in (-54.6, 54.6):
        m.block(x, 15.0, 0.3, 0.3, 11.0, "metal", [0.95, 0.85, 0.2])

    # The concourse all round, under and behind the stands.
    m.room(-85, -75, 85, -65, floor="concrete", height=5.0, light=None, **concourse)
    m.room(-85, 80, 85, 90, floor="concrete", height=5.0, light=None, **concourse)
    m.room(-85, -65, -75, 80, floor="concrete", height=5.0, light=None, **concourse)
    m.room(75, -65, 85, 80, floor="concrete", height=5.0, light=None, **concourse)
    for x in range(-76, 77, 19):
        m.light(x, 4.4, -70.0, 13.0, 1.2, WARM)
        m.light(x, 4.4, 85.0, 13.0, 1.2, WARM)
    for z in range(-50, 75, 19):
        m.light(-80.0, 4.4, z, 13.0, 1.2, WARM)
        m.light(80.0, 4.4, z, 13.0, 1.2, WARM)
    for x, z in ((-60.0, -70.0), (-20.0, -70.0), (20.0, -70.0), (60.0, -70.0), (-30.0, 85.0), (30.0, 85.0),
                 (-80.0, -20.0), (80.0, 40.0)):
        m.block(x, z + (-3.5 if z < 0 else 3.5) if abs(z) > 60 else z, 4.0 if abs(z) > 60 else 2.0,
                2.0 if abs(z) > 60 else 4.0, 1.1, "wood", [0.6, 0.4, 0.25])

    # The tunnels from the concourse to the field: the ways onto the field, boarded at its end.
    def tunnel_ns(bid, x, z0, z1, field_at_low, label):
        m.room(x - 2, z0, x + 2, z1, floor="concrete", height=3.0, light=WARM, **concourse)
        # Chest high at the field end: the team on the field shoots down the tunnel over it.
        if field_at_low:
            m.door(x - 2, z0 - 0.5, x + 2, z0, floor="concrete", barricade=bid, label=label, strength=1800, boards="window")
            m.door(x - 2, z1, x + 2, z1 + 0.5, floor="concrete")
        else:
            m.door(x - 2, z1, x + 2, z1 + 0.5, floor="concrete", barricade=bid, label=label, strength=1800, boards="window")
            m.door(x - 2, z0 - 0.5, x + 2, z0, floor="concrete")

    def tunnel_ew(bid, z, x0, x1, field_at_low, label, width=2.0, strength=1800, boards="window"):
        m.room(x0, z - width, x1, z + width, floor="concrete", height=3.0, light=WARM, **concourse)
        if field_at_low:
            m.door(x0 - 0.5, z - width, x0, z + width, floor="concrete", barricade=bid, label=label, strength=strength, boards=boards)
            m.door(x1, z - width, x1 + 0.5, z + width, floor="concrete")
        else:
            m.door(x1, z - width, x1 + 0.5, z + width, floor="concrete", barricade=bid, label=label, strength=strength, boards=boards)
            m.door(x0 - 0.5, z - width, x0, z + width, floor="concrete")

    tunnel_ns("home_tunnel", 0.0, -64.5, -45.5, False, "the tunnel behind home plate")
    tunnel_ns("sw_tunnel", -40.0, -64.5, -45.5, False, "the third-base tunnel")
    tunnel_ns("se_tunnel", 40.0, -64.5, -45.5, False, "the first-base tunnel")
    tunnel_ns("cf_tunnel", 0.0, 60.5, 79.5, True, "the centre-field gate")
    tunnel_ew("lf_tunnel", 10.0, -74.5, -55.5, False, "the left-field tunnel")
    tunnel_ew("rf_tunnel", 10.0, 55.5, 74.5, True, "the right-field tunnel")

    # The dugouts: open onto the field, each with a narrow tunnel back to the concourse.
    for side in (-1, 1):
        x0, x1 = (-63.0, -55.5) if side < 0 else (55.5, 63.0)
        m.room(x0, -32, x1, -24, floor="concrete", height=2.8, light=WARM, wall="paint", tint=[0.3, 0.42, 0.58],
               facade="concrete", facade_tint=[0.72, 0.72, 0.74])
        if side < 0:
            m.door(-55.5, -31, -55, -25, floor="grass")
            tunnel_ew("dugout_w", -28.0, -74.5, -63.5, True, "the third-base dugout", 1.0, 1200, "door")
        else:
            m.door(55, -31, 55.5, -25, floor="grass")
            tunnel_ew("dugout_e", -28.0, 63.5, 74.5, False, "the first-base dugout", 1.0, 1200, "door")
        bench_x = (x0 + 0.8) if side < 0 else (x1 - 0.8)
        # Not at -28: a bench there stood across the tunnel's door, which the graph did not
        # know about, and every zombie through it stuck behind the bench for the rest of the wave.
        for z in (-30.5, -25.5):
            m.prop("urban_detail-bench", bench_x, z, 90.0 * side)
        m.cache((x0 + x1) / 2, -26.0, table=False)
        m.post((x0 + x1) / 2 + 3.0 * side, -28.0)

    # The stands: tiers rising from the field wall to the concourse, open where a tunnel or a
    # dugout comes through.
    for x0, x1 in ((-74.5, -42.5), (-37.5, -2.5), (2.5, 37.5), (42.5, 74.5)):
        stands(m, x0, -64.5, x1, -45.6, 10, "n", rise=0.9, seat=(0.2, 0.32, 0.6))
    for x0, x1 in ((-74.5, -2.5), (2.5, 74.5)):
        stands(m, x0, 60.6, x1, 79.5, 8, "s", rise=0.7, seat=(0.62, 0.22, 0.2))
    for z0, z1 in ((-44.5, -33.0), (-23.0, 7.5), (12.5, 59.5)):
        stands(m, -74.5, z0, -55.6, z1, 9, "e", rise=0.85, seat=(0.2, 0.32, 0.6))
        stands(m, 55.6, z0, 74.5, z1, 9, "w", rise=0.85, seat=(0.2, 0.32, 0.6))
    # Over the dugouts and their tunnels the stands start above the roofs.
    for x0, x1 in ((-74.5, -55.6), (55.6, 74.5)):
        for z0, z1 in ((-32.5, -23.5),):
            toward = "e" if x0 < 0 else "w"
            stands(m, x0, z0, x1, z1, 5, toward, rise=0.9, start=3.4, seat=(0.2, 0.32, 0.6))
    # The scoreboard over the outfield bleachers.
    m.block(0.0, 78.8, 26.0, 1.0, 12.0, "metal", [0.2, 0.22, 0.25], y=5.6)
    m.block(0.0, 78.25, 22.0, 0.1, 7.0, "flat", [0.08, 0.1, 0.12], y=8.0)
    for i in range(9):
        m.boxes.append({"at": [r(-8.8 + i * 2.2), 13.0, 78.18], "size": [1.4, 0.8, 0.05], "mat": "glass",
                        "tint": [1.0, 0.8, 0.3], "solid": False, "nav": False})
    m.light(0.0, 11.0, 74.0, 20.0, 1.5, [1.0, 0.85, 0.5])
    for x, z in ((-70.0, -62.0), (70.0, -62.0), (-71.0, 32.0), (71.0, 32.0), (-40.0, 77.5), (40.0, 77.5)):
        tower(m, x, z)

    # The field's posts and caches.
    for x, z in ((0.0, -42.0), (-40.0, -42.0), (40.0, -42.0), (0.0, 57.0), (-52.0, 10.0), (52.0, 10.0),
                 (19.0, -19.0), (-19.0, -19.0), (0.0, -3.0), (0.0, -24.0), (-26.0, 26.0), (26.0, 26.0), (0.0, 38.0),
                 (-38.0, 45.0), (38.0, 45.0)):
        m.post(x, z)
    m.cache(0.0, -25.5)
    m.cache(0.0, 36.0)
    m.cache(-24.0, -38.0)
    for i in range(16):
        a = i * math.tau / 16
        m.spawn(math.cos(a) * 6.0, -18.0 + math.sin(a) * 6.0, math.degrees(a))

    # The car park round it all, and the turnstile gates into the concourse: open, because the
    # concourse is the horde's way in, not the team's to hold.
    ring(m, (-85, -75, 85, 90), (-112, -102, 112, 117), ("asphalt", "asphalt", "asphalt", "asphalt"))
    for x in (-47.0, 0.0, 47.0):
        m.door(x - 3, -75.5, x + 3, -75, floor="concrete")
        m.wall_lamp(x, -76.0, 4.2)
    for x in (-27.0, 27.0):
        m.door(x - 3, 90, x + 3, 90.5, floor="concrete")
        m.wall_lamp(x, 91.0, 4.2)
    for z in (-30.0, 43.0):
        m.door(-85.5, z - 3, -85, z + 3, floor="concrete")
        m.door(85, z - 3, 85.5, z + 3, floor="concrete")
    for z, yaw in ((-83.0, 0.0), (-88.5, 180.0), (98.0, 180.0), (103.5, 0.0)):
        parked(m, rng, -104.0, 104.0, z, 3.3, yaw, 0.45)
    for x in (-95.0, 95.0):
        for z in range(-60, 81, 14):
            if rng.random() < 0.55:
                m.prop(rng.choice(("cars_sedan", "cars_suv", "cars_van", "cars_taxi")), x, z, rng.uniform(-8, 8))
    for x in (-80.0, -40.0, 0.0, 40.0, 80.0):
        light_pole(m, x, -95.0)
        light_pole(m, x, 110.0)
    for z in (-40.0, 0.0, 40.0, 80.0):
        light_pole(m, -104.0, z)
        light_pole(m, 104.0, z)
    debris(m, rng, -104.0, -98.0, 104.0, -78.0, 16)
    for x, z in ((-108.0, -98.0), (-50.0, -99.0), (0.0, -99.0), (50.0, -99.0), (108.0, -98.0), (-108.0, 113.0),
                 (-50.0, 114.0), (50.0, 114.0), (108.0, 113.0), (-109.0, 10.0), (109.0, 10.0), (0.0, 114.0)):
        m.hint(x, z)
    m.path((0.0, -18.0))
    return m


def tent(m, x, z, w, d, colour, along_x=True, cross=False):
    """A big canvas tent: a box of canvas with a ridge along its length."""
    sx, sz = (w, d) if along_x else (d, w)
    m.block(x, z, sx, sz, 2.3, "paint", colour)
    m.block(x, z, sx * (1.0 if along_x else 0.55), sz * (0.55 if along_x else 1.0), 0.9, "paint", colour, y=2.3)
    if cross:
        face_z = z - sz / 2 - 0.03
        m.boxes.append({"at": [r(x), 1.5, r(face_z)], "size": [1.4, 0.4, 0.04], "mat": "flat", "tint": [0.85, 0.12, 0.12],
                        "solid": False, "nav": False})
        m.boxes.append({"at": [r(x), 1.5, r(face_z)], "size": [0.4, 1.4, 0.04], "mat": "flat", "tint": [0.85, 0.12, 0.12],
                        "solid": False, "nav": False})


def relief_camp():
    m = Map("zz_relief_camp", "Relief Camp",
            "An evacuation camp in a clearing: tents, trucks and a plywood wall. The trees come right up to it.",
            "survival", dict(NIGHT, fog=0.03, ambient=[0.36, 0.4, 0.5], ambient_energy=0.3), survivors=10,
            day=dict(DAY, fog=0.012), spacing=1.25)
    rng = random.Random(909)
    hoarding = [0.74, 0.64, 0.48]

    # The compound: a plywood wall round a trampled field.
    m.region(-45, -45, 45, 45, floor="dirt", height=3.2, wall="wood", tint=hoarding, facade="wood", facade_tint=hoarding)
    ring(m, (-45, -45, 45, 45), (-86, -86, 86, 86), ("grass", "grass", "grass", "grass"), height=4.0, wall="hedge",
         tint=[0.22, 0.36, 0.2])
    for bid, door, label in (("north_gate", (-3, 45, 3, 45.5), "the north gate"), ("south_gate", (-3, -45.5, 3, -45), "the south gate"),
                             ("west_gate", (-45.5, -3, -45, 3), "the west gate"), ("east_gate", (45, -3, 45.5, 3), "the east gate")):
        m.door(*door, floor="dirt", barricade=bid, label=label, boards="window", strength=2200)
    for bid, door in (("breach_nw", (-31, 45, -29, 45.5)), ("breach_ne", (29, 45, 31, 45.5)),
                      ("breach_sw", (-45.5, -31, -45, -29)), ("breach_se", (45, -31, 45.5, -29))):
        m.door(*door, floor="dirt", barricade=bid, label="a patched hole in the wall", strength=900)

    # Inside: rows of tents, the field hospital, the command tent, the depot, the trucks.
    for z in (-34.0, -24.0):
        for x in (-36.0, -26.0, -16.0):
            tent(m, x, z, 7.0, 5.0, [0.48, 0.52, 0.34])
    for z in (24.0, 34.0):
        for x in (-36.0, -26.0, -16.0):
            tent(m, x, z, 7.0, 5.0, [0.5, 0.5, 0.42] if x != -26.0 else [0.36, 0.44, 0.52])
    tent(m, 26.0, -28.0, 14.0, 8.0, [0.92, 0.92, 0.9], cross=True)
    tent(m, 26.0, 28.0, 10.0, 7.0, [0.42, 0.46, 0.3])
    for x in (-36.0, -26.0, -16.0):
        m.prop("survival_bedroll", x + 4.5, -29.0, 90.0)
    for x, z in ((14.0, 10.0), (17.0, 10.0), (20.0, 10.0), (14.0, 13.5), (17.0, 13.5)):
        m.prop("urban_pallet", x, z, rng.choice((0.0, 90.0)))
    for x, z in ((24.0, 12.0), (25.6, 12.2), (24.6, 13.6), (30.0, 9.5), (31.4, 9.8)):
        m.prop("survival_box-large", x, z, rng.uniform(0, 90))
    for x, z in ((33.0, 14.0), (34.0, 14.6), (33.4, 15.6)):
        m.prop("survival_barrel", x, z)
    m.prop("urban_truck-green", -34.0, 6.0, 90)
    m.prop("urban_truck-green", -34.0, -6.0, 90)
    m.prop("cars_ambulance", 36.0, -16.0, 0)
    m.prop("urban_truck-grey-cargo", 36.0, 20.0, 180)
    # The water tank on its legs, the generator, the watchtower.
    for dx in (-1.6, 1.6):
        for dz in (-1.6, 1.6):
            m.block(-12.0 + dx, 12.0 + dz, 0.3, 0.3, 3.0, "metal", [0.5, 0.5, 0.52])
    m.block(-12.0, 12.0, 4.0, 4.0, 2.6, "metal", [0.6, 0.66, 0.7], y=3.0)
    m.block(12.0, -12.0, 2.4, 1.4, 1.5, "metal", [0.85, 0.7, 0.2])
    m.light(12.0, 2.0, -12.0, 9.0, 1.2, [1.0, 0.8, 0.5])
    for dx in (-1.4, 1.4):
        for dz in (-1.4, 1.4):
            m.block(38.0 + dx, 38.0 + dz, 0.3, 0.3, 5.0, "wood", [0.5, 0.36, 0.24])
    m.block(38.0, 38.0, 3.6, 3.6, 0.3, "wood", [0.55, 0.4, 0.26], y=5.0)
    m.block(38.0, 38.0, 3.6, 3.6, 0.2, "wood", [0.45, 0.32, 0.2], y=7.4)
    m.light(38.0, 6.0, 38.0, 24.0, 2.0, FLOOD)
    m.prop("survival_campfire-pit", 0.0, 0.0)
    m.light(0.0, 1.2, 0.0, 10.0, 1.8, [1.0, 0.6, 0.3])
    for a in range(6):
        ang = a * math.tau / 6
        m.prop("urban_detail-bench" if a % 2 else "survival_tree-log", math.cos(ang) * 4.2, math.sin(ang) * 4.2,
               math.degrees(-ang) + 90.0)
    for x, z in ((-30.0, -12.0), (30.0, 0.0), (0.0, 30.0), (0.0, -30.0), (-20.0, 40.0), (20.0, -40.0),
                 (-38.0, 20.0), (-10.0, -20.0), (10.0, 20.0), (38.0, -38.0)):
        m.prop("roads_light-curved", x, z, rng.choice((0.0, 90.0, 180.0, 270.0)))
        m.light(x, 4.8, z, 24.0, 2.2, FLOOD)
    # Work lights over the four gates, so whoever holds one sees what comes.
    for x, z in ((0.0, 43.5), (0.0, -43.5), (-43.5, 0.0), (43.5, 0.0)):
        m.light(x, 3.6, z, 18.0, 2.0, FLOOD)
    for x, z, yaw in ((-6.0, 41.0, 0.0), (6.0, 41.0, 0.0), (-6.0, -41.0, 0.0), (6.0, -41.0, 0.0),
                      (-41.0, -6.0, 90.0), (-41.0, 6.0, 90.0), (41.0, -6.0, 90.0), (41.0, 6.0, 90.0)):
        m.prop("survival_fence-fortified", x, z, yaw)

    for x, z in ((0.0, 41.0), (0.0, -41.0), (-41.0, 0.0), (41.0, 0.0), (-30.0, 41.0), (30.0, 41.0), (-41.0, -30.0),
                 (41.0, -30.0), (8.0, 4.0), (-8.0, -4.0)):
        m.post(x, z)
    m.cache(22.0, 16.0)
    m.cache(20.0, -22.0)
    m.cache(-6.0, -6.0)
    m.cache(26.0, 23.0)
    for i in range(12):
        a = i * math.tau / 12
        m.spawn(math.cos(a) * 8.0, math.sin(a) * 8.0, math.degrees(a))

    # The woods: trees thick in the ring, thinner along the four tracks to the gates.
    kinds = ("nature_tree_pine_tall_a", "nature_tree_pine_round_a", "nature_tree_default", "nature_tree_tall",
             "nature_tree_cone", "graveyard_pine", "graveyard_pine-crooked")
    for i in range(130):
        x = rng.uniform(-84.0, 84.0)
        z = rng.uniform(-84.0, 84.0)
        if abs(x) < 50.0 and abs(z) < 50.0:
            continue
        if abs(x) < 6.0 or abs(z) < 6.0:
            continue
        m.prop(rng.choice(kinds), x, z, rng.uniform(0, 360))
    for i in range(24):
        x, z = rng.uniform(-84.0, 84.0), rng.uniform(-84.0, 84.0)
        if (abs(x) < 50.0 and abs(z) < 50.0) or abs(x) < 6.0 or abs(z) < 6.0:
            continue
        m.prop(rng.choice(("nature_rock_large_a", "nature_stump_old", "nature_log_large", "survival_rock-b")), x, z,
               rng.uniform(0, 360))
    for x0, z0, x1, z1 in ((-2.5, 45.5, 2.5, 85.5), (-2.5, -85.5, 2.5, -45.5), (-85.5, -2.5, -45.5, 2.5), (45.5, -2.5, 85.5, 2.5)):
        paint(m, x0, z0, x1, z1, "dirt", 0.004, [0.62, 0.5, 0.38])
    m.prop("cars_police", 6.0, 60.0, 12.0)
    m.prop("cars_sedan", -5.0, -64.0, 170.0)
    m.prop("roads_construction-barrier", 0.0, 49.0, 90)
    for x, z in ((-80.0, -80.0), (0.0, -82.0), (80.0, -80.0), (-82.0, 0.0), (82.0, 0.0), (-80.0, 80.0), (0.0, 82.0),
                 (80.0, 80.0), (-40.0, -82.0), (40.0, 82.0), (-82.0, 40.0), (82.0, -40.0)):
        m.hint(x, z)
    m.path((0.0, 0.0))
    return m


PLANS = (blackout_1, blackout_2, blackout_3, lot, chapel, high_school, mall, stadium, relief_camp)


# --- Toys -----------------------------------------------------------------------------------
#
# dot-props' toys (game-zombie-zone builds them from the document's `toys`, both ends, in this
# order). **Loose ones only**: barrels, tyres, balls, a bowling set. A survivor and a zombie walk
# through a loose toy and a survivor's walk or shot sends it on; a fixed one (a see-saw, a
# trampoline) would stand on the zombies' ground, which the nav floors do not know about, and
# be a wall a stand-in walks into. A hint names an anchor (the first survivor spawn, a route
# point, a post) and an offset; `settle_toys` moves it to the nearest spot within 10 m that is
# floored flat, clear of every box and prop by half a metre, and 1.5 m from every spawn and
# item. A hint that settles nowhere stops the build rather than leaving a toy out.

TOY_SIZE = {
    "beach_ball": (0.5, 1.0), "football": (0.15, 0.3), "bowling_ball": (0.15, 0.3), "bowling_pin": (0.1, 0.4),
    "barrel": (0.35, 0.9), "tyre": (0.45, 0.3), "_rack": (0.8, 0.4),
}
TOY_NOT_FLOOR = ("water", "lava", "slime", "foliage", "thin_ice")


def toy(tid, anchor="spawn", dx=0.0, dz=0.0, yaw=0.0, exact=False):
    if tid not in TOY_SIZE:
        raise SystemExit("toy %s is not a loose toy this builder places" % tid)
    return {"toy": tid, "anchor": anchor, "dx": dx, "dz": dz, "yaw": yaw, "exact": exact}


def toy_pins(anchor, dx, dz):
    """A rack of six bowling pins, settled as one: a triangle with its point toward -z."""
    return [{"toy": "_rack", "anchor": anchor, "dx": dx, "dz": dz, "yaw": 0.0, "exact": False}]


def _toy_anchor(doc, anchor):
    if anchor == "spawn":
        a = doc["spawns"]["survivors"][0]["at"]
    elif anchor[0] == "route":
        a = doc["route"][anchor[1]]
    elif anchor[0] == "post":
        a = doc["posts"][anchor[1]]
    else:
        raise SystemExit("toy anchor %s" % str(anchor))
    return a[0], a[1], a[2]


def _toy_floor(boxes, x, z, near_y, ground=None, ground_mat=None):
    """The top of the highest solid box (or the terrain heightfield `ground`) under (x, z) no
    more than a metre over near_y, or None."""
    best = None
    for b, lo, hi in boxes:
        if lo[0] <= x <= hi[0] and lo[2] <= z <= hi[2] and hi[1] <= near_y + 1.0 and (best is None or hi[1] > best[0]):
            best = (hi[1], b.get("mat"))
    h = ground.height(x, z) if ground else None
    if h is not None and h <= near_y + 1.0 and (best is None or h > best[0]):
        best = (h, ground_mat)
    return best


def settle_toys(doc, hints):
    solid = []
    for b in doc["boxes"]:
        lo = [b["at"][i] - b["size"][i] / 2.0 for i in range(3)]
        hi = [b["at"][i] + b["size"][i] / 2.0 for i in range(3)]
        solid.append((b, lo, hi))
    keep_off = [sp["at"] for sp in doc["spawns"].get("survivors", [])] + [it["at"] for it in doc.get("items", []) if "at" in it]
    ground = None
    if "terrain" in doc:
        from dotbsp import terrain   # on the path whenever a converter wrote a terrain (import_bsp)
        ground = terrain.Heightfield.decode(doc["terrain"])[0]
    placed, out = [], []
    for h in hints:
        ax, ay, az = _toy_anchor(doc, h["anchor"])
        radius, height = TOY_SIZE[h["toy"]]
        found = None
        rings = 1 if h["exact"] else 21
        for ring in range(rings):
            rr = ring * 0.5
            steps = max(1, int(round(2 * math.pi * rr / 0.5))) if rr > 0 else 1
            for k in range(steps):
                a = 2 * math.pi * k / steps
                x, z = r(ax + h["dx"] + rr * math.cos(a)), r(az + h["dz"] + rr * math.sin(a))
                under = [_toy_floor(solid, px, pz, ay, ground, doc.get("terrain", {}).get("mat")) for px, pz in ((x, z), (x - radius, z - radius), (x + radius, z - radius), (x - radius, z + radius), (x + radius, z + radius))]
                if any(u is None or u[1] in TOY_NOT_FLOOR for u in under):
                    continue
                top = under[0][0]
                if any(abs(u[0] - top) > 0.06 for u in under) or abs(top - ay) > 1.5:
                    continue
                m = radius + 0.5
                clear = True
                for b, lo, hi in solid:
                    if hi[1] - lo[1] < 0.05:
                        continue
                    if lo[0] < x + m and hi[0] > x - m and lo[2] < z + m and hi[2] > z - m and lo[1] < top + height + 0.3 and hi[1] > top + 0.06:
                        clear = False
                        break
                if clear:
                    for p in doc.get("props", []):
                        sx, sy, sz = size_of(p["id"])
                        reach = max(sx, sz) / 2.0 + m
                        if abs(p["at"][0] - x) < reach and abs(p["at"][2] - z) < reach and p["at"][1] - top < 2.0 and top - p["at"][1] < sy:
                            clear = False
                            break
                if clear and not h["exact"]:
                    for o in placed:
                        if math.hypot(o["at"][0] - x, o["at"][2] - z) < radius + TOY_SIZE[o["toy"]][0] + 0.5:
                            clear = False
                            break
                if clear and any(math.hypot(q[0] - x, q[2] - z) < 1.5 and abs(q[1] - top) < 2.0 for q in keep_off):
                    clear = False
                if clear:
                    found = (x, top, z)
                    break
            if found:
                break
        if found is None:
            raise SystemExit("%s: nowhere for %s near %s%+.1f,%+.1f" % (doc["id"], h["toy"], str(h["anchor"]), h["dx"], h["dz"]))
        if h["toy"] == "_rack":
            for row in range(3):
                for i in range(row + 1):
                    pin = {"toy": "bowling_pin", "at": [r(found[0] + (i - row * 0.5) * 0.45), r(found[1]), r(found[2] - 0.4 + row * 0.4)]}
                    out.append(pin)
            placed.append({"toy": "_rack", "at": [found[0], found[1], found[2]]})
            continue
        t = {"toy": h["toy"], "at": [found[0], r(found[1]), found[2]]}
        if h["yaw"]:
            t["yaw"] = h["yaw"]
        out.append(t)
        placed.append(t)
    return out


# Each map's toys, by theme: barrels and tyres in the streets, balls where people played.
TOYS = {
    "zz_blackout_1": [toy("barrel", ("route", 2), 3, 0), toy("barrel", ("route", 2), 3.8, 0.6), toy("tyre", ("route", 4), -3, 1, yaw=30),
                      toy("football", ("route", 5), 2, -2), toy("barrel", ("route", 6), -3, 0)],
    "zz_blackout_2": [toy("barrel", ("route", 1), 3, 0), toy("tyre", ("route", 3), -3, 1, yaw=60), toy("tyre", ("route", 3), -3.8, 2.2),
                      toy("beach_ball", ("route", 5), 2, 2), toy("barrel", ("route", 6), 3, -1)],
    "zz_blackout_3": [toy("barrel", ("route", 1), -3, 0), toy("barrel", ("route", 2), 3, 0), toy("tyre", ("route", 4), 2, 2),
                      toy("football", ("route", 5), -2, 1)],
    "zz_lot": [toy("barrel", "spawn", 6, 6), toy("barrel", "spawn", 6.8, 6.6), toy("tyre", "spawn", -6, 6, yaw=40), toy("football", "spawn", 4, -6)],
    "zz_chapel": [toy("barrel", ("post", 0), 3, -2), toy("tyre", ("post", 1), 2, 2), toy("football", "spawn", 4, 4)],
    "zz_high_school": [toy("football", "spawn", 4, 2), toy("beach_ball", "spawn", -4, 3), toy("bowling_ball", ("post", 3), 0, 0),
                       toy("barrel", ("post", 6), 2, 1), toy("tyre", ("post", 9), -2, 1), toy("football", ("post", 12), 2, -2)],
    "zz_mall": [toy("bowling_ball", "spawn", 4, 0), *toy_pins("spawn", 4, -8), toy("beach_ball", ("post", 4), 3, 0),
                toy("beach_ball", ("post", 8), -3, 0), toy("football", ("post", 11), 2, 2), toy("barrel", ("post", 2), 2, -2)],
    "zz_relief_camp": [toy("barrel", "spawn", 5, 4), toy("barrel", "spawn", 5.8, 4.6), toy("tyre", ("post", 2), 3, 0, yaw=20),
                       toy("tyre", ("post", 5), -3, 0), toy("football", "spawn", -4, -4)],
    "zz_stadium": [toy("football", "spawn", 6, 4), toy("football", "spawn", -8, 6), toy("beach_ball", "spawn", 10, -4),
                   toy("barrel", ("post", 3), 2, 2), toy("tyre", ("post", 10), -2, 2)],
}


def sync_sizes():
    with open(GAME_CATALOGUE) as f:
        catalogue = json.load(f)
    sizes = {p["id"]: p["size"] for p in catalogue["props"]}
    out = {"comment": "Prop sizes copied from game-zombie-zone/props/catalogue.json by build_maps.py --sync-sizes.",
           "props": dict(sorted(sizes.items()))}
    with open(SIZES_FILE, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print("synced %d prop sizes" % len(sizes))


def render(doc):
    return json.dumps(doc, indent=1, sort_keys=False) + "\n"


def main(argv):
    if "--sync-sizes" in argv:
        sync_sizes()
        return 0

    check = "--check" in argv
    os.makedirs(MAPS, exist_ok=True)
    stale = []

    for plan in PLANS:
        doc = plan().build()
        if TOYS.get(doc["id"]):
            doc["toys"] = settle_toys(doc, TOYS[doc["id"]])
        if doc["id"] in ambient.HAND:
            doc = ambient.put(doc, ambient.normalise(ambient.HAND[doc["id"]]))
        path = os.path.join(MAPS, doc["id"] + ".json")
        text = render(doc)

        if check:
            old = open(path).read() if os.path.exists(path) else ""
            if old != text:
                stale.append(path)
            continue

        with open(path, "w") as f:
            f.write(text)
        print("%-16s %4d boxes %4d props %3d items %2d objectives  %6d bytes" % (
            doc["id"], len(doc["boxes"]), len(doc["props"]), len(doc["items"]), len(doc["objectives"]), len(text)))

    if stale:
        for path in stale:
            print("not what the builder writes: %s" % os.path.relpath(path, ROOT))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
