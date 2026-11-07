#!/usr/bin/env python3
"""Per-map light grade for lightmapped converted worlds, kept by regeneration.

    python3 -I tools/look.py            # write the grade into maps/<id>.json and world/zz_world_<id>/<id>.json
    python3 -I tools/look.py --check    # fail when a committed file differs from the grade (CI)

A converted map is drawn from its author's own baked lightmap, which the converter writes at
exposure 1.0 and the game then lifts every surface to a mean light of 0.6 (`--zz-light-floor`,
the family's default for dark maps). Day-lit sources (the Abandoned Mall, 4-Way Tunnel) read as one
flat pale colour under that: no shadow can fall below the floor. `LOOK` sets, per map:

  light_floor      the map document's top-level `light_floor` (read by game-zombie-zone's ZzMap; it only
                   ever lowers the player's setting): the least mean light a lit surface gets.
  lightmap_scale   `lightmap.scale` of the world manifest (the lightmapped shader's exposure).
  flat_floor       False sets `lightmap.ambient.count` to 0. dot-map lights every surface with
                   max(baked light, the mean sky-facing ambient cube of the whole map), so a map whose
                   ambient cubes are brighter than most of its bake (the mall: mean 0.15, bake median
                   0.08) is lit by that one number nearly everywhere and shows no shadow at all. Without
                   the cubes the floor is the game's `light_floor`. The cubes also light actors
                   (DotMapLitWorld); without them an actor takes the document's `environment` ambient.

A re-conversion or `build_worlds.py` rewrites both files; run this afterwards.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

LOOK = {
    "zm_abandoned_mall": {"light_floor": 0.08, "lightmap_scale": 1.2, "flat_floor": False},
    "zm_4way_tunnel": {"light_floor": 0.1, "lightmap_scale": 2.0, "flat_floor": False},
}


def doc_text(id_, grade):
    path = os.path.join(ROOT, "maps", id_ + ".json")
    text = open(path).read()
    line = ' "light_floor": %s,\n' % repr(float(grade["light_floor"]))
    if re.search(r'^ "light_floor": .*\n', text, re.M):
        return path, re.sub(r'^ "light_floor": .*\n', line.replace("\\", "\\\\"), text, count=1, flags=re.M)
    return path, re.sub(r'^( "kill_y": .*\n)', lambda m: m.group(1) + line, text, count=1, flags=re.M)


def world_text(id_, grade):
    path = os.path.join(ROOT, "world", "zz_world_" + id_, id_ + ".json")
    data = json.load(open(path))
    data["lightmap"]["scale"] = float(grade["lightmap_scale"])
    if grade.get("flat_floor") is False:
        data["lightmap"]["ambient"]["count"] = 0
    return path, json.dumps(data, indent=1, sort_keys=True) + "\n"


def main():
    check = "--check" in sys.argv
    bad = 0
    for id_, grade in LOOK.items():
        for path, text in (doc_text(id_, grade), world_text(id_, grade)):
            if open(path).read() == text:
                continue
            if check:
                print("%s: differs from tools/look.py" % os.path.relpath(path, ROOT))
                bad += 1
            else:
                open(path, "w").write(text)
                print("wrote", os.path.relpath(path, ROOT))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
