"""Fails when a drawn world's manifest is unreadable or disagrees with its .bin, its map document or itself.

    python3 -I tools/check_worlds.py [world_root]

Every `world/zz_world_<id>/<id>.json` must parse, be a `dot-bsp-mesh` v1 with the entity sections
tools/build_worlds.py writes, name a .bin whose stored sha256 matches, belong to a document that
names it, and every mover must have the model its game animates (surfaces, and hulls when it is
carried solid). Runs on the committed files alone, so CI needs no source map.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SECTIONS = ("movers", "volumes", "links", "entities")
CARRIED = {"slide", "rotate", "plat", "path"}


def check(pack_dir):
    """The problems found in one world directory, as strings."""
    pack = os.path.basename(pack_dir)
    map_id = pack[len("zz_world_"):]
    bad = []
    path = os.path.join(pack_dir, map_id + ".json")
    try:
        with open(path) as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        return ["%s: does not parse: %s" % (path, e)]
    if m.get("format") != "dot-bsp-mesh" or m.get("version") != 1:
        bad.append("%s: not a dot-bsp-mesh v1" % pack)
    for k in SECTIONS:
        if not isinstance(m.get(k), list):
            bad.append("%s: no '%s' list (rebuild with tools/build_worlds.py)" % (pack, k))
    if not isinstance(m.get("destinations"), dict):
        bad.append("%s: no 'destinations' table" % pack)
    if bad:
        return bad
    try:
        with open(os.path.join(pack_dir, m["bin"]["file"]), "rb") as f:
            stored = f.read()
        if hashlib.sha256(stored).hexdigest() != m["bin"]["sha256"] or len(stored) != m["bin"]["stored_bytes"]:
            bad.append("%s: the .bin is not the one the manifest describes" % pack)
    except (OSError, KeyError) as e:
        bad.append("%s: no .bin: %s" % (pack, e))
    if not isinstance(m.get("zz", {}).get("materials"), dict):
        bad.append("%s: no zz.materials" % pack)
    drawn = {s["model"] for s in m["surfaces"]}
    hulled = {h["model"] for h in m["hulls"]}
    for r in m["movers"]:
        who = "%s mover %s (%s)" % (pack, r.get("targetname") or r["entity"], r["kind"])
        if r.get("model") is None or (r["model"] not in drawn and r["model"] not in hulled):
            bad.append("%s: its model has neither surfaces nor hulls" % who)
        elif r["kind"] in CARRIED and r.get("solid", True) and r["model"] not in hulled:
            bad.append("%s: solid but has no hull" % who)
        for k in ("origin", "mins", "maxs"):
            if len(r.get(k, [])) != 3:
                bad.append("%s: no %s" % (who, k))
    for rec in m["links"]:
        for k in ("from", "output", "input", "target", "delay"):
            if k not in rec:
                bad.append("%s: a link has no '%s'" % (pack, k))
                break
    docp = os.path.join(HERE, "..", "maps", map_id + ".json")
    if os.path.isfile(docp):
        with open(docp) as f:
            if json.load(f).get("world") != pack:
                bad.append("%s: maps/%s.json does not name it" % (pack, map_id))
    return bad


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.join(HERE, "..", "world")
    dirs = sorted(d for d in os.listdir(root) if d.startswith("zz_world_"))
    bad = []
    for d in dirs:
        bad += check(os.path.join(root, d))
    for line in bad:
        print("FAIL " + line)
    print("%d worlds, %d problems" % (len(dirs), len(bad)))
    return 1 if bad or not dirs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
