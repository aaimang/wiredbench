# Phase 0 results

Run on 2026-10-31. Spike code is in this folder. It is throwaway code that proves an approach, not
product code.

| Spike | Result | Confidence |
|---|---|---|
| Furni SWF to sprites | Works without Flash tools | High for floor furni; wall furni untested |
| Avatar frames | `habbo-imaging` is enough for v1 | High, with two limits |
| G-Presets round trip | Lossless on real files | High for our side; real-room import untested |
| Mock vs official API | Matches the spec and observed behaviour | Medium; sandbox comparison needs a room with keys |
| Real-room traces | Not run | Needs a room with the Web API add-on |

## 1. Furni SWF to sprites

`swf/swf_furni.py` reads SWFs using only the Python standard library, Pillow and `defusedxml`.

- **Coverage:** 786 of 786 tested furni produced sprites: all 284 `wf_*` boxes and 502 other floor
  furni (500 random plus showcase items).
- **Visual check:** a contact sheet of 20 poses looked correct, including all four throne directions
  and both switch states. The other furni were checked for sprites, not by eye.
- **Speed and size:** slowest parse 0.26 seconds; 751 SWFs took 14 MB, about 19 KB each. Caching on
  first use is practical.
- **Bug found and fixed:** frames can share one bitmap under several names, so a symbol ID must map
  to a list of names. This caused all 8 failures in the first run.

**Not covered:**
- Wall furni.
- Colour variants such as `bc_sphere_small*6`, which need `partcolors` tinting.
- Animation playback beyond the first frame.
- Drawing in PixiJS, which is Phase 2 work.

## 2. Avatar frames

`avatar/run_spike.py` tested `/habbo-imaging/avatarimage`.

| Tested | Result |
|---|---|
| Hotels | All 10 return images (`com`, `com.br`, `de`, `es`, `fi`, `fr`, `it`, `nl`, `com.tr`, `sandbox`) |
| Directions | 8 distinct images |
| Walk | `action=wlk` with `frame=0` to `3`: 4 distinct frames |
| Wave | `action=wav` with `frame=0` to `1`: 2 distinct frames |
| Poses | `sit`, `lay`, `wav`, `crr`, `drk`, `sig`, `respect` all change the image |
| Gestures | `sml`, `agr`, `sad`, `srp`, `spk`, `eyb` all change the image |
| Sizes | `s` 33×56, `m` 64×110, `l` 128×220, and head-only 54×62 |

**Limits:**
- `effect=1` did not change the image, so avatar effects need another approach.
- Direction 7 looked wrong: a head seen from behind, in a different colour, on a front-facing body.
  Test more figures before Phase 2 relies on it.
- `snk` looked the same as standing.

**Decision:** use `habbo-imaging` for v1 and cache the frames. Each avatar needs about 32 images for
walking, so frames load in the background. The `figuredata` renderer is no longer needed for v1.

## 3. G-Presets round trip

`gpresets/` tested the three files in `g-presets_presets`.

| File | Contents | Lossless | Renumbered IDs stay consistent |
|---|---|---|---|
| `Bot_shouts_picked_item.json` | 11 furni, 10 boxes | Yes | Yes |
| `music-parser.json` | 395 furni, 163 boxes, 106 mapped variables | Yes | Yes |
| `music-parser-cruel-summer.json` | Partial file, `wired.addons` only | Yes | Not applicable |

**Plan corrections:**
- **Target `sirjonasxx/G-Presets`, not the WiredSpast copy.** It was updated on 2026-10-26, supports
  variables, and matches these files. It still has no licence, so we match the format and copy no code.
- **Variables are supported.** The earlier concern about them is resolved.
- **More fields than planned:** `secondItems`, `variableIds`, `variableId`, `variables_map`,
  `quantifier`, `filter`, `inverse`, furni `variables`, `floorplan`, `recolorables` and
  `adsBackgrounds`.
- **Variable IDs are room-specific,** such as `317647`. Import must remap them by name using
  `variables_map`.
- **Partial files exist,** so the importer must handle a file with no `furni`.

**Not proven:** whether `config` strings or `options` values embed IDs that also need remapping, and
whether a file we write imports into a real room.

## 4. Mock vs official API

`mock_api/` is an in-memory mock of the WIRED endpoints.

- **Contract tests:** 21 of 21 pass. They cover behaviour recorded from a real room on 2026-10-18
  and response shapes from the official spec.
- **Spec coverage:** every WIRED operation in the spec is routed.
- **Official wrapper:** `wired-api-python` 0.1.4 works against the mock over real HTTP for everything
  except batch.
- **Wrapper bug:** its batch parser crashes on `"error": null`, which the live hotel returns on
  successful operations. The mock keeps the live format, and we should not rely on the wrapper for
  batch.
- **Spec drift can be automated:** `api-docs/swagger-ui-init.js` is reachable by script on both hotels.
  The sandbox and production specs were identical, with 35 paths and 38 schemas.
- **Sandbox with no keys:** room `1` and an invalid room ID both give the generic
  `{"error":"not-found"}`, so the mock does the same for a room without the add-on.

**Assumed, not observed:** invalid-value error codes, the refusal when mass deletion is off, read-only
batch requests, and `429` behaviour. Each is marked `ASSUMED` in `mock_api.py`.

## 5. Still needed

These need a real room, so they could not be run here:

1. Compare the mock with a real room using keys, including the assumed behaviours.
2. Import a generated preset into a real room with G-Presets.
3. Record real-room traces for engine fidelity.
4. Check whether G-Earth and G-Presets work on the Classic client.

None of these block Phase 1. They are needed before the matching features can be marked verified.
