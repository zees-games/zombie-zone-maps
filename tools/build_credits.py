"""Write CREDITS.md: author, page and licence of every map in tools/convert/ship.tsv, from its spec.

    python3 -I tools/build_credits.py

Flags what the licence does not clearly allow, so the person who publishes sees it.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = {"roy": "CC BY-NC-ND 4.0, the author's page forbids derivatives: shipped as a conversion on the same footing as the rest, but the first to remove if asked"}


def main():
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(HERE, "convert", "ship.tsv")) if not l.startswith("#")]
    out = ["# Credits", "",
           "Every map here is a conversion of a community map: the author is credited with a link, no texture or model of the original ships (materials and props are the game's own, CC0 or generated), and a map is removed on its author's request. Maps whose licence does not allow redistribution are not shipped (see `tools/convert/excluded.txt`).", "",
           "| Map | Author | Page | Licence | Note |", "| --- | --- | --- | --- | --- |"]
    for mid, _key in sorted(rows):
        s = json.load(open(os.path.join(HERE, "bsp", mid + ".json")))
        note = next((v for k, v in FLAGS.items() if k in mid.split("_")), "")
        out.append("| `%s` %s | %s | %s | %s | %s |" % (mid, s["name"], s["author"], s["page"], s["licence"], note))
    with open(os.path.join(HERE, "..", "CREDITS.md"), "w") as f:
        f.write("\n".join(out) + "\n")


main()
