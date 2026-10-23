"""The zombies' graph, worked out the way game-zombie-zone builds it, so the importer can say what
the game will reach before the game is run.

game-zombie-zone's `ZzNpcs.nav_for` hands each nav floor and each solid box to dot-npc's
`DotNpcNavBuilder`: a point every `spacing` metres inside a floor rectangle (the first half a
spacing in), dropped when it is within `clearance` of an obstacle, two points within half a spacing
at the same height are one, and two points within one and a half spacings join unless a sample
half a spacing along the line is inside an obstacle. A doorway a metre wide has no point in it, so
the room behind it is an island whatever a cell flood over the same boxes says. This is that
algorithm, in Python, with the same numbers; keep it in step with dot_npc_nav_builder.gd.
"""

import math


def _bounds(box):
    sx, sy, sz = box["size"]
    at = box["at"]
    yaw = math.radians(box.get("yaw", 0.0) or 0.0)
    if yaw:
        c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
        ex, ez = c * sx / 2 + s * sz / 2, s * sx / 2 + c * sz / 2
    else:
        ex, ez = sx / 2, sz / 2
    return [at[0] - ex, at[1] - sy / 2, at[2] - ez, at[0] + ex, at[1] + sy / 2, at[2] + ez]


def _is_floor(b, floors):
    top = b[4]
    for f in floors:
        if abs(top - f[4]) > 0.12:
            continue
        if b[0] < f[2] and b[3] > f[0] and b[2] < f[3] and b[5] > f[1]:
            return True
    return False


class Graph:
    def __init__(self, boxes, props, sizes, floors, spacing=1.0, clearance=0.35, terrain_pts=(), slope=1.0):
        """`terrain_pts`: the terrain's walk points (dotbsp.terrain.walk_points), joined by `slope`
        rise per metre as DotNpcNavBuilder.add_points joins them."""
        self.spacing, self.clearance = spacing, clearance
        obs = []
        for box in boxes:
            if not box.get("solid", True) or box.get("gate") or ("nav" in box and not box["nav"]):
                continue
            b = _bounds(box)
            if "nav" not in box and _is_floor(b, floors):
                continue
            obs.append(b)
        for p in props:
            sx, sy, sz = sizes[p["id"]]
            if sy < 0.5:
                continue
            yaw = math.radians(p.get("yaw", 0.0))
            c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
            ex, ez = c * sx / 2 + s * sz / 2, s * sx / 2 + c * sz / 2
            at = p["at"]
            obs.append([at[0] - ex, at[1], at[2] - ez, at[0] + ex, at[1] + sy, at[2] + ez])
        g = clearance
        self.obs = [[b[0] - g, b[1] - g, b[2] - g, b[3] + g, b[4] + g, b[5] + g] for b in obs]
        self.cells = {}
        for i, b in enumerate(self.obs):
            for ix in range(int(math.floor(b[0] / 4)), int(math.floor(b[3] / 4)) + 1):
                for iz in range(int(math.floor(b[2] / 4)), int(math.floor(b[5] / 4)) + 1):
                    self.cells.setdefault((ix, iz), []).append(i)
        self.pts = []
        self.slopes = []
        seen = {}

        def place(px, h, pz, slope_):
            if self.blocked(px, h, pz):
                return
            ck = (int(math.floor(px / spacing)), int(math.floor(pz / spacing)))
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in seen.get((ck[0] + dx, ck[1] + dz), ()):
                        q = self.pts[j]
                        if abs(q[1] - h) <= spacing * 0.5 and math.hypot(q[0] - px, q[2] - pz) < spacing * 0.5:
                            return
            seen.setdefault(ck, []).append(len(self.pts))
            self.pts.append((px, h, pz))
            self.slopes.append(slope_)

        for f in floors:
            h = f[4]
            x = f[0] + spacing * 0.5
            while x < f[2]:
                z = f[1] + spacing * 0.5
                while z < f[3]:
                    place(x, h, z, 0.0)
                    z += spacing
                x += spacing
        for p in terrain_pts:
            place(p[0], p[1], p[2], slope)
        self.parent = list(range(len(self.pts)))
        reach = spacing * 1.5
        near = {}
        for i, p in enumerate(self.pts):
            near.setdefault((int(math.floor(p[0] / reach)), int(math.floor(p[2] / reach))), []).append(i)
        self.near = near
        for i, p in enumerate(self.pts):
            hx, hz = int(math.floor(p[0] / reach)), int(math.floor(p[2] / reach))
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in near.get((hx + dx, hz + dz), ()):
                        if j <= i:
                            continue
                        # Exactly 1.5 apart is a coin toss in the game's float32, so it is not an edge here: a
                        # pair joined only by that toss is bridged by a real link instead.
                        q = self.pts[j]
                        sl = min(self.slopes[i], self.slopes[j])
                        rise = sl * math.hypot(p[0] - q[0], p[2] - q[2]) if sl > 0 else spacing * 0.5
                        if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 > reach * reach - 1e-3 or abs(p[1] - q[1]) > rise:
                            continue
                        if not self.crosses(p, q):
                            self.union(i, j)

    def blocked(self, x, y, z):
        for i in self.cells.get((int(math.floor(x / 4)), int(math.floor(z / 4))), ()):
            b = self.obs[i]
            if b[0] <= x <= b[3] and b[1] <= y <= b[4] and b[2] <= z <= b[5]:
                return True
        return False

    def crosses(self, a, b):
        d = math.dist(a, b)
        steps = max(int(d / max(self.spacing * 0.5, 0.1)), 1)
        for k in range(1, steps):
            t = k / steps
            if self.blocked(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t):
                return True
        return False

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i, j):
        a, b = self.find(i), self.find(j)
        if a != b:
            self.parent[b] = a

    def nearest(self, x, y, z, radius, flat=False):
        """The nearest point within radius (3-D, or on the ground plane when flat), as the game finds it."""
        best, bd = -1, radius * radius
        for i, p in enumerate(self.pts):
            if abs(p[0] - x) > radius or abs(p[2] - z) > radius:
                continue
            d = (p[0] - x) ** 2 + (p[2] - z) ** 2 + (0 if flat else (p[1] - y) ** 2)
            if d <= bd:
                best, bd = i, d
        return best
