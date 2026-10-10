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
    def __init__(self, x0, z0, x1, z1, floor, height, indoor=False, wall="brick", tint=None, rail=0.0, nav=True):
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

    def contains(self, x, z):
        return self.x0 <= x < self.x1 and self.z0 <= z < self.z1


class Map:
    def __init__(self, mid, name, blurb, mode, environment, next_map="", survive_seconds=0.0):
        self.doc = {
            "format": 1, "kind": "zombiezone_map", "id": mid, "name": name, "author": AUTHOR,
            "blurb": blurb, "mode": mode, "environment": environment, "kill_y": -20.0,
        }
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

    def door(self, x0, z0, x1, z1, floor="tile", gate=None, gate_mat="metal", gate_tint=None):
        """A doorway across a half-metre gap. With `gate`, a door an objective opens."""
        reg = self.region(x0, z0, x1, z1, floor, DOOR_H, indoor=True, wall="plaster")
        reg.door = True
        if gate:
            box = {"at": [r((x0 + x1) / 2), DOOR_H / 2, r((z0 + z1) / 2)], "size": [r(x1 - x0), DOOR_H, r(z1 - z0)],
                   "mat": gate_mat, "gate": gate}
            if gate_tint:
                box["tint"] = gate_tint
            self.boxes.append(box)
        return reg

    def gate(self, gid, x0, z0, x1, z1, height=3.0, mat="metal", tint=None):
        """A gate across open ground (a fence, a shutter) that an objective opens."""
        box = {"at": [r((x0 + x1) / 2), height / 2, r((z0 + z1) / 2)], "size": [r(x1 - x0), height, r(z1 - z0)],
               "mat": mat, "gate": gid}
        if tint:
            box["tint"] = tint
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

    def objective(self, oid, kind, x, y, z, label, seconds=2.0, holdout=0.0, opens=(), message="", radius=2.0):
        o = {"id": oid, "kind": kind, "at": [r(x), r(y), r(z)], "label": label, "seconds": seconds,
             "holdout": holdout, "opens": list(opens), "message": message}
        if kind == "reach":
            o["radius"] = radius
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

        def key(reg):
            return (reg.wall, tuple(reg.tint) if reg.tint else None, reg.height if not reg.rail else -reg.rail, reg.indoor)

        boxes = []
        # Edges along x (a wall facing -z or +z), then along z.
        for direction in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            dx, dz = direction
            along_x = dx == 0
            outer = range(nz) if along_x else range(nx)
            for line in outer:
                run = None
                for step in list(range(nx if along_x else nz)) + [None]:
                    reg = None
                    if step is not None:
                        i, k = (step, line) if along_x else (line, step)
                        here = at(i, k)
                        if here is not None and at(i + dx, k + dz) is None:
                            reg = here
                    if run is not None and (reg is None or key(reg) != key(run[0])):
                        boxes.append(self._wall_box(run, along_x, line, direction, gx0, gz0, at))
                        run = None
                    if reg is not None:
                        if run is None:
                            run = [reg, step, step]
                        else:
                            run[2] = step
        # Over every doorway, up to the taller side.
        for reg in self.regions:
            if reg.door:
                top = DOOR_H
                for other in self.regions:
                    if other is not reg and not other.door and self._touches(reg, other):
                        top = max(top, other.height if not other.rail else 0.0)
                if top > DOOR_H:
                    boxes.append({"at": [r((reg.x0 + reg.x1) / 2), r((DOOR_H + top) / 2), r((reg.z0 + reg.z1) / 2)],
                                  "size": [r(reg.x1 - reg.x0 + 0.02), r(top - DOOR_H), r(reg.z1 - reg.z0 + 0.02)], "mat": "brick"})
        return boxes

    @staticmethod
    def _touches(a, b):
        return a.x0 <= b.x1 and b.x0 <= a.x1 and a.z0 <= b.z1 and b.z0 <= a.z1

    def _wall_box(self, run, along_x, line, direction, gx0, gz0, at):
        reg, first, last = run
        dx, dz = direction
        height = reg.rail if reg.rail else reg.height
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
        box["mat"] = "wood" if reg.rail else reg.wall
        if reg.tint:
            box["tint"] = reg.tint
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

        doc = dict(self.doc)
        doc.update({
            "boxes": boxes,
            "props": self.props,
            "lights": self.lights,
            "spawns": {"survivors": self.spawns},
            "areas": self.areas,
            "route": self.route,
            "nav": {"spacing": 1.0, "clearance": 0.35, "floors": floors, "links": self.links},
            "items": self.items,
            "objectives": self.objectives,
            "sleepers": self.sleepers,
            "zombie_spawns": self.zombie_spawns,
        })
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
            "campaign", NIGHT, next_map="zz_blackout_2")
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
    m.gate("fence", 18.0, 60.0, 18.4, 72.5, 3.2, "metal", [0.55, 0.58, 0.6])
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
    m.item("weapon", -19.0, 0.0, 21.0, "battle_rifle")
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
                opens=["fence"], message="The lock is screaming. Here they come — hold on!")
    m.item("ammo", 14.0, 0.0, 61.0)
    m.item("throwable", 14.5, 0.0, 61.0, "pipe")
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
            "campaign", NIGHT, next_map="zz_blackout_3")
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
    m.item("weapon", 9.5, 0.0, 43.0, "drum_shotgun")
    m.item("medkit", -9.5, 0.0, 66.0)
    m.item("throwable", 0.0, 0.0, 74.0, "frag")
    m.item("box", 18.0, 0.0, 47.0, "explosive")
    m.objective("shutter", "use", 6.0, 1.0, 79.2, "Raise the loading shutter", seconds=2.5, holdout=45.0,
                opens=["shutter"], message="The motor is grinding. Everything heard that.")

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
            "campaign", DUSK)
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

    m.item("weapon", -22.0, 0.0, 38.5, "carbine")
    m.item("box", 22.0, 0.0, 34.0, "medical")
    m.item("box", 0.0, 0.0, 50.0)
    m.item("ammo", 2.5, 0.0, 95.0)
    m.item("ammo", -2.5, 0.0, 95.0)
    m.item("throwable", 2.5, 0.0, 92.0, "molotov")
    m.item("medkit", -2.5, 0.0, 92.0)
    m.objective("radio", "use", 0.0, 1.0, 98.5, "Radio the boat", seconds=3.0, holdout=90.0,
                opens=["boat"], message="They heard you. Ninety seconds — hold the pier!")

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
                            (0.0, 27.0, "weapon", "battle_rifle"), (-27.0, 8.0, "throwable", "pipe"),
                            (27.0, -8.0, "throwable", "molotov"), (-10.0, 25.0, "medkit", None)):
        m.item(kind, x, 0.0, z, iid)

    m.path((0, 0))
    for x, z in ((-29, -29), (29, -29), (-29, 29), (29, 29), (0, -29), (0, 29), (-29, 0), (29, 0)):
        m.hint(x, z)
    return m


def chapel():
    m = Map("zz_chapel", "Chapel Yard", "A graveyard in fog and a chapel with two doors. Six minutes.",
            "survival", FOG_NIGHT, survive_seconds=360.0)
    rng = random.Random(505)

    m.region(-28, -28, 28, 28, floor="grass", height=3.0, wall="stone", tint=[0.6, 0.62, 0.6])
    m.door(-1, -8.5, 1, -8, floor="wood_floor")
    m.door(-1, 8, 1, 8.5, floor="wood_floor")
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
                            (-25.0, 25.0, "ammo", None), (25.0, 0.0, "ammo", None), (-25.0, 0.0, "weapon", "carbine"),
                            (0.0, 25.0, "throwable", "molotov"), (0.0, -25.0, "throwable", "pipe")):
        m.item(kind, x, 0.0, z, iid)
    m.sleeper(-22.0, -4.0, 90)
    m.sleeper(22.0, 4.0, 270)

    m.path((0, 0))
    for x, z in ((-27, -27), (27, -27), (-27, 27), (27, 27), (0, -27), (0, 27), (-27, 0), (27, 0)):
        m.hint(x, z)
    return m


PLANS = (blackout_1, blackout_2, blackout_3, lot, chapel)


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
