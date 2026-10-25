#!/usr/bin/env python3
"""Whether a free camera stands in open space of a converted map, and what it sees first.

    python3 -I tools/camera_free.py <id> x,y,z[:lx,ly,lz] ...

A point inside a solid box of the document or of its server nav extra (maps/hulls/<id>.nav.json) is
"INSIDE"; for a point with a look target, the distance along the line to the first solid box is
printed, so a frame from "inside a wall" or looking at a surface a hand away is caught before it is
rendered. Boxes only (the hulls of a dropped ceiling are not read): a point under a dropped roof
slab reads free here.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import completeness  # noqa: E402


def load(map_id):
    doc = json.load(open(os.path.join(HERE, "..", "maps", map_id + ".json")))
    boxes = [b for b in doc["boxes"] if b.get("visible", True)]
    nav = os.path.join(HERE, "..", "maps", "hulls", map_id + ".nav.json")
    if os.path.exists(nav):
        boxes += [b for b in json.load(open(nav)).get("boxes", []) if b.get("visible", True)]
    return boxes


def main(argv):
    boxes = load(argv[1])
    g = completeness._grid(boxes)
    bad = 0
    for arg in argv[2:]:
        p, _, look = arg.partition(":")
        p = [float(v) for v in p.split(",")]
        inside = completeness._on_box(p, boxes, g)
        line = "%s %s" % (p, "INSIDE a box" if inside else "free")
        if look:
            q = [float(v) for v in look.split(",")]
            d = math.dist(p, q)
            hit = None
            t = 0.0
            while t <= d:
                s = [p[k] + (q[k] - p[k]) * t / d for k in range(3)]
                if completeness._on_box(s, boxes, g):
                    hit = t
                    break
                t += 0.25
            line += ", first box %s of %.0f m to the target" % ("%.1f m" % hit if hit is not None else "none", d)
        bad += inside
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
