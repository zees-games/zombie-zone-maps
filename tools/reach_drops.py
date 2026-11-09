#!/usr/bin/env python3
"""Drop the spawns the horde's graph cannot connect to the rest of the map (data-level, not a runtime filter).

tools/reach_drops.json lists, per map id, the survivor spawns ("survivors") and zombie spawns ("zombies") that
game-zombie-zone's `spot_probe --survival --reach` reports as unreachable (island ground with no walkable join to a
post or to the other spawns). Coordinates are matched to the document within 0.06 m. Run it after every
re-conversion (import_bsp.py rewrites the document from the source); `--check` fails when a listed spawn is still there.
Only maps where dropping leaves the team seats (`survivors`) and a horde standing are listed: a map whose whole set is
on islands stays a build/import problem (stairs, ladders, teleports), not something to delete.
    tools/reach_drops.py [--check] [map ...]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAPS = os.path.join(HERE, "..", "maps")


def _near(a, b):
    return all(abs(float(x) - float(y)) <= 0.06 for x, y in zip(a, b))


def apply(doc, want):
    sv = doc["spawns"]["survivors"]
    keep = [s for s in sv if not any(_near(s["at"] if isinstance(s, dict) else s, w) for w in want.get("survivors", []))]
    gone = {"survivors": len(sv) - len(keep)}
    doc["spawns"]["survivors"] = keep
    zs = doc["zombie_spawns"]
    keep = [z for z in zs if not any(_near(z, w) for w in want.get("zombies", []))]
    gone["zombies"] = len(zs) - len(keep)
    doc["zombie_spawns"] = keep
    return gone


def main(argv):
    check = "--check" in argv
    ids = [a for a in argv if not a.startswith("--")]
    rules = json.load(open(os.path.join(HERE, "reach_drops.json")))["maps"]
    bad = 0
    for mid, want in rules.items():
        if ids and mid not in ids:
            continue
        path = os.path.join(MAPS, mid + ".json")
        text = open(path).read()
        doc = json.loads(text)
        gone = apply(doc, want)
        if check:
            if gone["survivors"] or gone["zombies"]:
                print("%s: %d survivor and %d zombie spawns still listed in reach_drops.json" % (mid, gone["survivors"], gone["zombies"]))
                bad += 1
            continue
        if gone["survivors"] or gone["zombies"]:
            open(path, "w").write(json.dumps(doc, indent=1, ensure_ascii=False) + ("\n" if text.endswith("\n") else ""))
        print("%s: dropped %d survivor, %d zombie spawns" % (mid, gone["survivors"], gone["zombies"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
