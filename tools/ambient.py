#!/usr/bin/env python3
"""A map's creepy-ambience field (`ambient` in maps/<id>.json), authored once, kept by regeneration.

    python3 -I tools/ambient.py            # list every map: mood, where it came from
    python3 -I tools/ambient.py --check    # fail on a document without a valid field (CI)
    python3 -I tools/ambient.py --apply    # write the field into every maps/<id>.json that lacks or differs

The field is a mood name (a string) or an object, read by game-zombie-zone's ZzAudio:

    {"mood": "swamp", "indoor": "indoor_hall", "volume": 0.8, "frequency": 1.5, "extra": "cave_tunnel"}

`mood` is what plays outdoors, `indoor` what plays under a roof (default: see ZzAudio.INDOOR_OF),
`volume` and `frequency` scale the player's and server's settings for this map (0.25 to 2, 0 to 4),
`extra` adds another mood's one-shots to this map's own. Where it comes from, first hit wins: the
spec's `"ambient"` (tools/bsp/<id>.json), `HAND` below for the hand-built maps, else the keyword vote
of the converted world's soundscape and ambient_generic names. The vote is dot-audio's own
`DotAmbienceMoods.KEYWORDS`, read from its source so the two cannot drift.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
MOODS = ("outdoor_night", "indoor_hall", "industrial", "cave_tunnel", "snow_wind", "swamp", "city_ruins", "interior_horror")
KEYS = ("mood", "indoor", "volume", "frequency", "extra")

# The hand-built maps (tools/build_maps.py writes their documents). Authored by what each is.
HAND = {
    "zz_blackout_1": {"mood": "outdoor_night", "indoor": "indoor_hall"},
    "zz_blackout_2": {"mood": "industrial", "indoor": "industrial"},
    "zz_blackout_3": {"mood": "snow_wind", "indoor": "indoor_hall", "extra": "swamp"},
    "zz_chapel": {"mood": "interior_horror", "indoor": "interior_horror", "frequency": 1.3},
    "zz_high_school": {"mood": "outdoor_night", "indoor": "indoor_hall"},
    "zz_lot": {"mood": "city_ruins", "indoor": "indoor_hall"},
    "zz_mall": {"mood": "indoor_hall", "indoor": "indoor_hall", "extra": "city_ruins"},
    "zz_relief_camp": {"mood": "outdoor_night", "indoor": "indoor_hall", "frequency": 1.2},
    "zz_stadium": {"mood": "city_ruins", "indoor": "indoor_hall"},
}


def _gd_path():
    for p in (os.environ.get("DOTAUDIO_PATH", ""), os.path.join(ROOT, "..", "dot-audio")):
        f = os.path.join(p, "addons", "dot_audio", "core", "dot_ambience_moods.gd") if p else ""
        if os.path.isfile(f):
            return f
    sys.exit("ambient: dot-audio was not found beside this repository; set DOTAUDIO_PATH")


def keywords():
    """[(mood, [word, ...])] in dot-audio's tie-break order, from DotAmbienceMoods.KEYWORDS."""
    src = open(_gd_path()).read()
    body = src.split("const KEYWORDS := [", 1)[1].split("\n]\n", 1)[0]
    table = []
    for m in re.finditer(r"\[([A-Z_]+), \[(.*?)\]\]", body):
        mood = m.group(1).lower()
        table.append((mood, re.findall(r'"([^"]*)"', m.group(2))))
    return table


def vote(names, table=None):
    """The mood most of `names` point at (dot-audio's DotAmbienceMoods.vote), or ''."""
    table = table or keywords()
    tally = {}
    for raw in names:
        text = str(raw).lower()
        for mood, words in table:
            if any(w in text for w in words):
                tally[mood] = tally.get(mood, 0) + 1
    best, most = "", 0
    for mood, _ in table:
        if tally.get(mood, 0) > most:
            best, most = mood, tally[mood]
    return best


def names_in(sounds):
    """Soundscape names, and the message and stand-in of each ambient sound (DotAmbienceMoods.names_in)."""
    out = [str(r.get("soundscape", "")) for r in sounds.get("soundscapes", []) if isinstance(r, dict)]
    for r in sounds.get("ambient", []):
        if isinstance(r, dict):
            out += [str(r.get("message", "")), str(r.get("stand_in", ""))]
    return out


def normalise(field):
    """A field in its smallest valid form (a bare mood stays a string); raises ValueError otherwise."""
    if isinstance(field, str):
        field = {"mood": field}
    if not isinstance(field, dict) or field.get("mood") not in MOODS:
        raise ValueError("ambient needs a mood of %s" % ", ".join(MOODS))
    out = {}
    for k in KEYS:
        if k not in field:
            continue
        v = field[k]
        if k in ("mood", "indoor", "extra"):
            if v not in MOODS:
                raise ValueError("ambient %s '%s' is not a mood" % (k, v))
        elif k == "volume":
            v = round(min(max(float(v), 0.25), 2.0), 3)
        else:
            v = round(min(max(float(v), 0.0), 4.0), 3)
        out[k] = v
    extra = set(field) - set(KEYS)
    if extra:
        raise ValueError("ambient has unknown keys: %s" % ", ".join(sorted(extra)))
    return out["mood"] if list(out) == ["mood"] else out


def world_sounds(map_id, root=ROOT):
    path = os.path.join(root, "world", "zz_world_" + map_id, map_id + ".json")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f).get("sounds", {})


def resolve(map_id, spec=None, root=ROOT):
    """(field, source) for a map: the spec's own, the hand table, the world's sound-name vote, or (None, '')."""
    if spec and spec.get("ambient"):
        return normalise(spec["ambient"]), "spec"
    if map_id in HAND:
        return normalise(HAND[map_id]), "hand table"
    mood = vote(names_in(world_sounds(map_id, root)))
    if mood:
        return normalise(mood), "sound names"
    return None, ""


def put(doc, field):
    """`doc` with `ambient` right after `environment`, replacing any earlier one; key order is the file's."""
    out = {}
    for k, v in doc.items():
        if k == "ambient":
            continue
        out[k] = v
        if k == "environment":
            out["ambient"] = field
    if "ambient" not in out:
        out["ambient"] = field
    return out


def _spec(map_id):
    path = os.path.join(HERE, "bsp", map_id + ".json")
    return json.load(open(path)) if os.path.isfile(path) else None


def main(argv):
    check, apply_ = "--check" in argv, "--apply" in argv
    bad = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "maps", "*.json"))):
        with open(path) as f:
            doc = json.load(f)
        try:
            field, why = resolve(doc["id"], _spec(doc["id"]))
            have = doc.get("ambient")
            if have is not None:
                normalise(have)
        except ValueError as e:
            print("%s: %s" % (doc["id"], e))
            bad += 1
            continue
        if have is None and field is None:
            print("%-26s no ambient (no spec field, no sounds to vote)" % doc["id"])
            bad += 1
        elif apply_ and field is not None and have != field:
            with open(path, "w") as f:
                json.dump(put(doc, field), f, indent=1)
                f.write("\n")
            print("%-26s %s  (%s)" % (doc["id"], json.dumps(field), why))
        elif check and have is None:
            print("%-26s missing ambient" % doc["id"])
            bad += 1
        elif not check and not apply_:
            print("%-26s %s  (%s)" % (doc["id"], json.dumps(have if have is not None else field), "document" if have is not None else why))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
