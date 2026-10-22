# Textures the licence pass drew as a generated flat image

Measured 2026-10-22 over the eleven rebuilt worlds. `dot-map/tools/bsp/dotbsp/free_textures.tsv` maps a generic id to a free photographic set; an id with no photographic row is drawn by `dotbsp/textures.py` in the original's average colour. Better sets are added in dot-map (CC0 from ambientCG or Poly Haven, with URL, author and licence per row), not here.

## Worth a photographic set

| Generic id | Source names | Maps | Suggested CC0 set |
| --- | --- | --- | --- |
| carpet | `carpet/offflra`, `carpet/offflrb`, `cs_italy/carpet-sn03`, `customtext/gc textures/carpet/blue_carpet08_darker`, `customtext/gc textures/carpet/gray_carpet02`, `customtext/gc textures/carpet/red_carpet01`, `de_piranesi/pi_rug1`, `de_piranesi/pi_rug4`, `nippertextures/clue/clue_redcarp`, `props/carpetfloor001a`, `props/carpetfloor004a`, `props/carpetfloor006a`, `props/carpetfloor007a`, `props/carpetfloor008a` | zm_abandoned_mall, zm_atix_helicopter, zm_chaos_city, zm_house_outbreak, zm_officeattack | ambientCG Carpet (e.g. Carpet012, Carpet016) |
| snow | `custom/snowboard`, `custom/snowboard2` | zm_abandoned_mall | ambientCG Snow (e.g. Snow004) |

Glass is drawn generated on purpose (translucent tint, 14 names in all 11 maps).

## Drawn flat, no photographic set wanted

Decals, signs and posters (`custom/*`, `decals/*`), tool and dev textures (`dev/*`, `tools/*`), effects and sprites (`effects/*`, `sprites/*`, `lights/*`) and plain black. Per map:

| Texture | Maps |
| --- | --- |
| `bobpoblo/airport/restrooms` | zm_abandoned_mall |
| `cable/cable_lit` | ze_boat_escape |
| `cable/rope` | zm_house_outbreak |
| `cs_havana/lightb` | ze_blackmesa_escape |
| `cs_italy/black` | ze_boat_escape, ze_death_star_escape, ze_jurassicpark, zm_abandoned_mall, zm_atix_helicopter, zm_chaos_city |
| `decals/decalsigndanger001c` | ze_jurassicpark |
| `decals/infnum0` | ze_blackmesa_escape |
| `decals/infnum1` | ze_blackmesa_escape |
| `decals/infnum2` | ze_blackmesa_escape |
| `decals/infnum3` | ze_blackmesa_escape |
| `decals/infnum4` | ze_blackmesa_escape |
| `decals/infnum5` | ze_blackmesa_escape |
| `decals/infnum6` | ze_blackmesa_escape |
| `decals/ropeladderfootprints` | ze_boat_escape |
| `dev/dev_blendmeasure` | zm_chaos_city |
| `dev/dev_blendmeasure_wvt_patch` | zm_abandoned_mall |
| `dev/dev_measurecrate01` | zm_chaos_city |
| `dev/dev_measurecrate02` | zm_abandoned_mall |
| `dev/dev_measuregeneric01` | ze_blackmesa_escape, ze_jurassicpark |
| `dev/dev_measuregeneric01b` | zm_abandoned_mall |
| `dev/dev_measureice01` | zm_abandoned_mall |
| `dev/reflectivity_10` | zm_abandoned_mall |
| `dev/reflectivity_20` | zm_abandoned_mall |
| `dev/reflectivity_30` | zm_abandoned_mall |
| `dev/reflectivity_40` | zm_abandoned_mall |
| `dev/reflectivity_50` | zm_abandoned_mall |
| `dev/reflectivity_60` | zm_abandoned_mall |
| `effects/breenscreen_static01_` | zm_pathogen |
| `effects/building_card01` | zm_pathogen |
| `effects/combineshield/comshieldwall2` | ze_death_star_escape |
| `effects/fake_fog01` | zm_pathogen |
| `effects/fake_fog02` | zm_pathogen |
| `effects/offelevdrsa` | zm_abandoned_mall |
| `effects/rubble_card01` | zm_pathogen |
| `effects/stairsatp` | ze_jurassicpark, zm_atix_helicopter |
| `lights/fluorescentcool003a` | zm_atix_helicopter |
| `lights/white001` | ze_death_star_escape |
| `models/props/de_prodigy/tirestack` | zm_atix_helicopter |
| `models/props_combine/breentp_sheet` | ze_death_star_escape |
| `new/black` | zm_abandoned_mall |
| `new/galaga_control` | zm_abandoned_mall |
| `spongebob/other/yellow` | zm_abandoned_mall |
| `sprites/combineball_glow_red_1` | ze_boat_escape, ze_death_star_escape |
| `sprites/purpleglow1` | zm_officeattack |
| `tools/toolsblack` | ze_blackmesa_escape, ze_jurassicpark, zm_abandoned_mall, zm_officeattack, zm_pathogen |
| `vegas/pa-pacman_bottom` | zm_abandoned_mall |
| `vgui/screens/transparent` | ze_boat_escape |
| `custom/*` (16 shop signs and adverts) | zm_abandoned_mall |

## Not rebuilt

ze_nuke_beta, ze_runforyourlife_1_v4 and zs_ravenstreet have no source bsp on disk and no world.
