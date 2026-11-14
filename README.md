# zombie-zone-maps

The maps for [game-zombie-zone](https://github.com/zees-games/game-zombie-zone), a zombie survival game. Nine maps of our own: a three-map exodus called *Blackout* (corner shop, container depot, pier) and six survival maps. 42 more are converted from community maps.

A map is a JSON document, not a scene. The server reads the documents in its map directory and sends the current map to every client, so players need no map files. To add a map, drop one file in the directory. The format is in [maps/README.md](maps/README.md).

## Using it

[dot-bootstrap](https://github.com/modcommunity/dot-bootstrap) clones this repository next to game-zombie-zone and links it in as `maps/`. Run `./game.sh` in game-zombie-zone and these maps are there. On a server they are a separate pack, and the server owner names it in the map config.

## Our maps

| Map | Mode | What it is |
| --- | --- | --- |
| `zz_blackout_1` (Corner Shop) | exodus | A high street at night, an alley, a laundromat and a square split by a locked fence. Cut the lock and hold on |
| `zz_blackout_2` (The Depot) | exodus | A container yard and a warehouse of racks, with a loading shutter that opens only from inside |
| `zz_blackout_3` (The Pier) | exodus, finale | A seafront camp at dusk and a pier. Radio the boat from the end and hold the pier for ninety seconds |
| `zz_high_school` (Westbrook High) | survival, 12 | A night school with eight classrooms, a library, gym and cafeteria, every door and window boarded |
| `zz_mall` (Riverside Galleria) | survival, 14 | A mall with sixteen shops, a food court and eight ways in from the car park |
| `zz_stadium` (Harbor Park) | survival, 16 | A ballpark under six floodlight masts: diamond, stands, dugouts and tunnels |
| `zz_relief_camp` (Relief Camp) | survival, 10 | An evacuation camp in a clearing: tents, a field hospital and a watchtower behind a plywood wall |
| `zz_lot` (Parking Lot) | survival | A walled car park with a kiosk, rows of cars and four lamp posts |
| `zz_chapel` (Chapel Yard) | survival | A graveyard in fog with crypts and a chapel barricaded at each end |

The number after "survival" is the team size the map is built for; stand-ins fill the rest. The server decides how a survival map is held (`zz_survival`): ten waves by default, days and nights, or a clock. Every survival map supports all three.

An exodus map names the next one, so a won map leads on and the last hands over to the map vote. A lost map is replayed a few times before the server moves on.

## Converted community maps

Each keeps the author's layout. No texture or model of the original ships: materials map to the game's own surfaces and props to its CC0 catalogue. The full entries are in [licence.json](licence.json) and [CREDITS.md](CREDITS.md). Maps whose licence does not allow redistribution are not shipped (see `tools/convert/excluded.txt`).

| Map | Author | Source | Licence |
| --- | --- | --- | --- |
| `gm_balkans` (Gm Balkans) | Lg (Steam profile lg_designer) | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=1307357127) | none stated |
| `gm_bigisland` (Gm Bigisland) | Stinger21 (Matt Westphal) and Hiyougami (Jack Parsons), LEAKTEK | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=169600867) | none stated |
| `gm_boreas` (Boreas) | Blueberry_pie (Wouter Pleizier) | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=1572373847) | none stated |
| `gm_fork` (Gm Fork) | Blueberry_pie | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=326332456) | none stated |
| `gm_mallparking` (Gm Mallparking) | bean | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=2619660952) | none stated |
| `gm_shambles` (Gm Shambles) | Fartomaticatron | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=151544081) | none stated |
| `gm_vyten` (Gm Vyten) | Jake (Steam profile Jake2149) and Sir Zacko | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=1449731878) | none stated |
| `rp_asheville` (Rp Asheville) | VanderAGSN | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=2595136841) | none stated |
| `rp_deadcity` (Rp Deadcity) | NuclearGhost (level recreated from GSC Game World's S.T.A.L.K.E.R. Oblivion Lost) | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=1864156937) | none stated |
| `sunken_resort` (Sunken Resort) | Praisemantas | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3376822715) | none stated |
| `ze_biohazard_manor` (Biohazard Manor) | aeris004 | [GameBanana](https://gamebanana.com/mods/130643) | CC BY-NC-ND 4.0 |
| `ze_blackmesa_escape` (Black Mesa Escape) | Bill Smauz | [GameBanana](https://gamebanana.com/mods/130645) | CC BY-NC-ND 4.0 |
| `ze_boat_escape` (Boat Escape) | Kaju, with JJ45 (original author of the map it is built on) | [GameBanana](https://gamebanana.com/mods/130653) | CC BY-NC-ND 4.0 |
| `ze_death_star_escape` (Death Star Escape) | FreeZe1337, Hannibal, Keamon, Belafarinrod and Fuu | [GameBanana](https://gamebanana.com/mods/130692) | CC BY-NC-ND 4.0 |
| `ze_jurassicpark` (Jurassic Park) | Butterknife | [GameBanana](https://gamebanana.com/mods/130821) | CC BY-NC-ND 4.0 |
| `ze_nuke_beta` (Nuke (beta)) | Mikyuu | [GameBanana](https://gamebanana.com/mods/130898) | CC BY-NC-ND 4.0 |
| `ze_potc` (Potc) | FreeZe (Key Author); Kaemon (contributor) | [GameBanana](https://gamebanana.com/mods/130933) | CC BY-NC-ND 4.0 |
| `ze_runforyourlife_1_v4` (Run For Your Life) | flabes2 | [GameBanana](https://gamebanana.com/mods/130964) | CC BY-NC-ND 4.0 |
| `zm_16chambres` (16chambres) | zigomarvin (creator; uploaded by tiibo30100) | [GameBanana](https://gamebanana.com/mods/131197) | CC BY-NC-ND 4.0 |
| `zm_4way_tunnel` (4-Way Tunnel) | neko_daisuki | [GameBanana](https://gamebanana.com/mods/131215) | CC BY-NC-ND 4.0 |
| `zm_abandoned_mall` (Abandoned Mall) | WaterPyro | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=184522164) | none stated |
| `zm_antarctic_hospital` (Antarctic Hospital) | Ethosaur | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=332228832) | none stated |
| `zm_atix_helicopter` (ATIX Helicopter) | ATIX | [GameBanana](https://gamebanana.com/mods/131303) | CC BY-NC-ND 4.0 |
| `zm_blockfort` (Blockfort) | FlareFireburst | [GameBanana](https://gamebanana.com/mods/131382) | CC BY-NC-ND 4.0 |
| `zm_chaos_city` (Chaos City) | Niiskunkoppa (Emnu); helicopter by Aurora | [GameBanana](https://gamebanana.com/mods/130668) | CC BY-NC-ND 4.0 |
| `zm_day_lego` (Day Lego) | Ayrton09 (map creator) | [GameBanana](https://gamebanana.com/mods/131650) | CC BY-NC-ND 4.0 |
| `zm_hellarch` (Hellarch) | decox | [GameBanana](https://gamebanana.com/mods/131974) | CC BY-NC-ND 4.0 |
| `zm_house_outbreak` (House Outbreak) | WaterPyro | [GameBanana](https://gamebanana.com/mods/132025) | CC BY-NC-ND 4.0 |
| `zm_krusty_krab` (Krusty Krab) | FireWavezZ | [GameBanana](https://gamebanana.com/mods/132150) | CC BY-NC-ND 4.0 |
| `zm_lila_panic` (Lila Panic) | Lila (uploaded by tonyscha) | [GameBanana](https://gamebanana.com/mods/132209) | CC BY-NC-ND 4.0 |
| `zm_mansion_css` (Mansion Css) | Melodie (developer; converted from a Mansion map) | [GameBanana](https://gamebanana.com/mods/131181) | none stated |
| `zm_officeattack` (Office Attack) | kizzbizz | [GameBanana](https://gamebanana.com/mods/132500) | CC BY-NC-ND 4.0 |
| `zm_pathogen` (Pathogen) | Stelk | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=292859426) | none stated |
| `zm_roy_highway` (Roy Highway) | Roy (uploaded by Mo0nLiGht) | [GameBanana](https://gamebanana.com/mods/132705) | CC BY-NC-ND 4.0 |
| `zm_roy_the_ship` (Roy The Ship) | Roy (uploaded by Mo0nLiGht) | [GameBanana](https://gamebanana.com/mods/132707) | CC BY-NC-ND 4.0 |
| `zs_erosion` (Erosion) | Lime | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3400815298) | none stated |
| `zs_goth_house` (Goth House) | Draculine | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3730623999) | none stated |
| `zs_krusty_krab_large` (Krusty Krab Large) | Scott (Steam Workshop conversion to ZS); original Krusty Krab by FireWavezZ (gamebanana.com/mods/132150) | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=645191518) | none stated |
| `zs_lens` (Lens) | deadfs | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3212681027) | none stated |
| `zs_ravenstreet` (Raven Street) | Didixo | [GameBanana](https://gamebanana.com/mods/61387) | CC BY-NC-ND 4.0 |
| `zs_slugde` (Slugde) | Ethosaur | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=323893414) | none stated |
| `zs_verystill` (Verystill) | doggy prozac | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3209397565) | none stated |

"None stated" means the source page gives no licence; those maps are shared as conversions and removed on request. `zm_roy_highway` and `zm_roy_the_ship` are the first to go if the author asks.

If you made one of these maps and want it removed, open an issue at <https://github.com/zees-games/zombie-zone-maps/issues> and it goes.

## Building the maps

`tools/build_maps.py` writes our own maps. A map is a list of regions (rectangles a person can stand in). The builder adds each region's floor, walls on every open edge, ceilings, lintels over doorways, the ground the zombies walk on, and the props.

```bash
python3 tools/build_maps.py                # rewrite maps/*.json
python3 tools/build_maps.py --check        # exit 1 if a file differs from the builder's output
python3 tools/build_maps.py --sync-sizes   # copy prop sizes from ../game-zombie-zone
```

The JSON is committed and CI runs `--check`, so a hand edit to a built map is caught. Any `.json` file in `maps/` is loaded, including hand-written ones.

Game-zombie-zone's `examples/headless_maps.tscn` checks every map: it fits on the wire, props are known, spawns have floor, items can be picked up, the zombies' ground reaches every objective, and survival maps have spawns, posts and caches. `examples/headless_survival.tscn` plays each big survival map for a wave.

Converted maps come from `tools/import_bsp.py`, which reads a Source 1 `.bsp` through dot-map-convert (cloned beside this repository, or set `DOTBSP_PATH`):

```bash
python3 -P tools/import_bsp.py tools/bsp/<id>.json <file.bsp>
```

The spec in `tools/bsp/` names the author, source page, licence and mode. The `.bsp` is not committed; download it from the page in the spec. Per-map notes are in [docs/import-notes.md](docs/import-notes.md).

## Licence

MIT, see [LICENSE](LICENSE). The cars, street furniture, crates, gravestones, furniture, trees and shop fittings the maps use are Kenney's CC0 kits and live in game-zombie-zone. The converted maps keep the licences listed above.
