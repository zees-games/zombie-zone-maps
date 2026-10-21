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

## Survival maps: facades, barricades, posts, caches

- **A building has a facade** (`room(..., facade=, facade_tint=)`): the outdoor region's wall facing it across the gap takes the building's face, height and colour, not the car park's fence (`_walls`' `face`, looking past the gap between two rooms too, or each room gap was a slot of fence). Opt-in, so the street maps are byte-for-byte what they were. An opening in a facade gets a two-half lintel (wall inside, facade outside) and a facade building a `roof` over its ceiling.
- **A barricade is `door(..., barricade=id, label=, strength=, boards=)`** across the gap: `window` planks to 1.5 m (the team shoots over; use it wherever the team must see the horde: the mall's entrances, the ballpark's tunnels, the camp's gates, which were steel shutters nobody could shoot through), `door` planks to the lintel, `shutter` steel. Its boxes are `"nav": false` so the horde paths into it.
- **`post`, `cache`, `survivors=`, `day=`** on every big survival map; `wall_lamp` over windows and doors outside, or a horde at the boards is invisible at night.
- Big maps take `spacing=1.25`–`1.5` (fifteen to eighteen thousand nav points; build 1–2 s at map start) and stay under 10 KB on the wire.
- `fabric` and `rubber` have a red base under a tint: coloured canvas and seats are `paint` or `flat`.
- **Every door on a survival map gets a nav link through it** (`survival_links`): the graph drops a door's own points within half a spacing of a room's, and the school's gym doors lost all theirs, so the hallway reached the gym round the outside (`headless_maps` now fails a post reached the long way round). The street maps are left without, byte-for-byte.
- **Nothing across a doorway at body height** (a board, a sign, a shelf): the floor plan does not know about it and a stand-in stands against it.

## What `headless_maps` asks of every map

game-zombie-zone's `examples/headless_maps.tscn` builds each map the way a server does and checks twelve things, the zombie half being the one a render cannot show: from the first spawn, the zombies' ground (with every gate open) reaches every route point, objective, sleeper, spawn hint and the end area; with the gates shut, the end area is cut off. Run it after any change here.

**It found the builder's first bug on its first run**: the door floor was stretched along the door's long side instead of across the gap, so the laundromat, the warehouse and both maps' end rooms were islands the horde could never enter. The start rooms joined by luck (their floors were within the dedupe distance of the street's). Both gates and the far rooms were "reachable" only once the stretch was across the gap.

## Converted Source maps (`tools/import_bsp.py`)

**Reading the map and cutting brushes into boxes are dot-map's** (`dot-map/tools/bsp`, see its README): this importer is the game's adapter on top, deciding what an entity and a material mean here. A reader or box fix goes into dot-map, where every converting game gets it; re-convert the maps after one and diff. `zs_ravenstreet.json` was left as converted on 2026-10-17 when the rest moved to the shared tool, because its committed lightmap is hashed against the document and the re-conversion differed by one box by 1 mm: re-convert it with its next bake.

