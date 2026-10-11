# zombie-zone-maps

The maps for [**game-zombie-zone**](https://github.com/zees-games/game-zombie-zone): a three-map campaign, *Blackout*, from a corner shop through a container depot to the end of a pier, and two survival maps to hold for as long as the clock says. Five maps to start with, plus the practice street built into the game.

Every map is a **JSON document**, not a scene. A server reads the documents in its map directory and sends the one it is playing to every client when the map changes, so players need no map files at all and a new map is one file dropped into a directory. [`maps/README.md`](maps/README.md) is the format.

## Using it

[dot-bootstrap](https://github.com/modcommunity/dot-bootstrap) clones this repository next to game-zombie-zone and links it into the game as `maps/`, so `./game.sh` in game-zombie-zone plays these maps with nothing else to do. On a server they are delivered as a pack of their own, which the server owner names in their map config.

## The maps

| Map | Mode | What it is |
| --- | --- | --- |
| `zz_blackout_1` (Corner Shop) | campaign | A high street at night, an alley with a stash, a laundromat, and a square cut in half by a locked fence: cut the lock and hold on while everything that heard it comes |
| `zz_blackout_2` (The Depot) | campaign | A container yard, a warehouse of racks, and a loading shutter that only opens from inside, slowly and loudly |
| `zz_blackout_3` (The Pier) | campaign, finale | A seafront camp at dusk and a pier out over the water: radio the boat from the end and hold the pier for ninety seconds |
| `zz_lot` (Parking Lot) | survival, 5 minutes | A walled car park with a kiosk in the middle, rows of cars and four lamp posts |
| `zz_chapel` (Chapel Yard) | survival, 6 minutes | A graveyard in fog, crypts to put your back to, and a chapel with a door at each end |

A campaign map names the next one (`next`), so a won map leads to the next and the last one hands over to the map vote. A lost map is played again, a few times, before the server moves on.

## How they are made

`tools/build_maps.py` writes every document in `maps/`. A map there is a list of regions (rectangles a person can stand in), and the builder makes the rest from them: each region's floor, a wall on every edge that faces nothing, a ceiling over a room, a lintel over a doorway, and the ground the zombies walk, which is the regions themselves. Then the cars, the racks, the gravestones and the things lying about.

```bash
python3 tools/build_maps.py                # rewrite maps/*.json
python3 tools/build_maps.py --check        # exit 1 if a file differs from what the builder writes
python3 tools/build_maps.py --sync-sizes   # copy prop sizes from ../game-zombie-zone after it measures new models
```

The JSON is still what the game reads and is committed; CI runs `--check`, so a hand edit to a built document is caught instead of being lost on the next build. Hand-written documents the builder does not produce are fine too: anything in `maps/` with a `.json` extension is loaded.

Every map is then checked by game-zombie-zone's `examples/headless_maps.tscn`: it fits on the wire, every prop is one the game knows, every spawn has a floor and room for a person, no prop is sunk into a wall or floating, every item can be picked up, the zombies' ground reaches every objective, sleeper and the end room from the start, and a shut gate really does cut the way.

## License

MIT. See [LICENSE](LICENSE). The cars, street furniture, crates and gravestones the maps name are Kenney's (CC0) and live in game-zombie-zone.
