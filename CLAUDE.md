# zombie-zone-maps

The maps game-zombie-zone plays, as JSON documents. Read `../../CLAUDE.md` and `../game-zombie-zone/CLAUDE.md` first: the format is defined and validated by game-zombie-zone's `game/zz_map_doc.gd`, and `maps/README.md` is the mapper's copy of it.

**`maps/` is what the game reads**, through a dot-bootstrap link (`game-zombie-zone/.gitignore` names it). The game reads every `.json` there plus the practice street built into it; a refused document is listed by `zz_maps` with the reason, and every other map still plays.

**`tools/build_maps.py` writes every document, and the JSON is committed.** Edit the builder, run it, commit both. `--check` (CI) fails when a committed file differs from what the builder writes.

## A map is regions, and everything else follows from them

mg-prop-hunt-maps' builder places walls with their holes, one call per wall. This one does not, because a zombie map has a second floor plan that must agree with the first: the ground the zombies walk (`nav.floors`). Two lists kept by hand drift — a wall moved and a nav floor not is a zombie walking through the wall, and a doorway one floor short of the next room is a safe room no zombie ever enters. So a map here is a list of **regions** (rectangles a person can stand in) and the builder derives both from them: the floor, a wall on every edge of their union that faces nothing (`Map._walls`, found on a half-metre grid and merged into runs), a ceiling over an indoor region, and the nav floors, which are the regions.

- **Keep two regions that should not join half a metre apart**, and the gap fills with wall from both sides. A **door** is a region across that gap (`Map.door`); the builder puts a lintel over it up to the taller neighbour and stretches its nav floor 0.6 m into the rooms either side, because a door's own floor is half a metre deep and the graph would not cross it otherwise.
- **A wall reaches past a convex corner** by its own thickness so two walls meet, and never into ground somebody stands on (that is the L-shaped corner case; the extension is skipped where the next cell along the run is walkable).
- **A railing is a region with `rail=`**: the edges that face nothing are a 1.3 m wooden rail instead of a wall. 1.3 because a survivor jumps a metre; the pier is over water, and kill_y is below it.
- **Every region corner is on the half-metre grid**, and the builder stops on one that is not.

## What `headless_maps` asks of every map

game-zombie-zone's `examples/headless_maps.tscn` builds each map the way a server does and checks ten things, the zombie half being the one a render cannot show: from the first spawn, the zombies' ground (with every gate open) reaches every route point, objective, sleeper, spawn hint and the end area; with the gates shut, the end area is cut off. Run it after any change here.

**It found the builder's first bug on its first run**: the door floor was stretched along the door's long side instead of across the gap, so the laundromat, the warehouse and both maps' end rooms were islands the horde could never enter. The start rooms joined by luck (their floors were within the dedupe distance of the street's). Both gates and the far rooms were "reachable" only once the stretch was across the gap.

## Weapons the maps name that the server may not have

`molotov` and `pipe` are named as throwables. zee-dot-weapons has neither (its throwables are `frag` and `sticky`), so today the game draws a random throwable in their place (`ZzLoot.place_from_map`); a second weapon pack that defines them makes them real with no change here.

## Publishing

**This repository is a pack of its own, mounted on the server alone.** A server owner names it in their deployment's map config (dot-server-deploy's `cfg/content.yml`), and the game adds that mount's `maps/` to its catalogue. It is never in a client's content sync: a client is sent the one document being played. `.github/workflows/release.yml` runs `build_maps.py --check` and then dot-ci's release with `pack: true`.

**Not yet on GitHub** (2026-10-10): the remote is set, the repository is the owner's to create, and nothing is pushed or published.