**The importer must agree with the game's graph, not with its own cell flood.** `tools/nav_emulate.py` is dot-npc's `DotNpcNavBuilder` in Python (a point a metre apart, dropped within 0.35 m of an obstacle): a doorway a metre wide has no point in it, so a room the cell flood reached was an island to the horde (Raven Street's posts and caches failed `headless_maps` that way). Keep it in step with the builder. Posts go inside the houses (`post_region` in the spec) because posts on an open street leave the choke finder nothing to find. `drop_lids`/`drop_decor` remove the sky lid and distant scenery, whose walkable tops took the annotator's random routes off the ground; `roadblocks` pinch an open street so it has chokes (`headless_nav` fails a map with none on the horde's routes); `spawn_z_max` drops spawns pressed against a wall. Textures are never the author's; props map to Kenney ids by name (`prop_models`). A brush's surface comes from dot-map's shared `tools/bsp/dotbsp/source_textures.tsv` (a new texture goes there, never in this repository; `bsp.py unmapped <bsp>` lists what it misses); the importer's `GAME_MATERIAL` turns the list's generic ids into this game's (`wood_planks` is `wood`, `plaster_painted` is `paint`) and `OVERRIDES` keeps the two it knew better (road, pavement, glass). The list's tints are not used.

**Stairs made of clip slabs** (Pathogen): `clip_underlay` leaves an invisible slab lying 0.02 to 0.4 m under a floor out of the graph (it grows the clearance upward and left the whole ground floor without a point), and `keep_treads` keeps the small boxes that are stair treads (a neighbour within 6 cm whose top differs by 0.1 to 0.45 m) past `drop_small` and out of the graph, so the stairs stay solid for bodies and the flights still join the levels. Together with `flood_step` 0.55, `link_dy` 1.0 and `nav_min_depth` 1 they lift the share of the original's own navigation area that the horde's main ground covers from 43.6% to 53.9%; the rest of the lab (the roof level's steepest flights, slope 0.66 against the graph's 0.5) is still apart.

**The flood samples a cell's centre, so a wall thinner than a cell is invisible to it** (Run For Your Life's dividers are 2 cm): the route, items and zombie hints were put on the far side of walls the body cannot pass, and `headless_maps` found the zombies' ground cut. A spec opts in with `thin_walls` (Run For Your Life); Nuke's route was authored against the old flood and its panes of glass and clip slivers would seal it, so it is left off until redone. Items and `zombie_start` points must be inside the walls' rooms, and `headless_maps` checks them against the graph. Every map needs `toys` hints (`[toy, anchor, dx, dz]`, anchors `spawn`, `["route", i]`, `["post", i]`).

**Escape maps (exodus) need authoring the source's logic cannot carry.** Elevators, teleports, falling-rock puzzles and airstrikes have no equivalent in the map format, so a spec rewrites that part: `cut` (regions whose box centres go, optional material), `add_boxes` (stand-ins in game coordinates: a bridge, a stair whose steps are 1.0 long on the 0.5 grid and rise at most 0.5 so the metre-spaced graph has a point on each), `extra_gates` (a gate made of added boxes, at least 0.8 m thick or the route sampling misses it), `gate_names` (only these `func_door`s become gates, with their own label and hold-out), `drop_buried`, `survivor_start`/`zombie_start`/`items`, `kill_y`, `extra_links` (explicit nav links) and `route_bridge` (link the graph's components wherever the walked route crosses between them). Run `nav_emulate` on the output and read "points on the main ground" before trusting a map. Nuke and Run For Your Life ship this way; what each leaves out is in its spec.

## Toys

Every map's `toys` are dot-props' **loose** toys (barrels, tyres, balls, a bowling rack), from the builder's `TOYS` table: a hint names an anchor (the first survivor spawn, a route point, a post) and an offset, and `settle_toys` moves it to the nearest spot within 10 m floored flat, half a metre clear of every box and prop, 1.5 m from every spawn and item; a hint that settles nowhere stops the build. Never a fixed toy: the nav floors do not know about it, so it would be a wall a stand-in walks into. game-zombie-zone's `headless_maps` checks each is built, inside nothing, and still two seconds on.

## Weapons the maps name from the second pack

`molotov` and `pipe_bomb` are named as throwables. They are zed-dot-weapons' (the second pack); a server without it draws a random throwable in their place (`ZzLoot.place_from_map`).

## Publishing

**This repository is a pack of its own, mounted on the server alone.** A server owner names it in their deployment's map config (dot-server-deploy's `cfg/content.yml`), and the game adds that mount's `maps/` to its catalogue. It is never in a client's content sync: a client is sent the one document being played. `.github/workflows/release.yml` runs `build_maps.py --check` and then dot-ci's release with `pack: true`.

`project.godot` exists only so dot-ci's release can import this repository and attach the `-pack.zip`; it carries the editor's own header and no comments, because the editor rewrites the file on its first save and a checkout would show it modified.

**Publish after the game**: the Blackout maps say `exodus`, which a game before 2026-10-12 refuses.
